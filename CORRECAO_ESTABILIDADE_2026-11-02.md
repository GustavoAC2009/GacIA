# Gac.IA — correção de estabilidade (02/11/2026)

## O que mudou

- O menu de contexto é registrado recursivamente em todos os widgets Tk dos balões. O menu usa o ID e a sessão da mensagem, com Fixar/Desafixar e Apagar (com confirmação).
- Foi removido o clique global que chamava `focus_set()` na janela principal. O foco volta a ser controlado nativamente pelo Tk.
- O botão de salvar configurações fica oculto quando não há diferenças em relação ao último estado salvo.
- Nome/apelido aparece na parte inferior esquerda da barra lateral; configurações permanece à direita.
- O streaming agora é identificado pela sessão e geração da visualização. Eventos atrasados não são inseridos em conversas diferentes. Ao terminar uma resposta cuja área de chat foi reconstruída, o histórico persistido é recarregado.
- A inicialização da captura de voz define o estado antes de iniciar a thread e usa callbacks para sinalizar pronto/finalizado. Uma tentativa é reagendada se a captura anterior ainda estiver terminando.
- O microfone ao vivo calibra o ruído ambiente e usa histerese no detector de atividade de voz. A captura tenta a taxa nativa do dispositivo se 16 kHz não for aceito e reamostra para o Whisper.

## Validação executada

- `python -m compileall -q .`: aprovado.
- `python -m unittest discover -s tests -v`: 62 testes aprovados.
- O ZIP final é verificado com `ZipFile.testzip()`.

## Limitações do ambiente

Este ambiente de construção não tem CustomTkinter, SoundDevice nem acesso ao dispositivo físico de áudio/Ollama do computador-alvo. Portanto, foram executados testes automatizados com doubles/stubs e testes do motor de voz simulando o stream de áudio; não foi possível validar visualmente a GUI nem o microfone real no Windows. O comportamento final deve ser confirmado no equipamento do usuário.
