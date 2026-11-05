@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Preparar Gac.IA
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador.ps1" -Mode Prepare
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo.
    echo A preparacao terminou com erro. Consulte a mensagem acima.
    pause
) else (
    echo.
    echo Preparacao concluida. Pressione qualquer tecla para fechar.
    pause >nul
)
exit /b %CODIGO%
