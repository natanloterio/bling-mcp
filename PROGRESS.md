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

### Iteration 5 — full API coverage: CRUD + all modules ✅ (62 tests green, 93% coverage)
- [x] **Scope change:** from 16 read-only tools → **218 tools** (217 endpoints 1:1 with Bling v3 + meta). Full CRUD (GET/POST/PUT/PATCH/DELETE) + special actions. Writes enabled, no gate (per user decision).
- [x] `client.py` — added write verbs `post/put/patch/delete` via a shared `_request`; 204/empty body → `None`; `Content-Type: application/json` only when a body is sent.
- [x] **Declarative architecture** — `tools/spec.py` (`Endpoint`/`Param`, frozen), `tools/factory.py` (`build_tool` builds a typed MCP tool per spec via dynamic `__signature__`; validated by a FastMCP spike), `tools/registry.py` (aggregates 10 domain modules → `ALL_ENDPOINTS`, `MODULES`).
- [x] **10 domain modules** extracted from the authoritative SDK `AlexandreBellas/bling-erp-api-js` (`src/entities/<mod>/index.ts`), fanned out across **7 parallel subagents**: produtos 38, pedidos 31, contatos 11, financeiro 25, fiscal 31, estoque 8, logistica 20, producao 7, situacoes 12, cadastros 34 = **217**.
- [x] `config.py` — optional `BLING_MODULES` filter (comma-separated domains; default = all).
- [x] `server.py` — registers one `bling_<name>` tool per enabled endpoint via the factory; legacy 16 tool names preserved.
- [x] **Validation tests** (`test_registry.py`) guard the 217 specs: unique names, path placeholders == path_params, snake_case, legacy-name preservation, scale ≥200. Smoke: server registers exactly 218 tools with correct typed schemas.
- [x] Removed legacy `BlingTools`; docs updated (README domain table + write warning + `BLING_MODULES`, `.env.example`).

**Extraction recipe (reusable):** SDK `this.repository.index/show/store/update/replace/destroy` → `GET-list/GET-one/POST/PUT/PATCH/DELETE`; exact path from the literal `endpoint:` string, confirmed by the JSDoc `@see .../referencia#/<Mod>/<operationId>` fragment (`_`=`/`, `__name_`=`/{name}`, prefix = verb).

### Iteration 6 — token persistence + 401 retry ✅ (115 tests green, 94% coverage)

- [x] `token_store.py` — `TokenStore` Protocol, `NullTokenStore`, `JsonFileTokenStore`
      (atomic write via `os.replace`, `0600` on POSIX, per-`client_id` entries).
- [x] `auth.py` — boots from the store, adopts persisted tokens only when the
      seed fingerprint matches (so a re-bootstrap wins), persists after every
      refresh, and gained `force_refresh()` which re-reads the store first.
- [x] Clock default moved from `time.monotonic` to `time.time` — a persisted
      expiry has to survive the process. Trade-off recorded in the module docstring.
- [x] `client.py` — one retry on 401 via `force_refresh()`; closes the item
      deferred back in iteration 2.
- [x] `config.py`/`server.py` — `BLING_TOKEN_STORE` override, platform default.
- [x] Store failures degrade with a stderr warning; they never raise.

**Fixes:** the rotated refresh token used to live only in memory, so every
restart fell back to the original env-seeded token — which carries its own
fixed 30-day clock from the moment it was first issued. Nothing showed the
seed itself was invalidated by rotation; the process just never advanced past
that fixed expiry because it kept discarding every rotated (and later-issued)
refresh token on exit. Once the seed's 30 days ran out, every refresh attempt
failed with `HTTP 400` from the token endpoint — across restarts — until
someone re-ran the OAuth bootstrap by hand. Persisting the rotated token keeps
the 30-day window rolling forward instead of resetting to the original seed on
every restart; it does not remove Bling's 30-day expiry itself (see
[INSTALL.md](INSTALL.md#where-the-token-is-cached)).

### Remaining polish (optional — run `/loop ...` again to resume)
- [ ] Sample `manifests/claude_desktop_config.json` committed to the repo
- [ ] `x-bling-homologacao` header support for the `homologacao` module (needs per-endpoint header spec)
- [ ] Publish to PyPI so install collapses to `uvx bling-mcp`
- [ ] Retry/backoff for 429 honouring `Retry-After`

### Iteration — in-chat re-authorization ✅ (180 tests green, 95% coverage)
Problem: Bling's refresh token lapses after 30 idle days; recovery meant the CLI
bootstrap + editing the MCP client config + restart.
- [x] `TokenManager.install(payload)` adopts a freshly exchanged token set and persists it under the env seed fingerprint (restart-safe); refresh `400` now names `bling_authorize`
- [x] `config.oauth_callback_port` from `BLING_OAUTH_CALLBACK_PORT` (default 8765, validated)
- [x] `oauth_flow.AuthorizationFlow` — per-attempt state machine (pending/completed/failed/expired), random `state`, 5-min timeout
- [x] `callback_server.CallbackServer` — loopback-only `ThreadingHTTPServer` serving `/callback`, HTML result page, quiet logging
- [x] `reauth.ReauthService` — owns listener + current flow; degrades to manual paste when the port cannot bind
- [x] `tools/auth_tools.py` — `bling_authorize`, `bling_auth_status`, `bling_authorize_with_code`; always registered regardless of `BLING_MODULES`
- [x] `server.build_runtime` shares one `TokenManager` between `BlingClient` and `ReauthService`
- Review fixes: flow lock (PENDING→EXCHANGING claim, duplicate callbacks exchange once), non-ASCII `state` no longer crashes the handler, catch-all 500 page, exclusive port bind (Windows `SO_REUSEADDR`), `redirect_uri` echoed in the token request (RFC 6749 §4.1.3), RLock across `TokenManager` refresh/install
- Setup: register `http://localhost:8765/callback` as the Bling app redirect URL.
