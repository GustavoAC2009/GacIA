# Gac.IA — revisão final da atualização de 03/11/2026

## Objetivo

Revisar o pacote da Etapa 4, corrigir problemas concretos encontrados e reduzir atrito para usuários comuns, sem ampliar o escopo com recursos novos desnecessários.

## Correções aplicadas

### 1. Recuperação de ambientes Python incompletos

O instalador verificava a `.venv` somente quando `.venv\Scripts\python.exe` existia. Uma pasta `.venv` parcial/corrompida sem esse executável podia permanecer no caminho e impedir a criação do novo ambiente.

Agora o instalador verifica a pasta `.venv` inteira. Se não houver um CPython 3.13 x64 válido, move toda a pasta para `.venv_backup_<data>` e cria um ambiente novo. O backup não é apagado.

### 2. Instalação inicial mais leve

Voz/Whisper deixa de ser sugerida com base apenas na quantidade de RAM. Ter 8 GB de RAM não significa que a pessoa queira microfone, transcrição local ou bibliotecas nativas adicionais.

O componente de voz agora fica desmarcado por padrão e pode ser instalado depois pelo Gerenciador. A pesquisa web continua sendo oferecida como opção na instalação inicial. CUDA permanece explicitamente opcional e exige driver NVIDIA operacional.

### 3. Gerenciador sem pré-seleções inesperadas

Antes, a pesquisa web ausente era automaticamente marcada ao abrir o Gerenciador. Isso poderia levar alguém a instalar um recurso que pretendia apenas verificar.

Agora componentes opcionais ausentes começam desmarcados. Componentes instalados ou parcialmente instalados ficam marcados para atualização/reparo. Nada é desinstalado ao desmarcar.

### 4. ComfyUI: endpoint local configurável

A interface de geração de imagens agora expõe o endereço local do ComfyUI. Isso corrige a divergência entre a mensagem que dizia ser possível alterar a porta e a ausência de um campo visível para fazê-lo.

A validação aceita somente HTTP loopback (`localhost` ou IP de loopback), sem credenciais, query, fragmento ou caminho arbitrário. Endereços externos são rejeitados antes de qualquer requisição.

A checagem e a inicialização agora recebem o mesmo endereço configurado. Uma instância Desktop já ativa em uma porta personalizada pode ser usada normalmente. O launcher portátil legado ainda inicia na porta padrão 8188; se a pessoa configurar outra porta e a instância estiver desligada, a Gac.IA explica a limitação em vez de iniciar um processo que não atenderá ao endereço solicitado.

### 5. Arquitetura Python sem falso positivo ARM64

A validação anterior considerava apenas a versão e o tamanho do ponteiro. Isso poderia aceitar um Python ARM64 de 64 bits como se fosse x64. O instalador e o verificador agora exigem explicitamente `AMD64`/`x86_64`, coerentes com os wheels e o alvo de distribuição Windows x64.

### 6. Compatibilidade de codificação do PowerShell

O `instalador.ps1` agora usa BOM UTF-8, para que Windows PowerShell 5.1 interprete corretamente acentos e mensagens em português em vez de depender da página de código ANSI local.

### 7. Documentação

README e relatório da Etapa 4 foram atualizados com o comportamento de instalação mais leve, recuperação de `.venv` incompleta e configuração do endpoint local do ComfyUI.

## Validação executada

Ambiente de desenvolvimento: CPython 3.13.5 x64 em Linux.

- `python -m py_compile *.py agent/*.py memory/*.py tests/*.py`: aprovado.
- `python -m unittest discover -s tests -v`: **178 testes aprovados**.
- Testes novos cobrem: distinção AMD64/ARM64, BOM UTF-8 do PowerShell, URL loopback personalizada, rejeição de hosts externos, validação de portas, encaminhamento da URL ao launcher, limite de porta do launcher portátil, pré-seleção opt-in do Gerenciador e recuperação de `.venv` incompleta por verificação estática do script.
- O pacote foi criado pelo empacotador oficial do projeto, validado com `unzip -t`, extraído em pasta limpa e testado novamente com compilação e suíte completa.

## O que não foi possível validar neste ambiente

- O instalador PowerShell não foi executado no Windows nem validado pelo parser do PowerShell: não há `pwsh`/`powershell` neste ambiente.
- A interface CustomTkinter não foi iniciada: CustomTkinter não está instalado no ambiente de revisão e não há sessão gráfica Windows.
- Não foram executados Ollama, microfone, ComfyUI Desktop/portátil, CUDA real, geração de imagem real ou upscale com modelo real.
- Os testes de integração do ComfyUI usam API simulada; não comprovam compatibilidade com cada build/modelo/nó customizado.

Portanto, 178/178 é o resultado da suíte automatizada, não uma declaração de que todos os cenários reais de hardware e Windows já foram certificados.

## Instalação/atualização recomendada

1. Não apague a instalação antiga.
2. Extraia o ZIP novo em uma pasta separada para primeiro teste.
3. Na instalação antiga, preserve `config.json`, `data/`, workspaces, backups, modelos e runtimes.
4. Execute `instalar.bat` na pasta nova; adicione voz/CUDA somente se for usar esses recursos.
5. Depois da preparação, abra `gerenciador.bat` e execute Diagnóstico.
6. Inicie Ollama e ComfyUI separadamente quando necessários; confira o endereço do ComfyUI no popup de geração de imagens.

O pacote de código não inclui `.venv`, modelos, Ollama, ComfyUI, configurações pessoais ou bancos de dados.
