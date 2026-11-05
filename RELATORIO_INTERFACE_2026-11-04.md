# Gac.IA — revisão da interface (04/11/2026)

## O que mudou

- O botão `+` agora abre um painel maior, rolável e organizado em três grupos:
  - **Criar e editar arquivos:** Word, Excel, Slides, PDF e E-books.
  - **Criatividade e desenvolvimento:** Imagens e Código.
  - **Recursos da assistente:** Pesquisa na web, Voz e Anexar arquivo.
- Cada ferramenta tem ícone, nome e descrição curta. Os itens executam uma ação existente ou preparam um pedido contextual no campo de mensagem; não são apenas itens decorativos.
- A barra lateral pode ser recolhida e restaurada sem reconstruir a conversa ativa.
- O topo da conversa mostra o perfil configurado do usuário, quando houver nome definido.
- A pesquisa na web passou a usar controles compactos: botão de ativação e botão separado de configurações.
- A configuração da pesquisa permite escolher profundidade rápida (até 2 fontes), intermediária (até 5) ou profunda (até 8 e consulta complementar). Essa preferência é independente do perfil do modelo de linguagem.
- Preferência de profundidade é persistida em `config.json`; o roteamento automático de pesquisa continua ativo.
- Popups de ferramentas e pesquisa são fechados corretamente durante reconstruções de tema/interface.

## Decisão técnica importante

Esta entrega **não migra o framework gráfico para PySide6**. A janela atual é uma aplicação CustomTkinter com centenas de integrações diretas a widgets Tk, eventos, diálogos, callbacks e atualização de streaming. Substituir a janela por Qt sem antes separar o controlador e os serviços exigiria reescrever o ciclo de eventos, renderização de mensagens, anexos, menus de contexto, voz, popups, configurações e callbacks do agente. Fazer uma troca superficial criaria uma interface aparentemente nova, mas com alto risco de quebrar recursos existentes.

Por isso, esta revisão melhora o layout no framework que já funciona. A migração real para PySide6 continua sendo uma etapa arquitetural separada: primeiro extrair a lógica de conversa/streaming e serviços de um controlador independente da GUI; depois implementar a camada Qt e validar paridade funcional. Não foi adicionada dependência PySide6 nem alegada uma migração que não aconteceu.

## Limitações conhecidas

- A priorização configurável de fontes oficiais, científicas ou notícias ainda não existe no mecanismo atual; a tela informa isso explicitamente, em vez de oferecer controles sem efeito.
- O menu Ferramentas prepara solicitações para Word, Excel, Slides, PDF e E-books. A geração efetiva continua no orquestrador/agente existente após o usuário enviar o pedido.
- Os ícones usam caracteres/emoji disponíveis no sistema, não um pacote vetorial externo.

## Verificações realizadas

- `python -m py_compile interface.py`: aprovado.
- `python -m pytest -q`: **230 testes passaram e 34 subtestes passaram**.
- Não foi possível executar uma inspeção visual real da janela neste ambiente: CustomTkinter não está instalado e não há sessão gráfica utilizável para iniciar a aplicação. Portanto, a geometria e a interação visual no Windows ainda precisam de validação prática.

## Arquivos preservados

A atualização parte do pacote `GacIA_Atualizada_2026-11-04.zip`. Os módulos de agente, memória, voz, geração de imagens, Ollama, banco de dados e instalador foram mantidos; as alterações funcionais desta etapa concentram-se em `interface.py`.
