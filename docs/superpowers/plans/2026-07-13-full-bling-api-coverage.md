# Full Bling v3 API Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expandir o `bling-mcp` de 16 tools read-only para cobertura completa da API v3 do Bling — 42 módulos, 217 operações CRUD + ações especiais, uma tool MCP por endpoint.

**Architecture:** Registro declarativo. Cada endpoint é um `Endpoint` imutável (nome, método HTTP, path, params, body). Uma fábrica gera a tool MCP tipada por spec. O `BlingClient` ganha verbos de escrita. Domínios ficam em módulos pequenos sob `tools/`, agregados por `tools/registry.py` e registrados em `server.py`.

**Tech Stack:** Python ≥3.10, FastMCP (`mcp` SDK), `httpx` (sync), `pytest`, dataclasses frozen.

## Global Constraints

- **Imutabilidade:** dataclasses `frozen=True`; nunca mutar objetos existentes; drop de `None` já feito por `_clean_params`.
- **Arquivos pequenos:** 200-400 linhas típico, 800 máx. Split por domínio, não por camada.
- **Test runner:** `.venv/bin/python -m pytest` (a partir da raiz do projeto).
- **Cobertura ≥ 80%.**
- **Sem gate de escrita:** todas as tools sempre ativas, incluindo DELETE (decisão do usuário).
- **Retrocompatibilidade:** os 16 nomes de tool atuais (`bling_list_pedidos_vendas`, `bling_get_produto`, etc.) devem continuar existindo com os mesmos nomes.
- **Prefixo de tool:** todas registradas como `bling_<name>`.
- **Fonte autoritativa de endpoints:** SDK `AlexandreBellas/bling-erp-api-js`, arquivo `src/entities/<modulo>/index.ts`. Nunca adivinhar path/verbo.

### Receita de extração de endpoints (usada em todas as tasks de domínio)

Cada método público em `src/entities/<modulo>/index.ts` do SDK chama `this.repository.<m>(...)`. Mapeamento para o `Endpoint`:

| Chamada no SDK | Método HTTP | Path | Body? |
|---|---|---|---|
| `repository.index({endpoint, params})` | `GET` | `<endpoint>` | não |
| `repository.show({endpoint, id})` | `GET` | `<endpoint>/{id}` | não |
| `repository.store({endpoint, body})` | `POST` | `<endpoint>` | sim |
| `repository.update({endpoint, id, body})` | `PATCH` | `<endpoint>/{id}` | sim |
| `repository.replace({endpoint, id, body})` | `PUT` | `<endpoint>/{id}` | sim |
| `repository.destroy({endpoint, id, params})` | `DELETE` | `<endpoint>/{id}` (ou `<endpoint>` se `id: ''`) | não |
| `repository.create/callBlank/call` com endpoint custom | conforme `@see` | ver fragmento `@see` | conforme |

Para ações especiais (`change-situation`, `generate-nfe`, `post-stock`, `reverse-accounts`, `send`, `download`, etc.) e para confirmar o path exato, **use o fragmento `@see https://developer.bling.com.br/referencia#/<Modulo>/<operationId>`**: no `operationId`, `_` = `/` e `__nome_` = `/{nome}`. Ex.: `delete_produtos__idProduto_` → `DELETE /produtos/{idProduto}`; `post_produtos__idProduto__situacoes` → `POST /produtos/{idProduto}/situacoes`. O prefixo do operationId (`get`/`post`/`put`/`patch`/`delete`) confirma o verbo.

Como obter o arquivo de um módulo:
```bash
gh api "repos/AlexandreBellas/bling-erp-api-js/contents/src/entities/<modulo>/index.ts" --jq '.content' | base64 -d
```

Convenção de nome da tool (`Endpoint.name`, vira `bling_<name>`): `<verbo>_<recurso>[_<qualificador>]`, snake_case. Preserve os 16 nomes legados exatamente (ver README atual).

---

## Task 1: Spike — validar inferência de schema do FastMCP com assinatura dinâmica

**Files:**
- Create: `tests/test_factory_spike.py`
- Scratch: `src/bling_mcp/tools/factory.py` (versão mínima)

**Interfaces:**
- Produces: confirmação de que uma função com `__signature__`/`__annotations__` setados dinamicamente é aceita por `FastMCP.add_tool` e gera o input schema correto. Decide se o corpo da fábrica usa `__signature__` (plano A) ou `exec` de fonte (plano B).

- [ ] **Step 1: Escrever teste que registra uma tool de assinatura dinâmica**

```python
# tests/test_factory_spike.py
import inspect
from mcp.server.fastmcp import FastMCP

def _make(name, params_types):
    def impl(**kwargs):
        return kwargs
    impl.__name__ = name
    impl.__signature__ = inspect.Signature(
        [inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY,
                           annotation=t,
                           default=(inspect.Parameter.empty if req else None))
         for p, (t, req) in params_types.items()]
    )
    impl.__annotations__ = {p: t for p, (t, _req) in params_types.items()}
    impl.__doc__ = "spike tool"
    return impl

def test_dynamic_signature_registers_and_schemas():
    mcp = FastMCP("spike")
    fn = _make("bling_spike", {"id": (int, True), "nome": (str, False)})
    mcp.add_tool(fn, name="bling_spike")
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    assert "bling_spike" in tools
    schema = tools["bling_spike"].parameters
    assert "id" in schema["properties"]
    assert "nome" in schema["properties"]
    assert schema["properties"]["id"]["type"] == "integer"
    assert "id" in schema.get("required", [])
```

- [ ] **Step 2: Rodar e observar**

Run: `.venv/bin/python -m pytest tests/test_factory_spike.py -v`
Expected: PASS confirma plano A. Se FAIL (schema vazio / assinatura ignorada), adote plano B (gerar fonte via `exec` com `textwrap` + `compile`) e ajuste a Task 4 antes de prosseguir. Registre o resultado num comentário no topo de `factory.py`.

> Nota: `mcp._tool_manager.list_tools()` e `.parameters` são internos; se a API do SDK instalado diferir, inspecione `dir(mcp)` e ajuste o acesso. O objetivo do spike é só confirmar a inferência.

- [ ] **Step 3: Commit (se git init foi feito) ou anotar resultado**

```bash
git add tests/test_factory_spike.py src/bling_mcp/tools/factory.py 2>/dev/null; git commit -m "test: spike FastMCP dynamic signature inference" 2>/dev/null || true
```

---

## Task 2: `BlingClient` — verbos de escrita + 204

**Files:**
- Modify: `src/bling_mcp/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `BlingConfig`, `_Tokens` (existentes).
- Produces:
  - `BlingClient.post(path: str, json: dict | None = None, params: Mapping | None = None) -> Any`
  - `BlingClient.put(path, json=None, params=None) -> Any`
  - `BlingClient.patch(path, json=None, params=None) -> Any`
  - `BlingClient.delete(path, params=None) -> Any`
  - `BlingClient.get(...)` inalterado. Todos delegam a `_request(method, path, params, json)`. Corpo vazio/204 → `None`.

- [ ] **Step 1: Escrever testes falhando**

```python
# adicionar em tests/test_client.py
import httpx
from bling_mcp.client import BlingClient, BlingApiError

def _client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    cfg = type("C", (), {"api_base_url": "https://api.x/Api/v3"})()
    tok = type("T", (), {"get_access_token": lambda self: "tok"})()
    return BlingClient(cfg, tok, http)

def test_post_sends_json_body_and_content_type():
    seen = {}
    def h(req):
        seen["method"] = req.method
        seen["url"] = str(req.url)
        seen["ct"] = req.headers.get("content-type")
        seen["body"] = req.content
        return httpx.Response(201, json={"data": {"id": 9}})
    c = _client(h)
    out = c.post("produtos", json={"nome": "X"})
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/produtos")
    assert "application/json" in seen["ct"]
    assert b'"nome"' in seen["body"]
    assert out == {"data": {"id": 9}}

def test_delete_204_returns_none():
    c = _client(lambda req: httpx.Response(204))
    assert c.delete("produtos/5") is None

def test_put_and_patch_use_correct_verb():
    verbs = []
    c = _client(lambda req: (verbs.append(req.method), httpx.Response(200, json={}))[1])
    c.put("logisticas/1", json={"a": 1})
    c.patch("produtos/1", json={"b": 2})
    assert verbs == ["PUT", "PATCH"]

def test_write_error_raises_bling_api_error():
    c = _client(lambda req: httpx.Response(422, json={"error": "bad"}))
    try:
        c.post("produtos", json={})
        assert False
    except BlingApiError as e:
        assert e.status_code == 422
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `.venv/bin/python -m pytest tests/test_client.py -v`
Expected: FAIL (`AttributeError: 'BlingClient' object has no attribute 'post'`).

- [ ] **Step 3: Implementar `_request` + verbos**

```python
# client.py — substituir o método get por _request + wrappers
    def _request(self, method: str, path: str,
                 params: Mapping[str, Any] | None = None,
                 json: Any = None) -> Any:
        url = f"{self._config.api_base_url}/{path.lstrip('/')}"
        token = self._tokens.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            response = self._http.request(
                method, url, params=_clean_params(params), json=json, headers=headers
            )
        except httpx.HTTPError as exc:
            raise BlingApiError(0, f"Request to {path} failed: {exc}") from exc
        if not response.is_success:
            raise BlingApiError(
                response.status_code,
                f"Bling API error on {path}: HTTP {response.status_code} {response.text}",
                payload=_safe_json(response),
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, json=None, params=None):
        return self._request("POST", path, params=params, json=json)

    def put(self, path, json=None, params=None):
        return self._request("PUT", path, params=params, json=json)

    def patch(self, path, json=None, params=None):
        return self._request("PATCH", path, params=params, json=json)

    def delete(self, path, params=None):
        return self._request("DELETE", path, params=params)
```

> `httpx` com `json=None` não envia body nem `Content-Type` — comportamento correto para GET/DELETE. Com `json={...}` envia `application/json` automaticamente.

- [ ] **Step 4: Rodar — deve passar**

Run: `.venv/bin/python -m pytest tests/test_client.py -v`
Expected: PASS (todos, incluindo os testes GET pré-existentes).

- [ ] **Step 5: Commit**

```bash
git add src/bling_mcp/client.py tests/test_client.py; git commit -m "feat: add write verbs (post/put/patch/delete) + 204 handling to BlingClient" 2>/dev/null || true
```

---

## Task 3: `tools/spec.py` — dataclasses `Param` e `Endpoint`

**Files:**
- Create: `src/bling_mcp/tools/__init__.py`
- Create: `src/bling_mcp/tools/spec.py`
- Test: `tests/test_spec.py`
- Delete (no fim, Task 14): antigo `src/bling_mcp/tools.py`

**Interfaces:**
- Produces:
  - `Param(name: str, type: type = str)` (frozen)
  - `Endpoint(name, method, path, description, path_params=(), query_params=(), has_body=False)` (frozen)
  - `Endpoint.placeholders() -> set[str]` — nomes `{x}` no path.

> Cuidado: `src/bling_mcp/tools.py` (arquivo) e `src/bling_mcp/tools/` (package) não podem coexistir. Crie o package; o arquivo antigo só é removido na Task 14 (após o registry cobrir tudo). Durante a transição, `server.py` continua importando `from .tools import BlingTools` — mantenha um shim: em `tools/__init__.py` **não** reexporte `BlingTools` ainda; em vez disso a Task 14 troca o server. Para evitar quebra, faça a Task 3 criar o package E mover o conteúdo legado — ver Step 3.

- [ ] **Step 1: Teste falhando**

```python
# tests/test_spec.py
from bling_mcp.tools.spec import Param, Endpoint

def test_endpoint_is_frozen_and_reports_placeholders():
    e = Endpoint(
        name="get_produto", method="GET", path="produtos/{idProduto}",
        description="Get a product",
        path_params=(Param("idProduto", int),),
    )
    assert e.placeholders() == {"idProduto"}
    try:
        e.name = "x"
        assert False
    except Exception:
        pass

def test_no_placeholders_when_none():
    e = Endpoint(name="list_produtos", method="GET", path="produtos", description="d")
    assert e.placeholders() == set()
```

- [ ] **Step 2: Rodar — falha**

Run: `.venv/bin/python -m pytest tests/test_spec.py -v`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar spec + mover código legado para o package**

```python
# src/bling_mcp/tools/spec.py
from __future__ import annotations
import re
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Param:
    name: str
    type: type = str

@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str
    path: str
    description: str
    path_params: tuple[Param, ...] = ()
    query_params: tuple[Param, ...] = ()
    has_body: bool = False

    def placeholders(self) -> set[str]:
        return set(re.findall(r"{(\w+)}", self.path))
```

Mover o `BlingTools` legado: copie o conteúdo atual de `src/bling_mcp/tools.py` para `src/bling_mcp/tools/legacy.py` e faça `tools/__init__.py` reexportar `from .legacy import BlingTools` (mantém `server.py` funcionando sem mudança até a Task 13). Depois **delete** `src/bling_mcp/tools.py`.

```python
# src/bling_mcp/tools/__init__.py
from .legacy import BlingTools  # noqa: F401  (removido na Task 14)
```

- [ ] **Step 4: Rodar — passa (e a suíte inteira continua verde)**

Run: `.venv/bin/python -m pytest tests/test_spec.py tests/test_tools.py tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A src/bling_mcp/tools src/bling_mcp/tools.py tests/test_spec.py; git commit -m "feat: add Endpoint/Param spec; move legacy tools into tools package" 2>/dev/null || true
```

---

## Task 4: `tools/factory.py` — gerar tool MCP a partir de um `Endpoint`

**Files:**
- Modify: `src/bling_mcp/tools/factory.py` (do spike)
- Test: `tests/test_factory.py`

**Interfaces:**
- Consumes: `Endpoint`, `Param`; um client com `get/post/put/patch/delete`.
- Produces: `build_tool(endpoint: Endpoint, client) -> Callable` — função com `__name__ = "bling_" + endpoint.name`, docstring `f"{description} ({method} /{path})"`, assinatura: path params (obrigatórios, tipados), query params (opcionais `=None`), `body: dict` se `has_body`. Ao ser chamada, formata o path com os path params e invoca o verbo do client: query → `params=`, body → `json=`.

- [ ] **Step 1: Testes falhando**

```python
# tests/test_factory.py
import inspect
from bling_mcp.tools.spec import Param, Endpoint
from bling_mcp.tools.factory import build_tool

class FakeClient:
    def __init__(self): self.calls = []
    def get(self, path, params=None): self.calls.append(("GET", path, params, None)); return {"g": 1}
    def post(self, path, json=None, params=None): self.calls.append(("POST", path, params, json)); return {"p": 1}
    def delete(self, path, params=None): self.calls.append(("DELETE", path, params, None)); return None

def test_get_one_formats_path_and_calls_get():
    c = FakeClient()
    fn = build_tool(Endpoint("get_produto","GET","produtos/{idProduto}","d",
                             path_params=(Param("idProduto", int),)), c)
    assert fn.__name__ == "bling_get_produto"
    out = fn(idProduto=7)
    assert c.calls == [("GET", "produtos/7", {}, None)]
    assert out == {"g": 1}
    sig = inspect.signature(fn)
    assert sig.parameters["idProduto"].annotation is int
    assert sig.parameters["idProduto"].default is inspect.Parameter.empty

def test_list_passes_query_params_dropping_unset():
    c = FakeClient()
    fn = build_tool(Endpoint("list_produtos","GET","produtos","d",
                             query_params=(Param("pagina", int), Param("nome", str))), c)
    fn(pagina=2)
    assert c.calls == [("GET", "produtos", {"pagina": 2, "nome": None}, None)]

def test_create_passes_body():
    c = FakeClient()
    fn = build_tool(Endpoint("create_produto","POST","produtos","d", has_body=True), c)
    fn(body={"nome": "X"})
    assert c.calls == [("POST", "produtos", {}, {"nome": "X"})]

def test_delete_calls_delete_verb():
    c = FakeClient()
    fn = build_tool(Endpoint("delete_produto","DELETE","produtos/{idProduto}","d",
                             path_params=(Param("idProduto", int),)), c)
    assert fn(idProduto=3) is None
    assert c.calls == [("DELETE", "produtos/3", {}, None)]
```

- [ ] **Step 2: Rodar — falha**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `build_tool`**

```python
# src/bling_mcp/tools/factory.py
from __future__ import annotations
import inspect
from typing import Any, Callable
from .spec import Endpoint

_VERB = {"GET": "get", "POST": "post", "PUT": "put", "PATCH": "patch", "DELETE": "delete"}

def build_tool(endpoint: Endpoint, client) -> Callable[..., Any]:
    verb = _VERB[endpoint.method]
    path_names = [p.name for p in endpoint.path_params]
    query_names = [p.name for p in endpoint.query_params]

    def impl(**kwargs: Any) -> Any:
        path = endpoint.path.format(**{n: kwargs[n] for n in path_names})
        method = getattr(client, verb)
        if endpoint.method == "GET":
            return method(path, params={n: kwargs.get(n) for n in query_names} or None)
        if endpoint.method == "DELETE":
            return method(path, params={n: kwargs.get(n) for n in query_names} or None)
        # POST/PUT/PATCH
        return method(path,
                      json=kwargs.get("body") if endpoint.has_body else None,
                      params={n: kwargs.get(n) for n in query_names} or None)

    params = []
    for p in endpoint.path_params:
        params.append(inspect.Parameter(p.name, inspect.Parameter.KEYWORD_ONLY,
                                         annotation=p.type))
    for p in endpoint.query_params:
        params.append(inspect.Parameter(p.name, inspect.Parameter.KEYWORD_ONLY,
                                         annotation=p.type, default=None))
    if endpoint.has_body:
        params.append(inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY,
                                         annotation=dict))
    impl.__signature__ = inspect.Signature(params)
    impl.__annotations__ = {p.name: p.annotation for p in params}
    impl.__name__ = f"bling_{endpoint.name}"
    impl.__doc__ = f"{endpoint.description} ({endpoint.method} /{endpoint.path})"
    return impl
```

> Se o spike (Task 1) exigiu plano B, gere `impl` via fonte `exec` aqui, mantendo a mesma interface externa e os mesmos testes.

- [ ] **Step 4: Rodar — passa**

Run: `.venv/bin/python -m pytest tests/test_factory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bling_mcp/tools/factory.py tests/test_factory.py; git commit -m "feat: add build_tool factory for declarative endpoints" 2>/dev/null || true
```

---

## Task 5: `config.py` — `BLING_MODULES`

**Files:**
- Modify: `src/bling_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `BlingConfig.modules: tuple[str, ...] | None` — `None` se `BLING_MODULES` ausente/vazio; senão os nomes separados por vírgula, trimados.

- [ ] **Step 1: Teste falhando**

```python
# tests/test_config.py — adicionar
from bling_mcp.config import load_config

def _base_env(**extra):
    env = {"BLING_CLIENT_ID":"a","BLING_CLIENT_SECRET":"b","BLING_REFRESH_TOKEN":"c"}
    env.update(extra); return env

def test_modules_none_when_unset():
    assert load_config(_base_env()).modules is None

def test_modules_parsed_and_trimmed():
    cfg = load_config(_base_env(BLING_MODULES=" produtos , pedidos "))
    assert cfg.modules == ("produtos", "pedidos")
```

- [ ] **Step 2: Rodar — falha**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Adicionar campo `modules: tuple[str, ...] | None = None` ao dataclass `BlingConfig` (frozen) e no `load_config`:
```python
    raw = env.get("BLING_MODULES", "").strip()
    modules = tuple(m.strip() for m in raw.split(",") if m.strip()) or None
    # passar modules=modules na construção do BlingConfig
```

- [ ] **Step 4: Rodar — passa**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bling_mcp/config.py tests/test_config.py; git commit -m "feat: add optional BLING_MODULES config filter" 2>/dev/null || true
```

---

## Task 6: `tools/registry.py` — agregação + testes de validação

**Files:**
- Create: `src/bling_mcp/tools/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `Endpoint` de cada módulo de domínio (Tasks 7-12). No início só o meta-tool + `produtos` (Task 7 roda antes ou junto).
- Produces:
  - `ALL_ENDPOINTS: tuple[Endpoint, ...]` — concatenação de todos os módulos de domínio.
  - `MODULES: dict[str, tuple[Endpoint, ...]]` — nome de domínio → seus endpoints (para filtro `BLING_MODULES`).
  - `META_TOOLS` — a tool `list_accounts` (função pronta, não `Endpoint`).

> Ordem prática: implemente o **arquivo `registry.py` e seus testes de validação AGORA** (Task 6) importando os módulos de domínio que ainda vão existir. Rode os testes só depois que as Tasks 7-12 preencherem os módulos — ou rode incrementalmente à medida que cada domínio fica pronto. Os testes de validação são a rede de segurança dos 217 specs.

- [ ] **Step 1: Testes de validação (independem do conteúdo exato)**

```python
# tests/test_registry.py
from bling_mcp.tools.registry import ALL_ENDPOINTS, MODULES

def test_unique_tool_names():
    names = [e.name for e in ALL_ENDPOINTS]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"nomes duplicados: {dupes}"

def test_valid_http_methods():
    for e in ALL_ENDPOINTS:
        assert e.method in {"GET","POST","PUT","PATCH","DELETE"}, e.name

def test_path_placeholders_match_path_params():
    for e in ALL_ENDPOINTS:
        declared = {p.name for p in e.path_params}
        assert e.placeholders() == declared, (
            f"{e.name}: placeholders {e.placeholders()} != path_params {declared}")

def test_write_methods_have_body_flag_consistent():
    for e in ALL_ENDPOINTS:
        if e.method in {"POST","PUT","PATCH"}:
            pass  # has_body pode ser False p/ ações sem corpo; sem asserção rígida
        if e.method in {"GET","DELETE"}:
            assert e.has_body is False, e.name

def test_modules_union_equals_all():
    from itertools import chain
    union = tuple(chain.from_iterable(MODULES.values()))
    assert len(union) == len(ALL_ENDPOINTS)

def test_expected_scale():
    # 217 operações de domínio (meta-tool list_accounts é registrada à parte)
    assert len(ALL_ENDPOINTS) >= 200, len(ALL_ENDPOINTS)
```

- [ ] **Step 2: Implementar registry**

```python
# src/bling_mcp/tools/registry.py
from __future__ import annotations
from .produtos import ENDPOINTS as PRODUTOS
from .pedidos import ENDPOINTS as PEDIDOS
from .contatos import ENDPOINTS as CONTATOS
from .financeiro import ENDPOINTS as FINANCEIRO
from .fiscal import ENDPOINTS as FISCAL
from .estoque import ENDPOINTS as ESTOQUE
from .logistica import ENDPOINTS as LOGISTICA
from .producao import ENDPOINTS as PRODUCAO
from .situacoes import ENDPOINTS as SITUACOES
from .cadastros import ENDPOINTS as CADASTROS

MODULES = {
    "produtos": PRODUTOS, "pedidos": PEDIDOS, "contatos": CONTATOS,
    "financeiro": FINANCEIRO, "fiscal": FISCAL, "estoque": ESTOQUE,
    "logistica": LOGISTICA, "producao": PRODUCAO, "situacoes": SITUACOES,
    "cadastros": CADASTROS,
}
ALL_ENDPOINTS = tuple(e for eps in MODULES.values() for e in eps)
```

> Enquanto as Tasks 7-12 não existem, comente os imports ausentes para permitir progresso incremental — mas o commit final da Task 6 deve ter todos os 10 imports ativos.

- [ ] **Step 3: Rodar (após domínios prontos) — passa**

Run: `.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS (inclusive `test_path_placeholders_match_path_params`, que pega erros de extração).

- [ ] **Step 4: Commit**

```bash
git add src/bling_mcp/tools/registry.py tests/test_registry.py; git commit -m "feat: add endpoint registry with validation tests" 2>/dev/null || true
```

---

## Tasks 7–12: Módulos de domínio (extração dos endpoints) — PARALELIZÁVEIS

**Cada uma destas tasks é independente** e pode rodar em paralelo (subagentes distintos). Todas seguem o mesmo procedimento; muda só o conjunto de módulos-fonte do SDK e o arquivo de saída. Ao terminar, `test_registry.py` valida o resultado.

**Procedimento comum (aplicar em cada task):**
1. Para cada módulo-fonte, baixe `src/entities/<modulo>/index.ts` do SDK (comando na seção Global Constraints).
2. Para cada método público, aplique a tabela de mapeamento `repository.<m>` → `(método, path, body)` e confirme o path/verbo pelo fragmento `@see`.
3. Extraia os query params da chamada `params: {...}` (para `index`) e os path params dos `{...}` do path.
4. Escreva um `Endpoint(...)` por operação. Tipos: ids em path → `int`; query numéricos (`pagina`,`limite`,`id*`) → `int`, datas/strings → `str`, listas (`idsProdutos`,`codigos`) → `list`. `has_body=True` para store/update/replace e ações com corpo.
5. Preserve os nomes legados quando o endpoint coincidir (ver README atual: `list_produtos`, `get_produto`, `list_pedidos_vendas`, `get_pedido_venda`, `list_contatos`, `get_contato`, `list_contas_pagar`, `list_contas_receber`, `list_nfe`, `get_nfe`, `list_estoque_saldos`, `list_categorias_produtos`, `list_formas_pagamento`, `list_depositos`, `list_vendedores`).
6. Exporte `ENDPOINTS: tuple[Endpoint, ...]` no fim do arquivo.
7. Rode `.venv/bin/python -m pytest tests/test_registry.py -v` — deve passar.
8. Commit.

**Exemplo trabalhado (produtos — já verificado na fonte):**
```python
# src/bling_mcp/tools/produtos.py (trecho)
from .spec import Param, Endpoint
ENDPOINTS = (
    Endpoint("list_produtos","GET","produtos","List products",
        query_params=(Param("pagina",int),Param("limite",int),Param("criterio",str),
                      Param("tipo",str),Param("idComponente",int),
                      Param("dataInclusaoInicial",str),Param("dataInclusaoFinal",str),
                      Param("dataAlteracaoInicial",str),Param("dataAlteracaoFinal",str),
                      Param("idCategoria",int),Param("idLoja",int),Param("codigo",str),
                      Param("nome",str),Param("idsProdutos",list),Param("codigos",list))),
    Endpoint("get_produto","GET","produtos/{idProduto}","Get a product",
        path_params=(Param("idProduto",int),)),
    Endpoint("create_produto","POST","produtos","Create a product",has_body=True),
    Endpoint("update_produto","PUT","produtos/{idProduto}","Update a product",
        path_params=(Param("idProduto",int),),has_body=True),
    Endpoint("delete_produto","DELETE","produtos/{idProduto}","Delete a product",
        path_params=(Param("idProduto",int),)),
    Endpoint("delete_produtos","DELETE","produtos","Delete multiple products",
        query_params=(Param("idsProdutos",list),)),
    Endpoint("change_situation_produto","PATCH","produtos/{idProduto}/situacoes",
        "Change a product situation",path_params=(Param("idProduto",int),),has_body=True),
    Endpoint("change_situation_produtos","PATCH","produtos/situacoes",
        "Change multiple products situation",has_body=True),
)
```

### Task 7: `tools/produtos.py`
Módulos-fonte: `produtos`, `produtosEstruturas`, `produtosFornecedores`, `produtosLojas`, `produtosVariacoes`, `gruposDeProdutos`, `categoriasProdutos`. Saída: `src/bling_mcp/tools/produtos.py`. Test: valida via `tests/test_registry.py`.

### Task 8: `tools/pedidos.py`
Módulos-fonte: `pedidosVendas`, `pedidosCompras`, `propostasComerciais`. Inclui ações: `generate-nfe`, `generate-nfce`, `post-stock`, `post-stock-to-deposit`, `reverse-stock`, `post-accounts`, `reverse-accounts`, `change-situation`, `delete-many`. Saída: `src/bling_mcp/tools/pedidos.py`.

### Task 9: `tools/contatos.py`
Módulos-fonte: `contatos`, `contatosTipos`. Ações: `change-situation`, `change-situation-many`, `find-final-customer`, `find-types`, `delete-many`. Saída: `src/bling_mcp/tools/contatos.py`.

### Task 10: `tools/financeiro.py`
Módulos-fonte: `contasPagar`, `contasReceber`, `formasDePagamento`, `contasContabeis`, `categoriasReceitasDespesas`, `borderos`. Ações: `download`, `get-bank-slips`, `cancel-bank-slips`. Saída: `src/bling_mcp/tools/financeiro.py`.

### Task 11: `tools/fiscal.py`
Módulos-fonte: `nfes`, `nfces`, `nfses`, `naturezasDeOperacoes`. Ações: `send`, `post-stock`, `post-stock-to-deposit`, `reverse-stock`, `post-accounts`, `reverse-accounts`, `cancel`, `get-configurations`, `update-configurations`, `obtain-tax`. Saída: `src/bling_mcp/tools/fiscal.py`.

### Task 12: `tools/estoque.py`, `tools/logistica.py`, `tools/producao.py`, `tools/situacoes.py`, `tools/cadastros.py`
Um subagente pode fazer estes cinco (menores) ou dividir:
- `estoque.py`: `estoques` (`find-balance`, `get-balances`, `create`, `update`), `depositos`.
- `logistica.py`: `logisticas`, `logisticasEtiquetas`, `logisticasObjetos`, `logisticasRemessas` (`get-by-logistic`), `logisticasServicos`.
- `producao.py`: `ordensDeProducao` (`generate-over-demand`, `change-situation`).
- `situacoes.py`: `situacoes`, `situacoesModulos` (`get-modules`, `get-module-situations`, `get-module-transitions`, `get-module-actions`), `situacoesTransicoes`.
- `cadastros.py`: `categoriasLojas`, `canaisDeVenda` (`get-types`), `vendedores`, `empresas` (`me`), `usuarios` (`recover-password`, `validate-hash`), `camposCustomizados` (`find-by-module`, `get-modules`, `get-types`, `change-situation`), `contratos`, `notificacoes`, `homologacao`.

Cada arquivo exporta `ENDPOINTS`. Ao final de todas as tasks 7-12, `tests/test_registry.py` deve passar com `len(ALL_ENDPOINTS) >= 200`.

---

## Task 13: `server.py` — registrar endpoints via fábrica + filtro `BLING_MODULES`

**Files:**
- Modify: `src/bling_mcp/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `ALL_ENDPOINTS`, `MODULES` (registry), `build_tool` (factory), `BlingClient`, `BlingConfig.modules`.
- Produces: `register_tools(mcp, client, config)` registra `bling_list_accounts` + uma tool por `Endpoint` habilitado. `build_tools(config) -> BlingClient` (substitui o retorno de `BlingTools`).

- [ ] **Step 1: Testes falhando**

```python
# tests/test_server.py — adaptar/adicionar
from bling_mcp.server import create_server, build_tools
from bling_mcp.tools.registry import ALL_ENDPOINTS

class _Cfg:
    account_label="default"; modules=None
    api_base_url="https://api.x/Api/v3"

def test_registers_all_endpoints_plus_meta():
    mcp = create_server(client=object(), config=_Cfg())
    tools = {t.name for t in mcp._tool_manager.list_tools()}
    assert "bling_list_accounts" in tools
    assert len(tools) == len(ALL_ENDPOINTS) + 1
    assert all(n.startswith("bling_") for n in tools)

def test_module_filter_reduces_tools():
    class C(_Cfg): modules=("produtos",)
    mcp = create_server(client=object(), config=C())
    tools = {t.name for t in mcp._tool_manager.list_tools()}
    # só produtos + meta
    from bling_mcp.tools.registry import MODULES
    assert len(tools) == len(MODULES["produtos"]) + 1
```

- [ ] **Step 2: Rodar — falha**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

```python
# server.py — trechos-chave
from .tools.registry import ALL_ENDPOINTS, MODULES
from .tools.factory import build_tool

def build_tools(config):
    http = httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    tokens = TokenManager(config, http)
    return BlingClient(config, tokens, http)

def _enabled_endpoints(config):
    if not getattr(config, "modules", None):
        return ALL_ENDPOINTS
    return tuple(e for name in config.modules for e in MODULES.get(name, ()))

def register_tools(mcp, client, config):
    label = getattr(config, "account_label", "default")
    def list_accounts():
        "List the Bling account configured for this server install."
        return [{"id": label, "label": label}]
    list_accounts.__name__ = "bling_list_accounts"
    mcp.add_tool(list_accounts, name="bling_list_accounts")
    for e in _enabled_endpoints(config):
        mcp.add_tool(build_tool(e, client), name=f"bling_{e.name}")

def create_server(client, config, name="bling"):
    mcp = FastMCP(name)
    register_tools(mcp, client, config)
    return mcp

def main():
    config = load_config(os.environ)
    server = create_server(build_tools(config), config)
    server.run()
```

- [ ] **Step 4: Rodar — passa**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bling_mcp/server.py tests/test_server.py; git commit -m "feat: register all Bling endpoints as MCP tools via factory + module filter" 2>/dev/null || true
```

---

## Task 14: Limpeza legada + handshake stdio + docs

**Files:**
- Delete: `src/bling_mcp/tools/legacy.py`, `tests/test_tools.py` (substituídos por factory/registry)
- Modify: `src/bling_mcp/tools/__init__.py` (remover reexport de `BlingTools`)
- Modify: `README.md`, `PROGRESS.md`, `.env.example`

**Interfaces:**
- Consumes: tudo acima. Produces: suíte verde, cobertura ≥80%, docs atualizadas.

- [ ] **Step 1: Remover legado**

Delete `src/bling_mcp/tools/legacy.py` e `tests/test_tools.py`; limpe `tools/__init__.py` (deixe vazio ou só docstring). Confirme que nada mais importa `BlingTools`:
Run: `grep -rn "BlingTools" src tests`
Expected: sem resultados.

- [ ] **Step 2: Handshake stdio real (smoke)**

Adicione a `tests/test_server.py` um teste que faz `initialize` + `tools/list` sobre o server em memória e conta `len(ALL_ENDPOINTS)+1` tools com prefixo `bling_` (seguir o padrão do smoke existente descrito no PROGRESS.md iteração 3).

Run: `.venv/bin/python -m pytest -v`
Expected: PASS, suíte inteira.

- [ ] **Step 3: Cobertura**

Run: `.venv/bin/python -m pytest --cov=bling_mcp --cov-report=term-missing`
Expected: total ≥ 80%.

- [ ] **Step 4: Atualizar docs**

- `README.md`: substituir a tabela de 16 tools por uma visão por domínio (10 módulos, ~217 tools), documentar `BLING_MODULES`, e **aviso destacado**: “Escrita habilitada — inclui POST/PUT/PATCH/DELETE sem confirmação; um comando do LLM pode alterar/apagar dados no Bling.”
- `.env.example`: adicionar `# BLING_MODULES=produtos,pedidos` (comentado).
- `PROGRESS.md`: nova iteração registrando a cobertura completa.

- [ ] **Step 5: Commit**

```bash
git add -A; git commit -m "chore: remove legacy tools, add stdio smoke, update docs for full API coverage" 2>/dev/null || true
```

---

## Self-Review (checklist do autor)

- **Cobertura do spec:** client write verbs (T2) ✓; registro declarativo spec/factory/registry (T3,T4,T6) ✓; 42 módulos/217 ops (T7-12) ✓; filtro BLING_MODULES (T5,T13) ✓; sem gate de escrita (T13, sem código de gate) ✓; retrocompat nomes legados (T7-12 step 5) ✓; testes+cobertura (T14) ✓; risco FastMCP mitigado por spike (T1) ✓.
- **Placeholders:** nenhum “TBD/TODO”; as tasks 7-12 têm procedimento concreto + exemplo verificado, não “implemente depois”.
- **Consistência de tipos:** `Endpoint`/`Param` idênticos em spec/factory/registry/domínios; `build_tool(endpoint, client)`, `register_tools(mcp, client, config)`, `create_server(client, config)` consistentes entre T4/T13.
