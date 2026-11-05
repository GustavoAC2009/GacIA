# Guia de modelos, dependências e recursos da Gac.IA

## 1. Primeira configuração

A configuração ocorre em duas janelas sequenciais. A primeira salva preferências gerais (idioma, aparência, voz e personalidade). Depois, a segunda tela identifica CPU, RAM, GPUs/VRAM e estado do driver e apresenta as opções de recursos. Ela também fica disponível em **Configurações → Personalizar recursos**.

| Recurso | Dependência | Observações |
|---|---|---|
| Núcleo | `requirements-core.txt` | Sempre necessário; interface, HTTP e suporte básico a imagens. |
| Documentos | `requirements-office.txt` | `python-docx`, `openpyxl`, `python-pptx`, `pypdf`, `reportlab`. |
| OCR | `requirements-ocr.txt` | Também requer Tesseract instalado no Windows e idioma (por exemplo, `por`/`eng`). |
| Pesquisa web | `requirements-web.txt` | DDGS; só usado quando a pesquisa é solicitada/ativada. |
| Voz | `requirements-voice.txt` | Whisper e áudio; modelo Whisper é baixado quando a transcrição é usada. |
| CUDA para Whisper | `requirements-nvidia-cuda.txt` | Opcional, apenas se driver NVIDIA operacional for confirmado e Voz estiver selecionada. |

Recursos não selecionados não são instalados. Recursos desmarcados em uma atualização não são removidos automaticamente.

## 2. Modelos de linguagem Ollama

Nas instalações novas, o assistente recomenda três perfis da família Qwen 3.5:

| Perfil | Tag padrão | Download informado pelo catálogo | RAM/VRAM de referência do seletor |
|---|---|---:|---|
| Leve | `qwen3.5:2b` | 2,7–3,1 GB | 8 GB RAM / 4 GB VRAM |
| Intermediário | `qwen3.5:4b` | 3,3–4,0 GB | 12 GB RAM / 6 GB VRAM |
| Avançado | `qwen3.5:9b` | 6,6–7,6 GB | 16 GB RAM / 10 GB VRAM livre |

Os tamanhos são os intervalos exibidos no [catálogo oficial de tags Qwen 3.5 do Ollama](https://ollama.com/library/qwen3.5), consultado em 04/11/2026. O arquivo baixado não corresponde ao consumo total em execução: pesos carregados, contexto, cache KV, runtime e outros aplicativos também consomem RAM/VRAM. Os valores de RAM/VRAM acima são filtros conservadores de recomendação, não garantia de velocidade. Em CPU-only, o seletor só recomenda o perfil Avançado com pelo menos 32 GB de RAM total e 20 GB livres; GPUs sem medição confiável de VRAM não recebem automaticamente a recomendação Avançada.

Configurações antigas de Qwen 2.5 são preservadas, inclusive para permitir continuidade/reparo de instalações existentes. A seleção de um novo perfil no assistente grava a tag Qwen 3.5 correspondente. O download precisa ser marcado deliberadamente; o pull é enviado ao servidor Ollama configurado e oferece progresso/cancelamento. Se Ollama não estiver instalado ou ativo, a Gac.IA mostra uma orientação em vez de instalar escondido.

## 3. Modelos de imagem no ComfyUI

Instale o [ComfyUI Desktop](https://www.comfy.org/download) ou conecte uma instalação compatível existente. A Gac.IA usa o ComfyUI local, normalmente em `http://127.0.0.1:8188`. A pasta selecionada deve ser a raiz que contém `models/`.

### Checkpoints do catálogo inicial

| Checkpoint | Uso recomendado | Arquivo do catálogo | Licença declarada pelo repositório |
|---|---|---|---|
| Juggernaut XL v9 | Fotografia, retratos, realismo cinematográfico | `Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` | CreativeML Open RAIL-M |
| DreamShaper XL Turbo | Arte estilizada, ilustração, geração rápida | `DreamShaperXL_Turbo_SFWdpmppSde_half_pruned.safetensors` | `openrail++`; leia o texto completo da licença |
| Animagine XL 4.0 Opt | Anime e mangá | `animagine-xl-4.0-opt.safetensors` | CreativeML Open RAIL++-M |
| RealVisXL V5 FP16 | Fotografia e retratos realistas | `RealVisXL_V5.0_fp16.safetensors` | OpenRAIL++ |

Fontes oficiais: [Juggernaut](https://huggingface.co/RunDiffusion/Juggernaut-XL-v9), [DreamShaper XL Turbo](https://huggingface.co/Lykon/dreamshaper-xl-turbo), [Animagine](https://huggingface.co/cagliostrolab/animagine-xl-4.0), [RealVisXL](https://huggingface.co/SG161222/RealVisXL_V5.0). Os arquivos SDXL do catálogo ocupam aproximadamente 6.9–7.1 GB cada. O Juggernaut indica uso confortável com 8 GB de VRAM, mas isso não significa que qualquer workflow/resolução caiba em qualquer situação.

### Categorias suportadas

O inventário reconhece `checkpoints`, `loras`, `vae`, `controlnet`, `upscale_models`, `embeddings`, `clip_vision`, `text_encoders` e `diffusion_models`. Para LoRA, ControlNet, VAE e outros recursos adicionais, informe o repositório e o nome exato de um arquivo `.safetensors` do Hugging Face e selecione a categoria. O gerenciador genérico não presume compatibilidade entre arquiteturas SD 1.5, SDXL, Flux ou outros modelos: o usuário deve conferir a arquitetura do arquivo.

### Integridade, backup e remoção

- Cada download exige confirmação explícita.
- A Gac.IA consulta metadados e exige tamanho remoto informado; valida o SHA-256 quando publicado.
- Download parcial pode ser retomado quando o servidor suporta Range.
- Não sobrescreve por padrão. Com a opção de substituição, a versão anterior vai para `.bak`, `.bak.1` etc.
- Remoção exige confirmação e só atua sobre arquivos-modelo regulares dentro das pastas permitidas.
- A ferramenta baixa `.safetensors`; `.ckpt`, `.pth`, `.pt`, `.bin` e `.onnx` são apenas reconhecidos no inventário se instalados manualmente.

A Gac.IA não audita código, conteúdo, segurança nem licença de todos os modelos externos. Baixe apenas de autores/repositórios confiáveis e confira os termos de uso.

## 4. Documentos e apresentações

| Formato | O que a Gac.IA faz | Limites atuais |
|---|---|---|
| DOCX | Criar, ler, formatar, tabelas e substituição de texto em parágrafos/tabelas | Não é um editor de layout completo; edição de runs complexos pode perder parte da formatação. |
| XLSX/XLSM | Criar, ler, editar células/fórmulas, múltiplas abas, filtros, tabelas e gráficos simples | Macros de XLSM devem ser preservadas e testadas no Excel; nem todo recurso avançado do Excel é manipulado. |
| PPTX | Criar slides editáveis 16:9 com cinco temas, nove layouts, imagens e notas; editar texto e adicionar slides | Gerador de apresentações, não clone do Canva; troca de texto não cruza divisões internas de runs. |
| PDF | Criar, mesclar, extrair páginas, rotacionar, metadados e OCR em PDFs escaneados | Não edita livremente texto/imagens e não preserva layout complexo em OCR. |
| EPUB | Criar EPUB 3 com capítulos, sumário, metadados, CSS e capa; ler metadados e texto | Não reescreve nem edita um EPUB existente; não exporta MOBI/AZW. |

A geração de documentos usa bibliotecas Python locais. Não é necessário um checkpoint de imagem ou LLM específico para gerar cada formato, embora a qualidade do conteúdo dependa do modelo de linguagem que planeja o documento.

## 5. Pesquisa e latência

- Perfil Leve: até 2 fontes, consulta focada.
- Intermediário: até 5 fontes e leitura limitada de uma página pública.
- Top: até 8 fontes no total, divididas entre consulta principal e complementar, com leitura limitada de até duas páginas.
- A leitura é texto público limitado; não é navegação integral de sites nem prova independente.
- Os logs registram milissegundos da busca, TTFT, tempo total, carga do modelo, avaliação do prompt, tokens gerados e tokens/s quando o servidor fornece essas métricas, sem gravar o texto do prompt nessa linha de telemetria.
- O contexto solicitado ao Ollama é limitado por perfil: 4.096 tokens no Leve e 8.192 nos perfis Intermediário/Avançado. Isso controla picos de memória, mas reduz o volume de histórico/documento processado em uma única chamada.
- O botão 🧠 ativa o Modo Pensar mais. A Gac.IA consulta `/api/show` para descobrir os valores suportados pelo modelo e envia o valor exato de `thinking.values`; a descoberta bem-sucedida fica em cache por 10 minutos. Falhas de rede não ficam em cache. Modelo sem controle de pensamento continua respondendo, mas não recebe um `think` inventado.
- Pensar mais pode elevar o tempo de resposta e o número de tokens. Não é garantia de correção: revisão, testes, validação de arquivos e conferência de fontes são necessários.
- Pesquisa antes da inferência aumenta a latência quando ativada; profundidade e velocidade são compromissos distintos.

## 6. O que ainda depende do ambiente do usuário

O pacote de código não inclui os modelos grandes, ComfyUI, Ollama, Tesseract ou bibliotecas NVIDIA. A execução real do gerador depende de um ComfyUI acessível e de modelos compatíveis; OCR depende do executável e dos dados de idioma; voz depende dos dispositivos de áudio e do modelo Whisper; CUDA depende de driver/backend adequados. Os testes automatizados usam mocks para endpoints externos, por isso não substituem teste manual no Windows com GPU, áudio e rede reais.
