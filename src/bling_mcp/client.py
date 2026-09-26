"""Thin HTTP client for the Bling v3 API.

Wraps every verb with bearer authentication (via the token manager), URL
joining, query-param cleaning, error mapping, and a single retry on 401. The
httpx client is injected so the wrapper is testable without network access.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import httpx

from .auth import JWT_HEADER, looks_like_jwt
from .config import BlingConfig


class _Tokens(Protocol):
    def get_access_token(self) -> str: ...

    def force_refresh(self) -> str: ...


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
    """Client for the Bling v3 API with automatic retry on 401."""

    def __init__(
        self,
        config: BlingConfig,
        token_manager: _Tokens,
        http_client: httpx.Client,
    ) -> None:
        self._config = config
        self._tokens = token_manager
        self._http = http_client

    def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Send a request to a Bling endpoint and return the parsed JSON body.

        A body is sent (with ``Content-Type: application/json``) only when
        ``json`` is not ``None``; ``204 No Content`` and empty bodies return
        ``None``. Retries once on 401 after forcing a token refresh.
        """
        url = f"{self._config.api_base_url}/{path.lstrip('/')}"
        cleaned = _clean_params(params)

        def send(token: str) -> httpx.Response:
            # Bling wants ``enable-jwt: 1`` on every call made with a JWT. It is
            # keyed on the token's shape, not on config, so an opaque token still
            # in circulation is never sent with a header the docs do not cover.
            return self._http.request(
                method,
                url,
                params=cleaned,
                json=json,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    **(JWT_HEADER if looks_like_jwt(token) else {}),
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

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET a Bling endpoint and return the parsed JSON body."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """POST a JSON body to a Bling endpoint (create)."""
        return self._request("POST", path, params=params, json=json)

    def put(
        self,
        path: str,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """PUT a JSON body to a Bling endpoint (full replace)."""
        return self._request("PUT", path, params=params, json=json)

    def patch(
        self,
        path: str,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """PATCH a JSON body to a Bling endpoint (partial update)."""
        return self._request("PATCH", path, params=params, json=json)

    def delete(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> Any:
        """DELETE a Bling endpoint."""
        return self._request("DELETE", path, params=params)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
