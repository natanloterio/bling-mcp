# Installing bling-mcp

The server speaks MCP over **stdio**, so any MCP client launches it as a
subprocess. Start command (verified):

```
python -m bling_mcp
```

with these environment variables set:

| Variable | Required | Notes |
|----------|----------|-------|
| `BLING_CLIENT_ID` | yes | from your Bling app |
| `BLING_CLIENT_SECRET` | yes | from your Bling app |
| `BLING_REFRESH_TOKEN` | yes | obtained once via OAuth (see below) |
| `BLING_ACCOUNT_LABEL` | no | display label, default `default` |
| `BLING_API_BASE_URL` | no | default `https://api.bling.com.br/Api/v3` |
| `BLING_TOKEN_URL` | no | default `https://www.bling.com.br/Api/v3/oauth/token` |
| `BLING_TOKEN_STORE` | no | path to the token cache; default is the OS state dir (see below) |
| `BLING_OAUTH_CALLBACK_PORT` | no | loopback port for in-chat re-authorization, default `8765`; must match the redirect URL registered in the Bling app |
| `BLING_OAUTH_REDIRECT_HOST` | no | host written into the redirect URL, default `localhost`; use `127.0.0.1` if localhost resolves only to IPv6 |

---

## Windows

### 1. Install prerequisites

```powershell
winget install Python.Python.3.12
winget install astral-sh.uv      # optional but recommended
```

### 2. Get the code and install it

Copy/clone the `bling-mcp` folder to the machine, e.g. `C:\Users\<you>\bling-mcp`, then:

```powershell
cd C:\Users\<you>\bling-mcp
uv venv
uv pip install -e .
```

This creates `.venv\Scripts\python.exe` — the interpreter the MCP client will launch.

### 3. Register it with Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (create it if missing).

> **Microsoft Store build?** The Store (MSIX) build does *not* read that path —
> see [Windows gotchas](#windows-gotchas) below. The safest way on any build is
> **Settings → Developer → Edit Config** inside the app, which always opens the
> file the app actually uses. (`setup-windows.ps1` handles both automatically.)

**Recommended — point straight at the venv Python (no PATH dependency):**

```json
{
  "mcpServers": {
    "bling": {
      "command": "C:\\Users\\<you>\\bling-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "bling_mcp"],
      "env": {
        "BLING_CLIENT_ID": "your_client_id",
        "BLING_CLIENT_SECRET": "your_client_secret",
        "BLING_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

**Alternative — via uv:**

```json
{
  "mcpServers": {
    "bling": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\Users\\<you>\\bling-mcp", "python", "-m", "bling_mcp"],
      "env": { "BLING_CLIENT_ID": "...", "BLING_CLIENT_SECRET": "...", "BLING_REFRESH_TOKEN": "..." }
    }
  }
}
```

### 4. Restart Claude Desktop

Quit fully from the system tray (not just close the window), reopen, and the
`bling_*` tools appear.

### Windows gotchas

- **Microsoft Store build uses a different config path.** If you installed Claude
  Desktop from the Store (MSIX), it runs sandboxed and *virtualizes* `%APPDATA%`,
  so it does **not** read `%APPDATA%\Claude\claude_desktop_config.json`. Its real
  config lives under the package's LocalCache:
  ```
  %LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\claude_desktop_config.json
  ```
  Editing the `%APPDATA%` copy will silently do nothing. **Always edit via the app:
  Settings → Developer → Edit Config** — that opens the file the app actually uses.
  (The `logs\` folder also lives next to that real config, not under `%APPDATA%`.)
  The direct-download `.exe` build does use `%APPDATA%\Claude`.
- **Escape backslashes** in JSON paths (`C:\\Users\\...`).
- **Pass credentials in the `env` block**, not a `.env` file — Claude Desktop only
  injects what's in the config.
- If you use the `uv` form and Claude Desktop can't find `uv`, give its full path
  (e.g. `C:\\Users\\<you>\\.local\\bin\\uv.exe`) — or just use the recommended
  venv-Python form, which has no PATH dependency.

---

## macOS / Linux

Same as above; config lives at
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
Use `.venv/bin/python` as the command.

---

## Getting the initial refresh token (one-time OAuth)

Bling's `BLING_REFRESH_TOKEN` comes from a one-time authorization-code flow:

1. Open in a browser (replace `CLIENT_ID`):
   `https://www.bling.com.br/Api/v3/oauth/authorize?response_type=code&client_id=CLIENT_ID&state=xyz`
2. Approve; Bling redirects to your app's callback with `?code=...`.
3. Exchange the code for tokens:
   ```
   POST https://www.bling.com.br/Api/v3/oauth/token
   Authorization: Basic base64(CLIENT_ID:CLIENT_SECRET)
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code&code=THE_CODE
   ```
4. The response includes `refresh_token` — use it as `BLING_REFRESH_TOKEN`.

The server auto-refreshes the short-lived access token from there on, and
**persists the rotated refresh token** so it survives restarts.

### Where the token is cached

Bling's refresh token expires 30 days after it's issued. Refreshing it returns
the same response shape as the initial exchange above, including a **new
refresh token with its own fresh 30-day window** — so the server mirrors the
current token set to:

| Platform | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\bling-mcp\token.json` |
| macOS | `~/Library/Application Support/bling-mcp/token.json` |
| Linux | `$XDG_STATE_HOME/bling-mcp/token.json`, else `~/.local/state/bling-mcp/token.json` |

Override with `BLING_TOKEN_STORE`. The file holds live credentials — it is
created mode `0600` on macOS/Linux; on Windows it relies on the user profile.

`BLING_REFRESH_TOKEN` stays required: it is the seed. The cache records which
seed produced it, so re-running the OAuth bootstrap and pasting a new token into
the config just works — the stale cache entry is discarded automatically. If the
cache cannot be read or written, the server prints a warning to stderr and keeps
running with the token in memory only.

**This does not make the token immortal.** As long as the server refreshes at
least once within any 30-day window, the rolling window keeps renewing and it
never lapses. But if the server sits idle longer than that — stopped,
unreachable, or simply not invoked — the stored refresh token expires on
Bling's side regardless of the cache, and every refresh attempt then fails
(`HTTP 400` from the token endpoint). The error message tells the agent to call
`bling_authorize`, which recovers without touching the config — see below.

## Re-authorizing from the chat (after the 30-day lapse)

1. **Once:** in the Bling app settings (https://www.bling.com.br/cadastro.api.php)
   set the *link de redirecionamento* to `http://localhost:8765/callback`.
   Change the port with `BLING_OAUTH_CALLBACK_PORT` if 8765 is taken; the two
   must match.
2. In the chat, ask the agent to reconnect Bling (or let it react to the
   expiry error). It calls `bling_authorize` and shows you a link.
3. Open the link, approve. Bling redirects the browser to the local callback;
   the server exchanges the code and persists the new refresh token to the
   cache above. The page confirms success.
4. The agent calls `bling_auth_status` and resumes.

If step 3 shows a browser connection error (the listener could not bind, or the
server runs on another machine), copy the `code` parameter from the address
bar and tell the agent; it calls `bling_authorize_with_code`.

The link is valid for 5 minutes. The callback listener binds only to
`127.0.0.1`, validates a random `state`, and is started lazily on the first
`bling_authorize`. If `localhost` resolves only to IPv6 on your machine (a
custom hosts file or corporate DNS), register `http://127.0.0.1:8765/callback`
in Bling instead and set `BLING_OAUTH_REDIRECT_HOST=127.0.0.1`.

`BLING_REFRESH_TOKEN` in the config can stay as it is: the cache records the
re-authorized token under the same install, so restarts pick it up.

## Verify it works

```bash
python -m pytest          # all green
```
