# Gac.IA — Etapa 3: imagens, documentos e anexos

**Data:** 03/11/2026  
**Base:** `Gac.IA_Atualizada.zip` (entrega anterior)  
**Arquitetura preservada:** Python + CustomTkinter + Ollama + agente de ferramentas + ComfyUI local.

## Resumo

Este lote amplia o uso de documentos e imagens dentro do agente. A implementação não substitui a interface, o mecanismo Ollama ou o gerenciador atual de workspaces. Os arquivos manipulados pelo agente continuam restritos à cópia de trabalho; criação de novos arquivos evita sobrescrever arquivos existentes e operações destrutivas geram backup quando aplicável.

## Funcionalidades adicionadas

### PowerPoint (`.pptx`)

- Criação de apresentações com até 100 slides por operação.
- Layouts de título, conteúdo e seção; texto, listas, tabelas e notas do apresentador.
- Edição por substituição de texto em runs existentes e inclusão de novos slides.
- Gravação atômica e prevenção de sobrescrita na criação; backup antes da edição via ToolExecutor.
- Limitação conhecida: a substituição textual atua em cada run do PowerPoint. Uma expressão dividida entre vários runs não é reconstruída automaticamente, pois isso pode destruir formatação local.

### PDF

- Criação de PDFs paginados em A4 ou Letter, com título, parágrafos, tabelas e rodapé com número da página.
- Operações estruturais: mesclar de 2 a 30 arquivos, extrair páginas, girar páginas (90°, 180° ou 270°) e atualizar metadados.
- Operações que alteram o PDF existente geram backup pelo executor; criações e saídas de mesclagem/extração não sobrescrevem arquivos existentes.
- Limitação conhecida: não há edição arbitrária de texto/imagens/layout dentro de um PDF nem OCR de PDFs digitalizados. Fontes padrão do ReportLab também não garantem cobertura de todos os alfabetos, símbolos ou emojis.

### Planilhas (`.xlsx`)

- Criação com cabeçalho formatado, congelamento da primeira linha, filtro automático, tabela nativa quando os cabeçalhos permitem e larguras de colunas ajustadas com limite.
- Limite de criação de 10.000 linhas por operação.
- Edição de células e fórmulas já existente foi preservada.

### Super-resolução neural pelo ComfyUI

- Consulta os modelos realmente expostos pelo nó `UpscaleModelLoader` instalado no ComfyUI.
- Usa o fluxo oficial de nós `LoadImage` → `UpscaleModelLoader` → `ImageUpscaleWithModel` → `SaveImage`.
- Envia o arquivo à API local, aguarda a execução e valida o PNG recebido antes de retornar o caminho.
- Restringe o host ao ComfyUI local, aceita PNG/JPG/JPEG/WEBP/BMP/TIFF, limita entrada a 100 MB e 64 megapixels e tempo de execução a no máximo 30 minutos.
- Cria um novo PNG e preserva o original. Não baixa modelos automaticamente e não chama interpolação comum de super-resolução por IA.
- O comando `/upscale` pode detectar a única imagem existente no workspace; com várias imagens, exige um caminho explícito.
- O arquivo enviado permanece na pasta de entrada do ComfyUI; esta versão ainda não faz limpeza automática desse upload.

### Cartões de anexos no chat

- Mensagens com arquivos passam a exibir cartões com nome, formato e tamanho.
- O banco persiste somente metadados mínimos; caminhos absolutos não são salvos.
- O botão para abrir o original aparece apenas na mensagem recém-enviada, enquanto o caminho original ainda está disponível em memória. No histórico reaberto, o cartão continua informativo, mas não tenta abrir um caminho local que não foi persistido.
- O conteúdo técnico do marcador de metadados é removido antes de enviar histórico ao agente/chat e antes de exibir/copiar o texto da mensagem.

### Integração com o agente

Novas ferramentas registradas:

- `workspace_create_powerpoint`
- `workspace_edit_powerpoint`
- `workspace_create_pdf`
- `workspace_manage_pdf`
- `workspace_upscale_image`

Pedidos comuns de criação de apresentações, PDF, planilhas, Word e relatórios podem direcionar a conversa ao agente. O prompt do agente especifica os limites de cada formato.

## Arquivos principais alterados/adicionados

- `agent/documents.py`: criação/edição de PPTX, criação e operações estruturais de PDF, salvamento atômico de pacotes Office e aprimoramentos de XLSX.
- `agent/tools.py`: schemas e execução das novas ferramentas.
- `agent/orchestrator.py`: instruções específicas para o agente e resolução automática do único arquivo elegível para `/upscale`.
- `agent/commands.py`: ajuda, comando `/upscale` e detecção de intenção de criação de documentos.
- `image_generator.py`: catálogo de modelos e pipeline real de super-resolução via ComfyUI.
- `memory/attachments.py`: serialização segura dos metadados dos anexos, sem caminhos absolutos.
- `interface.py`: cartões de anexos e remoção dos metadados internos da apresentação e do contexto do modelo.
- `requirements.txt`: inclusão de `reportlab` para criação de PDF.
- `README.md`: capacidades, comandos e limites documentados.
- `tests/test_documents_advanced.py`, `tests/test_image_upscale.py`, `tests/test_attachments.py` e `tests/test_agent.py`: novos testes.

## Validação executada

- `python -m py_compile *.py agent/*.py memory/*.py tests/*.py`: concluído sem erro.
- `python -m unittest discover -s tests -v`: **141 testes aprovados**.
- Testes funcionais locais de criação/leitura de PPTX, edição e inclusão de slide, criação de PDF, mesclagem, extração, rotação, atualização de metadados e criação de XLSX formatado.
- Teste de integração do pipeline ComfyUI com respostas HTTP simuladas, verificando upload, workflow, polling, download e preservação do original.
- Testes de segurança para caminhos relativos, metadados sem caminhos absolutos e bloqueio de host ComfyUI remoto.

## O que não foi testado neste ambiente

- Interface CustomTkinter aberta no Windows real: layout, escala, renderização e clique dos cartões ainda precisam de validação visual.
- Geração e upscale com uma instalação real do ComfyUI e modelos efetivamente presentes.
- Chamadas reais ao Ollama usando cada modelo/perfil e tool calling em hardware de usuário.
- Dependências não foram instaladas no computador do usuário; `reportlab` passa a fazer parte de `requirements.txt` e será instalado pelo preparo padrão.

## Limitações remanescentes e próxima etapa

- Streaming token a token do agente e medição/otimização do tempo até o primeiro token ainda não foram implementados.
- Diagnóstico visual do espaço em branco no chat depende do `data/diagnostico_layout.json` e de uma captura gerada no Windows.
- OCR e edição visual livre de PDF não estão presentes.
- Edição PPTX não altera texto dividido em múltiplos runs.
- A telemetria de VRAM livre para AMD/Intel ainda não está implementada de forma equivalente à NVIDIA.
- Limpeza de uploads temporários enviados ao ComfyUI ainda não está implementada.
- A Etapa 4 (Manager/instalador modular, atualização e distribuição com seleção de componentes) permanece pendente; o instalador atual ainda instala o conjunto listado em `requirements.txt`.

## Referências técnicas consultadas

- API oficial do ComfyUI: https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml
- Guia oficial de API do ComfyUI: https://docs.comfy.org/development/comfyui-server/comms_routes
- Código/nós oficiais do ComfyUI: https://github.com/Comfy-Org/ComfyUI

A integração de upscale segue os endpoints e os nós documentados pelo próprio ComfyUI. Os testes locais simulam respostas da API; não constituem validação de execução GPU real.
