# Revisão de interface e estabilidade — 02/11/2026

## Alterações aplicadas

- Corrigida a distribuição vertical da área de conversa e da caixa de entrada para evitar espaço excedente sob o campo de mensagem.
- Corrigido o cálculo de altura dos blocos de texto: a contagem de linhas visuais não recebe mais uma linha artificial que criava uma faixa vazia.
- Unificadas as rolagens automáticas em callbacks controlados por sessão e geração da visualização. Callbacks antigos são cancelados ao trocar de conversa ou reconstruir a interface; o streaming agrupa rolagens para reduzir atualizações repetidas.
- Mensagens do usuário passaram a permitir seleção de texto e cópia, com botão próprio. Também podem ser editadas pelo botão ou pelo menu de contexto.
- A edição salva o texto no histórico. A resposta antiga não é regenerada automaticamente; isso é informado na janela de edição.
- Caminhos locais reconhecidos são destacados e podem ser abertos com clique. Arrastar o mouse preserva a seleção do texto. Caminhos do Windows com espaços são tratados como um único caminho.
- Comandos reconhecidos aparecem em azul isoladamente, sem colorir o restante da frase.
- O comando `/arquivo` foi substituído por `/analise`; documentação, ajuda, inferência de tarefas e roteamento foram atualizados.
- Valores padrão: tema claro, Whisper automático, Português (Brasil), personalidade equilibrada e voz feminina.
- Adicionado assistente de boas-vindas para escolher tema, voz, dispositivo Whisper, idioma e personalidade. As escolhas permanecem editáveis nas Configurações; a apresentação pode ser desativada.
- A tela inicial de cada nova conversa informa que `/ajuda` apresenta os comandos.

## Verificações

- `python -m py_compile interface.py config.py memory/database.py agent/commands.py agent/orchestrator.py tests/*.py` — aprovado.
- `python -m unittest discover -s tests -v` — 98 testes aprovados.

## Limitação da validação

A suíte automatizada e a compilação foram executadas neste ambiente. Não foi possível fazer uma inspeção visual interativa da janela do CustomTkinter no Windows nem iniciar um ComfyUI real daqui; portanto, a confirmação final do espaçamento em diferentes resoluções/temas e do fluxo real de geração de imagem deve ser feita ao abrir esta versão no Windows. A integração existente do ComfyUI e os dados locais foram preservados.
