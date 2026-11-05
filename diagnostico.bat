@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Diagnostico Gac.IA
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado. Execute preparar.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" diagnostico.py
echo.
echo O diagnostico nao modifica configuracoes nem arquivos.
pause
