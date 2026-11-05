# Relatório técnico — Gac.IA

**Revisão:** 04/11/2026  
**Base:** pacote `melhorar.zip` enviado nesta conversa  
**Ambiente de validação:** Linux, Python 3.13.5

## Resultado da revisão

A revisão partiu do projeto existente; não houve reconstrução do zero. As alterações priorizaram compatibilidade com instalações existentes, redução de trabalho desnecessário por mensagem, previsibilidade de consumo de memória, roteamento automático e confiabilidade de execução.

## Alterações realizadas

### Modelos e hardware

- Novas instalações passam a sugerir Qwen 3.5 2B, 4B e 9B nos perfis leve, intermediário e avançado.
- A estimativa de download usa os limites superiores publicados para evitar subestimar espaço em disco: até 3,1 GB, 4,0 GB e 7,6 GB, respectivamente. O consumo durante a execução é maior que o tamanho do download.
- Configurações existentes e tags de modelos personalizados/legados são preservadas; abrir o assistente de recursos não troca silenciosamente o modelo selecionado.
- Recomendações de modelo usam RAM livre e VRAM livre quando medidas. VRAM total não é tratada como VRAM disponível.
- O perfil avançado exige condições conservadoras de RAM e VRAM livre; contexto sugerido limitado a 8K (4K no perfil leve) para reduzir picos de memória.
- A recomendação automática de geração SDXL agora exige pelo menos 8 GB de VRAM livre medida e 16 GB de RAM. Se a VRAM livre não puder ser medida, o recurso não é pré-selecionado automaticamente.
- O catálogo ComfyUI não marca checkpoints como recomendados usando apenas a VRAM total; apresenta aviso explícito quando a VRAM livre é desconhecida.
- A avaliação de capacidade local avisa quando o computador está abaixo do mínimo ou quando não há dados suficientes para recomendar modelos maiores.

### Modo Pensar mais e Ollama

- Adicionado controle opcional de Pensar mais na interface, com preferência persistente.
- A integração consulta `/api/show` para descobrir os valores de `thinking` aceitos pelo modelo e envia o valor exato suportado ao `/api/chat`.
- A descoberta é armazenada em cache por 10 minutos para evitar uma chamada de metadados em toda mensagem.
- Falhas transitórias de consulta não são armazenadas no cache, permitindo nova tentativa.
- Quando o modelo não expõe controle de pensamento, a Gac.IA informa a limitação e mantém instruções de planejamento/revisão sem fingir que o modelo entrou em um modo especial.
- O modo rápido continua sendo o padrão; Pensar mais é opcional e pode aumentar o tempo de resposta.

### Agente, ferramentas e latência

- Pedidos explícitos de criação de arquivos TXT, JSON e CSV são reconhecidos pelo roteador de comandos, além dos fluxos já existentes.
- Adicionado fallback estruturado quando o modelo retorna uma resposta vazia sem chamadas nativas de ferramenta: solicita JSON, valida o nome da ferramenta contra o registro local e valida que os argumentos são um objeto antes da execução.
- O fallback respeita os limites de rodadas/chamadas e não executa nomes de ferramentas arbitrários.
- O modo Pensar mais instrui o agente a planejar, verificar e revisar o resultado, sem expor cadeia de raciocínio privada.
- Adicionados registros de métricas de execução: duração de rodada, tempo de ferramentas e dados de geração disponíveis no Ollama, sem registrar prompts completos.
- A interface mantém streaming e limita o contexto por perfil. Isso reduz picos e trabalho desnecessário, mas não garante maior velocidade de geração token a token; o desempenho real depende do modelo, hardware, contexto e backend.

### Interface e documentação

- Tema escuro passa a ser o padrão para novas instalações, conforme o layout aprovado. Configurações de tema já salvas são preservadas.
- Assistente de recursos exibe alertas de capacidade e recomendações conservadoras.
- Documentação de instalação/modelos atualizada com os perfis Qwen 3.5, tamanhos de download, limites de contexto, modo Pensar mais e preservação de modelos existentes.

## Validação executada

- **230 testes automatizados passaram** com `python -m unittest discover -s tests`.
- Sintaxe de todos os 94 arquivos Python verificada por AST sem erros.
- `config.example.json` validado como JSON.
- Os testes cobrem descoberta de suporte a thinking, cache e falhas transitórias, limites de hardware, VRAM livre versus total, recomendações de ComfyUI, roteamento de arquivos e fallback seguro de ferramentas.

## Limitações desta validação

Os testes foram executados em Linux com mocks/stubs onde apropriado. Não foi possível validar nesta execução:

- inicialização da interface CustomTkinter em Windows;
- instalação/atualização real no Windows;
- velocidade real e VRAM no RTX 3060;
- respostas reais do Ollama com cada tag Qwen 3.5;
- integração ponta a ponta com ComfyUI, geração de imagem, áudio e dispositivos locais.

Portanto, os 230 testes aprovados demonstram a aprovação da suíte automatizada disponível, não certificam funcionamento em todos os hardwares ou ausência total de falhas.

## Próximas validações recomendadas no Windows

1. Extrair o pacote em uma pasta nova e executar `preparar.bat` e `iniciar.bat`.
2. Conferir se `config.json`, conversas, memória, workspaces e modelos da instalação antiga continuam preservados ao migrar manualmente os dados desejados.
3. Testar os modelos Qwen 3.5 2B/4B/9B no Ollama instalado, começando pelo perfil recomendado para a memória livre detectada.
4. Ativar Pensar mais e confirmar no log se o modelo oferece controle de thinking; comparar resposta rápida e aprofundada.
5. Testar TXT/DOCX/XLSX/PPTX/PDF, pesquisa, voz e ComfyUI; observar RAM/VRAM e tempos registrados.

## Segurança da distribuição

O ZIP é montado pelo empacotador do projeto, que exclui `config.json`, bancos de dados, logs, backups, workspaces, modelos, caches e runtimes. Ele inclui somente o marcador `data/.gitkeep` da pasta de dados para não distribuir conteúdo pessoal.
