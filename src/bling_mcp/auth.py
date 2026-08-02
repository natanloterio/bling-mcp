"""OAuth 2.0 token management for the Bling v3 API.

Bling issues a short-lived (~6h) access token that is refreshed using a
long-lived refresh token. The refresh token may rotate on each refresh, so the
manager tracks its own current refresh token rather than mutating the
(immutable) config.

The HTTP client, clock and token store are injected to keep the refresh flow
testable without network access, real time, or the filesystem.

The clock is wall-clock (``time.time``) rather than ``time.monotonic`` because
the expiry is persisted and has to remain meaningful across process restarts.
The cost is sensitivity to clock adjustments; the 60s margin absorbs small
jumps and the client's 401 retry covers the rest.
"""

from __future__ import annotations

import base64
import time
from typing import Callable

import httpx

from .config import BlingConfig
from .token_store import NullTokenStore, StoredTokens, TokenStore, fingerprint

# Refresh this many seconds before the token actually expires, to avoid using a
# token that lapses mid-request.
DEFAULT_EXPIRY_MARGIN_SECONDS = 60


class AuthError(RuntimeError):
    """Raised when an OAuth token refresh fails."""


class TokenManager:
    """Caches and refreshes the Bling OAuth access token on demand."""

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

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing it if missing or near expiry."""
        if self._access_token is None or self._clock() >= self._expires_at - self._margin:
            self._refresh()
        assert self._access_token is not None  # set by _refresh on success
        return self._access_token

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

    def _refresh(self) -> None:
        credentials = f"{self._config.client_id}:{self._config.client_secret}"
        basic = base64.b64encode(credentials.encode()).decode()
        try:
            response = self._http.post(
                self._config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                headers={
                    "Authorization": f"Basic {basic}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:  # network/transport failure
            raise AuthError(f"Token refresh request failed: {exc}") from exc

        if not response.is_success:
            raise AuthError(
                f"Token refresh failed: HTTP {response.status_code} {response.text}"
            )

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
