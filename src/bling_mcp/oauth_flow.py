"""In-chat re-authorization: one authorization-code flow per attempt.

Bling's refresh token dies after 30 days without a refresh. Rather than editing
the MCP client config and restarting, the agent starts an
:class:`AuthorizationFlow`, shows the user its ``authorize_url``, and the
approval comes back either through the loopback callback (``complete``) or as a
code the user pastes into the chat (``complete_with_code``). Either path
exchanges the code and hands the new token set to the :class:`TokenManager`.

The flow is a small state machine: ``pending`` -> ``exchanging`` ->
``completed`` | ``failed``, or ``pending`` -> ``expired`` once the timeout
passes. Transitions are guarded by a lock because the callback arrives on a
``ThreadingHTTPServer`` thread while ``bling_authorize_with_code`` runs on the
MCP thread, and browsers happily deliver the same redirect twice. HTTP, clock
and state generation are injected so it is testable without network, time or
randomness.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from .auth import AuthError, TokenManager
from .authorize import build_authorize_url, exchange_code
from .config import BlingConfig

PENDING = "pending"
EXCHANGING = "exchanging"
COMPLETED = "completed"
FAILED = "failed"
EXPIRED = "expired"

# How long the user has to approve in the browser before the flow lapses.
DEFAULT_FLOW_TIMEOUT_SECONDS = 300
_STATE_BYTES = 32


class FlowError(RuntimeError):
    """Raised when a callback cannot be accepted for this flow."""


@dataclass(frozen=True)
class FlowStatus:
    """A snapshot of where the flow stands."""

    state: str
    detail: str = ""


class AuthorizationFlow:
    """One attempt to obtain a fresh Bling token set from the browser."""

    def __init__(
        self,
        config: BlingConfig,
        http_client: httpx.Client,
        token_manager: TokenManager,
        *,
        redirect_uri: str,
        clock: Callable[[], float] = time.time,
        timeout: float = DEFAULT_FLOW_TIMEOUT_SECONDS,
        state_factory: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._http = http_client
        self._tokens = token_manager
        self._clock = clock
        self._deadline = clock() + timeout
        self.redirect_uri = redirect_uri
        self.state = (state_factory or _random_state)()
        self.authorize_url = build_authorize_url(
            config.client_id, state=self.state, redirect_uri=redirect_uri
        )
        self._status = FlowStatus(PENDING)
        self._lock = threading.Lock()

    def status(self) -> FlowStatus:
        """Return the current state, promoting a stale pending flow to expired."""
        with self._lock:
            return self._current()

    def complete(self, code: str, state: str) -> None:
        """Accept the loopback callback, refusing a ``state`` this flow did not issue."""
        self._require_pending()
        if not _same_state(state, self.state):
            raise FlowError("Callback state does not match this authorization flow")
        self.complete_with_code(code)

    def complete_with_code(self, code: str) -> None:
        """Exchange ``code`` and install the tokens (manual paste skips the state check)."""
        self._claim()
        try:
            payload = exchange_code(
                self._config.client_id,
                self._config.client_secret,
                code,
                self._http,
                token_url=self._config.token_url,
                redirect_uri=self.redirect_uri,
                enable_jwt=self._config.enable_jwt,
            )
            self._tokens.install(payload)
        except AuthError as exc:
            self._settle(FlowStatus(FAILED, str(exc)))
            raise
        self._settle(FlowStatus(COMPLETED, "New Bling tokens installed and persisted."))

    def _current(self) -> FlowStatus:
        """Status as seen right now; caller must hold ``_lock``."""
        if self._status.state == PENDING and self._clock() > self._deadline:
            return FlowStatus(EXPIRED, "The authorization link timed out; start again.")
        return self._status

    def _require_pending(self) -> None:
        with self._lock:
            _raise_unless_pending(self._current())

    def _claim(self) -> None:
        """Atomically move PENDING -> EXCHANGING so only one caller talks to Bling."""
        with self._lock:
            _raise_unless_pending(self._current())
            self._status = FlowStatus(EXCHANGING, "Exchanging the authorization code.")

    def _settle(self, outcome: FlowStatus) -> None:
        with self._lock:
            self._status = outcome


def _raise_unless_pending(current: FlowStatus) -> None:
    if current.state == EXCHANGING:
        raise FlowError("Authorization is already in progress; wait for it to finish")
    if current.state != PENDING:
        raise FlowError(f"Authorization flow is already {current.state}")


def _same_state(candidate: str, expected: str) -> bool:
    """Constant-time comparison that never raises on non-ASCII input."""
    return secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def _random_state() -> str:
    return secrets.token_urlsafe(_STATE_BYTES)
