"""The three MCP tools that re-authorize Bling from the chat.

They are thin, named wrappers over :class:`~bling_mcp.reauth.ReauthService` so
the server can register them like any other tool. They are registered
unconditionally: the ``BLING_MODULES`` filter narrows the API surface, but a
server whose refresh token has expired must always be able to recover.
"""

from __future__ import annotations

from typing import Any, Callable

from ..reauth import ReauthService


def build_auth_tools(service: ReauthService) -> list[Callable[..., Any]]:
    """Return the ``bling_authorize*`` tool functions bound to ``service``."""

    def bling_authorize() -> dict[str, Any]:
        """Start re-authorizing this server with Bling and return the link to open.

        Use when Bling calls fail with an expired or revoked refresh token (it
        lapses after 30 days without a refresh) or when the user asks to
        reconnect Bling. Show the returned ``authorize_url`` to the user as a
        clickable link. After approval Bling redirects to the local callback
        and the new tokens are installed and persisted automatically; follow
        the ``instructions`` field and confirm with ``bling_auth_status``.
        """
        return service.begin()

    def bling_auth_status() -> dict[str, str]:
        """Report the state of the current Bling re-authorization.

        ``pending`` while waiting for the user to approve in the browser,
        ``completed`` once the new tokens are installed, ``failed`` or
        ``expired`` when a new ``bling_authorize`` is needed, ``none`` when no
        re-authorization has been started in this server process.
        """
        return service.status()

    def bling_authorize_with_code(code: str) -> dict[str, str]:
        """Finish re-authorization manually with the ``code`` from the redirect URL.

        Fallback for when the local callback could not receive Bling's
        redirect: the user opens the ``authorize_url``, approves, and copies
        the ``code`` query parameter from the address bar of the resulting
        page. The code is exchanged for tokens, which are installed and
        persisted immediately.
        """
        return service.complete_with_code(code)

    return [bling_authorize, bling_auth_status, bling_authorize_with_code]
