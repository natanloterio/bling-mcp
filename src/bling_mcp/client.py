"""Thin read-only HTTP client for the Bling v3 API.

Wraps GET requests with bearer authentication (via the token manager), URL
joining, query-param cleaning, and error mapping. The httpx client is injected
so the wrapper is testable without network access.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import httpx

from .config import BlingConfig


class _Tokens(Protocol):
    def get_access_token(self) -> str: ...


class BlingApiError(RuntimeError):
    """Raised when the Bling API returns a non-success response."""

    def __init__(self, status_code: int, message: str, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop params whose value is None so unset optional args are omitted."""
    if not params:
        return {}
    return {k: v for k, v in params.items() if v is not None}


class BlingClient:
    """Read-only client for Bling v3 GET endpoints."""

    def __init__(
        self,
        config: BlingConfig,
        token_manager: _Tokens,
        http_client: httpx.Client,
    ) -> None:
        self._config = config
        self._tokens = token_manager
        self._http = http_client

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET a Bling endpoint and return the parsed JSON body."""
        url = f"{self._config.api_base_url}/{path.lstrip('/')}"
        token = self._tokens.get_access_token()
        try:
            response = self._http.get(
                url,
                params=_clean_params(params),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise BlingApiError(0, f"Request to {path} failed: {exc}") from exc

        if not response.is_success:
            raise BlingApiError(
                response.status_code,
                f"Bling API error on {path}: HTTP {response.status_code} {response.text}",
                payload=_safe_json(response),
            )
        return response.json()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
