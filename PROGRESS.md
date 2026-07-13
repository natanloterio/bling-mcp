# Build Progress — bling-mcp

Autonomous build log (self-paced `/loop`). Each iteration makes incremental
design → implement → test progress until the MCP is functional, then stops.

## Design (reconstructed from Bling v3 public API + reference catalog)

- **Stack:** Python ≥3.10, FastMCP (`mcp` SDK), `httpx` (sync), `pytest`.
- **Auth:** OAuth 2.0 authorization-code flow; server stores a refresh token and
  auto-refreshes the ~6h access token. Token endpoint:
  `POST https://api.bling.com.br/Api/v3/oauth/token`.
- **API base:** `https://api.bling.com.br/Api/v3`.
- **Scope:** 16 read-only (GET) tools — see README table.
- **Layout (many small files, immutable data):**
  - `config.py` — env loading + validation (frozen dataclass)
  - `auth.py` — OAuth2 `TokenManager` (refresh, expiry, injectable client/clock)
  - `client.py` — `BlingClient`: GET wrapper, auth header, error handling, pagination
  - `tools/` — tool modules by domain (pedidos, produtos, contatos, financeiro, nfe, estoque, cadastros)
  - `server.py` — FastMCP server + `main()` entry point

## Iteration log

### Iteration 1 — scaffold + config ✅ (11 tests green)
- [x] Research existing impls (`mcp-dir/bling-mcp`, `talissonf/bling-erp-sdk`) + reconstruct 16-tool catalog
- [x] Scaffold project (pyproject, src layout, venv, deps install OK)
- [x] `config.py` — TDD: load/validate env → `BlingConfig` (frozen, immutable)
- [x] Confirmed OAuth endpoints (key finding below); added decoupled `token_url` to config via TDD

**Key finding — OAuth dual host:**
- Token endpoint: `POST https://www.bling.com.br/Api/v3/oauth/token` (host: `www.bling.com.br`)
- Data API base: `https://api.bling.com.br/Api/v3` (host: `api.bling.com.br`)
- Token request: header `Authorization: Basic base64(client_id:client_secret)`,
  body `application/x-www-form-urlencoded` `grant_type=refresh_token&refresh_token=...`
- Response: `{access_token, expires_in (~21600s/6h), refresh_token, token_type, scope}`
  — refresh_token may rotate, so `TokenManager` must keep its own current refresh token.

### Iteration 2 — auth + client ✅ (22 tests green, 94% coverage)
- [x] `auth.py` — TDD: `TokenManager` (inject httpx.Client + clock; cache, expiry margin, refresh-token rotation, `AuthError` on non-2xx) — 95%
- [x] `client.py` — TDD: `BlingClient.get()` (Bearer header from TokenManager, URL join, None-param dropping, `BlingApiError` with status_code) — 89%
- Deferred (noted): 401 → force-refresh-and-retry-once. Low risk since TokenManager refreshes proactively with a 60s margin; revisit after server is runnable.

### Iteration 3 — tools + runnable server ✅ (43 tests green, 89% coverage)
- [x] `tools.py` — TDD: `BlingTools`, 16 read-only methods → GET endpoints (100% cov)
- [x] `server.py` — FastMCP: `build_tools` → `create_server` → `register_tools` + `main()`; `__main__.py`
- [x] Smoke test: server registers exactly 16 `bling_`-prefixed tools (unit)
- [x] **End-to-end stdio smoke**: real MCP `initialize` + `tools/list` handshake returns all 16 tools — server is runnable
- [x] `INSTALL.md` incl. verified **Windows** steps (venv-python command, `env` block, OAuth bootstrap)
- [x] Coverage 89% overall (≥80% target met)

**STATUS: functional.** Server runs over stdio, exposes 16 read-only tools, suite green.

### Iteration 4 — OAuth helper + Windows one-click setup ✅ (53 tests green, 91% coverage)
- [x] `authorize.py` — TDD: `build_authorize_url` + `exchange_code` (one-time refresh-token bootstrap) + CLI `main` (`python -m bling_mcp.authorize url|exchange`) — 94%
- [x] `setup-windows.ps1` — installs uv → venv → package, optional OAuth token bootstrap, **merges** into Claude Desktop config (with .bak backup), runs stdio smoke test. PS 5.1 compatible.
- [x] `setup-windows.bat` — double-click launcher (ExecutionPolicy Bypass)
- [x] Verified the script's Python dependencies on Linux: `authorize url` CLI + the embedded stdio smoke (prints 16). PowerShell itself unrunnable here (no pwsh) — written to PS 5.1 spec and reviewed.

### Iteration 5 — full API coverage: CRUD + all modules ✅ (80 tests green, 93% coverage)
- [x] **Scope change:** from 16 read-only tools → **218 tools** (217 endpoints 1:1 with Bling v3 + meta). Full CRUD (GET/POST/PUT/PATCH/DELETE) + special actions. Writes enabled, no gate (per user decision).
- [x] `client.py` — added write verbs `post/put/patch/delete` via a shared `_request`; 204/empty body → `None`; `Content-Type: application/json` only when a body is sent.
- [x] **Declarative architecture** — `tools/spec.py` (`Endpoint`/`Param`, frozen), `tools/factory.py` (`build_tool` builds a typed MCP tool per spec via dynamic `__signature__`; validated by a FastMCP spike), `tools/registry.py` (aggregates 10 domain modules → `ALL_ENDPOINTS`, `MODULES`).
- [x] **10 domain modules** extracted from the authoritative SDK `AlexandreBellas/bling-erp-api-js` (`src/entities/<mod>/index.ts`), fanned out across **7 parallel subagents**: produtos 38, pedidos 31, contatos 11, financeiro 25, fiscal 31, estoque 8, logistica 20, producao 7, situacoes 12, cadastros 34 = **217**.
- [x] `config.py` — optional `BLING_MODULES` filter (comma-separated domains; default = all).
- [x] `server.py` — registers one `bling_<name>` tool per enabled endpoint via the factory; legacy 16 tool names preserved.
- [x] **Validation tests** (`test_registry.py`) guard the 217 specs: unique names, path placeholders == path_params, snake_case, legacy-name preservation, scale ≥200. Smoke: server registers exactly 218 tools with correct typed schemas.
- [x] Removed legacy `BlingTools`; docs updated (README domain table + write warning + `BLING_MODULES`, `.env.example`).

**Extraction recipe (reusable):** SDK `this.repository.index/show/store/update/replace/destroy` → `GET-list/GET-one/POST/PUT/PATCH/DELETE`; exact path from the literal `endpoint:` string, confirmed by the JSDoc `@see .../referencia#/<Mod>/<operationId>` fragment (`_`=`/`, `__name_`=`/{name}`, prefix = verb).

### Remaining polish (optional — run `/loop ...` again to resume)
- [ ] Sample `manifests/claude_desktop_config.json` committed to the repo
- [ ] 401 → force-refresh-and-retry-once in `BlingClient`
- [ ] `x-bling-homologacao` header support for the `homologacao` module (needs per-endpoint header spec)
- [ ] Publish to PyPI so install collapses to `uvx bling-mcp`
