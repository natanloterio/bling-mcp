#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot installer for the bling-mcp server on Windows.

.DESCRIPTION
    Installs uv (if missing), creates a virtual environment, installs the
    server, optionally bootstraps the Bling OAuth refresh token, registers the
    server with Claude Desktop (merging into any existing config), and runs a
    smoke test that the server starts and lists its tools.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1

.EXAMPLE
    .\setup-windows.ps1 -ClientId abc -ClientSecret xyz -RefreshToken r0
#>
[CmdletBinding()]
param(
    [string]$ClientId,
    [string]$ClientSecret,
    [string]$RefreshToken,
    [string]$AccountLabel = "default",
    [switch]$SkipClaudeConfig,
    [switch]$SkipSmokeTest,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoDir = $PSScriptRoot
$VenvDir = Join-Path $RepoDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# --- pretty output -----------------------------------------------------------
function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Note($m) { Write-Host "  $m" -ForegroundColor Gray }
function Write-Warn2($m){ Write-Host "  [!] $m" -ForegroundColor Yellow }
function Fail($m)       { Write-Host "`n[X] $m" -ForegroundColor Red; exit 1 }

Write-Host "============================================" -ForegroundColor Magenta
Write-Host "  bling-mcp  -  Windows setup" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Note "Repo: $RepoDir"

# --- 1. locate or install uv -------------------------------------------------
function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )) { if (Test-Path $p) { return $p } }
    return $null
}

Write-Step "Checking for uv (Python package/venv manager)"
$Uv = Find-Uv
if (-not $Uv) {
    Write-Note "uv not found - installing from astral.sh ..."
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Fail "Failed to install uv automatically. Install it manually from https://docs.astral.sh/uv/ and re-run."
    }
    $Uv = Find-Uv
    if (-not $Uv) { Fail "uv installed but could not be located. Open a new terminal and re-run this script." }
}
Write-Ok "uv: $Uv"

# --- 2. create venv + install ------------------------------------------------
Write-Step "Creating virtual environment (.venv) with Python 3.12"
Push-Location $RepoDir
try {
    & $Uv venv --python 3.12 $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "uv venv failed." }
    Write-Ok "Virtual environment ready"

    Write-Step "Installing bling-mcp into the virtual environment"
    & $Uv pip install --python $VenvPython -e $RepoDir
    if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed." }
    Write-Ok "Installed"
} finally {
    Pop-Location
}
if (-not (Test-Path $VenvPython)) { Fail "Expected interpreter not found at $VenvPython" }

# --- 3. collect credentials --------------------------------------------------
Write-Step "Bling API credentials"
if (-not $ClientId) {
    if ($NonInteractive) { Fail "ClientId is required (pass -ClientId)." }
    $ClientId = Read-Host "Bling CLIENT ID"
}
if (-not $ClientSecret) {
    if ($NonInteractive) { Fail "ClientSecret is required (pass -ClientSecret)." }
    $ClientSecret = Read-Host "Bling CLIENT SECRET"
}
if (-not $ClientId -or -not $ClientSecret) { Fail "Client id and secret are required." }

# --- 3b. obtain refresh token (one-time OAuth) if not supplied ---------------
if (-not $RefreshToken) {
    if ($NonInteractive) {
        Fail "RefreshToken is required in non-interactive mode (pass -RefreshToken)."
    }
    Write-Step "No refresh token supplied - starting one-time OAuth authorization"
    $authUrl = (& $VenvPython -m bling_mcp.authorize url --client-id $ClientId | Select-Object -Last 1).Trim()
    Write-Note "Opening your browser to authorize. If it doesn't open, visit:"
    Write-Host "  $authUrl" -ForegroundColor White
    try { Start-Process $authUrl } catch { Write-Warn2 "Could not auto-open the browser; copy the URL above." }
    Write-Note "After approving, Bling redirects to your callback URL containing '?code=...'."
    $code = (Read-Host "Paste the 'code' value from the redirect URL").Trim()
    if (-not $code) { Fail "No authorization code provided." }
    $env:BLING_CLIENT_ID = $ClientId
    $env:BLING_CLIENT_SECRET = $ClientSecret
    $RefreshToken = (& $VenvPython -m bling_mcp.authorize exchange --code $code --refresh-only | Select-Object -Last 1).Trim()
    if (-not $RefreshToken) { Fail "Failed to obtain a refresh token from the authorization code." }
    Write-Ok "Refresh token obtained"
}

# --- 4. register with Claude Desktop (merge, don't clobber) ------------------
function ConvertTo-HashtableRecursive($obj) {
    if ($null -eq $obj) { return $null }
    if ($obj -is [System.Collections.IDictionary]) {
        $ht = @{}
        foreach ($k in $obj.Keys) { $ht[$k] = ConvertTo-HashtableRecursive $obj[$k] }
        return $ht
    }
    if ($obj -is [PSCustomObject]) {
        $ht = @{}
        foreach ($p in $obj.PSObject.Properties) { $ht[$p.Name] = ConvertTo-HashtableRecursive $p.Value }
        return $ht
    }
    if ($obj -is [System.Collections.IEnumerable] -and $obj -isnot [string]) {
        $arr = @()
        foreach ($i in $obj) { $arr += ,(ConvertTo-HashtableRecursive $i) }
        return ,$arr
    }
    return $obj
}

if ($SkipClaudeConfig) {
    Write-Step "Skipping Claude Desktop configuration (-SkipClaudeConfig)"
} else {
    Write-Step "Registering server with Claude Desktop"
    $configPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $configDir = Split-Path $configPath
    if (-not (Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }

    $config = @{}
    if (Test-Path $configPath) {
        Copy-Item $configPath "$configPath.bak" -Force
        Write-Note "Backed up existing config to claude_desktop_config.json.bak"
        try {
            $config = ConvertTo-HashtableRecursive (Get-Content -Raw -Path $configPath | ConvertFrom-Json)
        } catch {
            Write-Warn2 "Existing config was not valid JSON; starting a fresh one."
            $config = @{}
        }
    }
    if (-not ($config -is [System.Collections.IDictionary])) { $config = @{} }
    if (-not $config.ContainsKey("mcpServers")) { $config["mcpServers"] = @{} }

    $config["mcpServers"]["bling"] = @{
        command = $VenvPython
        args    = @("-m", "bling_mcp")
        env     = @{
            BLING_CLIENT_ID     = $ClientId
            BLING_CLIENT_SECRET = $ClientSecret
            BLING_REFRESH_TOKEN = $RefreshToken
            BLING_ACCOUNT_LABEL = $AccountLabel
        }
    }

    $json = $config | ConvertTo-Json -Depth 12
    # PS 5.1's `Set-Content -Encoding UTF8` writes a BOM that breaks strict JSON
    # parsers (Claude Desktop ignores the whole file). Write UTF-8 *without* BOM.
    [System.IO.File]::WriteAllText($configPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok "Wrote $configPath"
}

# --- 5. smoke test -----------------------------------------------------------
if ($SkipSmokeTest) {
    Write-Step "Skipping smoke test (-SkipSmokeTest)"
} else {
    Write-Step "Smoke test: starting the server and listing tools"
    $smoke = @'
import asyncio, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    env = {**os.environ, "BLING_CLIENT_ID": "x", "BLING_CLIENT_SECRET": "x", "BLING_REFRESH_TOKEN": "x"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "bling_mcp"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print(len(tools.tools))

asyncio.run(main())
'@
    # The server logs to stderr; under "Stop" PowerShell can surface that as a
    # NativeCommandError, so relax error handling and merge streams just here.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $count = $null
    try {
        $raw = $smoke | & $VenvPython - 2>&1
        $count = ($raw | ForEach-Object { "$_" } |
                  Where-Object { $_ -match '^\s*\d+\s*$' } |
                  Select-Object -Last 1)
        if ($count) { $count = $count.Trim() }
    } catch {
        $count = $null
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    if ($count -match '^\d+$' -and [int]$count -ge 1) {
        Write-Ok "Server started and exposed $count tools"
    } else {
        Write-Warn2 "Smoke test inconclusive - the install itself completed. Restart Claude Desktop and check that the bling tools appear."
    }
}

# --- done --------------------------------------------------------------------
Write-Host "`n============================================" -ForegroundColor Magenta
Write-Host "  Setup complete" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Magenta
Write-Note "Next step: fully quit Claude Desktop (system tray -> Quit) and reopen it."
Write-Note "The 'bling_*' tools will then be available."
if ($SkipClaudeConfig) {
    Write-Note "You skipped Claude config; run the server manually with:"
    Write-Note "  `"$VenvPython`" -m bling_mcp"
}
