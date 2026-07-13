"""Bling read-only tool logic.

`BlingTools` holds one method per MCP tool. Methods are plain Python (no MCP
dependency) so they unit-test easily; ``server.py`` registers each as an MCP
tool. Optional filters default to ``None`` and are dropped by the client before
the request is sent.
"""

from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def get(self, path: str, params: dict | None = None) -> Any: ...


class BlingTools:
    """Read-only operations over the Bling v3 API."""

    def __init__(self, client: _Client, account_label: str = "default") -> None:
        self._client = client
        self._account_label = account_label

    # --- meta ------------------------------------------------------------------
    def list_accounts(self) -> list[dict]:
        """List the Bling account configured for this server install."""
        return [{"id": self._account_label, "label": self._account_label}]

    # --- pedidos de venda ------------------------------------------------------
    def list_pedidos_vendas(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        dataInicial: str | None = None,
        dataFinal: str | None = None,
        idContato: int | None = None,
        numero: str | None = None,
    ) -> Any:
        """List sales orders (GET /pedidos/vendas)."""
        return self._client.get(
            "pedidos/vendas",
            {
                "pagina": pagina,
                "limite": limite,
                "dataInicial": dataInicial,
                "dataFinal": dataFinal,
                "idContato": idContato,
                "numero": numero,
            },
        )

    def get_pedido_venda(self, id: int) -> Any:
        """Get a sales order by id (GET /pedidos/vendas/{id})."""
        return self._client.get(f"pedidos/vendas/{id}")

    # --- produtos --------------------------------------------------------------
    def list_produtos(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        nome: str | None = None,
        codigo: str | None = None,
        idCategoria: int | None = None,
        tipo: str | None = None,
        criterio: str | None = None,
    ) -> Any:
        """List products (GET /produtos)."""
        return self._client.get(
            "produtos",
            {
                "pagina": pagina,
                "limite": limite,
                "nome": nome,
                "codigo": codigo,
                "idCategoria": idCategoria,
                "tipo": tipo,
                "criterio": criterio,
            },
        )

    def get_produto(self, id: int) -> Any:
        """Get a product by id (GET /produtos/{id})."""
        return self._client.get(f"produtos/{id}")

    # --- contatos --------------------------------------------------------------
    def list_contatos(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        pesquisa: str | None = None,
        idTipoContato: int | None = None,
        numeroDocumento: str | None = None,
        idVendedor: int | None = None,
        uf: str | None = None,
    ) -> Any:
        """List contacts — customers/suppliers (GET /contatos)."""
        return self._client.get(
            "contatos",
            {
                "pagina": pagina,
                "limite": limite,
                "pesquisa": pesquisa,
                "idTipoContato": idTipoContato,
                "numeroDocumento": numeroDocumento,
                "idVendedor": idVendedor,
                "uf": uf,
            },
        )

    def get_contato(self, id: int) -> Any:
        """Get a contact by id (GET /contatos/{id})."""
        return self._client.get(f"contatos/{id}")

    # --- financeiro ------------------------------------------------------------
    def list_contas_pagar(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        dataEmissaoInicial: str | None = None,
        dataEmissaoFinal: str | None = None,
        dataVencimentoInicial: str | None = None,
        dataVencimentoFinal: str | None = None,
        situacao: str | None = None,
        idContato: int | None = None,
    ) -> Any:
        """List payables (GET /contas/pagar)."""
        return self._client.get(
            "contas/pagar",
            {
                "pagina": pagina,
                "limite": limite,
                "dataEmissaoInicial": dataEmissaoInicial,
                "dataEmissaoFinal": dataEmissaoFinal,
                "dataVencimentoInicial": dataVencimentoInicial,
                "dataVencimentoFinal": dataVencimentoFinal,
                "situacao": situacao,
                "idContato": idContato,
            },
        )

    def list_contas_receber(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        dataEmissaoInicial: str | None = None,
        dataEmissaoFinal: str | None = None,
        dataVencimentoInicial: str | None = None,
        dataVencimentoFinal: str | None = None,
        situacao: str | None = None,
        idContato: int | None = None,
    ) -> Any:
        """List receivables (GET /contas/receber)."""
        return self._client.get(
            "contas/receber",
            {
                "pagina": pagina,
                "limite": limite,
                "dataEmissaoInicial": dataEmissaoInicial,
                "dataEmissaoFinal": dataEmissaoFinal,
                "dataVencimentoInicial": dataVencimentoInicial,
                "dataVencimentoFinal": dataVencimentoFinal,
                "situacao": situacao,
                "idContato": idContato,
            },
        )

    def list_formas_pagamento(
        self, pagina: int | None = None, limite: int | None = None
    ) -> Any:
        """List payment methods (GET /formas-pagamentos)."""
        return self._client.get(
            "formas-pagamentos", {"pagina": pagina, "limite": limite}
        )

    # --- notas fiscais ---------------------------------------------------------
    def list_nfe(
        self,
        pagina: int | None = None,
        limite: int | None = None,
        dataEmissaoInicial: str | None = None,
        dataEmissaoFinal: str | None = None,
        situacao: int | None = None,
        tipo: int | None = None,
        numeroLoja: str | None = None,
    ) -> Any:
        """List electronic invoices / NF-e (GET /nfe)."""
        return self._client.get(
            "nfe",
            {
                "pagina": pagina,
                "limite": limite,
                "dataEmissaoInicial": dataEmissaoInicial,
                "dataEmissaoFinal": dataEmissaoFinal,
                "situacao": situacao,
                "tipo": tipo,
                "numeroLoja": numeroLoja,
            },
        )

    def get_nfe(self, id: int) -> Any:
        """Get an NF-e by id (GET /nfe/{id})."""
        return self._client.get(f"nfe/{id}")

    # --- estoque ---------------------------------------------------------------
    def list_estoque_saldos(
        self,
        idsProdutos: list[int] | None = None,
        codigos: list[str] | None = None,
    ) -> Any:
        """List stock balances per product (GET /estoques/saldos)."""
        return self._client.get(
            "estoques/saldos",
            {"idsProdutos": idsProdutos, "codigos": codigos},
        )

    def list_depositos(
        self, pagina: int | None = None, limite: int | None = None
    ) -> Any:
        """List warehouses/deposits (GET /depositos)."""
        return self._client.get("depositos", {"pagina": pagina, "limite": limite})

    # --- cadastros -------------------------------------------------------------
    def list_categorias_produtos(
        self, pagina: int | None = None, limite: int | None = None
    ) -> Any:
        """List product categories (GET /categorias/produtos)."""
        return self._client.get(
            "categorias/produtos", {"pagina": pagina, "limite": limite}
        )

    def list_vendedores(
        self, pagina: int | None = None, limite: int | None = None
    ) -> Any:
        """List salespeople (GET /vendedores)."""
        return self._client.get("vendedores", {"pagina": pagina, "limite": limite})
