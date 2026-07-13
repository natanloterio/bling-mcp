"""Pedidos (vendas, compras, propostas) endpoints for the Bling v3 API.

Extracted from the community SDK `AlexandreBellas/bling-erp-api-js`, source
modules `pedidosVendas`, `pedidosCompras`, `propostasComerciais`
(`src/entities/<modulo>/index.ts`). Every public method there calls
`this.repository.<verb>({endpoint, id, params, body})`; the literal
`endpoint`/`id` strings are authoritative for path/verb, confirmed against the
`@see .../referencia#/<Modulo>/<operationId>` JSDoc on each method.

Special actions on pedidos de vendas/compras (`lancar-estoque`,
`lancar-estoque/{idDeposito}`, `estornar-estoque`, `lancar-contas`,
`estornar-contas`, `gerar-nfe`, `gerar-nfce`, `situacoes/{idSituacao}`) always
send a hardcoded empty body (`body: {}`) in the SDK, so they take no `body`
argument here (`has_body=False`) — only path params matter. The
`change-situation` action on pedidos de compras and propostas comerciais does
forward a real body (`{valor: ...}` / `{situacao: ...}`), so those keep
`has_body=True`.
"""

from .spec import Endpoint, Param

ENDPOINTS = (
    # --- pedidos de vendas (pedidosVendas) ---------------------------------
    Endpoint(
        "list_pedidos_vendas",
        "GET",
        "pedidos/vendas",
        "List sales orders",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("idContato", int),
            Param("idsSituacoes", list),
            Param("dataInicial", str),
            Param("dataFinal", str),
            Param("dataAlteracaoInicial", str),
            Param("dataAlteracaoFinal", str),
            Param("dataPrevistaInicial", str),
            Param("dataPrevistaFinal", str),
            Param("numero", int),
            Param("idLoja", int),
            Param("idVendedor", int),
            Param("idControleCaixa", int),
            Param("numerosLojas", list),
        ),
    ),
    Endpoint(
        "get_pedido_venda",
        "GET",
        "pedidos/vendas/{idPedidoVenda}",
        "Get a sales order by id",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "create_pedido_venda",
        "POST",
        "pedidos/vendas",
        "Create a sales order",
        has_body=True,
    ),
    Endpoint(
        "update_pedido_venda",
        "PUT",
        "pedidos/vendas/{idPedidoVenda}",
        "Replace a sales order",
        path_params=(Param("idPedidoVenda", int),),
        has_body=True,
    ),
    Endpoint(
        "delete_pedido_venda",
        "DELETE",
        "pedidos/vendas/{idPedidoVenda}",
        "Delete a sales order",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "delete_many_pedidos_vendas",
        "DELETE",
        "pedidos/vendas",
        "Delete multiple sales orders",
        query_params=(Param("idsPedidosVendas", list),),
    ),
    Endpoint(
        "change_situation_pedido_venda",
        "PATCH",
        "pedidos/vendas/{idPedidoVenda}/situacoes/{idSituacao}",
        "Change a sales order situation",
        path_params=(Param("idPedidoVenda", int), Param("idSituacao", int)),
    ),
    Endpoint(
        "post_stock_to_deposit_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/lancar-estoque/{idDeposito}",
        "Post a sales order's stock to a specific deposit",
        path_params=(Param("idPedidoVenda", int), Param("idDeposito", int)),
    ),
    Endpoint(
        "post_stock_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/lancar-estoque",
        "Post a sales order's stock to the default deposit",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "reverse_stock_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/estornar-estoque",
        "Reverse a sales order's stock posting",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "post_accounts_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/lancar-contas",
        "Post a sales order's accounts (accounts receivable)",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "reverse_accounts_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/estornar-contas",
        "Reverse a sales order's accounts posting",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "generate_nfe_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/gerar-nfe",
        "Generate an NF-e (invoice) from a sales order",
        path_params=(Param("idPedidoVenda", int),),
    ),
    Endpoint(
        "generate_nfce_pedido_venda",
        "POST",
        "pedidos/vendas/{idPedidoVenda}/gerar-nfce",
        "Generate an NFC-e (consumer invoice) from a sales order",
        path_params=(Param("idPedidoVenda", int),),
    ),
    # --- pedidos de compras (pedidosCompras) -------------------------------
    Endpoint(
        "list_pedidos_compras",
        "GET",
        "pedidos/compras",
        "List purchase orders",
        query_params=(
            Param("pagina", int),
            Param("limite", int),
            Param("idFornecedor", int),
            Param("valorSituacao", int),
            Param("idSituacao", int),
            Param("dataInicial", str),
            Param("dataFinal", str),
        ),
    ),
    Endpoint(
        "get_pedido_compra",
        "GET",
        "pedidos/compras/{idPedidoCompra}",
        "Get a purchase order by id",
        path_params=(Param("idPedidoCompra", int),),
    ),
    Endpoint(
        "create_pedido_compra",
        "POST",
        "pedidos/compras",
        "Create a purchase order",
        has_body=True,
    ),
    Endpoint(
        "update_pedido_compra",
        "PUT",
        "pedidos/compras/{idPedidoCompra}",
        "Replace a purchase order",
        path_params=(Param("idPedidoCompra", int),),
        has_body=True,
    ),
    Endpoint(
        "delete_pedido_compra",
        "DELETE",
        "pedidos/compras/{idPedidoCompra}",
        "Delete a purchase order",
        path_params=(Param("idPedidoCompra", int),),
    ),
    Endpoint(
        "change_situation_pedido_compra",
        "PATCH",
        "pedidos/compras/{idPedidoCompra}/situacoes",
        "Change a purchase order situation",
        path_params=(Param("idPedidoCompra", int),),
        has_body=True,
    ),
    Endpoint(
        "post_stock_pedido_compra",
        "POST",
        "pedidos/compras/{idPedidoCompra}/lancar-estoque",
        "Post a purchase order's stock",
        path_params=(Param("idPedidoCompra", int),),
    ),
    Endpoint(
        "reverse_stock_pedido_compra",
        "POST",
        "pedidos/compras/{idPedidoCompra}/estornar-estoque",
        "Reverse a purchase order's stock posting",
        path_params=(Param("idPedidoCompra", int),),
    ),
    Endpoint(
        "post_accounts_pedido_compra",
        "POST",
        "pedidos/compras/{idPedidoCompra}/lancar-contas",
        "Post a purchase order's accounts (accounts payable)",
        path_params=(Param("idPedidoCompra", int),),
    ),
    Endpoint(
        "reverse_accounts_pedido_compra",
        "POST",
        "pedidos/compras/{idPedidoCompra}/estornar-contas",
        "Reverse a purchase order's accounts posting",
        path_params=(Param("idPedidoCompra", int),),
    ),
    # --- propostas comerciais (propostasComerciais) ------------------------
    Endpoint(
        "list_propostas_comerciais",
        "GET",
        "propostas-comerciais",
        "List commercial proposals",
        query_params=(
            Param("situacao", str),
            Param("idContato", str),
            Param("dataInicial", str),
            Param("dataFinal", str),
            Param("pagina", int),
            Param("limite", int),
        ),
    ),
    Endpoint(
        "get_proposta_comercial",
        "GET",
        "propostas-comerciais/{idPropostaComercial}",
        "Get a commercial proposal by id",
        path_params=(Param("idPropostaComercial", int),),
    ),
    Endpoint(
        "create_proposta_comercial",
        "POST",
        "propostas-comerciais",
        "Create a commercial proposal",
        has_body=True,
    ),
    Endpoint(
        "update_proposta_comercial",
        "PUT",
        "propostas-comerciais/{idPropostaComercial}",
        "Replace a commercial proposal",
        path_params=(Param("idPropostaComercial", int),),
        has_body=True,
    ),
    Endpoint(
        "delete_proposta_comercial",
        "DELETE",
        "propostas-comerciais/{idPropostaComercial}",
        "Delete a commercial proposal",
        path_params=(Param("idPropostaComercial", int),),
    ),
    Endpoint(
        "delete_many_propostas_comerciais",
        "DELETE",
        "propostas-comerciais",
        "Delete multiple commercial proposals",
        query_params=(Param("idsPropostasComerciais", list),),
    ),
    Endpoint(
        "change_situation_proposta_comercial",
        "PATCH",
        "propostas-comerciais/{idPropostaComercial}/situacoes",
        "Change a commercial proposal situation",
        path_params=(Param("idPropostaComercial", int),),
        has_body=True,
    ),
)
