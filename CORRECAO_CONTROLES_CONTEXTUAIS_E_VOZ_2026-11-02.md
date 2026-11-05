# Correção de menu contextual e controles de voz — 02/11/2026

## Menu de contexto das mensagens
- Cada widget Tk da mensagem recebe o bindtag `GacIAMessageContext`.
- O bindtag não depende do caminho Tcl do widget, que pode ser reutilizado quando o histórico é reconstruído.
- O menu oferece Fixar/Desafixar e Apagar mensagem; a ação de apagar fica destacada em vermelho e mantém confirmação.
- O binding global permanece como fallback para widgets internos incomuns.

## Conversa ao vivo
- Um controle adicional aparece somente enquanto a conversa ao vivo está inicializando ou ativa.
- O controle silencia apenas a entrada do microfone; não encerra a conversa nem interrompe a voz de saída.
- O áudio já enfileirado é descartado ao silenciar, os segmentos VAD são reiniciados e resultados de inferência concluídos após o mute são suprimidos.

## Leitura em voz alta
- O botão de leitura alterna de `🔊` para `🔇` durante a reprodução.
- Clicar novamente no mesmo botão interrompe a reprodução e restaura `🔊`.
- Cada reprodução possui seu próprio evento de cancelamento, evitando que um cancelamento atrasado seja perdido ou interrompa uma fala posterior.
- A interrupção também tenta parar a reprodução de fallback SAPI.

## Validação
- Compilação Python: aprovada.
- Testes automatizados: 70 aprovados.
- Integridade do ZIP: validada após empacotamento.
- Não foi possível executar interface gráfica, microfone físico, áudio Windows ou Ollama neste ambiente; esses itens exigem teste no computador Windows de destino.
