# Correção: e-books em PDF como formato padrão

Data: 04/11/2026

## Decisão de formato

A ferramenta principal `workspace_create_ebook` agora gera PDF (`.pdf`) como padrão para e-books destinados à distribuição digital, incluindo entrega como anexo em plataformas como Kiwify. A ferramenta EPUB 3 foi preservada separadamente em `workspace_create_epub`, para pedidos explícitos de EPUB refluível.

## Recursos do PDF editorial

- Capa editorial com título, subtítulo, autor, cor de destaque e imagem de capa opcional.
- Página de expediente com descrição, autor, idioma e informação sobre direitos sem presumir titularidade.
- Sumário com líderes pontilhados, numeração e links internos, além de marcadores de navegação do PDF.
- Quebra de página por capítulo e hierarquia de títulos/subtítulos.
- Markdown básico: negrito, itálico, links HTTP(S), listas, citações, código e separadores.
- Imagens opcionais por capítulo, com legenda; PNG, JPEG e WEBP podem ser normalizados via Pillow.
- Cabeçalho, rodapé, numeração e metadados de título, autor, assunto, criador e palavras-chave.
- Tamanhos A4 (padrão), A5 e Letter.
- Limites de segurança para capítulos, conteúdo, imagens e PDF final (100 MiB).
- Gravação atômica e recusa a sobrescrever arquivos existentes.

## Integração

- O menu E-books e seu prompt agora solicitam e-book PDF profissional.
- `workspace_create_ebook` força a extensão `.pdf`, inclusive se o modelo sugerir `.epub` por hábito.
- `workspace_create_epub` mantém EPUB explícito como formato alternativo.
- O prompt do orquestrador orienta o PDF como padrão e EPUB apenas mediante pedido explícito.
- Os e-books são gravados na pasta isolada da geração atual, conforme o fluxo de exportação existente.
- ReportLab e pypdf já estão incluídos em `requirements-office.txt`; nenhuma dependência nova foi adicionada.

## Validação

- `python -m compileall -q agent interface.py`: aprovado.
- `python -m unittest discover -s tests -q`: 283 testes aprovados.
- `python -m pytest -q`: 283 testes aprovados e 39 subtestes aprovados.
- Teste de integração confirma que `workspace_create_ebook` gera PDF mesmo quando recebe nome terminado em `.epub`.
- Teste separado confirma que `workspace_create_epub` continua gerando EPUB 3 válido.
- PDF de amostra renderizado em 5 páginas; conferidos visualmente capa, sumário, capítulo, ilustração e paginação.
- pypdf confirmou metadados, marcadores de navegação e anotações de links internos do sumário.

## Limitações

- A qualidade editorial depende também da qualidade e organização do conteúdo produzido pelo modelo. O gerador formata, mas não garante precisão factual do texto.
- A capa e imagens internas são opcionais; a ferramenta não busca nem gera imagens por si só. Ela incorpora caminhos de imagem existentes e validados no workspace.
- PDF é layout fixo; para leitores com fonte redimensionável e fluxo reconfigurável, solicitar EPUB explicitamente.
- O ambiente de desenvolvimento validou a geração local do PDF, mas a versão final deve ser conferida também no leitor de PDF e no fluxo de upload da plataforma escolhida.
