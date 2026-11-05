@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Gac.IA - Assistente Local
cd /d "%~dp0"

echo ========================================
echo                 GAC.IA
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python nao encontrado. Abrindo o instalador modular...
    call instalar.bat
    if errorlevel 1 goto erro_preparacao
)

if not exist ".venv\Scripts\python.exe" (
    echo O ambiente Python continua indisponivel. Abra gerenciador.bat para diagnostico.
    goto erro_preparacao
)

rem Um ambiente virtual antigo pode existir sem as dependencias da nova interface.
rem Verifique os imports do nucleo antes de executar main.py.
".venv\Scripts\python.exe" -c "import PySide6.QtCore, PySide6.QtWidgets, requests, PIL" >nul 2>nul
if errorlevel 1 (
    echo Dependencias obrigatorias da interface ausentes ou incompletas.
    echo Reparando automaticamente o nucleo da Gac.IA...
    echo Isso instala PySide6 no ambiente virtual local, sem alterar o Python global.
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalador.ps1" -Mode Prepare -Components core
    if errorlevel 1 goto erro_preparacao
)

rem Confirmacao final: nao inicia a aplicacao enquanto o nucleo continuar incompleto.
".venv\Scripts\python.exe" -c "import PySide6.QtCore, PySide6.QtWidgets, requests, PIL" >nul 2>nul
if errorlevel 1 (
    echo Nao foi possivel importar as dependencias obrigatorias mesmo apos o reparo.
    echo Consulte o erro do instalador acima ou execute diagnostico.bat.
    goto erro_preparacao
)

echo Nucleo da interface verificado.
echo Iniciando Gac.IA...
echo A verificacao do Ollama acontece durante o uso.
echo.
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto erro
exit /b 0

:erro_preparacao
echo.
echo A preparacao das dependencias falhou. A Gac.IA nao foi iniciada.
echo Verifique sua conexao com a internet e consulte o diagnostico.
pause
exit /b 1

:erro
echo.
echo A Gac.IA foi encerrada com erro.
pause
exit /b 1
