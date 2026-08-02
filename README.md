# bling-mcp

An MCP (Model Context Protocol) server for **[Bling ERP](https://www.bling.com.br)**
(bling.com.br) — a Brazilian SMB / e-commerce management platform by Locaweb.

It exposes Bling's **v3 REST API** as MCP tools over **OAuth 2.0**, so an MCP client
(Claude, etc.) can manage sales orders, products, contacts, financials, NF-e/NFC-e/NFS-e
invoices, stock, logistics, production and more.

> ⚠️ **Writes are enabled.** This server exposes the full CRUD surface — including
> `POST`/`PUT`/`PATCH`/`DELETE`. A single tool call from the LLM can **create, change
> or permanently delete** real data in your Bling account. Use a restricted OAuth app
> and/or the `BLING_MODULES` filter (below) to limit exposure.

## Tools

**218 tools** — one meta tool (`bling_list_accounts`) plus **217 tools mapped 1:1 to
Bling v3 endpoints**, generated from a declarative endpoint registry. Naming follows
`bling_<verb>_<resource>` (`list`/`get`/`create`/`update`/`delete`, plus special
actions like `change_situation_*`, `generate_nfe_*`, `post_stock_*`, `reverse_accounts_*`).

| Domain (module) | Tools | Covers |
|------|------:|--------|
| `produtos` | 38 | produtos, estruturas, fornecedores, lojas, variações, grupos, categorias |
| `pedidos` | 31 | pedidos de venda, pedidos de compra, propostas comerciais |
| `contatos` | 11 | contatos, tipos de contato |
| `financeiro` | 25 | contas a pagar/receber, formas de pagamento, contas contábeis, categorias receita/despesa, borderôs |
| `fiscal` | 31 | NF-e, NFC-e, NFS-e, naturezas de operação |
| `estoque` | 8 | estoques/saldos, depósitos |
| `logistica` | 20 | logísticas, etiquetas, objetos, remessas, serviços |
| `producao` | 7 | ordens de produção |
| `situacoes` | 12 | situações, módulos, transições |
| `cadastros` | 34 | categorias de lojas, canais de venda, vendedores, empresas, usuários, campos customizados, contratos, notificações, homologação |
| **Total** | **217** | + `bling_list_accounts` (local) = **218** |

### Limiting the tool surface

218 tools can exceed some MCP clients' practical limits. Set `BLING_MODULES` (comma-separated
domain names from the table above) to expose only the domains you need — omit it to expose
everything:

```
BLING_MODULES=produtos,pedidos,estoque
```

> Note: `homologacao` endpoints require Bling's `x-bling-homologacao` header (used only
> for API-certification sandboxing) which this server does not send; treat them as best-effort.

## Install

**Windows (one click):** double-click `setup-windows.bat` (or run
`powershell -ExecutionPolicy Bypass -File setup-windows.ps1`). It installs uv,
creates the venv, installs the server, can bootstrap your OAuth refresh token,
registers the server with Claude Desktop, and smoke-tests it. See
[INSTALL.md](INSTALL.md) for manual steps and macOS/Linux.

## Configuration

Credentials are OAuth 2.0 from your Bling app
(see https://www.bling.com.br/cadastro.api.php). The server auto-refreshes the
short-lived access token from your refresh token, and persists the rotated
refresh token to a small JSON cache (default path is the OS state dir; override
with `BLING_TOKEN_STORE`) so restarts don't fall back to a stale seed — see
[INSTALL.md](INSTALL.md#where-the-token-is-cached) for the per-platform paths
and the residual 30-day idle limitation. To obtain the first refresh
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
