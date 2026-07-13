"""Tests for the OAuth 2.0 token manager.

The HTTP client and clock are injected so the refresh flow can be exercised
without network access or real time passing.
"""

import base64

import httpx
import pytest

from bling_mcp.auth import AuthError, TokenManager
from bling_mcp.config import BlingConfig


def make_config(**over):
    base = dict(
        client_id="id",
        client_secret="sec",
        refresh_token="r0",
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


def build_client(responses):
    """Build an httpx.Client whose transport returns the queued responses.

    `responses` is a list of {"status": int, "json": dict}; the i-th request
    gets the i-th entry (the last entry repeats if more requests arrive).
    Every request is recorded for assertions.
    """
    requests = []

    def handler(request):
        requests.append(request)
        spec = responses[min(len(requests) - 1, len(responses) - 1)]
        return httpx.Response(
            spec.get("status", 200), json=spec.get("json"), request=request
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, requests


def test_get_access_token_returns_token_from_refresh_response():
    client, reqs = build_client(
        [{"json": {"access_token": "AT1", "expires_in": 3600, "refresh_token": "r1"}}]
    )
    tm = TokenManager(make_config(), client, clock=FakeClock())

    assert tm.get_access_token() == "AT1"
    assert len(reqs) == 1


def test_refresh_uses_basic_auth_and_form_body():
    cfg = make_config()
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(cfg, client, clock=FakeClock())

    tm.get_access_token()

    req = reqs[0]
    assert req.method == "POST"
    assert str(req.url) == cfg.token_url
    auth = req.headers["Authorization"]
    assert auth.startswith("Basic ")
    decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
    assert decoded == f"{cfg.client_id}:{cfg.client_secret}"
    body = req.content.decode()
    assert "grant_type=refresh_token" in body
    assert f"refresh_token={cfg.refresh_token}" in body


def test_token_is_cached_within_expiry():
    clock = FakeClock()
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(make_config(), client, clock=clock)

    first = tm.get_access_token()
    clock.advance(100)  # comfortably within the 3600s lifetime
    second = tm.get_access_token()

    assert first == second == "AT1"
    assert len(reqs) == 1  # no second refresh


def test_token_is_refreshed_after_expiry():
    clock = FakeClock()
    client, reqs = build_client(
        [
            {"json": {"access_token": "AT1", "expires_in": 3600}},
            {"json": {"access_token": "AT2", "expires_in": 3600}},
        ]
    )
    tm = TokenManager(make_config(), client, clock=clock)

    assert tm.get_access_token() == "AT1"
    clock.advance(3600)  # past the expiry-minus-margin threshold
    assert tm.get_access_token() == "AT2"
    assert len(reqs) == 2


def test_rotated_refresh_token_is_used_on_next_refresh():
    clock = FakeClock()
    client, reqs = build_client(
        [
            {"json": {"access_token": "AT1", "expires_in": 3600, "refresh_token": "r1"}},
            {"json": {"access_token": "AT2", "expires_in": 3600, "refresh_token": "r2"}},
        ]
    )
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock)

    tm.get_access_token()
    clock.advance(3600)
    tm.get_access_token()

    # First refresh used r0; after rotation the second must use r1.
    assert "refresh_token=r0" in reqs[0].content.decode()
    assert "refresh_token=r1" in reqs[1].content.decode()


def test_raises_auth_error_on_non_2xx():
    client, _ = build_client([{"status": 400, "json": {"error": "invalid_grant"}}])
    tm = TokenManager(make_config(), client, clock=FakeClock())

    with pytest.raises(AuthError):
        tm.get_access_token()
