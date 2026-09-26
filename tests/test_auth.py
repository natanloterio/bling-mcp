"""Tests for the OAuth 2.0 token manager.

The HTTP client and clock are injected so the refresh flow can be exercised
without network access or real time passing.
"""

import base64

import httpx
import pytest

from bling_mcp.auth import AuthError, TokenManager
from bling_mcp.config import BlingConfig
from bling_mcp.token_store import JsonFileTokenStore, StoredTokens, fingerprint


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


class FakeStore:
    """In-memory TokenStore double — records saves, never touches disk."""

    def __init__(self, entries=None):
        self.entries = dict(entries or {})
        self.saves = []

    def load(self, client_id):
        return self.entries.get(client_id)

    def save(self, client_id, tokens):
        self.saves.append((client_id, tokens))
        self.entries = {**self.entries, client_id: tokens}


def test_empty_store_falls_back_to_the_env_seed():
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(
        make_config(refresh_token="r0"), client, clock=FakeClock(), store=FakeStore()
    )

    tm.get_access_token()

    assert "refresh_token=r0" in reqs[0].content.decode()


def test_matching_fingerprint_adopts_the_stored_refresh_token():
    store = FakeStore(
        {"id": StoredTokens(refresh_token="r-rotated", seed_fingerprint=fingerprint("r0"))}
    )
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(
        make_config(refresh_token="r0"), client, clock=FakeClock(), store=store
    )

    tm.get_access_token()

    assert "refresh_token=r-rotated" in reqs[0].content.decode()


def test_divergent_fingerprint_discards_the_store_and_uses_the_new_seed():
    """A re-bootstrapped BLING_REFRESH_TOKEN must win over the stale entry."""
    store = FakeStore(
        {
            "id": StoredTokens(
                refresh_token="r-from-old-bootstrap",
                seed_fingerprint=fingerprint("r-previous-seed"),
            )
        }
    )
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(
        make_config(refresh_token="r-new-seed"), client, clock=FakeClock(), store=store
    )

    tm.get_access_token()

    assert "refresh_token=r-new-seed" in reqs[0].content.decode()


def test_valid_stored_access_token_avoids_any_http_call():
    clock = FakeClock(1000.0)
    store = FakeStore(
        {
            "id": StoredTokens(
                refresh_token="r1",
                seed_fingerprint=fingerprint("r0"),
                access_token="AT-CACHED",
                expires_at=1000.0 + 3600,
            )
        }
    )
    client, reqs = build_client([{"json": {"access_token": "AT-NEW", "expires_in": 3600}}])
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock, store=store)

    assert tm.get_access_token() == "AT-CACHED"
    assert reqs == []


def test_expired_stored_access_token_triggers_a_refresh():
    clock = FakeClock(1000.0)
    store = FakeStore(
        {
            "id": StoredTokens(
                refresh_token="r1",
                seed_fingerprint=fingerprint("r0"),
                access_token="AT-STALE",
                expires_at=900.0,  # already past
            )
        }
    )
    client, reqs = build_client([{"json": {"access_token": "AT-NEW", "expires_in": 3600}}])
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock, store=store)

    assert tm.get_access_token() == "AT-NEW"
    assert len(reqs) == 1


def test_refresh_persists_the_rotated_token_set():
    clock = FakeClock(1000.0)
    store = FakeStore()
    client, _ = build_client(
        [{"json": {"access_token": "AT1", "expires_in": 3600, "refresh_token": "r-next"}}]
    )
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock, store=store)

    tm.get_access_token()

    client_id, saved = store.saves[-1]
    assert client_id == "id"
    assert saved.refresh_token == "r-next"
    assert saved.access_token == "AT1"
    assert saved.expires_at == 1000.0 + 3600
    assert saved.seed_fingerprint == fingerprint("r0")


def test_store_is_optional_and_defaults_to_no_persistence():
    client, reqs = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(make_config(), client, clock=FakeClock())

    assert tm.get_access_token() == "AT1"
    assert len(reqs) == 1


def test_default_clock_is_wall_clock_so_expiry_survives_restart():
    import time as time_module

    store = FakeStore()
    client, _ = build_client([{"json": {"access_token": "AT1", "expires_in": 3600}}])
    tm = TokenManager(make_config(), client, store=store)  # no clock injected

    tm.get_access_token()

    # A persisted expiry is only meaningful as wall-clock. time.monotonic() is
    # relative to process start, so it would land near 3600, not near now+3600.
    _, saved = store.saves[-1]
    assert abs(saved.expires_at - (time_module.time() + 3600)) < 5


def test_force_refresh_ignores_a_still_valid_cached_token():
    clock = FakeClock()
    client, reqs = build_client(
        [
            {"json": {"access_token": "AT1", "expires_in": 3600}},
            {"json": {"access_token": "AT2", "expires_in": 3600}},
        ]
    )
    tm = TokenManager(make_config(), client, clock=clock)

    assert tm.get_access_token() == "AT1"
    assert tm.force_refresh() == "AT2"
    assert len(reqs) == 2


def test_force_refresh_returns_the_new_token_for_subsequent_calls():
    clock = FakeClock()
    client, _ = build_client(
        [
            {"json": {"access_token": "AT1", "expires_in": 3600}},
            {"json": {"access_token": "AT2", "expires_in": 3600}},
        ]
    )
    tm = TokenManager(make_config(), client, clock=clock)

    tm.get_access_token()
    tm.force_refresh()

    assert tm.get_access_token() == "AT2"


def test_force_refresh_picks_up_a_token_rotated_by_another_process():
    """Two servers share the store; the loser must not refresh with a dead token."""
    clock = FakeClock()
    store = FakeStore()
    client, reqs = build_client([{"json": {"access_token": "AT2", "expires_in": 3600}}])
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock, store=store)

    # Another process rotates r0 -> r-other and writes it to the shared store.
    store.entries = {
        "id": StoredTokens(
            refresh_token="r-other", seed_fingerprint=fingerprint("r0")
        )
    }

    tm.force_refresh()

    assert "refresh_token=r-other" in reqs[0].content.decode()


def test_force_refresh_propagates_auth_error():
    client, _ = build_client([{"status": 401, "json": {"error": "invalid_grant"}}])
    tm = TokenManager(make_config(), client, clock=FakeClock())

    with pytest.raises(AuthError):
        tm.force_refresh()


def test_restart_reuses_the_rotated_refresh_token_from_a_real_store(tmp_path):
    """The seam every other test misses: a real JsonFileTokenStore composed
    with TokenManager, round-tripped through actual JSON, across a process
    restart (a second TokenManager over the same file). FakeStore never
    exercises the JSON encode/decode of expires_at and access_token that
    production restarts depend on.
    """
    store_path = tmp_path / "token.json"
    clock = FakeClock()

    client1, _ = build_client(
        [{"json": {"access_token": "AT1", "expires_in": 3600, "refresh_token": "r1"}}]
    )
    tm1 = TokenManager(
        make_config(refresh_token="r0"), client1, clock=clock, store=JsonFileTokenStore(store_path)
    )
    tm1.get_access_token()  # refreshes r0 -> r1 and persists it to disk
    del tm1  # simulate the process exiting; only the file survives

    clock.advance(3600)  # past AT1's expiry, forcing the restarted manager to refresh
    client2, reqs2 = build_client(
        [{"json": {"access_token": "AT2", "expires_in": 3600, "refresh_token": "r2"}}]
    )
    tm2 = TokenManager(
        make_config(refresh_token="r0"), client2, clock=clock, store=JsonFileTokenStore(store_path)
    )
    tm2.get_access_token()

    # Must carry the rotated r1 from disk, not fall back to the env seed r0.
    assert "refresh_token=r1" in reqs2[0].content.decode()


# --- install (re-authorization from the chat) -----------------------------------
def test_install_adopts_the_token_set_without_any_http_call():
    clock = FakeClock(1000.0)
    client, reqs = build_client([{"json": {"access_token": "AT-NEVER", "expires_in": 1}}])
    tm = TokenManager(make_config(refresh_token="r-expired"), client, clock=clock)

    tm.install({"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600})

    assert tm.get_access_token() == "AT-NEW"
    assert reqs == []


def test_install_uses_the_new_refresh_token_on_the_next_refresh():
    clock = FakeClock(1000.0)
    client, reqs = build_client([{"json": {"access_token": "AT2", "expires_in": 3600}}])
    tm = TokenManager(make_config(refresh_token="r-expired"), client, clock=clock)

    tm.install({"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600})
    clock.advance(21600)
    tm.get_access_token()

    assert "refresh_token=r-new" in reqs[0].content.decode()


def test_install_persists_under_the_env_seed_fingerprint():
    """The store entry must be adopted on restart even though the env seed is
    the old, expired token — the re-authorization continues this install's
    lineage rather than starting a new one."""
    clock = FakeClock(1000.0)
    store = FakeStore()
    client, _ = build_client([])
    tm = TokenManager(
        make_config(refresh_token="r-expired"), client, clock=clock, store=store
    )

    tm.install({"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600})

    client_id, saved = store.saves[-1]
    assert client_id == "id"
    assert saved.refresh_token == "r-new"
    assert saved.access_token == "AT-NEW"
    assert saved.expires_at == 1000.0 + 21600
    assert saved.seed_fingerprint == fingerprint("r-expired")


def test_install_rejects_a_payload_without_a_refresh_token():
    client, _ = build_client([])
    tm = TokenManager(make_config(), client, clock=FakeClock())

    with pytest.raises(AuthError):
        tm.install({"access_token": "AT-NEW", "expires_in": 21600})


def test_refresh_rejected_with_400_explains_how_to_reauthorize():
    client, _ = build_client([{"status": 400, "json": {"error": "invalid_grant"}}])
    tm = TokenManager(make_config(), client, clock=FakeClock())

    with pytest.raises(AuthError, match="bling_authorize"):
        tm.get_access_token()


# --- thread safety (from code review) -----------------------------------------------
def test_install_during_an_in_flight_refresh_is_serialized_and_wins():
    """Callback thread installs a brand-new grant while an MCP tool call is
    mid-refresh on the old lineage. Without serialization the refresh lands
    last and overwrites r-new with the rotated old token."""
    import threading
    import time as time_module

    clock = FakeClock(1000.0)
    store = FakeStore()
    tm = None
    installer = []

    def handler(request):
        # First request only: the refresh on the old lineage. While it is in
        # flight, another thread installs the new grant.
        if len(reqs_seen) == 0:
            t = threading.Thread(
                target=tm.install,
                args=({"access_token": "AT-NEW", "refresh_token": "r-new", "expires_in": 21600},),
            )
            installer.append(t)
            t.start()
            time_module.sleep(0.1)  # give an unserialized install time to interleave
            reqs_seen.append(request)
            return httpx.Response(
                200, json={"access_token": "AT-OLD", "expires_in": 1, "refresh_token": "r-rotated-old"},
                request=request,
            )
        reqs_seen.append(request)
        return httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600}, request=request)

    reqs_seen = []
    client = httpx.Client(transport=httpx.MockTransport(handler))
    tm = TokenManager(make_config(refresh_token="r0"), client, clock=clock, store=store)

    tm.get_access_token()  # refresh #1, with the install racing it
    installer[0].join(5)

    clock.advance(100_000)  # force the next refresh, which reveals the winning lineage
    tm.get_access_token()

    assert "refresh_token=r-new" in reqs_seen[1].content.decode()
    saved = store.entries["id"]
    assert (saved.refresh_token, saved.access_token) == ("r-new", "AT-NEW") or saved.refresh_token != "r-rotated-old"
