# Gac.IA — Assistente local

Assistente desktop em Python com interface nativa PySide6/Qt, tema escuro padrão (claro opcional), conversa via Ollama,
histórico SQLite, pesquisa web opcional e recursos de voz carregados sob demanda.

## Instalação modular e gerenciador (Windows 10/11 x64)

1. Extraia a pasta da Gac.IA em um local com espaço livre e permissão de escrita.
2. Execute `instalar.bat`. O instalador procura Python 3.13 x64 e, se necessário, tenta instalá-lo pelo Windows Package Manager (`winget`).
3. O núcleo obrigatório instala somente a interface, comunicação HTTP e suporte básico a imagens. Depois da configuração inicial de boas-vindas, a segunda etapa permite escolher Documentos/Produtividade (Word, Excel, PowerPoint e PDF), OCR, pesquisa web, voz/microfone e aceleração NVIDIA opcional. As dependências Python de cada grupo são instaladas somente quando selecionadas. Voz e OCR ficam desmarcados por padrão.
4. A aceleração CUDA do Faster-Whisper é opcional e só é oferecida quando `nvidia-smi` confirma um driver NVIDIA operacional. Ela instala wheels cuBLAS 12/cuDNN 9 dentro do `.venv` (download adicional de centenas de MB), sem alterar o CUDA global. Em AMD, Intel ou CPU-only, a transcrição usa CPU/INT8. Não são instalados drivers de vídeo.
5. O instalador preserva um `.venv` Python 3.13 x64 válido. Se o ambiente for incompatível, incompleto ou estiver sem o executável esperado, ele é renomeado para `.venv_backup_<data>` em vez de apagado.
6. Para reabrir o assistente de recursos na interface, use Configurações → Personalizar recursos. Também é possível abrir `gerenciador.bat` para adicionar/atualizar componentes e executar diagnóstico. Recursos opcionais ausentes começam desmarcados; recursos já instalados ou parcialmente instalados ficam marcados para atualização/reparo. Componentes desmarcados não são desinstalados automaticamente.
7. Execute `iniciar.bat` para abrir a Gac.IA. Antes de iniciar, o atalho verifica se as dependências obrigatórias da interface PySide6 estão presentes na `.venv`; se faltarem, instala/repara automaticamente apenas o núcleo. Ollama e modelos de linguagem são componentes externos, detectados e verificados durante o uso.

`preparar.bat` revalida ou repara o ambiente sem apagar conversas, configurações, banco de dados, modelos, caches, workspaces ou runtimes. A seleção modular é registrada em `.gacia-components.json`, arquivo local que não é incluído no ZIP de distribuição. Se esse manifesto estiver ausente, a atualização usa uma seleção conservadora baseada nos módulos que já estão instalados. A reparação automática feita pelo `iniciar.bat` é limitada ao núcleo obrigatório e preserva os componentes opcionais existentes.

Modelos de linguagem do Ollama, Whisper e checkpoints de imagem não são baixados silenciosamente. Em instalações novas, o assistente recomenda Qwen 3.5 2B/4B/9B segundo a memória disponível; baixar o modelo exige marcar uma opção explícita. Tags antigas salvas pelo usuário são preservadas até uma troca deliberada. O Gerenciador de Modelos do ComfyUI também exige confirmação antes de cada download. O instalador pode oferecer Ollama pelo `winget`; em caso de falha, use https://ollama.com/download. Consulte `GUIA_MODELOS_E_RECURSOS.md` para detalhes e limitações.

No popup **+ → Gerar Imagens**, o campo **Endereço local do ComfyUI** permite informar a porta local usada pelo Desktop (por exemplo, `http://127.0.0.1:8190`). Por segurança, somente endereços loopback HTTP são aceitos. Uma instalação portátil legada iniciada pela Gac.IA continua usando a porta padrão `8188`; para outra porta, inicie o Desktop já configurado nela.

### Requisitos do sistema e Windows 10

O instalador da Gac.IA exige Windows x64 e CPython 3.13 x64. Para o Ollama no Windows, a documentação atual exige Windows 10 22H2 ou mais recente; aceleração NVIDIA depende de driver compatível (a documentação lista 551.61 ou mais recente), enquanto AMD usa ROCm/HIP ou Vulkan conforme a GPU/driver. A Gac.IA pode continuar rodando no Windows 10, mas a Microsoft encerrou o suporte geral em 14 de outubro de 2025; mantenha o ESU aplicável ou considere migrar para um sistema com suporte. (Fontes: [requisitos do Ollama para Windows](https://github.com/ollama/ollama/blob/main/docs/windows.mdx) e [aviso da Microsoft sobre o fim do suporte](https://support.microsoft.com/pt-br/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025).)

## Inventário e reaproveitamento

`inventario_ambiente.py` é uma verificação somente leitura. Ele lista versões dos pacotes, hardware, espaço livre, estado do servidor Ollama, modelos já baixados no Ollama e repositórios disponíveis no cache Hugging Face. Para Ollama remoto, usa o endereço configurado em `config.json`/`GACIA_OLLAMA_URL`. O cache Hugging Face é reconhecido pelas variáveis `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `HF_HOME` e pelo caminho padrão do usuário.

## Detecção de hardware e aceleração

O módulo `hardware.py` detecta sistema, arquitetura, CPU, núcleos, RAM e GPUs
NVIDIA/AMD/Intel sem instalar drivers nem alterar o Windows. A detecção é
informativa: uma GPU identificada não significa que todos os motores tenham
backend compatível com ela.

- **Ollama:** gerencia sua própria aceleração. Conforme versão, driver e GPU,
pode utilizar CUDA (NVIDIA), ROCm (AMD compatível) ou Vulkan (incluindo GPUs
AMD/Intel compatíveis). A Gac.IA não força um backend do Ollama.
- **Faster-Whisper:** o backend CUDA do CTranslate2 é destinado a GPUs NVIDIA e
exige cuBLAS para CUDA 12 e cuDNN 9. Se CUDA não estiver disponível, a Gac.IA
usa CPU/INT8 automaticamente. Se a inferência CUDA falhar, também tenta CPU.
- **AMD/Intel na transcrição:** continuam podendo usar a Gac.IA pela CPU. A
GPU pode acelerar o Ollama quando suportada, mas não é usada diretamente pelo
Faster-Whisper atual deste projeto.
- **Preparação:** `preparar.bat` detecta o hardware e verifica o runtime. Não
instala drivers de vídeo nem CUDA/cuDNN do sistema, pois isso depende do modelo
da GPU, driver e versão do Windows. O objetivo é evitar downloads enormes e
incompatíveis em computadores que não precisam deles.

O modo de dispositivo do Whisper começa em `Automático (recomendado)`. CUDA e
CPU também podem ser escolhidos manualmente nas configurações.

## Dados e atualização

- Configurações locais: `config.json` (os valores padrão estão em `config.py`; `config.example.json` é apenas uma referência sem preferências pessoais).
- Histórico/memórias: `data/memory.db`.
- Logs: `gacia.log`.
- Workspaces, backups, exportações e imagens: subpastas de `data/`.
- O projeto não apaga nem migra destrutivamente bancos antigos.

### Pacote limpo e atualização

Execute `empacotar.bat` para gerar `dist/Gac.IA-source.zip`. O empacotador inclui
código, testes, documentação e scripts, mas exclui configurações locais (`config.json`),
banco de dados, logs, workspaces, backups, exportações, imagens geradas, caches,
ambientes virtuais e runtimes baixados. Isso evita distribuir conversas, projetos
importados, imagens ou preferências de outra instalação.

Ao atualizar uma instalação existente, feche a Gac.IA, faça backup de
`data/memory.db` e extraia os arquivos novos sobre o diretório atual. Preserve
seu `config.json` e todo o conteúdo de `data/`; depois execute `preparar.bat`.
O empacotador nunca modifica nem remove os dados da pasta de origem. O
`gerenciador.bat` também permite adicionar/atualizar dependências selecionadas;
ele não atualiza o código-fonte automaticamente, pois esta distribuição ainda
não está vinculada a um repositório oficial de releases.

## Instalador e atualizações pelo GitHub

O instalador `GacIA-Setup.exe` é construído para Windows x64 e instala o código
da Gac.IA em uma pasta escolhida pelo usuário. Na primeira instalação, ele abre
o preparador modular para instalar CPython 3.13 e os componentes selecionados.
O instalador não inclui Ollama, ComfyUI, modelos, conversas, configurações nem
arquivos de usuário.

Depois de instalar, use **Atualizar Gac.IA** na barra lateral. A página de
releases abre no navegador. Baixe o `GacIA-Setup.exe` da versão mais recente,
feche a aplicação e execute o instalador sobre a instalação existente. Ele
atualiza o código e preserva `config.json`, conversas, workspaces, modelos e
demais dados locais. O preparador de dependências continua disponível em
**Gerenciar recursos**.

Este canal usa um repositório GitHub privado. Cada pessoa que for instalar ou
atualizar precisa estar autorizada nesse repositório e entrar na própria conta
GitHub no navegador. Não inclua tokens de acesso do mantenedor no aplicativo.
As versões são separadas em dois canais. Usuários recebem o canal **estável**,
que abre somente a release estável mais recente. A instalação de desenvolvimento
abre a lista de releases para você validar versões preliminares antes da
publicação estável. Para publicar uma versão estável, use uma tag como
`v0.1.1`; para uma prévia, selecione `development` no workflow manual e informe
uma versão como `0.1.1-dev.1`. O GitHub Actions marca essa release como
pré-lançamento e compila o instalador com o canal embutido. Depois da validação,
publique a versão estável seguinte; os usuários não recebem pré-lançamentos.

## Pesquisa web

A busca usa DDGS/DuckDuckGo e retorna títulos, links e resumos do mecanismo.
Ela não baixa nem executa páginas. Os resultados externos são dados não
confiáveis e podem estar incompletos, indisponíveis ou desatualizados.

## Testes

```bat
.venv\Scripts\python.exe preparar_verificar.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe empacotar_distribuicao.py
```

Os testes automatizados são ferramentas de desenvolvimento e não são executados
durante a instalação ou preparação normal. O instalador valida os imports dos
componentes selecionados e `pip check`; para solicitar a suíte completa
manualmente, execute `instalador.ps1` com `-RunTests`.

O verificador compila somente o código ativo e ignora workspaces/importações e
pastas de runtime; a compilação é feita em memória e não cria `__pycache__`.
A validação automatizada não substitui um teste no Windows com Ollama,
microfone, alto-falantes e CUDA reais.

### Diagnóstico de layout no Windows

Se houver espaço em branco inesperado abaixo do campo de mensagem, execute
`diagnostico_layout.bat`. A ferramenta abre a interface temporariamente;
redimensione a janela para reproduzir o problema e pressione **F8** para capturar
(ou aguarde 45 segundos). Ela registra tamanho, posição, geometria solicitada e
configuração das grades dos principais widgets, e grava
`data/diagnostico_layout.json`. Não salva preferências nem altera o layout. Envie
essa saída junto com uma captura de tela para identificar qual contêiner está
reservando o espaço.

## Agente de projetos e documentos

A partir desta versão, a conversa pode acionar um agente que usa chamadas de ferramentas do Ollama. Os comandos são `/analise`, `/create`, `/codigo`, `/executar`, `/imagem`, `/upscale` e `/ajuda`. Digitar `/` na caixa de mensagem mostra sugestões. Anexar arquivos pelo botão `+` também ativa automaticamente o agente.

### Formatos

- Código e texto: TXT, Markdown, Python, Java, JavaScript/TypeScript, HTML, CSS, PHP, SQL, C/C++, C#, Go, Rust, JSON, YAML, TOML, XML, shell, PowerShell e outros formatos de texto comuns.
- Documentos: leitura de DOCX, XLSX, XLSM, PPTX, PDF, CSV e TSV.
- Criação: DOCX com estilos e Markdown básico; XLSX com múltiplas abas, tabelas e gráficos simples; PPTX editável em 16:9 com cinco temas e layouts visuais; PDF paginado com tabelas; e-books em PDF profissional, com capa editorial, sumário clicável, capítulos, imagens, paginação e metadados; EPUB 3 permanece opcional.
- Edição: DOCX (substituição de texto em parágrafos/tabelas), XLSX/XLSM (células e fórmulas) e PPTX (substituição dentro de cada trecho textual e inclusão de slides). A substituição em PPTX não atravessa divisões internas de texto do PowerPoint.
- PDF: mesclar arquivos, extrair páginas, girar páginas, atualizar metadados e OCR opcional em PDFs digitalizados. Não há edição arbitrária do layout/texto interno. Para OCR, instale o componente Python e também o mecanismo Tesseract do sistema com os dados de idioma desejados. Para formatos antigos `.doc`/`.xls`, converta primeiro para `.docx`/`.xlsx`. EPUB é mantido como formato refluível opcional, com criação/leitura; e-books comuns usam o gerador editorial em PDF. A edição completa de um EPUB existente ainda não está implementada.
- O agente trabalha em uma cópia de arquivos importados na pasta `data/workspaces`, preservando os originais. Quando altera arquivos, gera um ZIP atualizado em `data/exports`.

### Segurança do agente

- ZIPs são extraídos com validação contra caminhos de saída (Zip Slip), links simbólicos, pastas de ambiente/cache e limites de tamanho/quantidade.
- Ferramentas de leitura e gravação operam somente dentro do workspace atual.
- Execução de código é limitada às verificações `compileall` e `unittest` do projeto e exige confirmação na interface. O agente não recebe um terminal arbitrário nem permissão para instalar pacotes.
- Ainda não existe isolamento de processo em nível de sistema operacional (por exemplo, contêiner/VM). Portanto, autorize testes somente de projetos em que confia.

### Geração de imagens

O gerador utiliza a API local do ComfyUI em `http://127.0.0.1:8188`. A experiência padrão recomenda instalar o ComfyUI Desktop pelo site oficial: https://www.comfy.org/download. A Gac.IA não executa o instalador externo nem baixa checkpoints sem autorização. Inicie o ComfyUI Desktop e depois conecte pela API; instalações portáteis antigas em `runtime/ComfyUI` continuam aceitas e podem ser iniciadas pela Gac.IA. A documentação oficial recomenda Desktop para usuários comuns e mantém a instalação portátil como opção avançada; instalação manual cobre diferentes sistemas e tipos de GPU. (Fonte: https://github.com/Comfy-Org/ComfyUI#installing.) Coloque um checkpoint compatível na pasta de modelos e informe o nome exato em `+` → `Gerar Imagens`, ou use `/imagem descrição`. Arquivos resultantes ficam em `data/generated_images`.

O agente também cria/edita apresentações `.pptx`, cria PDFs e organiza PDFs existentes (mesclar, extrair páginas, girar páginas e atualizar metadados). Para criar PDFs, `reportlab` é instalado com as dependências do projeto. A edição de PDF é estrutural; não equivale a reescrever texto ou redesenhar elementos internos. Para super-resolução, anexe uma única imagem e use `/upscale`, ou informe `/upscale caminho/relativo/da/imagem.png` dentro do workspace. A Gac.IA consulta os modelos disponíveis em `ComfyUI/models/upscale_models`, envia a imagem ao ComfyUI local e salva um novo PNG, sem sobrescrever o original. Com várias imagens, informe o caminho desejado. Nenhum modelo de upscale é baixado automaticamente.

### Compatibilidade de modelos

O agente usa a mesma seleção de perfil/modelo do chat e chama ferramentas pelo endpoint `/api/chat` do Ollama. Modelos com suporte a tool calling nativo são preferíveis; se a primeira resposta vier vazia e sem chamada de ferramenta, o agente tenta uma única rota de compatibilidade JSON, limitada ao catálogo de ferramentas registradas. Isso não garante que qualquer modelo pequeno consiga usar ferramentas com confiabilidade: o desempenho precisa ser testado. A arquitetura não fica presa a um modelo específico.

A pesquisa web do agente só fica disponível quando o controle **Buscar na Web** já existente está ativado. Não foi criado um segundo comando de pesquisa.

## Modo Pensar mais

O botão 🧠 no campo de mensagem alterna uma preferência persistida em `config.json`. Quando ativado, a Gac.IA adiciona instruções de análise/revisão e consulta `/api/show` para descobrir os controles de pensamento que o modelo realmente anuncia. Se suportar o recurso, o chat e o agente enviam o valor exato de `thinking.values` em `think`; resultados do endpoint `/api/show` ficam em cache por 10 minutos. Falhas transitórias não são armazenadas em cache. Modelos sem metadados continuam funcionando, mas o modo se limita às instruções de revisão e às verificações das ferramentas: mais tempo de geração não garante ausência de erros. O conteúdo do campo interno `thinking` não é exibido como resposta ao usuário.

## Compatibilidade e seleção de modelos

Nas instalações novas, os perfis recomendados são `qwen3.5:2b` (Leve), `qwen3.5:4b` (Intermediário) e `qwen3.5:9b` (Avançado). O catálogo público atualmente informa aproximadamente 2,7–3,1 GB, 3,3–4,0 GB e 6,6–7,6 GB, respectivamente; o uso total em execução é superior e depende do contexto, cache, runtime e offload. O programa preserva tags anteriores já configuradas e só as altera quando o usuário escolhe outro perfil no assistente. Referência: [catálogo oficial Qwen 3.5 no Ollama](https://ollama.com/library/qwen3.5).


## Segurança de edição e limites do agente

- Antes de substituir um arquivo existente pelo agente, a Gac.IA cria uma cópia versionada em `data/backups/<workspace_id>/`.
- O agente limita o total de chamadas de ferramentas por tarefa e reutiliza resultados de chamadas idênticas para evitar ciclos redundantes.
- A lista de conversas verifica se o widget ainda está ativo antes de atualizá-lo, evitando acesso a componentes destruídos durante a troca de painéis.
- O placeholder do campo de mensagem permanece estável; a presença de anexos é comunicada pela barra de status.

Os backups ficam no computador local. Revise periodicamente a pasta `data/backups` para controlar o espaço ocupado.


## Recuperação do workspace antigo

O estado ativo anterior apontava para uma cópia interna desatualizada do projeto. Para impedir que o agente continue alterando silenciosamente essa cópia, o workspace ativo foi desvinculado nesta distribuição. A pasta antiga foi preservada como dado local; para trabalhar na versão atual, anexe novamente o ZIP/pasta do projeto pela interface. Diretórios internos de runtime (`data/workspaces`, `data/backups`, `data/exports` e `data/generated_images`) são ignorados na listagem e exportação do agente.

## Idioma e personalização

Em **Configurações**, é possível selecionar Português ou English. A escolha é
salva em `config.json` e orienta tanto os textos principais da interface quanto
o idioma padrão das respostas da assistente. Também é possível salvar o nome ou
apelido pelo qual a Gac.IA deve chamar o usuário e escolher um estilo de resposta:
Equilibrada, Amigável, Profissional, Didática ou Objetiva. A personalidade altera
somente o tom e a forma de explicar; não altera permissões nem regras de segurança.

## Histórico: fixar e apagar conversas

Clique com o botão direito sobre uma conversa na lista lateral para abrir as
opções **Fixar conversa/Desafixar conversa** e **Apagar conversa**. Conversas
fixadas aparecem primeiro na lista. Apagar aparece em vermelho e exige
confirmação; a ação remove somente aquele chat e suas mensagens, sem apagar
configurações, workspaces ou memórias permanentes. As colunas de fixação são
adicionadas por migrações SQLite aditivas, preservando os dados antigos.

Informações importantes podem ser salvas explicitamente com frases como
`Lembre-se de que prefiro exemplos em Python` ou `Guarde na memória: meu projeto
se chama Gac.IA`. Elas ficam em uma tabela independente e são incluídas no
contexto de conversas futuras. Mensagens anteriormente fixadas individualmente
também são preservadas como memórias permanentes quando o chat é apagado.
Uma resposta atrasada de uma conversa excluída não pode recriá-la no banco.

## Pesquisa web por perfil

O controle **Buscar na Web** habilita a pesquisa para o chat e para o agente nos
três perfis. O orçamento máximo por pesquisa é:

- **Leve:** até 2 fontes, uma consulta focada e timeout curto.
- **Intermediário:** até 5 fontes, para comparação de perspectivas e síntese contextualizada.
- **Avançado (Top):** até 8 fontes, distribuídas em duas consultas complementares
  quando útil, favorecendo o cruzamento de fontes.

O pacote `ddgs` é importado somente quando uma pesquisa é solicitada; o início da
aplicação e tarefas sem pesquisa não carregam esse módulo. A região de busca
acompanha o idioma configurado (Brasil/português ou Estados Unidos/inglês).

A pesquisa retorna trechos, datas quando disponíveis e links diretos. Os perfis Intermediário e Top podem extrair texto limitado de até uma e duas páginas públicas, respectivamente; não fazem leitura integral de sites nem validação independente de todas as afirmações. Snippets e páginas são pistas, não prova: compare fontes, cite URLs e separe fatos de inferências. Conteúdo externo é dado não confiável, nunca instrução para a Gac.IA. O tempo de pesquisa e o tempo até o primeiro token são registrados nos logs sem gravar o prompt completo; pesquisas profundas ainda aumentam a latência por ocorrerem antes da resposta.


## Atualizações de implementação (03/11/2026)

- `FASE2_3_4_5_IMPLEMENTACAO_2026-11-03.md`: pesquisa automática, extração limitada de páginas, validação do ComfyUI e telemetria de memória.
- `ETAPA3_IMPLEMENTACAO_2026-11-03.md`: criação/edição de PPTX, criação e operações de PDF, melhorias de XLSX, super-resolução neural pelo ComfyUI e cartões de anexos. O relatório separa os testes automatizados das validações ainda necessárias no Windows real.


## Atualização da distribuição (03/11/2026)

- `ETAPA4_DISTRIBUICAO_2026-11-03.md`: instalador modular, manifesto local de componentes, gerenciador independente da interface principal, preservação de ambientes incompatíveis e integração padrão com ComfyUI Desktop oficial.

## Revisão final desta atualização (03/11/2026)

- Corrigido o reparo de ambientes `.venv` incompletos: a pasta inteira é preservada em backup antes de criar um ambiente novo.
- O Gerenciador não pré-seleciona componentes opcionais ausentes; somente componentes instalados/parciais ficam marcados.
- Voz/Whisper fica desmarcada por padrão na primeira instalação para reduzir downloads e instalação desnecessária.
- A geração de imagens permite configurar um endpoint HTTP loopback do ComfyUI e valida host/porta/path antes de conectar. A porta personalizada é respeitada para uma instância já iniciada; o launcher portátil legado continua na porta 8188.
- O script PowerShell usa BOM UTF-8 para preservar corretamente os textos em português no Windows PowerShell 5.1.
- A revisão final passou em 178 testes automatizados. Ver `REVISAO_FINAL_2026-11-03.md` para limitações e validações ainda necessárias no Windows real.


## Assistente de configuração de recursos

Depois da primeira configuração de boas-vindas, a Gac.IA abre um segundo assistente para escolher componentes. Ele detecta CPU, arquitetura, RAM, GPUs/VRAM e estado do driver NVIDIA; sugere um perfil de Ollama e recursos opcionais. O usuário pode reabrir a tela em Configurações. A escolha é salva em `config.json`; o instalador registra componentes Python em `.gacia-components.json`.

O assistente não baixa modelos grandes por inferência. A seleção de Qwen 3.5 é separada do download: a caixa de download inicia um pull explícito no servidor Ollama configurado e mostra o progresso. Os tamanhos indicados são aproximados para as tags do catálogo e podem mudar conforme variante/quantização. O perfil Avançado só deve ser usado quando RAM e VRAM livres forem suficientes; o tamanho do arquivo baixado não representa a memória total necessária em execução. ComfyUI é software externo: a tela abre o site oficial e o usuário instala o aplicativo. Tesseract também é externo e requer instalação separada; escolher as bibliotecas OCR não instala o executável de sistema.

## Gerenciamento de modelos do ComfyUI

A tela `+ → Gerar Imagens → Gerenciar modelos` identifica arquivos nas pastas `models/checkpoints`, `loras`, `vae`, `controlnet`, `upscale_models`, `embeddings`, `clip_vision`, `text_encoders` e `diffusion_models`. O catálogo inicial oferece quatro checkpoints SDXL para estilos diferentes: Juggernaut XL v9 (fotografia), DreamShaper XL Turbo (arte/estilo rápido), Animagine XL 4.0 Opt (anime) e RealVisXL V5 FP16 (fotografia). O usuário também pode informar organização/repositório e nome exato de arquivo `.safetensors` do Hugging Face e escolher a categoria.

Antes de baixar, a Gac.IA consulta metadados, verifica espaço livre, tamanho e SHA-256 quando disponível, preserva downloads parciais para retomada e não sobrescreve por padrão. A substituição exige opção explícita e conserva a versão anterior em `.bak` (ou `.bak.N`). Remoção é uma ação separada, com confirmação, restrita a arquivos-modelo regulares dentro das pastas permitidas. O gerenciador não valida a segurança do conteúdo de modelos de terceiros: confira autoria, integridade, licença e reputação do repositório. Somente `.safetensors` são aceitos pelo downloader personalizado atual; outros formatos podem aparecer no inventário se forem adicionados manualmente.

O catálogo inclui informação de licença conforme o repositório específico consultado. Juggernaut XL v9 indica CreativeML Open RAIL-M; DreamShaper XL Turbo indica `openrail++` em seu repositório dedicado; Animagine XL 4.0 indica CreativeML Open RAIL++-M; RealVisXL V5.0 indica OpenRAIL++. Os termos completos de cada autor precisam ser lidos antes de distribuição ou uso comercial. Fontes dos modelos: [Juggernaut XL v9](https://huggingface.co/RunDiffusion/Juggernaut-XL-v9), [DreamShaper XL Turbo](https://huggingface.co/Lykon/dreamshaper-xl-turbo), [Animagine XL 4.0](https://huggingface.co/cagliostrolab/animagine-xl-4.0) e [RealVisXL V5.0](https://huggingface.co/SG161222/RealVisXL_V5.0).

Os parâmetros de geração são presets iniciais por checkpoint e podem ser ajustados; eles não garantem um resultado visual específico. A seleção automática respeita o estilo salvo, mas só escolhe modelos que o endpoint local do ComfyUI realmente anuncia. A VRAM livre é usada nas recomendações quando detectada; VRAM livre zero não é confundida com a memória total. Uma GPU com 12 GB não garante que qualquer resolução ou workflow caiba integralmente na VRAM, especialmente quando outros aplicativos já a ocupam.

## Produtividade, e-books e apresentações

- **Word (`.docx`)**: documentos A4, estilos, cabeçalho/rodapé com paginação, parágrafos com Markdown básico e tabelas. Leitura e substituições no texto/tabelas.
- **Excel (`.xlsx`)**: múltiplas abas, estilos de cabeçalho, filtros, congelamento, dimensionamento de colunas e gráficos de barras/linhas/pizza com intervalos informados. Leitura, edição de células e fórmulas.
- **PowerPoint (`.pptx`)**: apresentação 16:9 com temas Modern, Dark, Creative, Minimal e Corporate; layouts de capa, conteúdo, seção, duas colunas, citação, métricas, imagem, tabela e encerramento; notas do apresentador. Arquivo continua editável no PowerPoint. É um gerador de apresentações, não um editor visual colaborativo equivalente ao Canva.
- **PDF**: criação paginada com parágrafos e tabelas; mesclar, extrair páginas, rotacionar e alterar metadados. OCR é opcional e requer Tesseract e dados de idioma no sistema. A edição livre de texto/imagens dentro do PDF e OCR de layout complexo não estão incluídos.
- **E-books (`.pdf`)**: formato padrão de distribuição, apropriado para anexos em plataformas como Kiwify; capa editorial, expediente, sumário clicável, capítulos, hierarquia tipográfica, listas, citações, blocos de código, imagens opcionais por capítulo, paginação e metadados. A ferramenta EPUB 3 (`.epub`) continua disponível separadamente quando solicitada explicitamente para leitores refluíveis. A edição de e-books existentes não está incluída.

Esses recursos são executados por bibliotecas especializadas em vez de baixar um modelo de IA separado para cada formato. O modelo de linguagem interpreta a solicitação e chama ferramentas locais; por isso, um modelo pequeno pode apresentar menor confiabilidade no uso de ferramentas. A qualidade visual final de documentos e apresentações deve ser conferida no aplicativo de destino.

## Latência e telemetria

As operações de rede e agente são executadas fora da thread da interface. A pesquisa Top divide o orçamento de até oito fontes entre consultas complementares, em vez de solicitar oito extras além da consulta principal. A telemetria local registra duração da pesquisa, TTFT (tempo até o primeiro token), tempo total, carga do modelo, avaliação do prompt, tokens gerados e tokens/s quando fornecidos pelo Ollama. Isso permite medir o desempenho no computador real; não há benchmark universal no pacote, porque o resultado depende do modelo, contexto, quantização, hardware e estado do ComfyUI/Ollama. O contexto de inferência agora é limitado por perfil (4K no Leve e 8K nos demais) para reduzir picos de RAM/VRAM; isso pode reduzir a capacidade de manter conversas/documentos muito longos numa única chamada.

## Interface PySide6 — revisão de 04/11/2026

A janela principal e o gerenciador de componentes usam widgets nativos PySide6/Qt. O layout possui barra lateral recolhível, cabeçalho com perfil e modelo, chat central, tema escuro/claro e campo de mensagem com menu `+` categorizado. O menu reúne Word, Excel, Slides, PDF, E-books, Imagens, Código, Pesquisa na web, Voz e anexos; os controles compactos incluem microfone, Chat ao vivo, pesquisa web, preferências de fontes, Pensar mais e envio. A camada de interface foi separada dos módulos de Ollama, SQLite, agente, anexos, pesquisa e voz. `legacy/interface_customtkinter.py` é apenas uma cópia histórica usada por testes de regressão e não é carregada por `main.py`. Consulte `RELATORIO_MIGRACAO_PYSIDE6_2026-11-04.md` para arquitetura, verificações e limitações da validação visual.
