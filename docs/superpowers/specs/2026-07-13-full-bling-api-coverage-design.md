# Design — Cobertura completa da API v3 do Bling no bling-mcp

**Data:** 2026-07-13
**Status:** Aprovado (aguardando revisão do spec pelo usuário)

## Objetivo

Expandir o `bling-mcp` de 16 tools read-only para **cobertura completa** da API v3 do
Bling: todos os módulos, CRUD completo (GET/POST/PUT/PATCH/DELETE) e ações especiais,
**uma tool MCP por endpoint**.

## Decisões (tomadas no brainstorming)

1. **Escopo:** CRUD completo — leitura e escrita (criar/editar/excluir) + ações especiais.
2. **Granularidade:** uma tool por endpoint (não tools genéricas parametrizadas).
3. **Segurança de escrita:** **sem gate** — todas as tools sempre ativas, incluindo DELETE.
   (Risco aceito explicitamente pelo usuário: uma chamada errada do LLM pode apagar dados.)
4. **Arquitetura:** **registro declarativo** — cada endpoint descrito como um `Endpoint`
   (dado imutável); uma fábrica gera a tool MCP tipada a partir do spec.
5. **Filtro opcional:** env `BLING_MODULES` para habilitar/desabilitar domínios;
   **default = todos habilitados** (não altera comportamento se não setado).

## Catálogo autoritativo

Extraído do SDK comunitário `AlexandreBellas/bling-erp-api-js` (que espelha a referência
oficial `developer.bling.com.br/referencia`):

- **42 módulos**, **217 operações**.
- O `(method, path)` exato de cada operação — em especial as ações especiais
  (`change-situation`, `generate-nfe`, `post-stock`, `post-stock-to-deposit`,
  `reverse-accounts`, `reverse-stock`, `send`, `download`, `get-bank-slips`,
  `cancel-bank-slips`, `add-component`, `generate-combinations`, etc.) — **será extraído
  da fonte autoritativa (SDK + referência oficial), nunca adivinhado.** Este mapeamento é o
  grosso do trabalho de implementação e será paralelizado por domínio.

Módulos (42): borderos, camposCustomizados, canaisDeVenda, categoriasLojas,
categoriasProdutos, categoriasReceitasDespesas, contasContabeis, contasPagar, contasReceber,
contatos, contatosTipos, contratos, depositos, empresas, estoques, formasDePagamento,
gruposDeProdutos, homologacao, logisticas, logisticasEtiquetas, logisticasObjetos,
logisticasRemessas, logisticasServicos, naturezasDeOperacoes, nfces, nfes, nfses,
notificacoes, ordensDeProducao, pedidosCompras, pedidosVendas, produtos, produtosEstruturas,
produtosFornecedores, produtosLojas, produtosVariacoes, propostasComerciais, situacoes,
situacoesModulos, situacoesTransicoes, usuarios, vendedores.

## Arquitetura

### 1. Camada HTTP — `client.py`

Refatorar para um `_request(method, path, params=None, json=None)` interno e expor:

- `get(path, params=None)` — mantido (retrocompatível)
- `post(path, json=None, params=None)`
- `put(path, json=None, params=None)`
- `patch(path, json=None, params=None)`
- `delete(path, params=None)`

Regras:
- Mesma auth Bearer via `TokenManager`, mesmo `_clean_params` (drop de `None`).
- Verbos com body enviam `Content-Type: application/json`.
- **204 No Content / corpo vazio → retorna `None`** (não estoura no `.json()`).
- Não-2xx → `BlingApiError(status_code, message, payload)` (inalterado).

### 2. Registro declarativo — package `tools/`

`tools.py` (arquivo único) → **package `tools/`**.

**`tools/spec.py`** — dados imutáveis:
```python
@dataclass(frozen=True)
class Param:
    name: str
    type: type = str        # int | str | list ...

@dataclass(frozen=True)
class Endpoint:
    name: str                          # sufixo → bling_<name>
    method: str                        # GET|POST|PUT|PATCH|DELETE
    path: str                          # template: "produtos/{id}"
    description: str
    path_params: tuple[Param, ...] = ()   # obrigatórios (default int p/ ids)
    query_params: tuple[Param, ...] = ()  # opcionais (default None)
    has_body: bool = False                # POST/PUT/PATCH → arg body: dict
```

**Módulos por domínio** (cada um exporta `list[Endpoint]`, alvo 200-400 linhas):
- `tools/produtos.py` — produtos, produtosEstruturas, produtosFornecedores,
  produtosLojas, produtosVariacoes, gruposDeProdutos, categoriasProdutos
- `tools/pedidos.py` — pedidosVendas, pedidosCompras, propostasComerciais
- `tools/contatos.py` — contatos, contatosTipos
- `tools/financeiro.py` — contasPagar, contasReceber, formasDePagamento,
  contasContabeis, categoriasReceitasDespesas, borderos
- `tools/fiscal.py` — nfes, nfces, nfses, naturezasDeOperacoes
- `tools/estoque.py` — estoques, depositos
- `tools/logistica.py` — logisticas, logisticasEtiquetas, logisticasObjetos,
  logisticasRemessas, logisticasServicos
- `tools/producao.py` — ordensDeProducao
- `tools/situacoes.py` — situacoes, situacoesModulos, situacoesTransicoes
- `tools/cadastros.py` — categoriasLojas, canaisDeVenda, vendedores, empresas,
  usuarios, camposCustomizados, contratos, notificacoes, homologacao

(A distribuição final de módulos→arquivo é ajustável no plano; critério: coesão de domínio
e tamanho de arquivo ≤ 800 linhas.)

**`tools/registry.py`** — agrega todas as listas em `ALL_ENDPOINTS: tuple[Endpoint, ...]`
mais o meta-tool `list_accounts`. Ponto único de composição.

### 3. Fábrica de tools — `tools/factory.py`

`build_tool(endpoint, client, account_label) -> Callable`:
- Constrói uma função com **assinatura real** para o FastMCP inferir o schema:
  - path params → args obrigatórios tipados (`id: int`)
  - query params → args opcionais (`= None`)
  - `has_body` → `body: dict`
- Seta `__name__`, `__doc__` (= `description` + `(MÉTODO /path)`), `__signature__`,
  `__annotations__` com tipos reais.
- Corpo chama `client.<verbo>(path_formatado, ...)` conforme `endpoint.method`.

**Risco técnico (mitigado no plano):** a inferência de schema do FastMCP a partir de
`__signature__` dinâmico precisa ser validada num **spike/teste inicial** antes de escalar
para 217. Fallback se o FastMCP não respeitar `__signature__`: gerar a função via `exec` de
código-fonte (padrão `dataclasses`). **O plano começa por esse spike.**

### 4. Servidor — `server.py`

- `register_tools(mcp, client, account_label)` itera `ALL_ENDPOINTS`, gera cada tool pela
  fábrica e registra como `bling_<name>`.
- Aplica filtro `BLING_MODULES` (se setado) antes de registrar.
- **Os 16 nomes de tool atuais são preservados** (retrocompatibilidade).
- Sem gate de escrita.

### 5. Filtro opcional de módulos

- Env `BLING_MODULES` (CSV de domínios, ex: `produtos,pedidos,estoque`).
- Não setado → todos os módulos. Setado → só os listados.
- Carregado em `config.py` (campo novo no `BlingConfig` frozen).

## Testes (TDD)

- **client:** `post/put/patch/delete` com httpx mockado; 204/corpo vazio → `None`;
  não-2xx → `BlingApiError`; header `Content-Type` nos verbos com body.
- **registry (alto valor p/ 217 specs):** nomes únicos; `method` válido; todo `{placeholder}`
  do path tem `Param` correspondente em `path_params` e vice-versa; sem duplicatas de nome.
- **factory:** tool gerada tem assinatura/anotações esperadas e chama o client com
  `(método, path, params, body)` corretos — via client fake.
- **server:** nº de tools registradas = `len(endpoints_habilitados)+1`; todas com prefixo
  `bling_`; filtro `BLING_MODULES` reduz o conjunto; handshake stdio `tools/list`.
- Manter cobertura ≥ 80%.

## Fora de escopo (YAGNI)

- Gate de escrita / confirmação / dry-run (usuário optou por sem proteção).
- Tools genéricas parametrizadas.
- Schemas tipados por endpoint para o body (body é `dict` livre; LLM monta conforme docs).
- Publicação no PyPI (item de polish pré-existente, não relacionado).

## Entregáveis

- `client.py` com verbos de escrita + tratamento 204.
- Package `tools/` (spec, factory, registry, ~10 módulos de domínio).
- `server.py` registrando os 217 endpoints + meta-tool via fábrica, com filtro `BLING_MODULES`.
- `config.py` com `BLING_MODULES`.
- Suíte de testes (client, registry, factory, server) ≥ 80% cobertura.
- README/PROGRESS atualizados (tabela de tools por domínio, aviso de escrita/DELETE ativos).
