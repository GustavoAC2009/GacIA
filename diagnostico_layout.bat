@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Diagnostico de Layout - Gac.IA
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado. Execute instalar.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" diagnostico_layout.py
set "CODIGO=%ERRORLEVEL%"
echo.
if "%CODIGO%"=="0" (
    echo Diagnostico concluido. O arquivo esta em data\diagnostico_layout.json.
) else (
    echo Nao foi possivel concluir o diagnostico. Consulte a mensagem acima.
)
pause
exit /b %CODIGO%
