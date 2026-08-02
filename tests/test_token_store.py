"""Tests for persistent Bling token storage.

Every filesystem test uses tmp_path; nothing here touches the real user state
directory or the network.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from bling_mcp.token_store import (
    JsonFileTokenStore,
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


def make_tokens(**over):
    base = dict(
        refresh_token="r1",
        seed_fingerprint="fp-seed",
        access_token="AT1",
        expires_at=1785000000.0,
    )
    base.update(over)
    return StoredTokens(**base)


def test_save_then_load_roundtrips_every_field(tmp_path):
    store = JsonFileTokenStore(tmp_path / "token.json")
    store.save("client-1", make_tokens())

    loaded = store.load("client-1")

    assert loaded == make_tokens()


def test_load_returns_none_when_file_is_absent(tmp_path):
    store = JsonFileTokenStore(tmp_path / "nope" / "token.json")
    assert store.load("client-1") is None


def test_load_returns_none_for_unknown_client_without_warning(tmp_path, capsys):
    store = JsonFileTokenStore(tmp_path / "token.json")
    store.save("client-1", make_tokens())

    assert store.load("client-2") is None
    assert capsys.readouterr().err == ""


def test_load_warns_and_returns_none_on_malformed_json(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_text("{not json at all", encoding="utf-8")
    store = JsonFileTokenStore(path)

    assert store.load("client-1") is None
    assert "token store" in capsys.readouterr().err


def test_load_warns_and_returns_none_on_entry_missing_required_field(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps({"version": 1, "accounts": {"client-1": {"access_token": "AT"}}}),
        encoding="utf-8",
    )
    store = JsonFileTokenStore(path)

    assert store.load("client-1") is None
    assert "client-1" in capsys.readouterr().err


def test_save_creates_missing_parent_directories(tmp_path):
    store = JsonFileTokenStore(tmp_path / "deep" / "nested" / "token.json")
    store.save("client-1", make_tokens())

    assert store.load("client-1") == make_tokens()


def test_save_writes_the_documented_shape(tmp_path):
    path = tmp_path / "token.json"
    JsonFileTokenStore(path).save("client-1", make_tokens())

    doc = json.loads(path.read_text(encoding="utf-8"))

    assert doc["version"] == 1
    assert doc["accounts"]["client-1"]["refresh_token"] == "r1"
    assert doc["accounts"]["client-1"]["seed_fingerprint"] == "fp-seed"


def test_save_keeps_other_clients_intact(tmp_path):
    store = JsonFileTokenStore(tmp_path / "token.json")
    store.save("client-1", make_tokens(refresh_token="r-one"))
    store.save("client-2", make_tokens(refresh_token="r-two"))

    assert store.load("client-1").refresh_token == "r-one"
    assert store.load("client-2").refresh_token == "r-two"


def test_save_overwrites_the_same_client(tmp_path):
    store = JsonFileTokenStore(tmp_path / "token.json")
    store.save("client-1", make_tokens(refresh_token="old"))
    store.save("client-1", make_tokens(refresh_token="new"))

    assert store.load("client-1").refresh_token == "new"


def test_save_leaves_no_temp_file_behind(tmp_path):
    store = JsonFileTokenStore(tmp_path / "token.json")
    store.save("client-1", make_tokens())

    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]


def test_concurrent_saves_use_separate_temp_files_and_cannot_corrupt(tmp_path, monkeypatch):
    """Two processes sharing one token.json must never write through the same
    temp path. The interleave is driven directly rather than raced with real
    threads: the moment store_a claims its temp file (via mkstemp) but before
    it has written a single byte or replaced anything, store_b is made to run
    an entire, independent save to completion. That is the exact window the
    old fixed ``token.json.tmp`` name let two writers collide in.

    With separate temp files there is nothing left to interleave on: whichever
    save's ``os.replace`` runs last simply wins (an accepted lost update), and
    the file is always one writer's complete, valid JSON -- never a splice of
    both.
    """
    path = tmp_path / "token.json"
    store_a = JsonFileTokenStore(path)
    store_b = JsonFileTokenStore(path)

    real_mkstemp = tempfile.mkstemp
    temp_names = []
    triggered = False

    def racing_mkstemp(*args, **kwargs):
        nonlocal triggered
        fd, name = real_mkstemp(*args, **kwargs)
        temp_names.append(name)
        if not triggered:
            triggered = True
            # store_a's temp file exists and is open, but store_a has not
            # written or replaced anything yet. A concurrent writer must be
            # free to finish its own save in full right now.
            store_b.save("client-1", make_tokens(refresh_token="from-b", expires_at=222.0))
        return fd, name

    monkeypatch.setattr(tempfile, "mkstemp", racing_mkstemp)

    store_a.save("client-1", make_tokens(refresh_token="from-a", expires_at=111.0))

    assert len(temp_names) == 2
    assert temp_names[0] != temp_names[1]  # each writer got its own file

    # store_a's os.replace ran last (after the nested store_b.save returned),
    # so store_a's version is installed -- and, critically, it parses cleanly.
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["accounts"]["client-1"]["refresh_token"] == "from-a"

    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]  # no .tmp survives


def test_save_warns_and_does_not_raise_when_path_is_unwritable(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    store = JsonFileTokenStore(blocker / "token.json")

    store.save("client-1", make_tokens())  # must not raise

    assert "token store" in capsys.readouterr().err


def test_save_warns_only_once_per_process(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    store = JsonFileTokenStore(blocker / "token.json")

    store.save("client-1", make_tokens())
    capsys.readouterr()  # drain the first warning
    store.save("client-1", make_tokens())

    assert capsys.readouterr().err == ""


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
def test_saved_file_is_owner_readable_only(tmp_path):
    path = tmp_path / "token.json"
    JsonFileTokenStore(path).save("client-1", make_tokens())

    assert path.stat().st_mode & 0o777 == 0o600


def test_load_warns_and_does_not_raise_on_invalid_utf8(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_bytes(b'\xff\xfe\x00\x01 not valid utf8 \x80\x81')
    store = JsonFileTokenStore(path)

    assert store.load("client-1") is None
    assert "token store" in capsys.readouterr().err


def test_save_warns_and_does_not_raise_on_invalid_utf8(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_bytes(b'\xff\xfe\x00\x01 not valid utf8 \x80\x81')
    store = JsonFileTokenStore(path)

    store.save("client-1", make_tokens())  # must not raise

    assert "token store" in capsys.readouterr().err


def test_load_warns_and_returns_none_on_non_dict_accounts(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps({"version": 1, "accounts": "not a dict"}),
        encoding="utf-8",
    )
    store = JsonFileTokenStore(path)

    assert store.load("client-1") is None
    assert "token store" in capsys.readouterr().err


def test_save_warns_and_continues_on_non_dict_accounts(tmp_path, capsys):
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps({"version": 1, "accounts": "not a dict"}),
        encoding="utf-8",
    )
    store = JsonFileTokenStore(path)

    store.save("client-1", make_tokens())

    assert "token store" in capsys.readouterr().err
    assert store.load("client-1") == make_tokens()
