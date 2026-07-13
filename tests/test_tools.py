"""Tests for the Bling tool layer (pure logic over a fake client)."""

import pytest

from bling_mcp.tools import BlingTools


class FakeClient:
    def __init__(self, result=None):
        self.calls = []
        self._result = result if result is not None else {"ok": True}

    def get(self, path, params=None):
        self.calls.append((path, params or {}))
        return self._result


@pytest.fixture
def tools():
    return BlingTools(FakeClient(), account_label="loja-x")


# --- list endpoints: method -> expected path -----------------------------------
LIST_CASES = [
    ("list_pedidos_vendas", "pedidos/vendas"),
    ("list_produtos", "produtos"),
    ("list_contatos", "contatos"),
    ("list_contas_pagar", "contas/pagar"),
    ("list_contas_receber", "contas/receber"),
    ("list_nfe", "nfe"),
    ("list_categorias_produtos", "categorias/produtos"),
    ("list_formas_pagamento", "formas-pagamentos"),
    ("list_depositos", "depositos"),
    ("list_vendedores", "vendedores"),
]


@pytest.mark.parametrize("method,path", LIST_CASES)
def test_list_endpoints_hit_expected_path(tools, method, path):
    getattr(tools, method)()
    assert tools._client.calls[0][0] == path


def test_list_pedidos_vendas_forwards_filters(tools):
    tools.list_pedidos_vendas(pagina=2, limite=50, numero="123")
    path, params = tools._client.calls[0]
    assert path == "pedidos/vendas"
    assert params["pagina"] == 2
    assert params["limite"] == 50
    assert params["numero"] == "123"


def test_get_pedido_venda_interpolates_id(tools):
    tools.get_pedido_venda(987)
    assert tools._client.calls[0][0] == "pedidos/vendas/987"


def test_get_produto_interpolates_id(tools):
    tools.get_produto(42)
    assert tools._client.calls[0][0] == "produtos/42"


def test_get_contato_interpolates_id(tools):
    tools.get_contato(7)
    assert tools._client.calls[0][0] == "contatos/7"


def test_get_nfe_interpolates_id(tools):
    tools.get_nfe(5)
    assert tools._client.calls[0][0] == "nfe/5"


def test_list_estoque_saldos_passes_array_params(tools):
    tools.list_estoque_saldos(idsProdutos=[1, 2, 3])
    path, params = tools._client.calls[0]
    assert path == "estoques/saldos"
    assert params["idsProdutos"] == [1, 2, 3]


def test_list_accounts_returns_configured_label_without_calling_api():
    client = FakeClient()
    tools = BlingTools(client, account_label="loja-x")

    accounts = tools.list_accounts()

    assert client.calls == []  # local, no API call
    assert accounts == [{"id": "loja-x", "label": "loja-x"}]


def test_returns_api_payload(tools):
    tools._client._result = {"data": [{"id": 1}]}
    assert tools.list_produtos() == {"data": [{"id": 1}]}
