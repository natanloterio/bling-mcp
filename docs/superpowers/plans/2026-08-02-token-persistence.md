# Token Persistence + 401 Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Bling refresh token survive process restarts by mirroring the rotated token to a JSON file, and recover from a rejected token by retrying once on HTTP 401.

**Architecture:** A new `token_store.py` defines an injectable `TokenStore` Protocol with two implementations — `NullTokenStore` (default, no-op) and `JsonFileTokenStore` (per-`client_id` entries in a JSON file under the OS state directory). `TokenManager` loads from the store at boot, adopts the persisted tokens only when their fingerprint matches the current env seed, and saves after every successful refresh. `BlingClient` gains a single retry on 401 that goes through a new `TokenManager.force_refresh()`.

**Tech Stack:** Python ≥3.10, httpx (sync, injected), pytest + pytest-cov, stdlib `json`/`hashlib`/`pathlib`/`os`.

**Spec:** `docs/superpowers/specs/2026-08-02-token-persistence-design.md`

## Global Constraints

- Python ≥3.10. `X | None` union syntax is used throughout; every module starts with `from __future__ import annotations`.
- **Immutability:** never mutate a loaded dict/dataclass in place. Build new dicts with `{**old, ...}`. `StoredTokens` is `@dataclass(frozen=True)`.
- **Never silently swallow errors.** Store I/O failures degrade to in-memory operation but MUST print a warning to stderr.
- Store failures must never raise out of `load`/`save`. The server keeps serving 218 tools even when the cache file is unusable.
- All 62 existing tests must stay green without modification, except `tests/test_client.py`'s `FakeTokens` (Task 5) which gains a method.
- Test doubles only — no test may touch the network or the real user state directory. Use `tmp_path` for file I/O.
- Coverage must stay ≥90% (currently 93%). Check with `.venv/bin/python -m pytest --cov=bling_mcp --cov-report=term`.
- Commit after every task with a conventional-commit message.
- Run tests with `.venv/bin/python -m pytest` from the repo root.

## File Structure

| File | Responsibility |
|---|---|
| `src/bling_mcp/token_store.py` (new, ~150 lines) | Token persistence: `StoredTokens`, `TokenStore` Protocol, `NullTokenStore`, `JsonFileTokenStore`, `fingerprint`, `default_store_path` |
| `src/bling_mcp/auth.py` (modify) | Boot from store, persist on refresh, `force_refresh()` |
| `src/bling_mcp/client.py` (modify) | Retry once on 401 |
| `src/bling_mcp/config.py` (modify) | Read `BLING_TOKEN_STORE` into `token_store_path` |
| `src/bling_mcp/server.py` (modify) | `build_token_store()` + inject into `TokenManager` |
| `tests/test_token_store.py` (new) | Tasks 1–2 |
| `tests/test_auth.py` (modify) | Tasks 3–4 |
| `tests/test_client.py` (modify) | Task 5 |
| `tests/test_server.py` (modify) | Task 6 |

---

### Task 1: Token store primitives (no I/O)

Pure, side-effect-free pieces first: the record type, the Protocol, the no-op implementation, the seed fingerprint, and platform path resolution. No filesystem access in this task.

**Files:**
- Create: `src/bling_mcp/token_store.py`
- Test: `tests/test_token_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `StoredTokens(refresh_token: str, seed_fingerprint: str, access_token: str | None = None, expires_at: float = 0.0)` — frozen dataclass
  - `class TokenStore(Protocol)` with `load(self, client_id: str) -> StoredTokens | None` and `save(self, client_id: str, tokens: StoredTokens) -> None`
  - `class NullTokenStore` implementing that Protocol
  - `fingerprint(seed: str) -> str`
  - `default_store_path(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path`
  - Constants `STORE_VERSION = 1`, `APP_DIR_NAME = "bling-mcp"`, `STORE_FILE_NAME = "token.json"`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_token_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_token_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bling_mcp.token_store'`

- [ ] **Step 3: Write the implementation**

Create `src/bling_mcp/token_store.py`:

```python
"""Persistent storage for rotated Bling OAuth tokens.

Bling rotates the refresh token on every refresh. Keeping the rotated value only
in memory means a process restart falls back to the (by then stale) seed from the
environment, so the token set is mirrored to a small JSON file in the user's
state directory.

The store is a Protocol so the token manager can be tested without touching the
filesystem, matching how the HTTP client and clock are already injected.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

STORE_VERSION = 1
APP_DIR_NAME = "bling-mcp"
STORE_FILE_NAME = "token.json"


@dataclass(frozen=True)
class StoredTokens:
    """A persisted token set for one Bling application.

    ``seed_fingerprint`` identifies the ``BLING_REFRESH_TOKEN`` that seeded this
    entry, so a re-bootstrapped environment token can be told apart from the
    rotated descendants of the previous one.
    """

    refresh_token: str
    seed_fingerprint: str
    access_token: str | None = None
    expires_at: float = 0.0


class TokenStore(Protocol):
    """Reads and writes token state keyed by Bling ``client_id``."""

    def load(self, client_id: str) -> StoredTokens | None: ...

    def save(self, client_id: str, tokens: StoredTokens) -> None: ...


class NullTokenStore:
    """A store that persists nothing — preserves in-memory-only behaviour."""

    def load(self, client_id: str) -> StoredTokens | None:
        return None

    def save(self, client_id: str, tokens: StoredTokens) -> None:
        return None


def fingerprint(seed: str) -> str:
    """Return a stable digest identifying the environment's seed token."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def default_store_path(
    env: Mapping[str, str] | None = None, platform: str | None = None
) -> Path:
    """Return the per-platform default location of the token store.

    Deliberately does not read ``BLING_TOKEN_STORE``: the override belongs to
    :func:`bling_mcp.config.load_config`, which owns every app-level env var.
    ``XDG_STATE_HOME`` is honoured because it is a platform convention rather
    than configuration of this application.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform

    if platform == "win32":
        base = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")

    return base / APP_DIR_NAME / STORE_FILE_NAME
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_token_store.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — 74 tests (62 existing + 12 new)

- [ ] **Step 6: Commit**

```bash
git add src/bling_mcp/token_store.py tests/test_token_store.py
git commit -m "feat: token store primitives — StoredTokens, Protocol, platform paths"
```

---

### Task 2: JsonFileTokenStore

The filesystem implementation: atomic writes, per-`client_id` isolation, and degradation-with-warning on every failure path.

**Files:**
- Modify: `src/bling_mcp/token_store.py` (append)
- Test: `tests/test_token_store.py` (append)

**Interfaces:**
- Consumes: `StoredTokens`, `STORE_VERSION` from Task 1.
- Produces: `class JsonFileTokenStore` with `__init__(self, path: Path)`, a **public** `self.path: Path` attribute (Task 6 asserts on it), and the `load`/`save` methods of the `TokenStore` Protocol.

**On-disk format:**

```json
{
  "version": 1,
  "accounts": {
    "<client_id>": {
      "refresh_token": "...",
      "seed_fingerprint": "...",
      "access_token": "...",
      "expires_at": 1785000000.0
    }
  }
}
```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_token_store.py` (and extend the import at the top of the file to `from bling_mcp.token_store import (JsonFileTokenStore, NullTokenStore, StoredTokens, default_store_path, fingerprint,)`):

```python
import json
import os

import pytest


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_token_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'JsonFileTokenStore'`

- [ ] **Step 3: Write the implementation**

Append to `src/bling_mcp/token_store.py` (and add `import json` to the imports at the top):

```python
class JsonFileTokenStore:
    """Mirrors token state to a JSON file, keyed by ``client_id``.

    Every failure is non-fatal: an unusable cache file must never stop the
    server from serving. Problems are reported on stderr once per process so a
    refresh loop cannot flood the log.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._warned = False

    def load(self, client_id: str) -> StoredTokens | None:
        document = self._read_document()
        if document is None:
            return None

        accounts = document.get("accounts")
        entry = accounts.get(client_id) if isinstance(accounts, dict) else None
        if entry is None:
            return None  # no entry for this client is normal, not a problem
        if not isinstance(entry, dict):
            self._warn(f"ignoring malformed entry for {client_id} in {self.path}")
            return None

        try:
            return StoredTokens(
                refresh_token=entry["refresh_token"],
                seed_fingerprint=entry["seed_fingerprint"],
                access_token=entry.get("access_token"),
                expires_at=float(entry.get("expires_at") or 0.0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            self._warn(f"ignoring malformed entry for {client_id} in {self.path}: {exc}")
            return None

    def save(self, client_id: str, tokens: StoredTokens) -> None:
        document = self._read_document() or {}
        accounts = document.get("accounts")
        accounts = accounts if isinstance(accounts, dict) else {}

        self._write_document(
            {
                **document,
                "version": STORE_VERSION,
                "accounts": {
                    **accounts,
                    client_id: {
                        "refresh_token": tokens.refresh_token,
                        "seed_fingerprint": tokens.seed_fingerprint,
                        "access_token": tokens.access_token,
                        "expires_at": tokens.expires_at,
                    },
                },
            }
        )

    def _read_document(self) -> dict | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            self._warn(f"could not read token store {self.path}: {exc}")
            return None

        try:
            document = json.loads(raw)
        except ValueError as exc:
            self._warn(f"ignoring malformed token store {self.path}: {exc}")
            return None

        if not isinstance(document, dict):
            self._warn(f"ignoring malformed token store {self.path}: not an object")
            return None
        return document

    def _write_document(self, document: dict) -> None:
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(document, indent=2), encoding="utf-8")
            self._restrict_permissions(temp)
            # os.replace is atomic on POSIX and on Windows within one volume, so
            # a crash mid-write can never leave a truncated store behind.
            os.replace(temp, self.path)
        except OSError as exc:
            self._warn(f"could not write token store {self.path}: {exc}")
            _remove_quietly(temp)

    def _restrict_permissions(self, path: Path) -> None:
        """Limit the file to its owner on POSIX; Windows relies on the profile."""
        if os.name != "posix":
            return
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            self._warn(f"could not restrict permissions on {path}: {exc}")

    def _warn(self, message: str) -> None:
        if self._warned:
            return
        self._warned = True
        print(f"[bling-mcp] token store: {message}", file=sys.stderr)


def _remove_quietly(path: Path) -> None:
    """Best-effort cleanup of a temp file whose write already failed."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_token_store.py -v`
Expected: PASS (25 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — 87 tests

- [ ] **Step 6: Commit**

```bash
git add src/bling_mcp/token_store.py tests/test_token_store.py
git commit -m "feat: JsonFileTokenStore with atomic writes and degrade-with-warning"
```

---

### Task 3: TokenManager reads and writes the store

Boot precedence (the three-way table from the spec) plus persistence after every refresh. Also changes the default clock, because a persisted expiry has to survive the process.

**Files:**
- Modify: `src/bling_mcp/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `StoredTokens`, `TokenStore`, `NullTokenStore`, `fingerprint` from Tasks 1–2.
- Produces: `TokenManager.__init__(config, http_client, clock=time.time, expiry_margin=60, store=None)` — `store` is keyword-optional and defaults to `NullTokenStore()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py` (and add `from bling_mcp.token_store import StoredTokens, fingerprint` to the imports):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'store'`

- [ ] **Step 3: Write the implementation**

In `src/bling_mcp/auth.py`, add to the imports:

```python
from .token_store import NullTokenStore, StoredTokens, TokenStore, fingerprint
```

Replace `__init__` (currently lines 34-47) with:

```python
    def __init__(
        self,
        config: BlingConfig,
        http_client: httpx.Client,
        clock: Callable[[], float] = time.time,
        expiry_margin: int = DEFAULT_EXPIRY_MARGIN_SECONDS,
        store: TokenStore | None = None,
    ) -> None:
        self._config = config
        self._http = http_client
        self._clock = clock
        self._margin = expiry_margin
        self._store = store if store is not None else NullTokenStore()
        self._seed_fingerprint = fingerprint(config.refresh_token)
        self._refresh_token = config.refresh_token
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._adopt(self._store.load(config.client_id))

    def _adopt(self, stored: StoredTokens | None) -> None:
        """Take over persisted tokens, but only if this env seeded them.

        A fingerprint mismatch means ``BLING_REFRESH_TOKEN`` was re-bootstrapped
        since the entry was written, so the entry is stale and gets ignored —
        otherwise the old token would silently mask the new one.
        """
        if stored is None or stored.seed_fingerprint != self._seed_fingerprint:
            return
        self._refresh_token = stored.refresh_token
        self._access_token = stored.access_token
        self._expires_at = stored.expires_at
```

Then update the docstring for the module clock note and replace the tail of `_refresh` (currently lines 79-84) with:

```python
        payload = response.json()
        self._access_token = payload["access_token"]
        self._expires_at = self._clock() + float(payload.get("expires_in", 0))
        rotated = payload.get("refresh_token")
        if rotated:
            self._refresh_token = rotated
        self._persist()

    def _persist(self) -> None:
        self._store.save(
            self._config.client_id,
            StoredTokens(
                refresh_token=self._refresh_token,
                seed_fingerprint=self._seed_fingerprint,
                access_token=self._access_token,
                expires_at=self._expires_at,
            ),
        )
```

Finally, update the module docstring to record the clock trade-off — replace the last paragraph with:

```python
The HTTP client, clock and token store are injected to keep the refresh flow
testable without network access, real time, or the filesystem.

The clock is wall-clock (``time.time``) rather than ``time.monotonic`` because
the expiry is persisted and has to remain meaningful across process restarts.
The cost is sensitivity to clock adjustments; the 60s margin absorbs small
jumps and the client's 401 retry covers the rest.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (14 tests — 6 existing + 8 new)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — 95 tests

- [ ] **Step 6: Commit**

```bash
git add src/bling_mcp/auth.py tests/test_auth.py
git commit -m "feat: TokenManager boots from and persists to the token store"
```

---

### Task 4: TokenManager.force_refresh()

The entry point the client calls after a 401. Re-reads the store first so a token rotated by a second process is picked up instead of being spent on a doomed refresh.

**Files:**
- Modify: `src/bling_mcp/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `_adopt`, `_refresh`, `_store` from Task 3.
- Produces: `TokenManager.force_refresh() -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_auth.py -k force_refresh -v`
Expected: FAIL — `AttributeError: 'TokenManager' object has no attribute 'force_refresh'`

- [ ] **Step 3: Write the implementation**

Add to `TokenManager` in `src/bling_mcp/auth.py`, immediately after `get_access_token`:

```python
    def force_refresh(self) -> str:
        """Refresh unconditionally, consulting the store first.

        Called after the API rejects a token with 401. Another process may have
        rotated the refresh token since this one loaded it, so the disk copy is
        re-read before spending the in-memory token on a request that would
        fail. The seed fingerprint is unchanged by rotation, so an entry written
        by a sibling process is always adopted.
        """
        self._adopt(self._store.load(self._config.client_id))
        self._refresh()
        assert self._access_token is not None  # set by _refresh on success
        return self._access_token
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — 99 tests

- [ ] **Step 6: Commit**

```bash
git add src/bling_mcp/auth.py tests/test_auth.py
git commit -m "feat: TokenManager.force_refresh re-reads the store before renewing"
```

---

### Task 5: BlingClient retries once on 401

**Files:**
- Modify: `src/bling_mcp/client.py:17-18` (the `_Tokens` Protocol) and `src/bling_mcp/client.py:50-87` (`_request`)
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `TokenManager.force_refresh()` from Task 4.
- Produces: no new public API — `get`/`post`/`put`/`patch`/`delete` keep their signatures.

- [ ] **Step 1: Write the failing tests**

In `tests/test_client.py`, replace the `FakeTokens` class (lines 23-30) with:

```python
class FakeTokens:
    def __init__(self, token="TOK", refreshed="TOK2"):
        self.token = token
        self.refreshed = refreshed
        self.calls = 0
        self.forced = 0

    def get_access_token(self):
        self.calls += 1
        return self.token

    def force_refresh(self):
        self.forced += 1
        self.token = self.refreshed
        return self.token
```

Then append:

```python
def test_401_forces_a_refresh_and_retries_once():
    http, reqs = build_client([{"status": 401, "json": {}}, {"json": {"data": [1]}}])
    tokens = FakeTokens("STALE", refreshed="FRESH")
    client = BlingClient(make_config(), tokens, http)

    assert client.get("produtos") == {"data": [1]}
    assert tokens.forced == 1
    assert len(reqs) == 2
    assert reqs[0].headers["Authorization"] == "Bearer STALE"
    assert reqs[1].headers["Authorization"] == "Bearer FRESH"


def test_second_401_raises_bling_api_error():
    http, reqs = build_client([{"status": 401, "json": {"error": "unauthorized"}}])
    tokens = FakeTokens()
    client = BlingClient(make_config(), tokens, http)

    with pytest.raises(BlingApiError) as exc:
        client.get("produtos")

    assert exc.value.status_code == 401
    assert tokens.forced == 1  # retried exactly once, not in a loop
    assert len(reqs) == 2


def test_successful_request_never_forces_a_refresh():
    http, _ = build_client([{"json": {}}])
    tokens = FakeTokens()
    client = BlingClient(make_config(), tokens, http)

    client.get("produtos")

    assert tokens.forced == 0


def test_403_and_500_do_not_retry():
    for status in (403, 500):
        http, reqs = build_client([{"status": status, "json": {}}])
        tokens = FakeTokens()
        client = BlingClient(make_config(), tokens, http)

        with pytest.raises(BlingApiError):
            client.get("produtos")

        assert tokens.forced == 0
        assert len(reqs) == 1


def test_retry_replays_method_body_and_params():
    http, reqs = build_client([{"status": 401, "json": {}}, {"status": 201, "json": {}}])
    client = BlingClient(make_config(), FakeTokens(), http)

    client.post("produtos", json={"nome": "X"}, params={"loja": 7})

    assert [r.method for r in reqs] == ["POST", "POST"]
    assert b'"nome"' in reqs[1].content
    assert reqs[1].url.params.get("loja") == "7"


def test_retry_applies_to_delete_too():
    http, reqs = build_client([{"status": 401, "json": {}}, {"status": 204}])
    client = BlingClient(make_config(), FakeTokens(), http)

    assert client.delete("produtos/5") is None
    assert [r.method for r in reqs] == ["DELETE", "DELETE"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_client.py -v`
Expected: FAIL — `test_401_forces_a_refresh_and_retries_once` raises `BlingApiError` instead of returning the body

- [ ] **Step 3: Write the implementation**

In `src/bling_mcp/client.py`, extend the Protocol:

```python
class _Tokens(Protocol):
    def get_access_token(self) -> str: ...

    def force_refresh(self) -> str: ...
```

Replace the body of `_request` (lines 63-87) with:

```python
        url = f"{self._config.api_base_url}/{path.lstrip('/')}"
        cleaned = _clean_params(params)

        def send(token: str) -> httpx.Response:
            return self._http.request(
                method,
                url,
                params=cleaned,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )

        try:
            response = send(self._tokens.get_access_token())
            if response.status_code == 401:
                # A 401 means the token was rejected before the request was
                # processed, so replaying it is safe even for POST and DELETE.
                # Exactly one retry: a second 401 is a real authorization
                # failure, not a stale token.
                response = send(self._tokens.force_refresh())
        except httpx.HTTPError as exc:
            raise BlingApiError(0, f"Request to {path} failed: {exc}") from exc

        if not response.is_success:
            raise BlingApiError(
                response.status_code,
                f"Bling API error on {path}: HTTP {response.status_code} {response.text}",
                payload=_safe_json(response),
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
```

Also update the `_request` docstring to mention the retry, and the module docstring's first line — it still says "Thin **read-only** HTTP client", which has been wrong since write verbs were added:

```python
"""Thin HTTP client for the Bling v3 API.

Wraps every verb with bearer authentication (via the token manager), URL
joining, query-param cleaning, error mapping, and a single retry on 401. The
httpx client is injected so the wrapper is testable without network access.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_client.py -v`
Expected: PASS (15 tests — 9 existing + 6 new)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: PASS — 105 tests

- [ ] **Step 6: Commit**

```bash
git add src/bling_mcp/client.py tests/test_client.py
git commit -m "feat: retry once on 401 after forcing a token refresh"
```

---

### Task 6: Wire the store into config and server

**Files:**
- Modify: `src/bling_mcp/config.py:26-66`
- Modify: `src/bling_mcp/server.py:24-28`
- Test: `tests/test_config.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `JsonFileTokenStore`, `default_store_path` (Tasks 1–2); `TokenManager(store=...)` (Task 3).
- Produces: `BlingConfig.token_store_path: str | None`; `server.build_token_store(config: BlingConfig) -> JsonFileTokenStore`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_token_store_path_defaults_to_none():
    assert load_config(_base_env()).token_store_path is None


def test_token_store_path_is_read_from_env():
    cfg = load_config(_base_env(BLING_TOKEN_STORE="/custom/token.json"))
    assert cfg.token_store_path == "/custom/token.json"


def test_blank_token_store_path_is_treated_as_unset():
    cfg = load_config(_base_env(BLING_TOKEN_STORE="   "))
    assert cfg.token_store_path is None
```

> `_base_env(**extra)` is the existing helper at `tests/test_config.py:8-16`.
> The file also has a `VALID_ENV` dict; either works, but `_base_env` takes
> overrides directly, so use it.

Append to `tests/test_server.py`. Note this file has **no** `make_config` helper
— it uses a `_Cfg` duck-typed stub that has no `token_store_path`, so these
tests need a real `BlingConfig`:

```python
from pathlib import Path

from bling_mcp.config import BlingConfig
from bling_mcp.server import build_token_store, build_tools
from bling_mcp.token_store import JsonFileTokenStore, default_store_path


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


def test_build_token_store_honours_the_configured_path():
    store = build_token_store(make_config(token_store_path="/custom/token.json"))

    assert isinstance(store, JsonFileTokenStore)
    assert store.path == Path("/custom/token.json")


def test_build_token_store_falls_back_to_the_platform_default():
    assert build_token_store(make_config()).path == default_store_path()


def test_build_tools_injects_the_token_store(tmp_path):
    cfg = make_config(token_store_path=str(tmp_path / "token.json"))

    client = build_tools(cfg)

    assert isinstance(client._tokens._store, JsonFileTokenStore)
```

> `build_tools` opens an `httpx.Client` but makes no network call, so this test
> is offline. Reaching into `client._tokens._store` is deliberate: it is the
> only way to assert the injection actually happened.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_server.py -v`
Expected: FAIL — `AttributeError: 'BlingConfig' object has no attribute 'token_store_path'` and `ImportError: cannot import name 'build_token_store'`

- [ ] **Step 3: Write the implementation**

In `src/bling_mcp/config.py`, add the field **last** in `BlingConfig` (after `modules`, so existing positional construction is unaffected):

```python
    token_store_path: str | None = None
```

And in `load_config`, before the `return`:

```python
    store_path = (env.get("BLING_TOKEN_STORE") or "").strip() or None
```

then add `token_store_path=store_path,` to the `BlingConfig(...)` call.

In `src/bling_mcp/server.py`, add the imports:

```python
from pathlib import Path

from .token_store import JsonFileTokenStore, default_store_path
```

and replace `build_tools` (lines 24-28) with:

```python
def build_token_store(config: BlingConfig) -> JsonFileTokenStore:
    """Resolve the token store: the configured path, else the platform default."""
    path = (
        Path(config.token_store_path)
        if config.token_store_path
        else default_store_path()
    )
    return JsonFileTokenStore(path)


def build_tools(config: BlingConfig) -> BlingClient:
    """Assemble the HTTP client (no network call until a tool runs)."""
    http = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    tokens = TokenManager(config, http, store=build_token_store(config))
    return BlingClient(config, tokens, http)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_server.py -v`
Expected: PASS (16 + 9 tests)

- [ ] **Step 5: Run the full suite with coverage**

Run: `.venv/bin/python -m pytest --cov=bling_mcp --cov-report=term`
Expected: PASS — 111 tests, TOTAL coverage ≥90%

- [ ] **Step 6: Verify the server still starts and registers 218 tools**

Run:

```bash
BLING_CLIENT_ID=x BLING_CLIENT_SECRET=y BLING_REFRESH_TOKEN=z \
BLING_TOKEN_STORE=/tmp/bling-token-check.json \
.venv/bin/python -c "
import os
from bling_mcp.server import build_tools, create_server
from bling_mcp.config import load_config
cfg = load_config(os.environ)
print(len(create_server(build_tools(cfg), cfg)._tool_manager.list_tools()))
"
```

Expected: prints `218`. No network call happens, so no credentials are needed.

- [ ] **Step 7: Commit**

```bash
git add src/bling_mcp/config.py src/bling_mcp/server.py tests/test_config.py tests/test_server.py
git commit -m "feat: wire BLING_TOKEN_STORE through config into the server"
```

---

### Task 7: Documentation

**Files:**
- Modify: `INSTALL.md:12-19` (env table) and the gotchas section
- Modify: `README.md` (env table)
- Modify: `.env.example`
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: the behaviour built in Tasks 1–6.
- Produces: nothing code-facing.

- [ ] **Step 1: Add the env var to INSTALL.md**

Add this row to the table at `INSTALL.md:12-19`:

```markdown
| `BLING_TOKEN_STORE` | no | path to the token cache; default is the OS state dir (see below) |
```

And replace the closing line of the OAuth section (`INSTALL.md:137`, "The server auto-refreshes the short-lived access token from there on.") with:

```markdown
The server auto-refreshes the short-lived access token from there on, and
**persists the rotated refresh token** so it survives restarts.

### Where the token is cached

Bling issues a new refresh token on every refresh and the previous one stops
working, so the server mirrors the current token set to:

| Platform | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\bling-mcp\token.json` |
| macOS | `~/Library/Application Support/bling-mcp/token.json` |
| Linux | `$XDG_STATE_HOME/bling-mcp/token.json`, else `~/.local/state/bling-mcp/token.json` |

Override with `BLING_TOKEN_STORE`. The file holds live credentials — it is
created mode `0600` on macOS/Linux; on Windows it relies on the user profile.

`BLING_REFRESH_TOKEN` stays required: it is the seed. The cache records which
seed produced it, so re-running the OAuth bootstrap and pasting a new token into
the config just works — the stale cache entry is discarded automatically. If the
cache cannot be read or written, the server prints a warning to stderr and keeps
running with the token in memory only.
```

- [ ] **Step 2: Add the same row to the README env table**

Run `grep -n "BLING_ACCOUNT_LABEL" README.md` to locate the table, then add:

```markdown
| `BLING_TOKEN_STORE` | no | path to the token cache; default is the OS state dir |
```

- [ ] **Step 3: Add the variable to `.env.example`**

```bash
# Optional: where the rotated refresh token is cached.
# Default: %LOCALAPPDATA%\bling-mcp\token.json (Windows),
#          ~/Library/Application Support/bling-mcp/token.json (macOS),
#          ~/.local/state/bling-mcp/token.json (Linux)
# BLING_TOKEN_STORE=
```

- [ ] **Step 4: Record the iteration in PROGRESS.md**

Replace the "Remaining polish" section's first two bullets and add above it:

```markdown
### Iteration 6 — token persistence + 401 retry ✅

- [x] `token_store.py` — `TokenStore` Protocol, `NullTokenStore`, `JsonFileTokenStore`
      (atomic write via `os.replace`, `0600` on POSIX, per-`client_id` entries).
- [x] `auth.py` — boots from the store, adopts persisted tokens only when the
      seed fingerprint matches (so a re-bootstrap wins), persists after every
      refresh, and gained `force_refresh()` which re-reads the store first.
- [x] Clock default moved from `time.monotonic` to `time.time` — a persisted
      expiry has to survive the process. Trade-off recorded in the module docstring.
- [x] `client.py` — one retry on 401 via `force_refresh()`; closes the item
      deferred back in iteration 2.
- [x] `config.py`/`server.py` — `BLING_TOKEN_STORE` override, platform default.
- [x] Store failures degrade with a stderr warning; they never raise.

**Fixes:** the rotated refresh token used to live only in memory, so any restart
fell back to the (already spent) seed from the env block.

### Remaining polish (optional — run `/loop ...` again to resume)
- [ ] Sample `manifests/claude_desktop_config.json` committed to the repo
- [ ] `x-bling-homologacao` header support for the `homologacao` module (needs per-endpoint header spec)
- [ ] Publish to PyPI so install collapses to `uvx bling-mcp`
- [ ] Retry/backoff for 429 honouring `Retry-After`
```

Also fix the stale test count at `PROGRESS.md:58` — the header says "80 tests green", the real count before this work was 62. Update it to `62 tests green, 93% coverage`.

- [ ] **Step 5: Fix the stale package description**

`pyproject.toml:3` still says "read-only tools over OAuth 2.0", which stopped being true when write verbs landed in iteration 5. Replace with:

```toml
description = "MCP server for Bling ERP (bling.com.br) v3 API — full CRUD over OAuth 2.0."
```

- [ ] **Step 6: Verify the docs match reality**

Run: `.venv/bin/python -m pytest --cov=bling_mcp --cov-report=term`
Expected: PASS — 111 tests, coverage ≥90%. Confirm the numbers you wrote into `PROGRESS.md` match this output; correct them if they drifted.

- [ ] **Step 7: Commit**

```bash
git add INSTALL.md README.md .env.example PROGRESS.md pyproject.toml
git commit -m "docs: document BLING_TOKEN_STORE, token persistence, and 401 retry"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `StoredTokens`, `TokenStore` Protocol, `NullTokenStore` | 1 |
| `fingerprint`, `default_store_path` (+ XDG, no `BLING_TOKEN_STORE`) | 1 |
| `JsonFileTokenStore`, JSON shape, atomic write, `0600` | 2 |
| Boot precedence table (absent / matching / divergent fingerprint) | 3 |
| Persist after every refresh; access token + expiry persisted | 3 |
| Clock `monotonic` → `time.time` trade-off | 3 |
| `force_refresh()` re-reads the store (concurrency) | 4 |
| 401 retry, exactly once, preserves method/body/params | 5 |
| `config.token_store_path` from `BLING_TOKEN_STORE` | 6 |
| `server.build_tools` injects the store | 6 |
| Read failure / malformed JSON → warning + treat as empty | 2 |
| Write failure → warning once, no raise | 2 |
| Docs: INSTALL, README, `.env.example`, PROGRESS | 7 |
| Out of scope (file locking, 429 backoff, encryption) | not implemented, by design |

No gaps.

**Placeholder scan:** every code step contains runnable code; no TBD/TODO. The two "Note for the implementer" callouts in Task 6 point at existing helpers whose exact names must be read from the test files — that is a lookup instruction, not a deferred decision.

**Type consistency:** `StoredTokens` field order (`refresh_token`, `seed_fingerprint`, `access_token`, `expires_at`) is identical in Tasks 1, 2, 3 and 4. `JsonFileTokenStore.path` is public in Task 2 and asserted in Task 6. `force_refresh() -> str` is defined in Task 4 and consumed by the Protocol in Task 5. `store` is keyword-optional in Task 3 and passed by keyword in Task 6.

**Test counts:** 62 existing → 74 (T1) → 87 (T2) → 95 (T3) → 99 (T4) → 105 (T5) → 111 (T6).
