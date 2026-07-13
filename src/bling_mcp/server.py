"""FastMCP server wiring for the Bling MCP.

Composition root: config → TokenManager → BlingClient → BlingTools → MCP tools.
Run over stdio via the ``bling-mcp`` console script or ``python -m bling_mcp``.
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

from .auth import TokenManager
from .client import BlingClient
from .config import BlingConfig, load_config
from .tools import BlingTools

DEFAULT_TIMEOUT_SECONDS = 30.0


def build_tools(config: BlingConfig) -> BlingTools:
    """Assemble the tool layer from config (no network call until a tool runs)."""
    http = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    tokens = TokenManager(config, http)
    client = BlingClient(config, tokens, http)
    return BlingTools(client, config.account_label)


def register_tools(mcp: FastMCP, tools: BlingTools) -> None:
    """Register each BlingTools method as a ``bling_``-prefixed MCP tool."""
    mapping = {
        "bling_list_accounts": tools.list_accounts,
        "bling_list_pedidos_vendas": tools.list_pedidos_vendas,
        "bling_get_pedido_venda": tools.get_pedido_venda,
        "bling_list_produtos": tools.list_produtos,
        "bling_get_produto": tools.get_produto,
        "bling_list_contatos": tools.list_contatos,
        "bling_get_contato": tools.get_contato,
        "bling_list_contas_pagar": tools.list_contas_pagar,
        "bling_list_contas_receber": tools.list_contas_receber,
        "bling_list_nfe": tools.list_nfe,
        "bling_get_nfe": tools.get_nfe,
        "bling_list_estoque_saldos": tools.list_estoque_saldos,
        "bling_list_categorias_produtos": tools.list_categorias_produtos,
        "bling_list_formas_pagamento": tools.list_formas_pagamento,
        "bling_list_depositos": tools.list_depositos,
        "bling_list_vendedores": tools.list_vendedores,
    }
    for name, fn in mapping.items():
        mcp.add_tool(fn, name=name)


def create_server(tools: BlingTools, name: str = "bling") -> FastMCP:
    """Build a FastMCP server with all Bling tools registered."""
    mcp = FastMCP(name)
    register_tools(mcp, tools)
    return mcp


def main() -> None:
    """Console entry point: load config from env and serve over stdio."""
    config = load_config(os.environ)
    server = create_server(build_tools(config))
    server.run()


if __name__ == "__main__":
    main()
