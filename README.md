# bling-mcp

An MCP (Model Context Protocol) server for **[Bling ERP](https://www.bling.com.br)**
(bling.com.br) — a Brazilian SMB / e-commerce management platform by Locaweb.

It exposes Bling's **v3 REST API** as MCP tools over **OAuth 2.0**, so an MCP client
(Claude, etc.) can read sales orders, products, contacts, financials, NF-e invoices
and stock balances.

> Status: **read-only** (GET endpoints). Write operations are intentionally out of
> scope for the initial version.

## Tools

16 read-only tools mapped to Bling v3 endpoints:

| Tool | Endpoint |
|------|----------|
| `bling_list_accounts` | (local) connected accounts |
| `bling_list_pedidos_vendas` / `bling_get_pedido_venda` | `/pedidos/vendas` |
| `bling_list_produtos` / `bling_get_produto` | `/produtos` |
| `bling_list_contatos` / `bling_get_contato` | `/contatos` |
| `bling_list_contas_pagar` | `/contas/pagar` |
| `bling_list_contas_receber` | `/contas/receber` |
| `bling_list_nfe` / `bling_get_nfe` | `/nfe` |
| `bling_list_estoque_saldos` | `/estoques/saldos` |
| `bling_list_categorias_produtos` | `/categorias/produtos` |
| `bling_list_formas_pagamento` | `/formas-pagamentos` |
| `bling_list_depositos` | `/depositos` |
| `bling_list_vendedores` | `/vendedores` |

## Install

**Windows (one click):** double-click `setup-windows.bat` (or run
`powershell -ExecutionPolicy Bypass -File setup-windows.ps1`). It installs uv,
creates the venv, installs the server, can bootstrap your OAuth refresh token,
registers the server with Claude Desktop, and smoke-tests it. See
[INSTALL.md](INSTALL.md) for manual steps and macOS/Linux.

## Configuration

Credentials are OAuth 2.0 from your Bling app
(see https://www.bling.com.br/cadastro.api.php). The server auto-refreshes the
short-lived access token from your refresh token. To obtain the first refresh
token: `python -m bling_mcp.authorize url --client-id <ID>` then
`python -m bling_mcp.authorize exchange --code <CODE> --refresh-only`.

## Development

```bash
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/python -m pytest          # run tests
```

Built test-first (TDD). See `PROGRESS.md` for the build log.

## License

MIT
