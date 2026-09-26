"""Tests for the loopback HTTP listener that receives Bling's OAuth redirect.

These bind a real socket on 127.0.0.1 (ephemeral port) — the one seam a fake
would hide is the HTTP parsing itself.
"""

import httpx
import pytest

from bling_mcp.auth import TokenManager
from bling_mcp.callback_server import CallbackServer
from bling_mcp.config import BlingConfig
from bling_mcp.oauth_flow import COMPLETED, FAILED, PENDING, AuthorizationFlow


def make_config():
    return BlingConfig(
        client_id="id",
        client_secret="sec",
        refresh_token="r-expired",
        api_base_url="https://api.test/v3",
        token_url="https://auth.test/token",
    )


def build_http(responses):
    requests = []

    def handler(request):
        requests.append(request)
        spec = responses[min(len(requests) - 1, len(responses) - 1)]
        return httpx.Response(spec.get("status", 200), json=spec.get("json"), request=request)

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


TOKENS = {"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600}


@pytest.fixture
def running():
    """A started server plus a mutable slot holding the flow it should serve."""
    slot = {"flow": None}
    server = CallbackServer(port=0, flow_provider=lambda: slot["flow"])
    server.start()
    try:
        yield server, slot
    finally:
        server.stop()


def make_flow(server, responses=None):
    http, reqs = build_http(responses if responses is not None else [{"json": TOKENS}])
    tm = TokenManager(make_config(), http, clock=lambda: 1000.0)
    flow = AuthorizationFlow(
        make_config(), http, tm, redirect_uri=server.redirect_uri,
        clock=lambda: 1000.0, state_factory=lambda: "S1",
    )
    return flow, tm


def hit(server, path):
    return httpx.get(f"http://127.0.0.1:{server.port}{path}", timeout=5)


def test_binds_an_ephemeral_port_and_reports_a_localhost_redirect_uri(running):
    server, _ = running
    assert server.port > 0
    assert server.redirect_uri == f"http://localhost:{server.port}/callback"


def test_valid_callback_completes_the_flow_and_shows_a_success_page(running):
    server, slot = running
    flow, tm = make_flow(server)
    slot["flow"] = flow

    response = hit(server, "/callback?code=CODE-1&state=S1")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "autorizad" in response.text.lower()
    assert flow.status().state == COMPLETED
    assert tm.get_access_token() == "AT-NEW"


def test_forged_state_is_rejected_with_400_and_flow_stays_pending(running):
    server, slot = running
    flow, _ = make_flow(server)
    slot["flow"] = flow

    response = hit(server, "/callback?code=CODE-1&state=FORGED")

    assert response.status_code == 400
    assert flow.status().state == PENDING


def test_missing_code_is_a_400(running):
    server, slot = running
    slot["flow"], _ = make_flow(server)

    assert hit(server, "/callback?state=S1").status_code == 400


def test_user_denial_from_bling_is_reported_not_exchanged(running):
    server, slot = running
    flow, _ = make_flow(server)
    slot["flow"] = flow

    response = hit(server, "/callback?error=access_denied&state=S1")

    assert response.status_code == 400
    assert "access_denied" in response.text
    assert flow.status().state == PENDING


def test_exchange_failure_is_a_502_and_marks_the_flow_failed(running):
    server, slot = running
    flow, _ = make_flow(server, [{"status": 400, "json": {"error": "invalid_grant"}}])
    slot["flow"] = flow

    response = hit(server, "/callback?code=BAD&state=S1")

    assert response.status_code == 502
    assert flow.status().state == FAILED


def test_callback_without_an_active_flow_is_a_404(running):
    server, _ = running
    assert hit(server, "/callback?code=X&state=S1").status_code == 404


def test_unknown_paths_are_404(running):
    server, slot = running
    slot["flow"], _ = make_flow(server)
    assert hit(server, "/somewhere").status_code == 404


def test_stop_releases_the_port():
    server = CallbackServer(port=0, flow_provider=lambda: None)
    server.start()
    port = server.port
    server.stop()

    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/callback", timeout=2)


def test_start_is_idempotent(running):
    server, _ = running
    port = server.port
    server.start()
    assert server.port == port


def test_fixed_port_is_honoured():
    probe = CallbackServer(port=0, flow_provider=lambda: None)
    probe.start()
    free_port = probe.port
    probe.stop()

    server = CallbackServer(port=free_port, flow_provider=lambda: None)
    server.start()
    try:
        assert server.port == free_port
    finally:
        server.stop()


# --- robustness (from code review) --------------------------------------------------
def test_non_ascii_state_is_a_400_not_a_crash(running):
    server, slot = running
    flow, _ = make_flow(server)
    slot["flow"] = flow

    response = hit(server, "/callback?code=C&state=%C3%A9")

    assert response.status_code == 400
    assert flow.status().state == PENDING


def test_unexpected_handler_error_renders_a_500_page():
    def exploding_provider():
        raise RuntimeError("boom")

    server = CallbackServer(port=0, flow_provider=exploding_provider)
    server.start()
    try:
        response = hit(server, "/callback?code=C&state=S")
    finally:
        server.stop()

    assert response.status_code == 500
    assert "boom" not in response.text  # internals stay out of the browser


def test_listener_does_not_share_its_port_with_another_process(running):
    """SO_REUSEADDR on Windows lets a second process bind a port that is already
    being listened on, which would silently split the redirects between two
    bling-mcp instances. The listener must bind exclusively."""
    server, _ = running
    assert server._httpd.allow_reuse_address is False


def test_redirect_uri_host_is_configurable_while_bind_stays_loopback():
    server = CallbackServer(port=0, flow_provider=lambda: None, redirect_host="127.0.0.1")
    server.start()
    try:
        assert server.redirect_uri == f"http://127.0.0.1:{server.port}/callback"
        assert server._httpd.server_address[0] == "127.0.0.1"
    finally:
        server.stop()
