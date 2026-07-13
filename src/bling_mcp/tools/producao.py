"""Producao (manufacturing) endpoints for the Bling v3 API.

Source SDK module: ``ordensDeProducao``.
"""
from .spec import Endpoint, Param

ENDPOINTS = (
    Endpoint(
        "delete_ordem_producao",
        "DELETE",
        "ordens-producao/{idOrdemProducao}",
        "Delete a production order",
        path_params=(Param("idOrdemProducao", int),),
    ),
    Endpoint(
        "list_ordens_producao",
        "GET",
        "ordens-producao",
        "List production orders",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("idsSituacoes", list),
        ),
    ),
    Endpoint(
        "get_ordem_producao",
        "GET",
        "ordens-producao/{idOrdemProducao}",
        "Get a production order",
        path_params=(Param("idOrdemProducao", int),),
    ),
    Endpoint(
        "create_ordem_producao",
        "POST",
        "ordens-producao",
        "Create a production order",
        has_body=True,
    ),
    Endpoint(
        "generate_over_demand_ordem_producao",
        "POST",
        "ordens-producao/gerar-sob-demanda",
        "Generate production orders over demand",
    ),
    Endpoint(
        "update_ordem_producao",
        "PUT",
        "ordens-producao/{idOrdemProducao}",
        "Update a production order",
        path_params=(Param("idOrdemProducao", int),),
        has_body=True,
    ),
    Endpoint(
        "change_situation_ordem_producao",
        "PATCH",
        "ordens-producao/{idOrdemProducao}/situacoes",
        "Change a production order situation",
        path_params=(Param("idOrdemProducao", int),),
        has_body=True,
    ),
)
