"""Re-authorization service: the object behind the ``bling_authorize*`` tools.

Owns the loopback :class:`CallbackServer` (started lazily, kept for the
process lifetime) and the current :class:`AuthorizationFlow`. Each ``begin``
mints a new flow with its own ``state``; the server resolves the active flow
through a provider so it never holds a stale reference.

If the configured port cannot be bound (another instance, a firewall, or the
port taken by something else) the link is still returned and the user falls
back to pasting the code via ``complete_with_code``.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .auth import TokenManager
from .callback_server import CallbackServer
from .config import BlingConfig
from .oauth_flow import (
    DEFAULT_FLOW_TIMEOUT_SECONDS,
    EXCHANGING,
    PENDING,
    AuthorizationFlow,
)

NO_FLOW = "none"

_INSTRUCTIONS_AUTO = (
    "Show the user the authorize_url as a clickable link. After they approve in "
    "the browser, Bling redirects to the local callback and the new tokens are "
    "installed automatically; confirm with bling_auth_status. If the browser "
    "shows a connection error instead, ask the user for the `code` parameter "
    "from the address bar and call bling_authorize_with_code."
)
_INSTRUCTIONS_MANUAL = (
    "The local callback listener could not start ({reason}). Show the user the "
    "authorize_url as a clickable link; after they approve, Bling redirects to "
    "{redirect_uri}, which will fail to load. Ask them for the `code` parameter "
    "from that address bar and call bling_authorize_with_code with it."
)


class ReauthService:
    """Start, track and finish in-chat Bling re-authorizations."""

    def __init__(
        self,
        config: BlingConfig,
        http_client: httpx.Client,
        token_manager: TokenManager,
        *,
        clock: Callable[[], float] = time.time,
        timeout: float = DEFAULT_FLOW_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self._http = http_client
        self._tokens = token_manager
        self._clock = clock
        self._timeout = timeout
        self._flow: AuthorizationFlow | None = None
        self._server = CallbackServer(
            port=config.oauth_callback_port,
            flow_provider=lambda: self._flow,
            redirect_host=config.oauth_redirect_host,
        )

    def begin(self) -> dict[str, Any]:
        """Start a fresh flow and return what the agent needs to show the user."""
        if self._flow is not None and self._flow.status().state == EXCHANGING:
            raise RuntimeError(
                "An authorization is in progress; check bling_auth_status before starting another"
            )
        listen_error = self._ensure_listening()
        redirect_uri = self._server.redirect_uri  # same host/port whether or not it bound
        self._flow = self._new_flow(redirect_uri)
        instructions = (
            _INSTRUCTIONS_AUTO
            if listen_error is None
            else _INSTRUCTIONS_MANUAL.format(reason=listen_error, redirect_uri=redirect_uri)
        )
        return {
            "authorize_url": self._flow.authorize_url,
            "redirect_uri": redirect_uri,
            "callback_listening": listen_error is None,
            "expires_in_seconds": int(self._timeout),
            "instructions": instructions,
        }

    def status(self) -> dict[str, str]:
        """Report the current flow's state for the agent to relay."""
        if self._flow is None:
            return {"status": NO_FLOW, "detail": "No authorization started; call bling_authorize."}
        snapshot = self._flow.status()
        return {"status": snapshot.state, "detail": snapshot.detail}

    def complete_with_code(self, code: str) -> dict[str, str]:
        """Manual fallback: exchange a code the user pasted from the address bar."""
        cleaned = (code or "").strip()
        if not cleaned:
            raise ValueError("code must not be blank")
        if self._flow is None or self._flow.status().state != PENDING:
            self._flow = self._new_flow(self._server.redirect_uri)
        self._flow.complete_with_code(cleaned)
        return self.status()

    def close(self) -> None:
        """Stop the listener (idempotent)."""
        self._server.stop()

    def _new_flow(self, redirect_uri: str) -> AuthorizationFlow:
        return AuthorizationFlow(
            self._config,
            self._http,
            self._tokens,
            redirect_uri=redirect_uri,
            clock=self._clock,
            timeout=self._timeout,
        )

    def _ensure_listening(self) -> str | None:
        """Start the callback server; return the failure reason instead of raising."""
        try:
            self._server.start()
        except OSError as exc:
            return str(exc)
        return None
