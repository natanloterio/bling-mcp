"""Estoque (stock) endpoints for the Bling v3 API.

Source SDK modules: ``estoques``, ``depositos``.
"""
from .spec import Endpoint, Param

ENDPOINTS = (
    # --- estoques ------------------------------------------------------
    Endpoint(
        "find_balance_estoque",
        "GET",
        "estoques/saldos/{idDeposito}",
        "Get stock balance of products in a specific warehouse",
        path_params=(Param("idDeposito", int),),
        query_params=(Param("idsProdutos", list), Param("codigos", list)),
    ),
    Endpoint(
        "list_estoque_saldos",
        "GET",
        "estoques/saldos",
        "List stock balances per product (GET /estoques/saldos)",
        query_params=(Param("idsProdutos", list), Param("codigos", list)),
    ),
    Endpoint(
        "create_estoque",
        "POST",
        "estoques",
        "Create a stock movement",
        has_body=True,
    ),
    Endpoint(
        "update_estoque",
        "PUT",
        "estoques/{idEstoque}",
        "Update a stock movement",
        path_params=(Param("idEstoque", int),),
        has_body=True,
    ),
    # --- depositos -------------------------------------------------------------
    Endpoint(
        "list_depositos",
        "GET",
        "depositos",
        "List warehouses/deposits (GET /depositos)",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("descricao", str),
            Param("situacao", int),
        ),
    ),
    Endpoint(
        "get_deposito",
        "GET",
        "depositos/{idDeposito}",
        "Get a warehouse/deposit",
        path_params=(Param("idDeposito", int),),
    ),
    Endpoint(
        "create_deposito",
        "POST",
        "depositos",
        "Create a warehouse/deposit",
        has_body=True,
    ),
    Endpoint(
        "update_deposito",
        "PUT",
        "depositos/{idDeposito}",
        "Update a warehouse/deposit",
        path_params=(Param("idDeposito", int),),
        has_body=True,
    ),
)
