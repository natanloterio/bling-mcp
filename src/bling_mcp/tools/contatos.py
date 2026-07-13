"""Contact endpoints for the Bling v3 API."""

from .spec import Endpoint, Param

ENDPOINTS = (
    # --- contatos ------------------------------------------------------------
    Endpoint(
        name="list_contatos",
        method="GET",
        path="contatos",
        description="List contacts (customers/suppliers).",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("pesquisa", str),
            Param("criterio", str),
            Param("dataInclusaoInicial", str),
            Param("dataInclusaoFinal", str),
            Param("dataAlteracaoInicial", str),
            Param("dataAlteracaoFinal", str),
            Param("idTipoContato", int),
            Param("idVendedor", int),
            Param("uf", str),
            Param("telefone", str),
            Param("idsContatos", list),
            Param("numeroDocumento", str),
        ),
    ),
    Endpoint(
        name="get_contato",
        method="GET",
        path="contatos/{idContato}",
        description="Get a contact by id.",
        path_params=(Param("idContato", int),),
    ),
    Endpoint(
        name="find_types_contato",
        method="GET",
        path="contatos/{idContato}/tipos",
        description="Get the contact types assigned to a contact.",
        path_params=(Param("idContato", int),),
    ),
    Endpoint(
        name="find_final_customer",
        method="GET",
        path="contatos/consumidor-final",
        description="Get the final consumer contact record.",
    ),
    Endpoint(
        name="change_situation_contato",
        method="PATCH",
        path="contatos/{idContato}/situacoes",
        description="Change a contact's status.",
        path_params=(Param("idContato", int),),
        has_body=True,
    ),
    Endpoint(
        name="change_situation_many_contatos",
        method="POST",
        path="contatos/situacoes",
        description="Change the status of multiple contacts.",
        has_body=True,
    ),
    Endpoint(
        name="create_contato",
        method="POST",
        path="contatos",
        description="Create a contact.",
        has_body=True,
    ),
    Endpoint(
        name="update_contato",
        method="PUT",
        path="contatos/{idContato}",
        description="Update a contact.",
        path_params=(Param("idContato", int),),
        has_body=True,
    ),
    Endpoint(
        name="delete_contato",
        method="DELETE",
        path="contatos/{idContato}",
        description="Delete a contact.",
        path_params=(Param("idContato", int),),
    ),
    Endpoint(
        name="delete_many_contatos",
        method="DELETE",
        path="contatos",
        description="Delete multiple contacts.",
        query_params=(Param("idsContatos", list),),
    ),
    # --- contatosTipos ---------------------------------------------------------
    Endpoint(
        name="list_contato_tipos",
        method="GET",
        path="contatos/tipos",
        description="List contact types.",
    ),
)
