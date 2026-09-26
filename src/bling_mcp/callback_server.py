"""Loopback HTTP listener for Bling's OAuth redirect.

Bling sends the browser to the redirect URI registered on the app
(``http://localhost:<port>/callback``) with ``code`` and ``state``. This tiny
server, bound to 127.0.0.1 only, hands both to whichever
:class:`~bling_mcp.oauth_flow.AuthorizationFlow` is active and shows the user a
plain page saying whether it worked, so the whole re-authorization finishes in
the browser tab the chat link opened.

The active flow is looked up through ``flow_provider`` on every request, so the
server can stay up across attempts while each attempt owns its own ``state``.
"""

from __future__ import annotations

import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .auth import AuthError
from .oauth_flow import AuthorizationFlow, FlowError

CALLBACK_PATH = "/callback"
_BIND_HOST = "127.0.0.1"
DEFAULT_REDIRECT_HOST = "localhost"

FlowProvider = Callable[[], "AuthorizationFlow | None"]


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    """Bind the port exclusively.

    The stdlib default sets ``SO_REUSEADDR``, which on Windows lets a second
    process bind a port another one is already listening on. Two bling-mcp
    instances on the default port would then both "succeed" and split the
    redirects between them; failing to bind is what triggers the manual fallback.
    """

    allow_reuse_address = False


class CallbackServer:
    """Serves ``/callback`` on the loopback interface in a daemon thread."""

    def __init__(
        self,
        port: int,
        flow_provider: FlowProvider,
        redirect_host: str = DEFAULT_REDIRECT_HOST,
    ) -> None:
        self._requested_port = port
        self._flow_provider = flow_provider
        self._redirect_host = redirect_host
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def port(self) -> int:
        """The bound port (meaningful only after :meth:`start`)."""
        return self._httpd.server_address[1] if self._httpd else self._requested_port

    @property
    def redirect_uri(self) -> str:
        return f"http://{self._redirect_host}:{self.port}{CALLBACK_PATH}"

    def start(self) -> None:
        """Bind and serve in the background; a second call is a no-op."""
        if self._httpd is not None:
            return
        handler = _make_handler(self._flow_provider)
        self._httpd = _ExclusiveHTTPServer((_BIND_HOST, self._requested_port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="bling-oauth-callback", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Shut down and release the port; safe to call when not running."""
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None


def _make_handler(flow_provider: FlowProvider) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            try:
                self._route()
            except Exception as exc:  # noqa: BLE001 — never drop the connection
                print(f"[bling-mcp] oauth callback: {exc!r}", file=sys.stderr)
                self._page(HTTPStatus.INTERNAL_SERVER_ERROR, "Erro interno ao processar o retorno do Bling.")

        def _route(self) -> None:
            url = urlparse(self.path)
            if url.path != CALLBACK_PATH:
                self._page(HTTPStatus.NOT_FOUND, "Página não encontrada.")
                return
            flow = flow_provider()
            if flow is None:
                self._page(
                    HTTPStatus.NOT_FOUND,
                    "Nenhuma autorização em andamento. Peça ao agente para chamar bling_authorize.",
                )
                return
            status, message = _handle_callback(flow, parse_qs(url.query))
            self._page(status, message)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return  # stdio MCP servers must keep stderr quiet

        def _page(self, status: HTTPStatus, message: str) -> None:
            body = _render(status, message).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _handle_callback(flow: AuthorizationFlow, query: dict[str, list[str]]) -> tuple[HTTPStatus, str]:
    """Map the redirect's query string onto the flow; return what to show the user."""
    if "error" in query:
        return HTTPStatus.BAD_REQUEST, f"O Bling recusou a autorização: {query['error'][0]}"
    code = _first(query, "code")
    if not code:
        return HTTPStatus.BAD_REQUEST, "O redirecionamento do Bling veio sem o parâmetro code."
    try:
        flow.complete(code=code, state=_first(query, "state"))
    except FlowError as exc:
        return HTTPStatus.BAD_REQUEST, f"Autorização recusada: {exc}"
    except AuthError as exc:
        return HTTPStatus.BAD_GATEWAY, f"Falha ao trocar o código pelos tokens: {exc}"
    return HTTPStatus.OK, "Bling autorizado com sucesso. Pode fechar esta aba e voltar ao chat."


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    return values[0] if values else ""


def _render(status: HTTPStatus, message: str) -> str:
    title = "bling-mcp" if status == HTTPStatus.OK else f"bling-mcp — erro {status.value}"
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        f"<title>{title}</title></head>"
        "<body style='font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem'>"
        f"<h1 style='font-size:1.25rem'>{title}</h1><p>{_escape(message)}</p></body></html>"
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
