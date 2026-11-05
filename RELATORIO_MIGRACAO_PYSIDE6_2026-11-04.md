# Relatório técnico — migração da interface Gac.IA para PySide6

**Data:** 04/11/2026  
**Base:** `GacIA_Interface_2026-11-04(1).zip`  
**Resultado:** camada principal de interface e gerenciador reescritos em PySide6; serviços e dados locais preservados.

## 1. O que mudou

- `main.py` agora inicia a aplicação com `QApplication` e abre a janela Qt.
- `interface.py` foi refeito como janela nativa `QMainWindow`, com sinais Qt para entregar streaming, estados, aprovações e eventos de voz à thread gráfica.
- `gerenciador.py` passou a usar PySide6, mantendo o instalador PowerShell e a seleção modular de dependências.
- `diagnostico_layout.py` foi atualizado para capturar a geometria da janela Qt.
- `requirements-core.txt`, `componentes.py`, `preparar_verificar.py`, `diagnostico.py` e `inventario_ambiente.py` passaram a reconhecer PySide6 como dependência central.
- A cópia anterior da janela foi arquivada em `legacy/interface_customtkinter.py` para os testes de regressão. O caminho iniciado por `main.py` não importa nem executa CustomTkinter; os únicos usos restantes no código Python estão na cópia histórica e no teste que a cobre.

## 2. Interface entregue

- Barra lateral recolhível, com Nova conversa, Conversas, Arquivos, Modelos, Configurações e Gerenciar recursos.
- Cabeçalho da área principal com perfil do modelo e menu de perfil do usuário.
- Área central de chat, tela inicial de boas-vindas e cartões de mensagem com Markdown.
- Tema escuro padrão e tema claro selecionável.
- Campo de mensagem expansível, anexos em chips, suporte a arrastar e soltar arquivos e envio com Enter.
- Menu `+` organizado em categorias, com ícone, nome e descrição: Word, Excel, Slides, PDF, E-books, Imagens, Código, Pesquisa na web, Voz e Anexar arquivo.
- Controles compactos para microfone, Chat ao vivo, pesquisa na web, preferências da pesquisa, Pensar mais, cancelar e enviar.
- Menu de pesquisa com perfis de até 2, 5 ou 8 fontes. Preferências adicionais podem priorizar fontes oficiais, científicas e jornalísticas; a opção de fontes antigas/sem data instrui o modelo a conferir datas e sinalizar limitações.
- Central de Arquivos para exportações, workspaces, imagens geradas e backups, com abertura de itens/pastas e anexos.

## 3. Lógica preservada e integração

A migração reaproveita os módulos de Ollama, SQLite, memória, histórico, anexos, agente, workspaces, documentos, ComfyUI, pesquisa e voz. O worker de chat executa fora da thread da interface; sinais Qt transportam os eventos para atualização segura dos widgets. As ferramentas do menu `+` encaminham instruções específicas para o agente de arquivos, em vez de depender somente do texto livre do modelo.

O mecanismo de pesquisa usado pelo chat e pelo agente compartilha as mesmas preferências e limitações por perfil. A seleção de fontes complementares não pode exceder o orçamento total de resultados do perfil.

O estado dos botões de microfone e Chat ao vivo foi revisado para evitar que fiquem visualmente ativos quando o outro modo de captura está inicializando ou encerrando. A abertura de arquivos também informa quando o sistema operacional não consegue abrir o item.

## 4. Dependências e compatibilidade

O núcleo agora declara `PySide6>=6.12,<6.13`, além de `requests` e `Pillow`. A versão 6.12.0 do PySide6 está publicada no PyPI e oferece wheels Windows x86-64; a página do pacote lista suporte a Python 3.10–3.15, incluindo Python 3.13. Referências:

- https://pypi.org/project/PySide6/6.12.0/
- https://doc.qt.io/qt-6/windows.html
- https://doc.qt.io/qtforpython-6/overviews/qtdoc-windows.html

**Atenção ao Windows:** Qt 6.12 suporta Windows 10 versão 1809 ou posterior e Windows 11 x64. A documentação oficial informa que Qt 6.12 será a última versão do Qt com suporte ao Windows 10. Isso não impede o uso desta versão em instalações compatíveis do Windows 10, mas limita futuras atualizações do framework nesse sistema.

## 5. Verificações realizadas neste ambiente

- `python -m compileall -q .` — concluído sem erros de sintaxe.
- `python -m pytest -q` — **232 testes aprovados e 39 subtestes aprovados**.
- `python -m unittest discover -s tests -q` — **232 testes aprovados** (mesmo executor chamado pelo instalador).
- Busca estática por `tkinter`/`customtkinter` fora de `legacy/` e `tests/` — nenhum uso encontrado no caminho ativo do aplicativo.
- O pacote final é gerado pelo empacotador do projeto, que exclui `config.json`, banco SQLite, logs, workspaces, backups, arquivos exportados, imagens geradas, caches e ambientes virtuais.

## 6. Limitações importantes da validação

**A interface PySide6 não foi iniciada visualmente neste ambiente.** A biblioteca PySide6 não está instalada no executor e a tentativa de instalação não foi possível por indisponibilidade de resolução de rede. Portanto, os resultados acima comprovam sintaxe, testes automatizados e consistência estática, mas não comprovam ainda que todos os widgets e interações funcionam corretamente no Windows real.

Antes de considerar a migração homologada, executar no computador Windows de destino:

1. `instalar.bat`/`preparar.bat`, confirmando instalação do núcleo PySide6 e dos componentes selecionados.
2. `iniciar.bat`: abertura, redimensionamento, recolhimento da barra lateral e temas claro/escuro.
3. Nova conversa, histórico, fixar/apagar/editar mensagem e resposta em streaming com Ollama.
4. Menu `+`: selecionar cada ferramenta e confirmar o encaminhamento ao agente; anexar e arrastar arquivos.
5. Gerar/editar um DOCX, XLSX, PPTX, PDF e EPUB com os módulos correspondentes instalados.
6. Pesquisa rápida/intermediária/profunda, preferências de fontes e acionamento automático por intenção.
7. Microfone manual, Chat ao vivo, interrupção, troca entre modos e reprodução TTS com dispositivos de áudio reais.
8. Gerenciador de componentes, reparo/atualização e diagnóstico.
9. Escala do Windows/DPI e resoluções como 1366×768 e 1920×1080.

A migração do código-fonte não cria um executável `.exe`; a execução continua sendo pelo ambiente Python administrado pelo instalador do projeto. O empacotamento binário pode ser tratado numa etapa separada após a validação visual e funcional em Windows.

## 7. Procedimento recomendado para atualizar uma instalação existente

1. Fechar a Gac.IA e o gerenciador.
2. Fazer backup de `data/` (principalmente `data/memory.db`) e preservar `config.json`.
3. Extrair os arquivos do ZIP sobre a pasta do projeto, sem substituir os dados locais.
4. Executar `preparar.bat` para instalar/atualizar o núcleo PySide6 e conferir os componentes existentes.
5. Executar `iniciar.bat` e realizar a lista de validação da seção 6.

**Não apague `.venv`, `data/` nem `config.json` manualmente como etapa de migração.** O instalador deve cuidar do ambiente e preservar dados locais.
