"""Status/workflow endpoints for the Bling v3 API."""

from .spec import Endpoint, Param

ENDPOINTS = (
    # --- situacoes -------------------------------------------------------------
    Endpoint(
        name="get_situacao",
        method="GET",
        path="situacoes/{idSituacao}",
        description="Get a status by id.",
        path_params=(Param("idSituacao", int),),
    ),
    Endpoint(
        name="create_situacao",
        method="POST",
        path="situacoes",
        description="Create a status.",
        has_body=True,
    ),
    Endpoint(
        name="update_situacao",
        method="PUT",
        path="situacoes/{idSituacao}",
        description="Update a status.",
        path_params=(Param("idSituacao", int),),
        has_body=True,
    ),
    Endpoint(
        name="delete_situacao",
        method="DELETE",
        path="situacoes/{idSituacao}",
        description="Delete a status.",
        path_params=(Param("idSituacao", int),),
    ),
    # --- situacoesModulos --------------------------------------------------------
    Endpoint(
        name="get_modules",
        method="GET",
        path="situacoes/modulos",
        description="List system modules that support statuses.",
    ),
    Endpoint(
        name="get_module_situations",
        method="GET",
        path="situacoes/modulos/{idModuloSistema}",
        description="List statuses of a system module.",
        path_params=(Param("idModuloSistema", int),),
    ),
    Endpoint(
        name="get_module_actions",
        method="GET",
        path="situacoes/modulos/{idModuloSistema}/acoes",
        description="List actions of a system module.",
        path_params=(Param("idModuloSistema", int),),
    ),
    Endpoint(
        name="get_module_transitions",
        method="GET",
        path="situacoes/modulos/{idModuloSistema}/transicoes",
        description="List status transitions of a system module.",
        path_params=(Param("idModuloSistema", int),),
    ),
    # --- situacoesTransicoes -----------------------------------------------------
    Endpoint(
        name="get_transicao",
        method="GET",
        path="situacoes/transicoes/{idTransicao}",
        description="Get a status transition by id.",
        path_params=(Param("idTransicao", int),),
    ),
    Endpoint(
        name="create_transicao",
        method="POST",
        path="situacoes/transicoes",
        description="Create a status transition.",
        has_body=True,
    ),
    Endpoint(
        name="update_transicao",
        method="PUT",
        path="situacoes/transicoes/{idTransicao}",
        description="Update a status transition.",
        path_params=(Param("idTransicao", int),),
        has_body=True,
    ),
    Endpoint(
        name="delete_transicao",
        method="DELETE",
        path="situacoes/transicoes/{idTransicao}",
        description="Delete a status transition.",
        path_params=(Param("idTransicao", int),),
    ),
)
