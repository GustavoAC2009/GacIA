@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Empacotar Gac.IA
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" empacotar_distribuicao.py
) else (
    py -3.13 empacotar_distribuicao.py
)
set "CODIGO=%ERRORLEVEL%"
echo.
if "%CODIGO%"=="0" (
    echo Pacote criado em dist\Gac.IA-source.zip.
) else (
    echo Falha ao empacotar. Consulte a mensagem acima.
)
pause
exit /b %CODIGO%
