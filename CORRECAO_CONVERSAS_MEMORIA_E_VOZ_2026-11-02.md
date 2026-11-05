# Correção — Conversas, memória permanente e cancelamento de voz

## Menu da lista de conversas
- O clique com o botão direito foi associado aos botões da lista lateral e aos widgets internos criados pelo CustomTkinter.
- O menu oferece **Fixar conversa/Desafixar conversa** e **Apagar conversa** em vermelho.
- Conversas fixadas são ordenadas antes das demais.
- Apagar uma conversa remove somente sua linha em `conversas_gacia` e suas mensagens em `historico`.
- A exclusão pede confirmação e, quando necessário, cancela uma geração associada à conversa. Um tombstone impede respostas atrasadas de recriar o chat.

## Memórias independentes
- Foi adicionada a tabela `memorias_salvas`, separada do histórico dos chats.
- Pedidos explícitos como `Lembre-se de que ...`, `Guarde na memória: ...`, `Remember that ...` são registrados sem uma chamada adicional ao modelo.
- Memórias salvas são adicionadas ao contexto do chat comum e do agente, como dados/contexto e não como instruções do sistema.
- Mensagens individualmente fixadas em versões anteriores são copiadas para essa tabela antes da exclusão do chat.
- A migração é aditiva: não apaga as tabelas ou conversas existentes.

## Cancelamento da fala
- O thread da interface não chama mais `pygame.mixer.music.stop()`/`unload()` durante a reprodução.
- O botão de parar sinaliza um `threading.Event`; o worker que iniciou o mixer observa o evento e executa `stop`/`unload` no próprio thread, evitando chamadas concorrentes ao recurso global `pygame.mixer.music`.
- O fallback SAPI usa o loop externo do pyttsx3 quando disponível, permitindo observar cancelamento e chamar `engine.stop()` no mesmo thread que criou a engine.
- O encerramento da aplicação não descarrega o mixer a partir da thread da interface.

## Testes
- Testes automatizados de persistência, fixação/ordenação, exclusão isolada, memórias independentes, bloqueio de gravação tardia, menu contextual da lista lateral e cancelamento de voz.
- A interface real, o driver de áudio, o pyttsx3/SAPI e os alto-falantes ainda devem ser validados no Windows do usuário.
