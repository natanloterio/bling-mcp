"""FastMCP server wiring for the Bling MCP.

Composition root: config -> TokenManager -> BlingClient -> declarative endpoint
registry -> one MCP tool per endpoint (via the factory), plus the
re-authorization tools over a ReauthService that shares the same TokenManager.
Run over stdio via the ``bling-mcp`` console script or ``python -m bling_mcp``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from .auth import TokenManager
from .client import BlingClient
from .config import BlingConfig, load_config
from .reauth import ReauthService
from .token_store import JsonFileTokenStore, default_store_path
from .tools.auth_tools import build_auth_tools
from .tools.factory import build_tool
from .tools.registry import ALL_ENDPOINTS, MODULES

DEFAULT_TIMEOUT_SECONDS = 30.0


def build_token_store(config: BlingConfig) -> JsonFileTokenStore:
    """Resolve the token store: the configured path, else the platform default."""
    path = (
        Path(config.token_store_path)
        if config.token_store_path
        else default_store_path()
    )
    return JsonFileTokenStore(path)


@dataclass(frozen=True)
class Runtime:
    """Everything the server needs at run time, sharing one TokenManager."""

    client: BlingClient
    reauth: ReauthService


def build_runtime(config: BlingConfig) -> Runtime:
    """Assemble client and re-auth service (no network call until a tool runs)."""
    http = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    tokens = TokenManager(config, http, store=build_token_store(config))
    return Runtime(
        client=BlingClient(config, tokens, http),
        reauth=ReauthService(config, http, tokens),
    )


def build_tools(config: BlingConfig) -> BlingClient:
    """Assemble the HTTP client only (kept for callers that need no re-auth)."""
    return build_runtime(config).client


def enabled_endpoints(config: BlingConfig):
    """Return the endpoints to register, honoring the ``BLING_MODULES`` filter."""
    modules = getattr(config, "modules", None)
    if not modules:
        return ALL_ENDPOINTS
    return tuple(
        endpoint for name in modules for endpoint in MODULES.get(name, ())
    )


def register_tools(
    mcp: FastMCP,
    client: BlingClient,
    config: BlingConfig,
    reauth: ReauthService | None = None,
) -> None:
    """Register the meta tool, one tool per endpoint and, given a service, the re-auth tools."""
    label = getattr(config, "account_label", "default")

    def list_accounts() -> list[dict]:
        """List the Bling account configured for this server install."""
        return [{"id": label, "label": label}]

    list_accounts.__name__ = "bling_list_accounts"
    mcp.add_tool(list_accounts, name="bling_list_accounts")

    for endpoint in enabled_endpoints(config):
        mcp.add_tool(build_tool(endpoint, client), name=f"bling_{endpoint.name}")

    if reauth is not None:
        for tool in build_auth_tools(reauth):
            mcp.add_tool(tool, name=tool.__name__)


def create_server(
    client: BlingClient,
    config: BlingConfig,
    reauth: ReauthService | None = None,
    name: str = "bling",
) -> FastMCP:
    """Build a FastMCP server with all enabled Bling tools registered."""
    mcp = FastMCP(name)
    register_tools(mcp, client, config, reauth)
    return mcp


def main() -> None:
    """Console entry point: load config from env and serve over stdio."""
    config = load_config(os.environ)
    runtime = build_runtime(config)
    server = create_server(runtime.client, config, runtime.reauth)
    try:
        server.run()
    finally:
        runtime.reauth.close()


if __name__ == "__main__":
    main()
