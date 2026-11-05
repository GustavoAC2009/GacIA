# Correção da inicialização — PySide6 ausente

**Data:** 04/11/2026  
**Base:** Gac.IA PySide6 
**Erro reportado:** `ModuleNotFoundError: No module named 'PySide6'` ao importar `interface.py`.

## Causa identificada

O `iniciar.bat` anterior verificava apenas se `.venv\Scripts\python.exe` existia. Ao atualizar uma instalação que já possuía um ambiente virtual criado para a interface antiga, o atalho considerava o ambiente pronto e executava `main.py` sem confirmar se PySide6 havia sido instalado. O próprio instalador já declarava PySide6 em `requirements-core.txt`, mas não era chamado neste caso.

A mensagem “A verificação do Ollama acontece durante o uso” não está relacionada ao erro e foi preservada.

## Alterações

1. `iniciar.bat` verifica os imports essenciais do núcleo (`PySide6.QtCore`, `PySide6.QtWidgets`, `requests` e `PIL`) usando especificamente o Python de `.venv`.
2. Se algum desses imports estiver ausente, o inicializador executa `instalador.ps1 -Mode Prepare -Components core`, que instala/repara o núcleo obrigatório no ambiente virtual local.
3. A reparação é limitada a `core`; o manifesto do instalador preserva componentes opcionais já registrados.
4. Antes de abrir a janela, o inicializador repete a verificação. Se continuar falhando, encerra sem executar a interface e orienta o usuário a consultar o diagnóstico.
5. `main.py` fornece uma mensagem de orientação se for executado manualmente com um Python que não tenha PySide6.
6. Foi adicionado teste de regressão para o cenário em que `.venv` existe, mas PySide6 está ausente.

## O que não é alterado

- Python global do Windows.
- Instalação, serviço, modelos ou configuração do Ollama.
- Conversas, banco SQLite, preferências, workspaces e arquivos do usuário.
- Componentes opcionais já instalados, que permanecem no manifesto.

## Verificações realizadas neste ambiente

- `python -m unittest discover -s tests -v`: **234 testes aprovados**.
- `python -m pytest -q` (invocado como `python -m pytest -q`): **234 testes aprovados e 39 subtestes aprovados**.
- Teste dedicado do inicializador antigo com `.venv` presente e PySide6 ausente: aprovado.
- Teste dedicado da mensagem de orientação de `main.py`: aprovado.
- Compilação/sintaxe dos fontes: verificada pela suíte e pelo verificador do projeto.

## Limitação da validação

Este ambiente não dispõe de Windows nem do PySide6 instalado para executar o instalador PowerShell ou abrir a janela Qt. Portanto, a correção do fluxo foi validada por inspeção e testes automatizados, mas a instalação efetiva e a abertura visual devem ser confirmadas no Windows.

## Como aplicar

Extraia este ZIP sobre a pasta atual da Gac.IA, sem apagar `.venv`, `config.json`, `data/` ou pastas de usuário, e execute `iniciar.bat`. Se PySide6 estiver ausente, a preparação do núcleo começará automaticamente. A instalação exige acesso à internet para baixar os pacotes, caso ainda não estejam em cache.
