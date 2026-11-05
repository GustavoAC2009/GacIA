@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Gerenciador - Gac.IA
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0gerenciador.py"
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" gerenciador.py
    exit /b %ERRORLEVEL%
)

echo O ambiente ainda nao foi preparado. Iniciando o instalador modular...
call instalar.bat
if errorlevel 1 exit /b 1
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0gerenciador.py"
    exit /b 0
)
".venv\Scripts\python.exe" gerenciador.py
exit /b %ERRORLEVEL%
