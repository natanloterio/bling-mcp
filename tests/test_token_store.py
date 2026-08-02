"""Tests for persistent Bling token storage.

Every filesystem test uses tmp_path; nothing here touches the real user state
directory or the network.
"""

from pathlib import Path

from bling_mcp.token_store import (
    NullTokenStore,
    StoredTokens,
    default_store_path,
    fingerprint,
)


def test_fingerprint_is_stable_for_the_same_seed():
    assert fingerprint("seed-abc") == fingerprint("seed-abc")


def test_fingerprint_differs_between_seeds():
    assert fingerprint("seed-abc") != fingerprint("seed-xyz")


def test_fingerprint_does_not_contain_the_seed():
    assert "seed-abc" not in fingerprint("seed-abc")


def test_stored_tokens_is_immutable():
    tokens = StoredTokens(refresh_token="r1", seed_fingerprint="fp")
    try:
        tokens.refresh_token = "r2"
    except Exception as exc:  # FrozenInstanceError subclasses AttributeError
        assert isinstance(exc, AttributeError)
    else:
        raise AssertionError("StoredTokens must be frozen")


def test_stored_tokens_access_fields_default_to_empty():
    tokens = StoredTokens(refresh_token="r1", seed_fingerprint="fp")
    assert tokens.access_token is None
    assert tokens.expires_at == 0.0


def test_default_store_path_on_windows_uses_localappdata():
    path = default_store_path(
        env={"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}, platform="win32"
    )
    assert path == Path(r"C:\Users\me\AppData\Local") / "bling-mcp" / "token.json"


def test_default_store_path_on_macos_uses_application_support():
    path = default_store_path(env={}, platform="darwin")
    assert path == Path.home() / "Library" / "Application Support" / "bling-mcp" / "token.json"


def test_default_store_path_on_linux_honours_xdg_state_home():
    path = default_store_path(env={"XDG_STATE_HOME": "/custom/state"}, platform="linux")
    assert path == Path("/custom/state") / "bling-mcp" / "token.json"


def test_default_store_path_on_linux_falls_back_to_local_state():
    path = default_store_path(env={}, platform="linux")
    assert path == Path.home() / ".local" / "state" / "bling-mcp" / "token.json"


def test_default_store_path_ignores_bling_token_store():
    """The override is config.py's job, not the path resolver's."""
    path = default_store_path(
        env={"BLING_TOKEN_STORE": "/should/be/ignored", "XDG_STATE_HOME": "/custom/state"},
        platform="linux",
    )
    assert path == Path("/custom/state") / "bling-mcp" / "token.json"


def test_null_store_loads_nothing():
    assert NullTokenStore().load("client-1") is None


def test_null_store_save_is_a_noop():
    store = NullTokenStore()
    store.save("client-1", StoredTokens(refresh_token="r1", seed_fingerprint="fp"))
    assert store.load("client-1") is None
