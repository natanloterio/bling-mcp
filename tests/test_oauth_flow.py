"""Tests for the in-chat re-authorization flow (authorization-code grant).

HTTP, clock and state generation are injected so the flow can be driven
without network, real time or randomness.
"""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bling_mcp.auth import AuthError, TokenManager
from bling_mcp.config import BlingConfig
from bling_mcp.oauth_flow import (
    COMPLETED,
    EXPIRED,
    FAILED,
    PENDING,
    AuthorizationFlow,
    FlowError,
)


def make_config(**over):
    base = dict(
        client_id="id",
        client_secret="sec",
        refresh_token="r-expired",
        api_base_url="https://api.test/v3",
        token_url="https://auth.test/token",
        account_label="default",
    )
    base.update(over)
    return BlingConfig(**base)


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
        return httpx.Response(
            spec.get("status", 200), json=spec.get("json"), request=request
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


TOKENS = {"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600}


def make_flow(responses=None, clock=None, timeout=300):
    clock = clock or FakeClock()
    http, reqs = build_http(responses if responses is not None else [{"json": TOKENS}])
    tm = TokenManager(make_config(), http, clock=clock)
    flow = AuthorizationFlow(
        make_config(),
        http,
        tm,
        redirect_uri="http://localhost:8765/callback",
        clock=clock,
        timeout=timeout,
        state_factory=lambda: "STATE-1",
    )
    return flow, tm, reqs


def test_new_flow_is_pending():
    flow, _, _ = make_flow()
    assert flow.status().state == PENDING


def test_authorize_url_carries_client_id_state_and_redirect():
    flow, _, _ = make_flow()
    query = parse_qs(urlparse(flow.authorize_url).query)

    assert query["client_id"] == ["id"]
    assert query["state"] == ["STATE-1"]
    assert query["redirect_uri"] == ["http://localhost:8765/callback"]
    assert query["response_type"] == ["code"]


def test_complete_exchanges_the_code_and_installs_the_tokens():
    flow, tm, reqs = make_flow()

    flow.complete(code="CODE-1", state="STATE-1")

    assert flow.status().state == COMPLETED
    assert "code=CODE-1" in reqs[0].content.decode()
    assert tm.get_access_token() == "AT-NEW"
    assert len(reqs) == 1  # the install left nothing to refresh


def test_complete_rejects_a_mismatched_state_and_stays_pending():
    flow, _, reqs = make_flow()

    with pytest.raises(FlowError, match="state"):
        flow.complete(code="CODE-1", state="FORGED")

    assert flow.status().state == PENDING
    assert reqs == []  # a forged callback must never spend the code


def test_complete_records_an_exchange_failure():
    flow, _, _ = make_flow([{"status": 400, "json": {"error": "invalid_grant"}}])

    with pytest.raises(AuthError):
        flow.complete(code="BAD", state="STATE-1")

    status = flow.status()
    assert status.state == FAILED
    assert "400" in status.detail


def test_complete_with_code_skips_the_state_check():
    """Manual fallback: the user pasted the code from the address bar."""
    flow, tm, _ = make_flow()

    flow.complete_with_code("CODE-1")

    assert flow.status().state == COMPLETED
    assert tm.get_access_token() == "AT-NEW"


def test_flow_expires_after_the_timeout():
    clock = FakeClock()
    flow, _, _ = make_flow(clock=clock, timeout=300)

    clock.advance(301)

    assert flow.status().state == EXPIRED


def test_completing_an_expired_flow_is_refused():
    clock = FakeClock()
    flow, _, reqs = make_flow(clock=clock, timeout=300)
    clock.advance(301)

    with pytest.raises(FlowError, match="expired"):
        flow.complete(code="CODE-1", state="STATE-1")

    assert reqs == []


def test_a_completed_flow_cannot_be_completed_twice():
    flow, _, reqs = make_flow()
    flow.complete(code="CODE-1", state="STATE-1")

    with pytest.raises(FlowError):
        flow.complete(code="CODE-2", state="STATE-1")

    assert len(reqs) == 1


def test_completed_flow_does_not_expire():
    clock = FakeClock()
    flow, _, _ = make_flow(clock=clock, timeout=300)
    flow.complete(code="CODE-1", state="STATE-1")

    clock.advance(10_000)

    assert flow.status().state == COMPLETED


def test_default_state_is_random_and_url_safe():
    http, _ = build_http([{"json": TOKENS}])
    tm = TokenManager(make_config(), http, clock=FakeClock())
    a = AuthorizationFlow(make_config(), http, tm, redirect_uri="http://l/cb")
    b = AuthorizationFlow(make_config(), http, tm, redirect_uri="http://l/cb")

    assert a.state != b.state
    assert len(a.state) >= 16
    assert parse_qs(urlparse(a.authorize_url).query)["state"] == [a.state]


# --- concurrency & robustness (from code review) ------------------------------------
def test_state_check_tolerates_non_ascii_input():
    flow, _, reqs = make_flow()

    with pytest.raises(FlowError, match="state"):
        flow.complete(code="C", state="é-forged")

    assert reqs == []
    assert flow.status().state == PENDING


def test_expired_flow_reports_expired_even_with_a_forged_state():
    clock = FakeClock()
    flow, _, _ = make_flow(clock=clock)
    clock.advance(301)

    with pytest.raises(FlowError, match="expired"):
        flow.complete(code="C", state="FORGED")


def test_concurrent_duplicate_callbacks_exchange_once_and_end_completed():
    """Browser prefetch + navigation, or a refresh, delivers the same callback
    twice on two ThreadingHTTPServer threads. Only one may reach Bling, and the
    loser must not overwrite a success with FAILED."""
    import threading

    entered = threading.Event()
    release = threading.Event()
    requests = []

    def handler(request):
        requests.append(request)
        entered.set()
        assert release.wait(5), "test deadlock"
        return httpx.Response(200, json=TOKENS, request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    clock = FakeClock()
    tm = TokenManager(make_config(), http, clock=clock)
    flow = AuthorizationFlow(
        make_config(), http, tm, redirect_uri="http://l/cb", clock=clock,
        state_factory=lambda: "S",
    )

    first = threading.Thread(target=flow.complete, kwargs={"code": "C", "state": "S"})
    first.start()
    assert entered.wait(5)  # first caller is now inside the exchange

    with pytest.raises(FlowError, match="in progress|already"):
        flow.complete(code="C", state="S")  # the duplicate, while the first is in flight

    release.set()
    first.join(5)

    assert flow.status().state == COMPLETED
    assert len(requests) == 1


def test_exchange_sends_the_redirect_uri_it_authorized_with():
    """RFC 6749 §4.1.3: redirect_uri is required in the token request when it
    was present in the authorization request."""
    flow, _, reqs = make_flow()

    flow.complete(code="C", state="STATE-1")

    body = parse_qs(reqs[0].content.decode())
    assert body["redirect_uri"] == ["http://localhost:8765/callback"]


def test_exchange_requests_a_jwt_when_the_config_says_so():
    flow, _, reqs = make_flow()

    flow.complete(code="C", state="STATE-1")

    assert reqs[0].headers["enable-jwt"] == "1"
