# Correção de relevância de imagens, uso de VRAM e tradução de prompts — 04/11/2026

## Resumo

Esta revisão corrige a seleção de imagens fora do tema e a preparação de VRAM antes de gerar imagens para apresentações. Também automatiza a tradução dos briefs visuais de português para inglês usando o próprio Ollama local. O texto dos slides e a conversa continuam em português.

## Diagnóstico do `gacia.log`

O log enviado pelo usuário registra a criação do plano de apresentação em 04/11/2026 às 21:39:55 e, logo depois, duas tentativas de geração visual bloqueadas porque havia somente **1.699 MB de VRAM livre**. O limite de primeira carga era 3.500 MB. O arquivo não registra os termos "Minecraft" nem "sífilis"; portanto, confirma a falha de disponibilidade de VRAM, mas não identifica qual imagem específica foi escolhida.

As chamadas aparecem em sequência, não há evidência no log de um único lote com várias imagens concorrentes. O problema era que a aplicação tentava a geração local repetidamente sem liberar primeiro a memória ocupada pelos modelos já residentes.

## 1. Relevância e fidelidade temática

- A âncora do assunto é extraída do pedido original, removendo palavras comuns de comando e cortesia em português (por exemplo: "por favor", "poderia", "crie", "apresentação").
- O planejador não é mais tratado como fonte confiável para `image_query` e `image_prompt` livres. Esses campos são ignorados; consultas e prompts são reconstruídos a partir do pedido original, do título do slide e do conteúdo textual validado.
- Antes de usar uma imagem do Wikimedia Commons, o código exige que a âncora principal esteja no título ou na descrição de metadados do arquivo. A licença continua sendo validada separadamente. Um arquivo licenciado, mas sem correspondência temática, não é baixado nem inserido.
- A pesquisa mantém o tema global na consulta, em vez de pesquisar somente um subtítulo isolado.
- Os prompts enviados ao gerador local também são obrigados a conter o assunto principal traduzido; o assunto não pode ser substituído por outro no campo de prompt retornado pelo tradutor.
- O prompt negativo usa uma lista genérica controlada pelo programa, não conteúdo livre do planejador.

**Limite conhecido:** a checagem do Commons é textual (título e descrição), não é um classificador visual dos pixels. Ela bloqueia incompatibilidades evidentes como um arquivo nomeado/descrido como ilustração médica sem relação com Minecraft, mas não prova o conteúdo visual de qualquer imagem. Um futuro verificador visual offline exigiria outro modelo e mais VRAM; ele não foi adicionado para não competir com Ollama/ComfyUI.

## 2. Tradução automática local

- O Ollama traduz uma única vez os briefs de todos os slides para inglês, com saída JSON estruturada e temperatura zero.
- A tradução acontece no endpoint local configurado para Ollama; não usa Google Translate, DeepL nem serviço externo.
- A tradução recebe apenas o pedido original, os títulos e o conteúdo textual dos slides. Hints de imagem inventados pelo planejador não são enviados.
- O PPTX permanece em português; somente a consulta externa e o prompt de imagem são em inglês.
- Se o Ollama não responder ou a tradução falhar, a aplicação usa um template de prompt em inglês com o assunto original preservado em vez de cancelar a apresentação.
- Quando a tarefa for apenas buscar imagens no Commons, o modelo Ollama permanece aquecido. Ele só é descarregado antes de uma geração local que realmente precise da VRAM.

O parâmetro `keep_alive: 0` do endpoint `/api/chat` descarrega o modelo após a solicitação vazia, conforme a documentação oficial do Ollama: https://github.com/ollama/ollama/blob/main/docs/api.md.

## 3. Preparação e serialização da GPU

- A geração local é executada em sequência, com no máximo duas imagens por apresentação.
- O workflow do ComfyUI define `EmptyLatentImage.batch_size = 1`.
- Uma trava global serializa geração e upscale dentro da Gac.IA; não são submetidos dois workflows pesados simultaneamente pelo programa.
- Antes da primeira geração, a aplicação solicita que o Ollama descarregue o modelo usado no planejamento/tradução.
- A aplicação consulta `GET /queue` do ComfyUI. Se houver workflow ativo ou pendente, não tenta liberar memória nem inicia outra carga concorrente.
- Com a fila vazia, solicita `POST /free` com `unload_models: true` e `free_memory: true`, conforme o esquema da API atual: https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml.
- Depois, consulta o `nvidia-smi` local e aguarda a liberação de memória por até sete leituras, sem chamadas externas.
- Primeira carga do modelo de imagem: mínimo de 3.500 MB livres. Geração seguinte, reutilizando o checkpoint já carregado: mínimo de 2.000 MB livres.
- Em ambos os casos, a geração é bloqueada se a GPU estiver a 82 °C ou mais, ou com utilização de 80% ou mais. Se uma tentativa local falhar por falta de recursos, a aplicação não repete a mesma carga pesada para todos os slides.
- Depois de concluir a sequência, a memória ociosa do ComfyUI pode ser liberada novamente, desde que sua fila esteja vazia.

A rota `/free` e a rota `/queue` constam na documentação de comunicação do servidor ComfyUI: https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx.

## 4. Testes adicionados/atualizados

- Rejeição de arquivo do Commons com título/descrição de ilustração de sífilis quando a âncora pedida é `minecraft`, sem baixar o arquivo.
- Aceitação de arquivo cuja descrição contém a âncora Minecraft.
- Extração correta de âncoras em pedidos como "Por favor, pode criar uma apresentação bonita sobre Minecraft com shaders?".
- Verificação de que hints livres do planejador não contaminam a tradução local.
- Verificação de que o conteúdo do pedido continua ancorado no prompt inglês.
- Verificação da geração local em sequência, com reutilização do checkpoint na segunda imagem e limite de duas imagens.
- Verificação de trava global de concorrência para workflows ComfyUI.
- Verificação de que `/free` só é chamado quando a fila está vazia e usa os campos `unload_models` e `free_memory`.
- Verificação das decisões de VRAM, temperatura e utilização.

Resultados nesta revisão:

- `python -m compileall -q .`: aprovado.
- `python -m unittest discover -s tests -q`: **284 testes aprovados**.
- `python -m pytest -q`: **284 testes aprovados e 39 subtestes aprovados**.

## Limitações da validação

O ambiente de revisão não tem uma instância ComfyUI conectada nem a RTX 3060 do usuário. Os testes de GPU, fila e chamadas de API são unitários com recursos simulados; portanto, não afirmam que uma geração real foi concluída neste ambiente. A validação final de temperatura/VRAM e a inspeção visual da apresentação precisam ocorrer no Windows do usuário.
