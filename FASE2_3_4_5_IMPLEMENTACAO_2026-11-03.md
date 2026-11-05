# Gac.IA — Lote de implementação das etapas 2, 3, 4 e 5

## Escopo desta entrega

Esta entrega continua a partir do ZIP da Fase 1. Não migra CustomTkinter, não substitui Ollama e não reconstrói a aplicação.

O lote implementa melhorias verificáveis em:
- roteamento automático para pesquisa explícita e consultas dependentes de dados atuais;
- leitura limitada de páginas públicas encontradas pela pesquisa;
- validação de disponibilidade da API do ComfyUI;
- validação de checkpoint antes do envio do workflow;
- mensagens de erro HTTP mais informativas;
- detecção de RAM disponível e VRAM livre NVIDIA, quando `nvidia-smi` está disponível;
- recomendação de resolução baseada em memória disponível quando a telemetria existe.

## Arquivos alterados

### `pesquisa_web.py`
- Adicionada `detectar_intencao_pesquisa()`.
- Pedidos como “pesquise na internet”, “busque na web” e “veja as notícias” acionam pesquisa mesmo com o botão manual desligado.
- Sinais comuns de informação dinâmica (preços, versões mais recentes, notícias, lançamentos, compatibilidade atual) também acionam pesquisa.
- Adicionada leitura de até 2 páginas em paralelo, com limite de tamanho, timeout, sem seguir redirecionamentos e com bloqueio de hosts/IPs locais ou privados.
- A extração remove scripts, estilos e elementos não textuais.
- O conteúdo extraído é identificado como texto de página e mantém a URL original para conferência.
- Falhas na leitura não descartam o resultado original do buscador.

### `interface.py`
- O chat normal combina o botão de pesquisa com a detecção automática de intenção.
- Quando há resultados, tenta extrair conteúdo de até uma página no perfil rápido e até duas nos demais perfis.
- A pesquisa e leitura ocorrem na thread de processamento já existente, não na thread principal da interface.

### `comfy_manager.py`
- `/system_stats` só é considerado disponível com HTTP 200 e resposta JSON estruturada com `system` e `devices`.
- A recomendação de parâmetros usa VRAM livre NVIDIA quando disponível e RAM disponível quando detectável; caso contrário, utiliza os valores totais como estimativa.

### `image_generator.py`
- O checkpoint informado é comparado com a lista real de checkpoints exposta pelo ComfyUI antes de enviar o workflow.
- Respostas HTTP de erro do endpoint `/prompt` e do histórico passam a preservar detalhes limitados da resposta.
- Respostas JSON inesperadas recebem mensagens específicas.

### `hardware.py`
- Adicionada leitura de RAM total e disponível.
- Adicionada consulta de VRAM total/livre por GPU NVIDIA usando `nvidia-smi`.
- Não foi adicionada dependência obrigatória: em outras GPUs ou sem `nvidia-smi`, os campos podem permanecer indisponíveis.

### Testes
- Novos testes para intenção de pesquisa explícita e automática.
- Novos testes para extração HTML e bloqueio de destinos locais/privados.
- Novos testes para health check do ComfyUI.
- Novos testes para recomendações baseadas em memória livre.

## Validação executada

- Compilação sintática dos módulos principais e testes.
- Suíte completa: **117 testes aprovados**.
- Testes executados localmente sem iniciar ComfyUI, Ollama ou a janela gráfica.
- A leitura real de páginas e a geração de imagens precisam ser validadas no Windows com internet e ComfyUI instalados.

## Limitações conhecidas e trabalho ainda pendente

Este lote não conclui integralmente as quatro etapas agregadas. Permanecem pendentes:
- medir o tempo até o primeiro token e instrumentar o Core por etapa;
- streaming do agente de ferramentas (atualmente suas chamadas ainda não são transmitidas token a token);
- reduzir o bloqueio da primeira resposta quando uma pesquisa automática é feita antes da inferência;
- verificação de VRAM livre AMD/Intel por APIs específicas;
- testar a API do ComfyUI em execução no Windows, incluindo geração real;
- correção visual final após receber `data/diagnostico_layout.json` e captura de tela;
- gerenciador modular de dependências, upscaler, cartões de arquivos, criação de PPTX/PDF e instalador distribuível.

Não declarar essas funcionalidades como concluídas.

## Pesquisa externa usada para conferir compatibilidade

- README oficial do ComfyUI: https://github.com/Comfy-Org/ComfyUI
  - Confirma os pacotes portáteis separados para AMD, Intel e NVIDIA; pacote CUDA 13/Python 3.13 para NVIDIA moderna; pacote CUDA 12.6/Python 3.12 para NVIDIA série 10 e anteriores.
  - Recomenda ComfyUI Desktop para usuários regulares e descreve o portátil como opção standalone.
- OpenAPI oficial do ComfyUI: https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml
  - Documenta o endpoint `/api/system_stats` como endpoint de estatísticas do sistema.

## Segurança e integridade

A leitura de páginas externas é limitada a HTTP(S), portas 80/443, sem credenciais na URL, sem redirecionamentos, com validação DNS para bloquear IPs não públicos, timeout e limite de 1 MiB. Isso reduz riscos de SSRF, mas não substitui uma sandbox de navegador completa nem elimina toda possibilidade de DNS rebinding.

Nenhum banco de memória, configuração local, workspace, log ou imagem gerada foi removido da pasta original.
