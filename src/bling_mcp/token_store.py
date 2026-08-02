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
import json
import os
import sys
import tempfile
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

        accounts = self._accounts_of(document)
        if accounts is None:
            return None
        entry = accounts.get(client_id)
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
        accounts = self._accounts_of(document) or {}

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
        except (OSError, UnicodeDecodeError) as exc:
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

    def _accounts_of(self, document: dict) -> dict | None:
        """Extract ``document["accounts"]`` as a dict.

        A missing key is normal (empty store) and returns ``{}`` without a
        warning. A present-but-wrong-shaped value warns and returns ``None``,
        letting each caller decide whether that is fatal (``load``) or
        recoverable by starting from an empty dict (``save``).
        """
        accounts = document.get("accounts")
        if accounts is None:
            return {}
        if not isinstance(accounts, dict):
            self._warn(f"ignoring malformed accounts in {self.path}: expected dict, got {type(accounts).__name__}")
            return None
        return accounts

    def _write_document(self, document: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A unique name per writer: two processes saving concurrently must
            # never share one temp path, or the loser's os.replace can install
            # a half-written file, or fail after the winner already replaced
            # it out from under them. mkstemp also creates the file at 0600,
            # so the live refresh token is never briefly group-readable before
            # _restrict_permissions runs.
            fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=f"{self.path.name}.", suffix=".tmp")
        except OSError as exc:
            self._warn(f"could not write token store {self.path}: {exc}")
            return

        temp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(document, indent=2))
            self._restrict_permissions(temp)
            # os.replace is atomic on POSIX and on Windows within one volume, so
            # a crash mid-write can never leave a truncated store behind.
            os.replace(temp, self.path)
        except (OSError, TypeError) as exc:
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
