@echo off
REM Double-click launcher for the bling-mcp Windows setup.
REM Runs the PowerShell installer with an execution policy bypass for this process.
echo Starting bling-mcp setup...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" %*
echo.
pause
