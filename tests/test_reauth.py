"""Tests for ReauthService: what the MCP tools call.

Owns the callback server and the current AuthorizationFlow; the tools are thin
wrappers over begin / status / complete_with_code.
"""

import socket

import httpx
import pytest

from bling_mcp.auth import AuthError, TokenManager
from bling_mcp.callback_server import CallbackServer
from bling_mcp.config import BlingConfig
from bling_mcp.oauth_flow import COMPLETED, EXPIRED, PENDING
from bling_mcp.reauth import NO_FLOW, ReauthService


def make_config(port=0):
    return BlingConfig(
        client_id="id",
        client_secret="sec",
        refresh_token="r-expired",
        api_base_url="https://api.test/v3",
        token_url="https://auth.test/token",
        oauth_callback_port=port,
    )


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def build_http(responses):
    requests = []

    def handler(request):
        requests.append(request)
        spec = responses[min(len(requests) - 1, len(responses) - 1)]
        return httpx.Response(spec.get("status", 200), json=spec.get("json"), request=request)

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


TOKENS = {"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600}


@pytest.fixture
def service():
    clock = FakeClock()
    http, reqs = build_http([{"json": TOKENS}])
    tm = TokenManager(make_config(), http, clock=clock)
    svc = ReauthService(make_config(port=0), http, tm, clock=clock)
    try:
        yield svc, tm, reqs, clock
    finally:
        svc.close()


def test_status_before_any_attempt_says_so(service):
    svc, *_ = service
    assert svc.status()["status"] == NO_FLOW


def test_begin_starts_the_listener_and_returns_the_link(service):
    svc, *_ = service

    result = svc.begin()

    assert result["authorize_url"].startswith("https://www.bling.com.br/Api/v3/oauth/authorize?")
    assert result["callback_listening"] is True
    assert result["redirect_uri"].startswith("http://localhost:")
    assert result["redirect_uri"] in result["authorize_url"] or "redirect_uri=" in result["authorize_url"]
    assert result["expires_in_seconds"] == 300
    assert svc.status()["status"] == PENDING


def test_begin_serves_the_callback_on_the_reported_port(service):
    svc, tm, _, _ = service
    result = svc.begin()
    state = svc._flow.state  # the browser would carry this back from Bling

    response = httpx.get(f"{result['redirect_uri']}?code=C1&state={state}", timeout=5)

    assert response.status_code == 200
    assert svc.status()["status"] == COMPLETED
    assert tm.get_access_token() == "AT-NEW"


def test_begin_again_replaces_a_stale_flow_but_keeps_the_listener(service):
    svc, _, _, clock = service
    first = svc.begin()
    clock.advance(301)
    assert svc.status()["status"] == EXPIRED

    second = svc.begin()

    assert second["redirect_uri"] == first["redirect_uri"]
    assert second["authorize_url"] != first["authorize_url"]  # fresh state
    assert svc.status()["status"] == PENDING


def test_begin_falls_back_to_manual_when_the_port_is_taken():
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]
    http, _ = build_http([{"json": TOKENS}])
    tm = TokenManager(make_config(), http, clock=FakeClock())
    svc = ReauthService(make_config(port=taken), http, tm, clock=FakeClock())
    try:
        result = svc.begin()
    finally:
        svc.close()
        blocker.close()

    assert result["callback_listening"] is False
    assert "bling_authorize_with_code" in result["instructions"]
    assert result["redirect_uri"] == f"http://localhost:{taken}/callback"
    assert result["authorize_url"]  # the link still works; only the auto-capture is lost


def test_complete_with_code_finishes_the_pending_flow(service):
    svc, tm, reqs, _ = service
    svc.begin()

    result = svc.complete_with_code("C1")

    assert result["status"] == COMPLETED
    assert "code=C1" in reqs[0].content.decode()
    assert tm.get_access_token() == "AT-NEW"


def test_complete_with_code_works_without_a_prior_begin(service):
    """A code is bound to the app, not to a flow — pasting one should just work."""
    svc, tm, _, _ = service

    result = svc.complete_with_code("C1")

    assert result["status"] == COMPLETED
    assert tm.get_access_token() == "AT-NEW"


def test_complete_with_code_after_expiry_starts_a_fresh_flow(service):
    svc, tm, _, clock = service
    svc.begin()
    clock.advance(301)

    result = svc.complete_with_code("C1")

    assert result["status"] == COMPLETED


def test_complete_with_code_rejects_a_blank_code(service):
    svc, *_ = service
    with pytest.raises(ValueError, match="code"):
        svc.complete_with_code("   ")


def test_complete_with_code_surfaces_the_exchange_failure():
    http, _ = build_http([{"status": 400, "json": {"error": "invalid_grant"}}])
    tm = TokenManager(make_config(), http, clock=FakeClock())
    svc = ReauthService(make_config(port=0), http, tm, clock=FakeClock())
    try:
        with pytest.raises(AuthError):
            svc.complete_with_code("BAD")
        status = svc.status()
    finally:
        svc.close()

    assert status["status"] == "failed"
    assert "400" in status["detail"]


def test_close_stops_the_listener(service):
    svc, *_ = service
    result = svc.begin()

    svc.close()

    with pytest.raises(httpx.ConnectError):
        httpx.get(result["redirect_uri"], timeout=2)


# --- concurrency (from code review) --------------------------------------------------
def test_begin_refuses_to_replace_a_flow_whose_exchange_is_in_flight():
    import threading

    entered = threading.Event()
    release = threading.Event()

    def handler(request):
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, json=TOKENS, request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    clock = FakeClock()
    tm = TokenManager(make_config(), http, clock=clock)
    svc = ReauthService(make_config(port=0), http, tm, clock=clock)
    try:
        svc.begin()
        worker = threading.Thread(target=lambda: svc.complete_with_code("C1"))
        worker.start()
        assert entered.wait(5)

        with pytest.raises(RuntimeError, match="in progress"):
            svc.begin()

        release.set()
        worker.join(5)
        assert svc.status()["status"] == COMPLETED
    finally:
        svc.close()


def test_begin_uses_the_configured_redirect_host():
    http, _ = build_http([{"json": TOKENS}])
    cfg = BlingConfig(
        client_id="id", client_secret="sec", refresh_token="r0",
        token_url="https://auth.test/token", oauth_callback_port=0,
        oauth_redirect_host="127.0.0.1",
    )
    svc = ReauthService(cfg, http, TokenManager(cfg, http, clock=FakeClock()), clock=FakeClock())
    try:
        result = svc.begin()
    finally:
        svc.close()

    assert result["redirect_uri"].startswith("http://127.0.0.1:")
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A" in result["authorize_url"]
