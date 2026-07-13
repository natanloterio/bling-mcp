"""Logistica (shipping/logistics) endpoints for the Bling v3 API.

Source SDK modules: ``logisticas``, ``logisticasEtiquetas``, ``logisticasObjetos``,
``logisticasRemessas``, ``logisticasServicos``.
"""
from .spec import Endpoint, Param

ENDPOINTS = (
    # --- logisticas ------------------------------------------------------------
    Endpoint(
        "delete_logistica",
        "DELETE",
        "logisticas/{idLogistica}",
        "Delete a logistic",
        path_params=(Param("idLogistica", int),),
    ),
    Endpoint(
        "list_logisticas",
        "GET",
        "logisticas",
        "List logistics",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("tipoIntegracao", str),
            Param("situacao", int),
        ),
    ),
    Endpoint(
        "get_logistica",
        "GET",
        "logisticas/{idLogistica}",
        "Get a logistic",
        path_params=(Param("idLogistica", int),),
    ),
    Endpoint(
        "create_logistica",
        "POST",
        "logisticas",
        "Create a logistic",
        has_body=True,
    ),
    Endpoint(
        "update_logistica",
        "PUT",
        "logisticas/{idLogistica}",
        "Update a logistic",
        path_params=(Param("idLogistica", int),),
        has_body=True,
    ),
    # --- logisticasEtiquetas -----------------------------------------------------
    Endpoint(
        "list_logistica_etiquetas",
        "GET",
        "logisticas/etiquetas",
        "List shipping labels for sales orders",
        query_params=(Param("formato", str), Param("idsVendas", list)),
    ),
    # --- logisticasObjetos -------------------------------------------------------
    Endpoint(
        "delete_logistica_objeto",
        "DELETE",
        "logisticas/objetos/{idObjeto}",
        "Delete a custom logistic object",
        path_params=(Param("idObjeto", int),),
    ),
    Endpoint(
        "get_logistica_objeto",
        "GET",
        "logisticas/objetos/{idObjeto}",
        "Get a logistic object",
        path_params=(Param("idObjeto", int),),
    ),
    Endpoint(
        "create_logistica_objeto",
        "POST",
        "logisticas/objetos",
        "Create a logistic object",
        has_body=True,
    ),
    Endpoint(
        "update_logistica_objeto",
        "PUT",
        "logisticas/objetos/{idObjeto}",
        "Update a logistic object",
        path_params=(Param("idObjeto", int),),
        has_body=True,
    ),
    # --- logisticasRemessas ------------------------------------------------------
    Endpoint(
        "delete_logistica_remessa",
        "DELETE",
        "logisticas/remessas/{idRemessa}",
        "Delete a shipping dispatch",
        path_params=(Param("idRemessa", int),),
    ),
    Endpoint(
        "get_logistica_remessa",
        "GET",
        "logisticas/remessas/{idRemessa}",
        "Get a shipping dispatch",
        path_params=(Param("idRemessa", int),),
    ),
    Endpoint(
        "get_by_logistic_remessa",
        "GET",
        "logisticas/{idLogistica}/remessas",
        "Get shipping dispatches for a logistic",
        path_params=(Param("idLogistica", int),),
    ),
    Endpoint(
        "create_logistica_remessa",
        "POST",
        "logisticas/remessas",
        "Create a shipping dispatch",
        has_body=True,
    ),
    Endpoint(
        "update_logistica_remessa",
        "PUT",
        "logisticas/remessas/{idRemessa}",
        "Update a shipping dispatch",
        path_params=(Param("idRemessa", int),),
        has_body=True,
    ),
    # --- logisticasServicos ------------------------------------------------------
    Endpoint(
        "list_logistica_servicos",
        "GET",
        "logisticas/servicos",
        "List logistic services",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("tipoIntegracao", str),
        ),
    ),
    Endpoint(
        "get_logistica_servico",
        "GET",
        "logisticas/servicos/{idLogisticaServico}",
        "Get a logistic service",
        path_params=(Param("idLogisticaServico", int),),
    ),
    Endpoint(
        "change_situation_logistica_servico",
        "PATCH",
        "logisticas/{idLogisticaServico}/situacoes",
        "Enable or disable a logistic service",
        path_params=(Param("idLogisticaServico", int),),
        has_body=True,
    ),
    Endpoint(
        "create_logistica_servico",
        "POST",
        "logisticas/servicos",
        "Create a logistic service",
        has_body=True,
    ),
    Endpoint(
        "update_logistica_servico",
        "PUT",
        "logisticas/servicos/{idLogisticaServico}",
        "Update a logistic service",
        path_params=(Param("idLogisticaServico", int),),
        has_body=True,
    ),
)
