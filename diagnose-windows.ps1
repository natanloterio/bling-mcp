#Requires -Version 5.1
<#
.SYNOPSIS
    Diagnoses why the bling MCP server may not be loading in Claude Desktop.
.DESCRIPTION
    Locates the Claude Desktop config in BOTH known locations:
      - Direct download (.exe installer):  %APPDATA%\Claude
      - Microsoft Store (MSIX, sandboxed): %LOCALAPPDATA%\Packages\*Claude*\LocalCache\Roaming\Claude
    The Store build virtualizes %APPDATA%, so its real config lives under the
    package's LocalCache — editing %APPDATA%\Claude there has no effect.
    For each config found it checks presence, BOM, JSON validity and the bling
    entry, tests that the configured Python can import the package, and dumps the
    tail of the MCP logs sitting next to that config. A report is saved to Desktop.
#>

$ErrorActionPreference = "Continue"
$report = Join-Path ([Environment]::GetFolderPath('Desktop')) "bling-mcp-diagnostico.txt"
try { Start-Transcript -Path $report -Force | Out-Null } catch {}

Write-Host "===== Diagnostico bling-mcp ====="

# --- locate every Claude config dir -----------------------------------------
$candidates = @()
$candidates += Join-Path $env:APPDATA "Claude"                       # direct download
$pkgRoot = Join-Path $env:LOCALAPPDATA "Packages"                    # MSIX / Store
if (Test-Path $pkgRoot) {
    Get-ChildItem $pkgRoot -Directory -Filter "*Claude*" -ErrorAction SilentlyContinue |
        ForEach-Object { $candidates += Join-Path $_.FullName "LocalCache\Roaming\Claude" }
}

$withCfg = $candidates | Where-Object { Test-Path (Join-Path $_ "claude_desktop_config.json") }
Write-Host "Caminhos checados : $($candidates.Count)"
Write-Host "Com config        : $($withCfg.Count)"
if (-not $withCfg) {
    Write-Host "!! Nenhum claude_desktop_config.json encontrado. Caminhos verificados:"
    $candidates | ForEach-Object { Write-Host "   $_" }
}

function Test-ClaudeConfigDir($dir) {
    $cfg = Join-Path $dir "claude_desktop_config.json"
    Write-Host ""
    Write-Host "==================================================================="
    Write-Host "Config dir  : $dir"
    Write-Host "Config path : $cfg"
    Write-Host "Config existe: $(Test-Path $cfg)"

    if (Test-Path $cfg) {
        $bytes = [System.IO.File]::ReadAllBytes($cfg)
        $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
        Write-Host "Tem BOM     : $hasBom  (BOM quebra o parser do Claude)"
        try {
            $json = Get-Content -Raw $cfg | ConvertFrom-Json
            Write-Host "JSON valido : True"
            $servers = @()
            if ($json.mcpServers) { $servers = $json.mcpServers.PSObject.Properties.Name }
            Write-Host "Servidores  : $($servers -join ', ')"
            $bling = $json.mcpServers.bling
            if ($bling) {
                Write-Host "command     : $($bling.command)"
                Write-Host "args        : $($bling.args -join ' ')"
                Write-Host "python existe: $(Test-Path $bling.command)"
                $envKeys = @()
                if ($bling.env) { $envKeys = $bling.env.PSObject.Properties.Name }
                Write-Host "env keys    : $($envKeys -join ', ')  (valores ocultos)"
                Write-Host "--- teste de import ---"
                if (Test-Path $bling.command) {
                    & $bling.command -c "import bling_mcp, sys; print('import OK -', sys.version.split()[0])" 2>&1 |
                        ForEach-Object { Write-Host "  $_" }
                } else {
                    Write-Host "  PULADO: python.exe nao encontrado nesse caminho"
                }
            } else {
                Write-Host "!! NAO existe mcpServers.bling neste config"
            }
        } catch {
            Write-Host "JSON valido : False -> $($_.Exception.Message)"
        }
    }

    # logs sit next to whichever config the app actually uses
    $logs = Join-Path $dir "logs"
    Write-Host "--- logs em $logs ---"
    if (Test-Path $logs) {
        Get-ChildItem $logs -Filter *.log | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
        foreach ($name in @("mcp-server-bling.log", "mcp.log")) {
            $f = Join-Path $logs $name
            if (Test-Path $f) {
                Write-Host "===== $name (ultimas 30 linhas) ====="
                Get-Content $f -Tail 30
                Write-Host ""
            }
        }
    } else {
        Write-Host "(pasta de logs nao existe -> o Claude desta pasta nunca subiu o MCP)"
    }
}

# Prefer dirs that actually have a config; otherwise show every candidate so the
# user sees exactly where the app would look.
$toCheck = if ($withCfg) { $withCfg } else { $candidates }
foreach ($d in $toCheck) { Test-ClaudeConfigDir $d }

# --- running processes -------------------------------------------------------
Write-Host ""
Write-Host "--- processos Claude rodando agora ---"
Get-Process -Name "*claude*" -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName | Format-Table -AutoSize

try { Stop-Transcript | Out-Null } catch {}
Write-Host ""
Write-Host "Relatorio salvo em: $report" -ForegroundColor Green
Write-Host "Me envie esse arquivo (ou um print desta janela)."
