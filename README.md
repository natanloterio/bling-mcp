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

**221 tools** — one meta tool (`bling_list_accounts`), three re-authorization tools
(`bling_authorize`, `bling_auth_status`, `bling_authorize_with_code`, see
[Re-authorizing from the chat](#re-authorizing-from-the-chat)) plus **217 tools mapped
1:1 to Bling v3 endpoints**, generated from a declarative endpoint registry. Naming follows
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
| **Total** | **217** | + `bling_list_accounts` + 3 re-auth tools (local) = **221** |

### Limiting the tool surface

221 tools can exceed some MCP clients' practical limits. Set `BLING_MODULES` (comma-separated
domain names from the table above) to expose only the domains you need — omit it to expose
everything. The meta and re-authorization tools are always registered:

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

### Re-authorizing from the chat

Bling's refresh token expires after **30 days without a refresh**. When that
happens every call fails with an `AuthError` that tells the agent to call
`bling_authorize`. No config editing or restart is needed:

1. The agent calls `bling_authorize` and shows you the returned link.
2. You open it, approve in Bling, and Bling redirects your browser to
   `http://localhost:8765/callback` (port from `BLING_OAUTH_CALLBACK_PORT`).
3. The server, listening on that loopback port, exchanges the code, installs
   the new tokens in memory and persists them to the token cache. The tab shows
   "Bling autorizado com sucesso".
4. The agent confirms with `bling_auth_status` and carries on.

**One-time setup:** register `http://localhost:8765/callback` as the app's
*link de redirecionamento* at https://www.bling.com.br/cadastro.api.php. Bling
only redirects to the registered URL.

**Fallback:** if the redirect page cannot load (listener could not bind, remote
MCP host, different machine), copy the `code` parameter from the address bar
and give it to the agent, which calls `bling_authorize_with_code`. The link is
valid for 5 minutes; the callback validates an unguessable `state` and only
binds to `127.0.0.1`.

## Development

```bash
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/python -m pytest          # run tests
```

Built test-first (TDD). See `PROGRESS.md` for the build log.

## License

MIT
