@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Instalador Modular - Gac.IA
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador.ps1" -Mode Install
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo.
    echo A instalacao terminou com erro. Consulte a mensagem acima.
    pause
)
exit /b %CODIGO%
