# Gac.IA — Etapa 4: distribuição, preparação e gerenciador

**Data:** 03/11/2026  
**Base:** Etapa 3 atualizada  
**Plataforma do instalador:** Windows 10/11 x64  
**Python alvo:** CPython 3.13 x64

## Resumo

Esta etapa transforma a preparação da Gac.IA em um fluxo modular, recuperável e auditável. O núcleo e as ferramentas de escritório são obrigatórios; pesquisa na web, voz e aceleração CUDA do Whisper são componentes separados. Um gerenciador independente da interface principal permite verificar e adicionar recursos sem exigir que CustomTkinter ou as dependências de voz estejam funcionando.

A atualização preserva configurações, banco de dados, workspaces, modelos, caches e runtimes. O instalador não remove componentes desmarcados: a seleção registrada é mesclada com o manifesto anterior. Ambientes virtuais incompatíveis são renomeados para uma pasta de backup em vez de apagados.

## O que foi implementado

### 1. Dependências modulares

| Arquivo | Conteúdo | Seleção |
|---|---|---|
| `requirements-core.txt` | CustomTkinter, HTTP, Pillow e inclusão do pacote Office | Obrigatório |
| `requirements-office.txt` | DOCX, XLSX, PPTX e PDF | Incluído no núcleo |
| `requirements-web.txt` | DDGS | Opcional |
| `requirements-voice.txt` | NumPy, SoundDevice, Faster-Whisper/CTranslate2, Pygame, Edge TTS, pyttsx3 e pywin32 no Windows | Opcional |
| `requirements-nvidia-cuda.txt` | cuBLAS 12 e cuDNN 9 para Whisper | Opcional, somente NVIDIA |
| `requirements.txt` | Agregador tradicional de core + web + voz | Compatibilidade/manual; não inclui CUDA |

CUDA não é instalada apenas porque uma GPU NVIDIA foi identificada. O instalador exige que `nvidia-smi` execute corretamente e pergunta antes de instalar os pacotes adicionais, que podem exigir centenas de megabytes. Se o componente CUDA não for escolhido ou não estiver utilizável, o Whisper permanece em CPU/INT8. AMD e Intel continuam com o caminho de CPU no Faster-Whisper atual; isso não impede o Ollama de selecionar seu próprio backend compatível.

### 2. Instalador PowerShell

`instalador.ps1` oferece quatro modos:

- `Install`: preparação inicial, seleção dos componentes opcionais e oferta de instalação do Ollama pelo `winget`.
- `Prepare`: repara/revalida os componentes já registrados no manifesto.
- `Update`: atualiza as dependências dos componentes registrados ou explicitamente selecionados.
- `Status`: executa o inventário sem instalar dependências.

O fluxo valida Windows x64, procura CPython 3.13 x64, cria ou reutiliza `.venv`, instala o núcleo e os opcionais escolhidos, executa `pip check`, valida imports/sintaxe e roda os testes automatizados. O manifesto só é salvo depois de as verificações terminarem com sucesso.

Se uma `.venv` existir, mas não for CPython 3.13 x64 válida — inclusive se a pasta estiver incompleta ou sem `Scripts\python.exe` — ela é movida para `.venv_backup_<data>` com sufixo em caso de colisão. Não é apagada.

### 3. Gerenciador independente

`gerenciador.py` utiliza apenas Tkinter da biblioteca padrão, portanto pode abrir mesmo quando a interface principal ou CustomTkinter estiverem com problema. Ele oferece:

- seleção de pesquisa web, voz e CUDA do Whisper; componentes opcionais ausentes começam desmarcados e os instalados/parciais ficam marcados para atualização/reparo;
- estados instalado, parcial e ausente;
- instalação/reparo em uma janela PowerShell separada;
- diagnóstico do hardware, dependências, Ollama, ComfyUI e espaço livre;
- acesso à aplicação, páginas oficiais e pasta de dados.

Desmarcar um componente significa apenas não atualizá-lo naquela operação. O pacote não é desinstalado e o manifesto mantém os componentes previamente registrados. Não existe uma opção de remoção automática de dependências compartilhadas.

### 4. Manifesto e diagnóstico

`componentes.py` é baseado apenas na biblioteca padrão. Ele normaliza a seleção, valida dependências entre componentes, detecta instalações parciais e grava `.gacia-components.json` atomicamente. O manifesto contém apenas o schema, os identificadores de componentes e a versão do Python; não guarda caminhos pessoais.

`inventario_ambiente.py` é somente leitura. Ele lista versões, estados dos componentes, hardware, espaço livre, estado do Ollama e modelos/caches reconhecidos. Componentes parcialmente instalados aparecem como reparáveis, com os módulos ausentes.

### 5. Integração com ComfyUI

A recomendação padrão para novos usuários do Windows agora é o ComfyUI Desktop oficial. A Gac.IA abre a página oficial, mas não baixa nem executa silenciosamente instaladores externos. Depois de instalado e iniciado pelo usuário, a Gac.IA conecta à API local, normalmente em `http://127.0.0.1:8188`.

Instalações portáteis existentes continuam aceitas. O mecanismo automático antigo foi mantido apenas como caminho legado/avançado. Se a rotina legada encontrar uma pasta preexistente incompleta, ela agora a preserva em backup; se a promoção da nova instalação falhar, tenta restaurar a pasta anterior. Modelos/checkpoints de geração e upscale continuam sendo baixados separadamente, por escolha do usuário.

A disponibilidade de aceleração depende da GPU, driver e backend. Não se promete que toda GPU identificada será acelerada pelo Desktop. Quando não houver backend de GPU compatível, o uso em CPU pode ser necessário; a instalação manual oficial do ComfyUI continua sendo uma alternativa para configurações específicas.

### 6. Scripts e distribuição limpa

- `instalar.bat`, `preparar.bat`, `iniciar.bat` e `gerenciador.bat` chamam os fluxos adequados.
- `preparar_verificar.py` aceita `--components` e valida apenas os opcionais selecionados, além do núcleo.
- `empacotar_distribuicao.py` exclui configuração local, banco, logs, workspaces, arquivos importados/gerados, ambientes virtuais, backups de `.venv`, runtimes, caches e manifesto local.
- `.gacia-components.json` foi adicionado ao `.gitignore` e à lista de exclusão do ZIP.

O gerenciador ainda não baixa atualizações do código-fonte: não há um repositório oficial de releases configurado. A atualização do código permanece manual, por ZIP, preservando `config.json` e `data/`.

## Correções adicionais aplicadas nesta revisão

1. A caixa CUDA do gerenciador agora depende de `nvidia-smi` funcional, não apenas do nome da GPU no inventário. Isso evita bloquear atualizações ao abrir a instalação em outro computador sem driver NVIDIA operacional.
2. Componentes desmarcados não são esquecidos pelo manifesto nem desinstalados.
3. O instalador deixa a aceleração CUDA desmarcada por padrão, devido ao download adicional grande; voz/Whisper também fica desmarcada na instalação inicial para evitar instalar bibliotecas nativas sem necessidade.
4. A instalação portátil legada do ComfyUI não remove mais uma pasta preexistente incompleta; a substituição usa backup e rollback.
5. O inventário distingue módulos parciais dos ausentes e informa os itens faltantes.
6. A recomendação de memória do ComfyUI respeita valores de VRAM/RAM livre iguais a zero; zero não é substituído pela capacidade total.
7. A documentação do ComfyUI foi ajustada para não prometer aceleração universal de GPU.
8. A documentação do agregador `requirements.txt` deixa claro que CUDA não faz parte dele.
9. O reparo preserva também uma pasta `.venv` incompleta/corrompida sem `Scripts\python.exe`, evitando tentar criar um novo ambiente sobre arquivos desconhecidos.
10. O Gerenciador não marca automaticamente extras ausentes; isso evita que uma verificação de status instale algo que o usuário não escolheu.
11. A geração de imagens permite configurar um endpoint local loopback do ComfyUI, valida o endereço e respeita a porta personalizada de uma instância já ativa. A inicialização do launcher portátil legado permanece limitada à porta 8188 e informa isso claramente.
12. O instalador e o verificador distinguem CPython x64/AMD64 de ARM64; um Python de 64 bits ARM não passa por engano como ambiente x64.
13. `instalador.ps1` recebe BOM UTF-8 para manter corretamente os textos acentuados no Windows PowerShell 5.1.

## Hardware e compatibilidade

- **NVIDIA:** Ollama gerencia sua própria aceleração. Whisper pode usar CUDA quando o driver for funcional e o componente opcional estiver instalado. ComfyUI depende do backend e do modelo compatíveis.
- **AMD:** Ollama pode usar backend compatível (ROCm/Vulkan conforme GPU e driver). Whisper usa CPU/INT8 nesta implementação. ComfyUI Desktop possui suporte AMD ROCm no Windows para GPUs compatíveis a partir da versão 0.7.0.
- **Intel:** Ollama/ComfyUI dependem do backend disponível para o hardware e driver. Whisper usa CPU/INT8 nesta implementação.
- **CPU-only:** chat local e ferramentas da Gac.IA continuam dependendo do Ollama/modelo escolhido; Whisper pode executar na CPU se o componente de voz estiver instalado, mas será mais lento.

Ollama para Windows atualmente requer Windows 10 22H2 ou posterior. O instalador avisa quando detecta Windows 10 anterior à build 19045, mas não bloqueia a Gac.IA. A Microsoft encerrou o suporte geral do Windows 10 em 14/10/2025; isso é um risco de segurança separado da compatibilidade do Python/Gac.IA.

## Validação executada

- `python -m py_compile *.py agent/*.py memory/*.py tests/*.py`: aprovado.
- `python -m unittest discover -s tests -v`: **178 testes aprovados** na revisão final.
- Testes adicionais cobrem dependências modulares, manifesto, instalação parcial, exigência de driver NVIDIA para CUDA, recomendação do ComfyUI Desktop, preservação/rollback de pasta preexistente, opt-in de componentes, validação de URL local e encaminhamento de portas do ComfyUI, além da distinção entre AMD64 e ARM64 e codificação do PowerShell.
- ZIP: integridade conferida com `unzip -t`.
- Extração limpa: compilação Python e suíte de testes executadas novamente a partir do ZIP.

## Limitações e validações ainda necessárias

Esta validação foi feita em ambiente de desenvolvimento Linux. Não havia PowerShell disponível, portanto `instalador.ps1` foi revisado estaticamente, mas **não foi executado nem analisado pelo parser do PowerShell no Windows**. Antes de considerar a distribuição pronta para todos os usuários, ainda é necessário testar:

1. instalação inicial em Windows 10 22H2 e Windows 11 x64;
2. instalação sem NVIDIA, com NVIDIA e com driver NVIDIA ausente/quebrado;
3. adicionar componentes, reabrir o gerenciador, desmarcar componentes e executar `Prepare`/`Update`;
4. GUI real com CustomTkinter, Ollama, voz/microfone e ComfyUI Desktop/portátil;
5. geração e upscale com modelos reais, além de verificar a porta configurada;
6. preservação da `.venv` e dos dados em uma atualização sobre uma instalação usada.

O ZIP não é um instalador EXE assinado. A distribuição continua sendo código-fonte + bootstrapper PowerShell/BAT, com dependências baixadas sob demanda.

## Fontes oficiais consultadas

- Ollama — requisitos do Windows: https://github.com/ollama/ollama/blob/main/docs/windows.mdx
- Microsoft — fim do suporte ao Windows 10: https://support.microsoft.com/pt-br/windows/deployment/updates-lifecycle/windows-10-support-has-ended-on-october-14-2025
- ComfyUI — instalação e recomendação Desktop: https://github.com/Comfy-Org/ComfyUI#installing
- ComfyUI — download Desktop: https://www.comfy.org/download
- ComfyUI — suporte AMD ROCm no Windows Desktop: https://blog.comfy.org/p/official-amd-rocm-support-arrives
- CTranslate2 — wheels para Windows e versões de Python: https://pypi.org/project/ctranslate2/
- Faster-Whisper — requisitos CUDA/cuBLAS/cuDNN: https://github.com/SYSTRAN/faster-whisper
- NVIDIA — wheels cuDNN para Windows: https://docs.nvidia.com/cudnn/latest/installation/backend/windows/
