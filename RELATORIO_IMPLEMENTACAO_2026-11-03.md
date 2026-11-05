# Gac.IA — Relatório de implementação e validação

**Revisão:** 03/11/2026  
**Base:** `Gac.IA_Atualizacao_Final_2026-11-03.zip`  
**Pacote gerado:** `Gac.IA_Revisada_2026-11-03.zip`

## Resultado da validação disponível

- **220/220 testes automatizados passaram** (`python -m unittest discover -s tests -v`).
- **48 arquivos Python ativos** passaram na verificação de sintaxe em memória, sem gerar bytecode.
- Os nove layouts de PowerPoint e o tema Creative têm teste de geração e leitura do arquivo `.pptx`.
- O EPUB é validado como ZIP, com `mimetype` na posição e forma exigidas, OPF/XHTML legíveis e proteção contra caminhos internos maliciosos.
- O gerenciador de modelos tem testes para metadados, hash SHA-256, tamanho, retomada, cancelamento, backup antes de substituição, caminhos permitidos e remoção segura.
- O empacotador produziu um ZIP com 82 entradas. `unzip -t` não encontrou erros.
- A inspeção do pacote confirmou que configurações locais, bancos de dados, logs, modelos, workspaces, runtimes, caches e ambientes virtuais não foram incluídos.

**Ambiente de execução dos testes:** CPython 3.13.5, Linux x86_64. Esses resultados comprovam os testes automatizados executados neste ambiente; não equivalem a uma validação de instalação e uso no Windows do usuário.

## Implementações incluídas

### Assistente de configuração e componentes

- Segunda janela após as preferências iniciais, com detecção de sistema, CPU, arquitetura, RAM, GPUs/VRAM e estado do driver NVIDIA.
- Seleção opcional de documentos/produtividade, OCR, pesquisa web, voz/microfone, aceleração CUDA e geração de imagens.
- Recomendação de perfil de modelo de linguagem local conforme a capacidade identificada.
- Opção explícita para baixar o modelo escolhido pelo Ollama, com progresso e cancelamento.
- Preferências persistidas e opção de reabrir em **Configurações → Personalizar recursos**.
- Dependências Python divididas por componente. Componentes desmarcados não são removidos automaticamente; manifestos antigos preservam Office, que antes estava agrupado no núcleo.
- CUDA para Whisper só é selecionável quando o driver NVIDIA é confirmado e a voz está selecionada. Sem CUDA, o caminho CPU continua disponível.
- ComfyUI e Tesseract são tratados como programas externos; a tela orienta para os canais oficiais, em vez de instalar executáveis silenciosamente.

### Modelos de linguagem

O catálogo oferece três perfis Qwen2.5 no Ollama:

| Perfil | Modelo | Tamanho aproximado publicado |
|---|---|---:|
| Leve | `qwen2.5:1.5b-instruct` | 986 MB |
| Intermediário | `qwen2.5:7b-instruct` | 4,7 GB |
| Avançado | `qwen2.5:14b-instruct` | 9,0 GB |

Os tamanhos são aproximados e variam conforme a variante/tag publicada. Nenhum modelo é baixado apenas por abrir a Gac.IA ou concluir a detecção de hardware: o pull depende da caixa de confirmação do usuário.

### ComfyUI e geração de imagens

- Catálogo de checkpoints SDXL para fotografia/realismo, arte/ilustração e anime: Juggernaut XL v9, DreamShaper XL Turbo, Animagine XL 4.0 Opt e RealVisXL V5.0 FP16.
- Presets distintos de sampler, steps, CFG e prompt para cada checkpoint; fallback conservador para modelos desconhecidos.
- Seleção automática do checkpoint instalado conforme o estilo salvo, sem presumir que um modelo ausente existe.
- Inventário de `checkpoints`, `loras`, `vae`, `controlnet`, `upscale_models`, `embeddings`, `clip_vision`, `text_encoders` e `diffusion_models`.
- Download explícito de `.safetensors` do catálogo ou de repositório/arquivo informado pelo usuário no Hugging Face; validação de metadados, tamanho, espaço livre, hash quando publicado, arquivo parcial e cancelamento.
- Não sobrescreve por padrão; substituição exige opção explícita e preserva cópias `.bak` sem colisão. Remoção é separada e restrita às pastas de modelos permitidas.
- O catálogo informa a licença conforme o repositório consultado. A licença e os termos do autor devem ser lidos antes de redistribuir ou usar comercialmente.

O gerenciador personalizado baixa somente arquivos `.safetensors`. Outros formatos podem aparecer no inventário quando adicionados manualmente. O código não embute os modelos: cada checkpoint SDXL ocupa aproximadamente 6,9–7,1 GB e deve ser baixado por escolha do usuário.

### Ferramentas de produtividade

- **Word (`.docx`):** A4, estilos, títulos, listas, negrito, itálico, código inline, tabelas, cabeçalho/rodapé e numeração de página; leitura e substituições em parágrafos/tabelas.
- **Excel (`.xlsx`):** várias abas, formatação de cabeçalho, tabelas, filtros, congelamento, larguras automáticas, gráficos simples (barras, linhas e pizza), leitura e edição de células/fórmulas.
- **PowerPoint (`.pptx`):** 16:9, cinco temas (Modern, Dark, Creative, Minimal e Corporate), nove layouts (capa, conteúdo, seção, duas colunas, citação, métricas, imagem, tabela e encerramento), notas do apresentador e arquivo editável.
- **PDF:** criação paginada com tabelas, leitura de texto, mesclagem, extração de páginas, rotação, metadados e OCR opcional.
- **E-books:** criação EPUB 3 com metadados, capítulos, sumário, estilos e capa PNG/JPEG opcional; leitura de metadados e texto. O formato é produzido sem biblioteca externa adicional.

Essas funções usam bibliotecas especializadas; não exigem um modelo de IA diferente para cada extensão. O LLM interpreta o pedido e aciona ferramentas locais.

### Pesquisa e latência

- Perfis de pesquisa com orçamentos de até 2, 5 e 8 resultados.
- Perfil avançado divide o limite entre duas consultas complementares executadas em paralelo, preservando a prioridade dos resultados da consulta original.
- Deduplicação de URLs e limite de três resultados por domínio.
- Leitura limitada de até duas páginas no perfil avançado; páginas públicas somente, HTTP(S), sem credenciais, portas não padrão ou redirecionamentos; DNS é conferido contra IPs públicos e há limites de timeout/tamanho/conteúdo.
- A interface registra duração de pesquisa, TTFT (tempo até o primeiro token) e tempo total por rota, sem registrar o prompt integral.

A telemetria permite medir a latência no computador de destino, mas **não é um benchmark**. Quando a pesquisa web está ativa, a busca e a leitura de páginas ainda acontecem antes da chamada de chat ao Ollama e, portanto, compõem o tempo até o primeiro token. O paralelismo reduz a duração de consultas complementares, mas não elimina o custo de rede.

## Limitações que permanecem explícitas

1. **Validação de Windows:** o ambiente desta revisão é Linux. Não foi possível executar `instalador.ps1`, PowerShell 5.1, instalador/gerenciador `.bat`, nem interagir com a interface CustomTkinter. Neste ambiente, `customtkinter` não está instalado e não há display gráfico.
2. **Hardware e serviços reais:** não foi possível validar uma RTX/NVIDIA CUDA, AMD/Intel, GPU/VRAM real, Ollama em execução, pull real de modelo, servidor ComfyUI ou geração/upscale real. Os testes destas integrações usam mocks/endpoints simulados.
3. **Voz:** não foi possível testar microfone, alto-falantes, drivers de áudio, Whisper real ou síntese em dispositivo Windows.
4. **OCR:** o componente Python é opcional, mas o executável Tesseract e os dados de idioma precisam ser instalados separadamente. Os testes de OCR usam ferramentas simuladas; não há validação de OCR de documentos reais nesta sessão.
5. **PDF:** não existe edição arbitrária e livre de texto/imagens mantendo o layout interno de qualquer PDF. OCR de tabelas/layouts complexos pode exigir revisão.
6. **EPUB:** criação e leitura estão disponíveis; edição completa de um EPUB existente e exportação MOBI/AZW não estão implementadas.
7. **PowerPoint:** os layouts são templates programáticos editáveis. Não é um editor visual colaborativo com arrastar-e-soltar equivalente ao Canva.
8. **Instalador final:** o pacote entregue é um ZIP de código-fonte limpo; não foi produzido um instalador `.exe` (por exemplo, PyInstaller + Inno Setup).

## Procedimento recomendado de validação no Windows

1. Extrair o ZIP numa pasta nova, sem misturá-lo com workspaces ou ambiente virtual antigos.
2. Executar `instalar.bat`/`instalador.ps1` conforme o guia e selecionar os componentes desejados na segunda tela.
3. Confirmar que a instalação grava o manifesto e que **Configurações → Personalizar recursos** reabre a seleção.
4. Validar chat comum/streaming, pesquisa nos três perfis, leitura de um DOCX/XLSX/PPTX/PDF e criação de EPUB.
5. Iniciar o ComfyUI, apontar a pasta correta, confirmar inventário e baixar primeiro um arquivo de modelo menor antes de iniciar um checkpoint de aproximadamente 7 GB.
6. Validar geração e upscale reais na GPU; verificar uso de VRAM, tempo e saída.
7. Testar voz e OCR apenas se os componentes e os programas externos correspondentes tiverem sido instalados.
8. Executar `python -m unittest discover -s tests -v` no Windows e guardar `gacia.log`/saída do instalador para diagnóstico de diferenças específicas do PC.

## Referências oficiais consultadas

- Ollama Qwen2.5 e tags/tamanhos: https://ollama.com/library/qwen2.5/tags
- Juggernaut XL v9: https://huggingface.co/RunDiffusion/Juggernaut-XL-v9
- DreamShaper XL Turbo: https://huggingface.co/Lykon/dreamshaper-xl-turbo
- Animagine XL 4.0: https://huggingface.co/cagliostrolab/animagine-xl-4.0
- RealVisXL V5.0: https://huggingface.co/SG161222/RealVisXL_V5.0
- Convenções de modelos/pastas do ComfyUI: https://github.com/Comfy-Org/docs/blob/main/basic-concepts/models.mdx e https://github.com/comfyanonymous/ComfyUI/blob/master/extra_model_paths.yaml.example
- Tesseract OCR: https://tesseract-ocr.github.io/tessdoc/Installation.html
- ComfyUI: https://www.comfy.org/download

---

**Conclusão:** as mudanças de código listadas foram implementadas e os testes automatizados disponíveis passaram. A revisão não declara o produto integralmente homologado para Windows/GPU/serviços reais; essa etapa só pode ser concluída executando a nova versão no computador de destino.
