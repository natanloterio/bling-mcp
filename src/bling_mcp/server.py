"""FastMCP server wiring for the Bling MCP.

Composition root: config -> TokenManager -> BlingClient -> declarative endpoint
registry -> one MCP tool per endpoint (via the factory). Run over stdio via the
``bling-mcp`` console script or ``python -m bling_mcp``.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from .auth import TokenManager
from .client import BlingClient
from .config import BlingConfig, load_config
from .token_store import JsonFileTokenStore, default_store_path
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


def build_tools(config: BlingConfig) -> BlingClient:
    """Assemble the HTTP client (no network call until a tool runs)."""
    http = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    tokens = TokenManager(config, http, store=build_token_store(config))
    return BlingClient(config, tokens, http)


def enabled_endpoints(config: BlingConfig):
    """Return the endpoints to register, honoring the ``BLING_MODULES`` filter."""
    modules = getattr(config, "modules", None)
    if not modules:
        return ALL_ENDPOINTS
    return tuple(
        endpoint for name in modules for endpoint in MODULES.get(name, ())
    )


def register_tools(mcp: FastMCP, client: BlingClient, config: BlingConfig) -> None:
    """Register the meta tool plus one ``bling_``-prefixed tool per endpoint."""
    label = getattr(config, "account_label", "default")

    def list_accounts() -> list[dict]:
        """List the Bling account configured for this server install."""
        return [{"id": label, "label": label}]

    list_accounts.__name__ = "bling_list_accounts"
    mcp.add_tool(list_accounts, name="bling_list_accounts")

    for endpoint in enabled_endpoints(config):
        mcp.add_tool(build_tool(endpoint, client), name=f"bling_{endpoint.name}")


def create_server(
    client: BlingClient, config: BlingConfig, name: str = "bling"
) -> FastMCP:
    """Build a FastMCP server with all enabled Bling tools registered."""
    mcp = FastMCP(name)
    register_tools(mcp, client, config)
    return mcp


def main() -> None:
    """Console entry point: load config from env and serve over stdio."""
    config = load_config(os.environ)
    server = create_server(build_tools(config), config)
    server.run()


if __name__ == "__main__":
    main()
