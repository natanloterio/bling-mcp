@echo off
REM Double-click launcher for the bling-mcp diagnostics.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose-windows.ps1"
echo.
pause
