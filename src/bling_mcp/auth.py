"""OAuth 2.0 token management for the Bling v3 API.

Bling issues a short-lived (~6h) access token that is refreshed using a
long-lived refresh token. The refresh token may rotate on each refresh, so the
manager tracks its own current refresh token rather than mutating the
(immutable) config.

The HTTP client and clock are injected to keep the refresh flow testable without
network access or real time.
"""

from __future__ import annotations

import base64
import time
from typing import Callable

import httpx

from .config import BlingConfig

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
        clock: Callable[[], float] = time.monotonic,
        expiry_margin: int = DEFAULT_EXPIRY_MARGIN_SECONDS,
    ) -> None:
        self._config = config
        self._http = http_client
        self._clock = clock
        self._margin = expiry_margin
        self._refresh_token = config.refresh_token
        self._access_token: str | None = None
        self._expires_at = 0.0

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing it if missing or near expiry."""
        if self._access_token is None or self._clock() >= self._expires_at - self._margin:
            self._refresh()
        assert self._access_token is not None  # set by _refresh on success
        return self._access_token

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
