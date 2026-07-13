"""Tests for the declarative Endpoint/Param specs."""

import pytest

from bling_mcp.tools.spec import Endpoint, Param


def test_endpoint_reports_placeholders():
    e = Endpoint(
        name="get_produto",
        method="GET",
        path="produtos/{idProduto}",
        description="Get a product",
        path_params=(Param("idProduto", int),),
    )
    assert e.placeholders() == {"idProduto"}


def test_endpoint_is_frozen():
    e = Endpoint(name="list_produtos", method="GET", path="produtos", description="d")
    with pytest.raises(Exception):
        e.name = "x"  # type: ignore[misc]


def test_no_placeholders_when_none():
    e = Endpoint(name="list_produtos", method="GET", path="produtos", description="d")
    assert e.placeholders() == set()


def test_nested_path_placeholders():
    e = Endpoint(
        name="change_situation_produto",
        method="PATCH",
        path="produtos/{idProduto}/situacoes/{idSituacao}",
        description="d",
        path_params=(Param("idProduto", int), Param("idSituacao", int)),
    )
    assert e.placeholders() == {"idProduto", "idSituacao"}
