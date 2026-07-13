"""Smoke tests: the server registers exactly the expected tool surface."""

from bling_mcp.server import create_server
from bling_mcp.tools import BlingTools

EXPECTED_TOOLS = {
    "bling_list_accounts",
    "bling_list_pedidos_vendas",
    "bling_get_pedido_venda",
    "bling_list_produtos",
    "bling_get_produto",
    "bling_list_contatos",
    "bling_get_contato",
    "bling_list_contas_pagar",
    "bling_list_contas_receber",
    "bling_list_nfe",
    "bling_get_nfe",
    "bling_list_estoque_saldos",
    "bling_list_categorias_produtos",
    "bling_list_formas_pagamento",
    "bling_list_depositos",
    "bling_list_vendedores",
}


class FakeClient:
    def get(self, path, params=None):
        return {}


def _server():
    return create_server(BlingTools(FakeClient(), account_label="default"))


def test_server_registers_exactly_the_expected_tools():
    names = {t.name for t in _server()._tool_manager.list_tools()}
    assert names == EXPECTED_TOOLS


def test_server_exposes_sixteen_bling_prefixed_tools():
    names = [t.name for t in _server()._tool_manager.list_tools()]
    assert len(names) == 16
    assert all(n.startswith("bling_") for n in names)


def test_each_tool_has_a_description():
    for tool in _server()._tool_manager.list_tools():
        assert tool.description, f"{tool.name} is missing a description"
