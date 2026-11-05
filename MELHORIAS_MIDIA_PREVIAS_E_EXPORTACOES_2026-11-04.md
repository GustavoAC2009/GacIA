# Melhorias de mídia, prévias e exportações — 04/11/2026

## Apresentações com recursos visuais

- Novas apresentações incluem recursos visuais por padrão, salvo quando o usuário pede explicitamente uma apresentação sem imagens.
- O coordenador escolhe imagens conforme o assunto de cada slide. Por padrão, tenta localizar fotografias/ilustrações no Wikimedia Commons e, quando não encontra recurso adequado ou o download falha, tenta gerar uma ilustração local pelo ComfyUI.
- Pedidos explícitos por imagens geradas por IA usam o ComfyUI; pedidos explícitos por imagens da internet priorizam o Commons. O usuário pode pedir "somente imagens geradas", "imagens da internet" ou "sem imagens".
- A pesquisa de imagens é separada da pesquisa textual da web: a caixa de busca de fontes textuais pode permanecer desativada, mas a coleta de recursos visuais solicitados usa a API do Commons. Essa operação precisa de conexão com a internet.
- O downloader só aceita arquivos de `upload.wikimedia.org`, limita tamanho e tipos MIME, registra autor/crédito, nome, licença, URL da licença e página de origem. Licenças não comerciais (NC) e sem derivadas (ND) são rejeitadas; são aceitas classes como CC0, domínio público, CC BY e CC BY-SA quando identificadas no metadado.
- Os créditos ficam nas notas do slide e em `recursos_visuais/CREDITOS_E_LICENCAS.txt`. Imagens são enquadradas/cortadas para caber no layout. Licenças CC BY-SA podem impor condições adicionais para adaptações; consulte a licença indicada no crédito antes de redistribuir a apresentação.
- A política limita a até cinco imagens obtidas online e até duas ilustrações geradas localmente por apresentação. A geração local respeita a proteção de temperatura/VRAM já existente; falhas de imagem não devem deixar slides vazios.
- Imagens WEBP/BMP são convertidas em memória para PNG quando necessário para incorporação no PPTX; o original não é alterado.

## Paleta de ferramentas

- O botão `+` abre uma janela Qt horizontal e retangular, sem barra de rolagem horizontal.
- Todas as dez ferramentas e recursos são apresentados simultaneamente, em grade responsiva: Word, Excel, Slides, PDF, E-books, Imagens, Código, Pesquisa, Voz e Anexar.

## Isolamento de gerações

- Cada solicitação que cria um documento tem uma pasta exclusiva em `data/exports/<tipo>_<data>_<id>/`.
- Arquivos e recursos visuais de uma apresentação ficam juntos na pasta daquela apresentação, incluindo `recursos_visuais/` e créditos.
- Geração de imagens e super-resolução usam pastas exclusivas em `data/generated_images/`.
- Uma nova geração não exporta novamente o workspace inteiro nem adiciona resultados antigos ao ZIP de uma solicitação simples. A exportação ZIP continua reservada a alterações efetivas de um projeto de trabalho.

## Prévias e navegação

- O chat mostra cartões de prévia após a resposta final quando encontra caminhos existentes para imagens, PPTX, EPUB, PDF, DOCX e XLSX.
- PPTX: prévia simplificada do primeiro slide, incluindo a primeira imagem incorporada quando disponível.
- EPUB: capa existente ou trecho textual do primeiro capítulo.
- PDF: primeira página quando PyMuPDF está instalado; caso contrário, cartão informativo.
- Imagens: miniatura real e dimensões.
- A central Arquivos exibe prévias, permite abrir o arquivo e fornece link clicável para o diretório que contém o arquivo.
- Caminhos reconhecidos no texto da conversa são convertidos em links locais para abrir o diretório correspondente.

## Verificações e limitações

- `python -m compileall -q .`: aprovado.
- `python -m unittest discover -s tests -q`: 273 testes aprovados.
- `python -m pytest -q`: 273 testes aprovados e 39 subtestes aprovados.
- Os testes verificam a política de licenças, download controlado, atribuições, inserção de imagens e compatibilidade WEBP em PPTX, prévias/caminhos na interface via análise estática e isolamento dos diretórios de geração.
- O ambiente de validação não tem PySide6 instalado, portanto não foi possível abrir a janela Qt real nem executar validação visual no Windows. Os resultados acima são testes automatizados e inspeção/compilação de código, não um teste funcional na máquina do usuário.
