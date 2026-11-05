# Atualização — personalização, histórico e pesquisa web

## Preferências do usuário

- Idioma: Português (Brasil) ou English.
- Nome/apelido: salvo em `config.json` e incluído nas instruções do modelo.
- Personalidade: equilibrada, amigável, profissional, didática ou objetiva.
- A personalidade muda estilo, não permissões nem controles de segurança.

## Ações no histórico

- Botão direito em mensagem salva abre menu de contexto.
- Fixar/Desafixar mantém o estado na base SQLite e prioriza mensagens fixadas no contexto.
- Apagar usa confirmação e remove somente o registro da sessão correspondente.
- A coluna `fixada` é criada com migração aditiva; registros históricos existentes não são descartados.
- A exibição do histórico detalhado segue a ordem cronológica.

## Pesquisa na internet

O controle existente **Buscar na Web** habilita a ferramenta no chat comum e no agente. Os limites são aplicados no backend, mesmo se o modelo solicitar uma quantidade maior:

| Perfil | Orçamento máximo | Estratégia |
|---|---:|---|
| Leve | 2 fontes | Uma busca focada, timeout de 6 s |
| Intermediário | 5 fontes | Uma busca, timeout de 8 s |
| Avançado (Top) | 8 fontes | Duas buscas complementares, timeout de 12 s |

A importação de `ddgs` permanece tardia: tarefas sem pesquisa não carregam o pacote. O idioma controla a região de busca. URLs não públicas, esquemas que não sejam HTTP(S), endereços locais e IPs não globais são filtrados.

Os resultados são trechos retornados pelo mecanismo de busca, com URLs para conferência; o sistema não baixa nem lê integralmente as páginas. A assistente recebe instruções para não tratar trechos como prova, citar links e separar evidência, inferência e hipótese.

## Validação desta revisão

- `python -m compileall -q .`: aprovado.
- `python -m unittest discover -s tests -v`: 51 testes aprovados.
- Foram adicionados testes para a ordem cronológica do histórico, persistência/fixação, migração SQLite, orçamento de fontes por perfil, duas consultas no perfil Avançado e disponibilidade da ferramenta nos três perfis.
- Não foi possível realizar teste visual da interface nem teste real com Ollama neste ambiente: CustomTkinter não está instalado e não há display gráfico. A validação final deve ocorrer no Windows do usuário.
