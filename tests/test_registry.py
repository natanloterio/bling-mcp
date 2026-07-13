"""Validation of the aggregated endpoint catalog.

These tests are the safety net for the ~217 hand-declared endpoint specs: a
typo in a path, a missing path param, or a duplicate tool name fails here.
"""

from itertools import chain

from bling_mcp.tools.registry import ALL_ENDPOINTS, MODULES


def test_unique_tool_names():
    names = [e.name for e in ALL_ENDPOINTS]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate tool names: {dupes}"


def test_valid_http_methods():
    for e in ALL_ENDPOINTS:
        assert e.method in {"GET", "POST", "PUT", "PATCH", "DELETE"}, e.name


def test_path_placeholders_match_path_params():
    for e in ALL_ENDPOINTS:
        declared = {p.name for p in e.path_params}
        assert e.placeholders() == declared, (
            f"{e.name}: placeholders {e.placeholders()} != path_params {declared}"
        )


def test_read_methods_have_no_body():
    for e in ALL_ENDPOINTS:
        if e.method in {"GET", "DELETE"}:
            assert e.has_body is False, e.name


def test_names_are_snake_case_identifiers():
    for e in ALL_ENDPOINTS:
        assert e.name.isidentifier() and e.name.islower(), e.name


def test_modules_union_equals_all():
    union = tuple(chain.from_iterable(MODULES.values()))
    assert len(union) == len(ALL_ENDPOINTS)


def test_expected_scale():
    assert len(ALL_ENDPOINTS) >= 200, len(ALL_ENDPOINTS)


def test_legacy_tool_names_preserved():
    names = {e.name for e in ALL_ENDPOINTS}
    legacy = {
        "list_pedidos_vendas",
        "get_pedido_venda",
        "list_produtos",
        "get_produto",
        "list_contatos",
        "get_contato",
        "list_contas_pagar",
        "list_contas_receber",
        "list_nfe",
        "get_nfe",
        "list_estoque_saldos",
        "list_categorias_produtos",
        "list_formas_pagamento",
        "list_depositos",
        "list_vendedores",
    }
    missing = sorted(legacy - names)
    assert not missing, f"legacy tool names dropped: {missing}"
