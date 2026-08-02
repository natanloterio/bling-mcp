# Design — Persistência do refresh token rotacionado + retry no 401

**Data:** 2026-08-02
**Status:** Aprovado (aguardando revisão do spec pelo usuário)

## Problema

O `TokenManager` renova o access token corretamente **dentro do processo**
(`auth.py:49-54`) e acompanha a rotação do refresh token em memória
(`auth.py:82-84`), mas nada é gravado em disco. A cada restart do processo —
reiniciar o Claude Desktop, reboot, crash — `load_config` relê
`BLING_REFRESH_TOKEN` do ambiente, que é o token original do bootstrap OAuth.

O refresh token do Bling expira 30 dias após ser emitido; um refresh
bem-sucedido retorna um refresh token **novo**, com uma janela de 30 dias
reiniciada (verificado em developer.bling.com.br/aplicativos e confirmado por
log de produção — não há evidência de que o token anterior seja invalidado
pela rotação). O bug é que o token rotacionado, que carregava esse relógio
reiniciado, era descartado por viver só em memória: a cada restart o processo
voltava a semear do `BLING_REFRESH_TOKEN` original do ambiente, cujo relógio de
30 dias seguia contando desde o bootstrap inicial e vencia no prazo —
produzindo `HTTP 400` a partir daí, exigindo re-executar o bootstrap manual.

Problema secundário, listado como pendente desde a iteração 2
(`PROGRESS.md:72`): `client.py:79-84` levanta `BlingApiError` direto em 401, sem
tentar renovar o token.

Reescrever o `.env` não é opção: as credenciais chegam pelo bloco `env` do
`claude_desktop_config.json` e não há `.env` em runtime (`INSTALL.md:104`).

## Decisões (tomadas no brainstorming)

1. **Local do store:** diretório de estado do SO, com override por
   `BLING_TOKEN_STORE`. Defaults: `%LOCALAPPDATA%\bling-mcp\token.json`
   (Windows), `~/.local/state/bling-mcp/token.json` (Linux),
   `~/Library/Application Support/bling-mcp/token.json` (macOS).
2. **Precedência:** entradas chaveadas por `client_id`, cada uma gravando um
   fingerprint do seed do env. Fingerprint bate → o store vence. Diverge →
   entrada descartada e re-semeada do env. Resolve re-bootstrap sem passo manual
   e evita colisão entre contas.
3. **Escopo do que persiste:** refresh token, access token e expiry. Restart
   dentro da janela de ~6h reaproveita o access token e não gasta refresh.
4. **Falha de I/O:** warning no stderr e segue em memória. Não derruba o
   servidor por causa de um arquivo de cache.
5. **Acoplamento:** `TokenStore` como Protocol injetável, seguindo o padrão de
   `http_client` e `clock` já injetados em `auth.py`.
6. **Retry:** dentro de `BlingClient._request`, apenas em 401, apenas uma vez.

## Componentes

### Novo: `src/bling_mcp/token_store.py`

- `StoredTokens` — dataclass frozen: `refresh_token: str`,
  `access_token: str | None`, `expires_at: float` (unix wall-clock),
  `seed_fingerprint: str`.
- `TokenStore` — Protocol: `load(client_id) -> StoredTokens | None`,
  `save(client_id, tokens) -> None`.
- `NullTokenStore` — no-op. Default do `TokenManager`, preserva o comportamento
  atual e mantém os 62 testes existentes válidos sem alteração.
- `JsonFileTokenStore(path)` — formato
  `{"version": 1, "accounts": {"<client_id>": {...}}}`. Escrita atômica via
  arquivo `.tmp` + `os.replace()` (atômico em POSIX e em Windows no mesmo
  volume). `chmod 0600` no POSIX após criar; no Windows o chmod é efetivamente
  no-op e a proteção vem de o arquivo estar no perfil do usuário.
  Diretório criado com `parents=True, exist_ok=True`.
- `default_store_path() -> Path` — apenas os defaults por plataforma; **não** lê
  `BLING_TOKEN_STORE` (isso é responsabilidade de `config.py`). No Linux
  respeita `XDG_STATE_HOME` quando definido, caindo em `~/.local/state`; essa é
  uma convenção de plataforma, não configuração da aplicação.
- `fingerprint(seed) -> str` — SHA-256 hex do seed. Serve só de comparador; não
  duplica o segredo em claro além do que o arquivo já contém.

### Alterado: `src/bling_mcp/config.py`

`BlingConfig` ganha `token_store_path: str | None`; `load_config` lê
`BLING_TOKEN_STORE`. Mantém toda leitura de ambiente numa fronteira só.

### Alterado: `src/bling_mcp/auth.py`

- `__init__` recebe `store: TokenStore = NullTokenStore()`.
- Clock default muda de `time.monotonic` para `time.time` (ver Trade-offs).
- No boot, `store.load(client_id)` decide a semente (ver Fluxo).
- `_refresh()` grava no store após sucesso.
- Novo `force_refresh() -> str`: recarrega o store do disco, então renova
  ignorando o cache em memória.

### Alterado: `src/bling_mcp/client.py`

- O Protocol `_Tokens` ganha `force_refresh() -> str`.
- `_request` retenta uma vez em 401.

### Alterado: `src/bling_mcp/server.py`

`build_tools` resolve o caminho como
`Path(config.token_store_path) if config.token_store_path else default_store_path()`,
constrói o `JsonFileTokenStore` e o injeta no `TokenManager`.

## Fluxo

**Boot.** `TokenManager.__init__` chama `store.load(client_id)`:

| Estado do store | Ação |
|---|---|
| Sem entrada para o `client_id` | Semeia do env |
| Entrada com fingerprint igual ao do seed do env | Adota `refresh_token`, `access_token` e `expires_at` do disco |
| Entrada com fingerprint diferente | Descarta a entrada, semeia do env (re-bootstrap detectado) |

**Uso normal.** `get_access_token()` mantém a lógica atual (renova se ausente ou
a menos de 60s do expiry). A diferença é que o access token vindo do disco pode
ainda estar válido, então um restart dentro da janela não dispara refresh algum.
Todo `_refresh()` bem-sucedido persiste o estado novo.

**401.** `_request` detecta 401, chama `tokens.force_refresh()` e repete a
requisição uma única vez, preservando método, body e params. Um segundo 401 vira
`BlingApiError` normal. Repetir é seguro mesmo em POST/DELETE porque um 401
significa que a requisição foi rejeitada antes de ser processada.

**Concorrência.** `force_refresh()` recarrega o store do disco antes de chamar o
endpoint de token. Se outro processo do servidor rotacionou no meio, este adota o
valor fresco em vez de tentar renovar com um refresh token já morto. Não é file
locking; cobre o caso real (Claude Desktop rodando junto com um teste manual) sem
introduzir lock.

## Tratamento de erros

- **Leitura falha ou JSON malformado** → warning no stderr, trata como store
  vazio, cai no seed do env.
- **Escrita falha** → warning no stderr uma única vez por processo (flag para não
  repetir a cada refresh), segue em memória.
- `AuthError` e `BlingApiError` mantêm a semântica atual.

## Trade-offs registrados

**Wall-clock em vez de monotonic.** Persistir o expiry exige um relógio que
sobreviva ao processo, então o default passa de `time.monotonic()` para
`time.time()`. Wall-clock não é imune a ajuste de relógio: um salto de NTP pode
fazer o servidor considerar vivo um token já morto. A margem de 60s cobre saltos
pequenos e o retry no 401 é a rede de segurança para o resto. Os testes
existentes injetam clock próprio, então apenas o default muda.

**Access token em disco.** Amplia a superfície, mas o refresh token — que já vai
para o arquivo — é estritamente mais poderoso, então o acréscimo é marginal.

## Fora de escopo

- File locking entre processos.
- Retry/backoff para 429 e 5xx (o 429 do Bling merece tratamento próprio,
  respeitando `Retry-After`).
- Criptografia do arquivo ou integração com keychain do SO.

## Testes (TDD, RED primeiro)

**`tests/test_token_store.py`** (novo): path default por plataforma; override via
`BLING_TOKEN_STORE`; roundtrip save/load; arquivo ausente → `None`; JSON
corrompido → `None` + warning; escrita atômica (nenhum `.tmp` remanescente);
`client_id`s distintos não colidem; falha de escrita não levanta exceção;
permissões 0600 em POSIX.

**`tests/test_auth.py`** (casos novos): as três variações de boot da tabela
acima; access token válido no disco evita chamada HTTP; access expirado no disco
dispara refresh; `_refresh` grava no store; `force_refresh` recarrega o disco e
ignora o cache.

**`tests/test_client.py`** (casos novos): 401 → `force_refresh` + uma retentativa
bem-sucedida; 401 duplo → `BlingApiError`; 403 e 500 não retentam; a retentativa
preserva método, body e params; sucesso não chama `force_refresh`.

**`tests/test_server.py`**: `build_tools` injeta um `JsonFileTokenStore`.

Meta de cobertura: manter ≥90% (atual: 93%).

## Documentação a atualizar

`INSTALL.md` (nova env `BLING_TOKEN_STORE`, explicar que o token agora se mantém
sozinho entre restarts), `README.md` (tabela de env), `.env.example`,
`PROGRESS.md` (fechar o pendente do 401 e registrar a iteração).
