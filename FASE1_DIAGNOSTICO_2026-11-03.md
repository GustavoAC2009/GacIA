# Fase 1 — estabilização e higiene da base (03/11/2026)

## Escopo desta entrega

Esta atualização preserva a interface CustomTkinter, o Core atual, os motores,
o agente, o banco SQLite e os fluxos de instalação. Não foi feita migração de
framework nem substituição de motores.

## Alterações efetuadas

1. `preparar_verificar.py`
   - A varredura de sintaxe agora ignora diretórios de runtime e cópias de
     workspaces (`data/workspaces`, `data/backups`, `data/exports`, imagens,
     runtimes, caches e ambientes virtuais).
   - A sintaxe é validada com `compile()` em memória, respeitando o encoding de
     cada fonte com `tokenize.open()`. Isso evita criar bytecode/`__pycache__`
     durante a verificação.
   - A lista de arquivos pode ser inspecionada e testada isoladamente.

2. `diagnostico_layout.py` e `diagnostico_layout.bat`
   - Criado diagnóstico executável no Windows para coletar geometria real da
     janela, dos contêineres de chat e do compositor de mensagens.
   - Registra posições, dimensões reais e solicitadas, gerenciadores e pesos/
     configurações das linhas da grade.
   - Executa sem abrir o assistente de boas-vindas e sem salvar alterações em
     `config.json`.
   - Permite redimensionar a janela e capturar com F8; captura automaticamente
     após 45 segundos e fecha a janela.
   - Grava `data/diagnostico_layout.json`.

3. `empacotar_distribuicao.py` e `empacotar.bat`
   - Criado empacotador de distribuição baseado em uma política explícita de
     exclusão de dados locais.
   - O ZIP inclui fontes, testes, documentação e scripts; exclui config local,
     conversas/memórias, logs, workspaces, backups, exportações, imagens,
     caches, ambientes virtuais e runtimes.
   - A criação é feita em arquivo temporário e finalizada por substituição
     atômica; o diretório original nunca é apagado ou limpo.

4. `config.example.json`, `.gitignore` e `README.md`
   - Adicionada referência de configuração sem nome ou preferências pessoais.
   - Adicionadas regras para backups, diagnóstico, distribuição e backups de
     ambientes virtuais.
   - Documentados empacotamento limpo, atualização preservando dados e coleta
     do diagnóstico visual.

## Diagnóstico do layout existente

A árvore principal em `interface.py` usa `grid` de maneira consistente:

- janela: coluna do chat com peso 1 e linha principal com peso 1;
- `chat_container`: cabeçalho sem expansão, conversa com peso 1 e compositor
  sem expansão;
- compositor: campo de mensagem na primeira linha e barra de status na segunda.

Não foi identificado um `QSpacerItem` (a aplicação nem usa Qt) nem uma linha
extra com peso abaixo do compositor. Há margens externas de 20 px na grade do
chat e 8 px entre a área rolável e o compositor. Isso, isoladamente, não explica
um grande espaço vazio.

A revisão anterior afirma que já corrigiu a distribuição vertical e a altura
calculada do Markdown, mas o ZIP atual não contém captura da janela nem log de
geometria. O ambiente de análise não dispõe de CustomTkinter instalado e não
conseguiu acessar o PyPI para instalá-lo; portanto, não foi possível abrir a
janela gráfica real aqui. Não foi feita alteração arbitrária em `interface.py`.

Para concluir a identificação da área em branco, executar `diagnostico_layout.bat`
no Windows, redimensionar a janela para reproduzir o problema e pressionar F8
(ou aguardar 45 segundos). Enviar o JSON e uma captura de tela. O relatório
separa o espaço dentro do `chat_container`, no compositor e na margem inferior
da janela.

## Validação

- Suíte original antes das alterações: 98 testes aprovados.
- Suíte após as alterações: 102 testes aprovados na cópia extraída do ZIP limpo.
- Sintaxe: 28 arquivos Python ativos verificados; nenhum bytecode é criado pelo
  verificador novo.
- Empacotamento: 51 arquivos no ZIP; testes confirmam a exclusão de dados locais
  e a preservação de código, documentação e scripts.
- Um aviso de recurso SQLite em um teste de migração antigo foi eliminado ao
  fechar explicitamente a conexão de teste; a aplicação não foi alterada por isso.

## Fora do escopo desta fase

- Não foram modificados `interface.py`, `comfy_manager.py`, `image_generator.py`,
  `pesquisa_web.py`, `agent/` ou `instalador.ps1`.
- A correção visual final aguarda medições da janela no Windows.
- Nenhum banco, workspace, configuração ou imagem da pasta original foi apagado.
