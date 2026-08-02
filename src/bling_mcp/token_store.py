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
