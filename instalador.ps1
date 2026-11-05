[CmdletBinding()]
param(
    [ValidateSet('Install', 'Prepare', 'Update', 'Status')]
    [string]$Mode = 'Install',
    [string]$Components = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Manifest = Join-Path $Root '.gacia-components.json'

function Write-Stage([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('=' * 68) -ForegroundColor DarkCyan
}

function Test-Python313([string]$Exe) {
    if (-not (Test-Path -LiteralPath $Exe)) { return $false }
    & $Exe -c "import platform,sys,struct; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64') else 1)" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Find-Python313 {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3.13 -c "import platform,sys,struct; raise SystemExit(0 if sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64') else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { return @{ Launcher = $pyLauncher.Source; Args = @('-3.13') } }
    }
    $candidates = @(
        (Join-Path $env:LocalAppData 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    )
    if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Python313\python.exe') }
    foreach ($candidate in $candidates) {
        if (Test-Python313 $candidate) { return @{ Launcher = $candidate; Args = @() } }
    }
    return $null
}

function Ensure-Python313 {
    $python = Find-Python313
    if ($python) { return $python }
    Write-Stage 'INSTALANDO PYTHON 3.13 X64'
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'CPython 3.13 x64 não foi encontrado e winget não está disponível. Instale pelo site oficial: https://www.python.org/downloads/windows/ e execute instalar.bat novamente.'
    }
    Write-Host 'Será usado o instalador oficial do Python pelo Windows Package Manager.'
    & $winget.Source install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        & $winget.Source install --id Python.Python.3.13 --exact --silent --accept-package-agreements --accept-source-agreements
    }
    if ($LASTEXITCODE -ne 0) { throw 'A instalação do Python falhou. Verifique o winget ou instale manualmente pelo site oficial.' }
    $env:Path = (Join-Path $env:LocalAppData 'Programs\Python\Python313') + ';' + (Join-Path $env:LocalAppData 'Programs\Python\Python313\Scripts') + ';' + $env:Path
    $python = Find-Python313
    if (-not $python) { throw 'Python foi instalado, mas não foi localizado nesta sessão. Feche e abra o instalador novamente.' }
    return $python
}

function Invoke-Python([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Comando Python falhou (código $LASTEXITCODE): $($Arguments -join ' ')" }
}

function Ask-YesNo([string]$Question, [bool]$DefaultYes = $false) {
    $hint = if ($DefaultYes) { 'S/n' } else { 's/N' }
    $answer = Read-Host "$Question [$hint]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $DefaultYes }
    return ($answer.Trim() -match '^(s|sim|y|yes)$')
}

function Get-HardwareSummary([string]$Exe) {
    $raw = & $Exe -c "import json,hardware; print(json.dumps(hardware.detectar_hardware(), ensure_ascii=False))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { throw 'Não foi possível detectar o hardware.' }
    return (($raw -join "`n") | ConvertFrom-Json)
}

function Test-NvidiaDriver {
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    $smiPath = if ($smi) { $smi.Source } else { $null }
    if (-not $smiPath) {
        $candidates = @(
            (Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe'),
            (Join-Path $env:WINDIR 'System32\nvidia-smi.exe')
        )
        $smiPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $smiPath) { return $false }
    & $smiPath -L *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-ComponentsFromManifest([string]$Exe) {
    if (Test-Path -LiteralPath $Manifest) {
        try {
            $dados = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
            $lista = @($dados.componentes | ForEach-Object { [string]$_ })
            if ($dados.schema -eq 1) { $lista += 'office' }
            if ($lista.Count -gt 0) { return (($lista | Select-Object -Unique) -join ',') }
        } catch {
            Write-Host 'Manifesto local inválido; será feita uma seleção conservadora.' -ForegroundColor Yellow
        }
    }
    $fallback = & $Exe -c "import componentes; print(','.join(componentes.componentes_para_atualizacao()))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $fallback) { return (($fallback -join '').Trim()) }
    return 'core'
}

function Select-Components([string]$Raw, [string]$Action, $Hardware, [bool]$NvidiaDriverOK) {
    if (-not [string]::IsNullOrWhiteSpace($Raw)) {
        $selected = @($Raw.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    } elseif ($Action -in @('Prepare', 'Update')) {
        $selected = @((Get-ComponentsFromManifest $VenvPython).Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    } else {
        Write-Stage 'SELEÇÃO DOS COMPONENTES'
        Write-Host 'O núcleo (interface, comunicação com Ollama e suporte básico a imagens) é obrigatório.'
        $selected = @('core')
        if (Ask-YesNo 'Instalar ferramentas Office (Word, Excel, PowerPoint e PDF)?' $true) { $selected += 'office' }
        if (Ask-YesNo 'Instalar OCR para PDFs digitalizados? (também exige o mecanismo Tesseract do sistema)' $false) { $selected += 'ocr' }
        if (Ask-YesNo 'Instalar pesquisa na web?' $true) { $selected += 'web' }
        # Voz adiciona bibliotecas nativas e o modelo Whisper será baixado depois.
        # Não inferir interesse do usuário a partir de RAM: o recurso pode ser
        # adicionado posteriormente pelo Gerenciador, sem reinstalar o núcleo.
        $voiceDefault = $false
        if (Ask-YesNo 'Instalar voz, microfone e transcrição Whisper? (pode adicionar depois no Gerenciador)' $voiceDefault) {
            $selected += 'voice'
            if ($NvidiaDriverOK -and (Ask-YesNo 'Instalar aceleração NVIDIA CUDA/cuDNN para Whisper? (download adicional de centenas de MB)' $false)) {
                $selected += 'whisper-cuda'
            }
        }
    }
    $selected = @('core') + @($selected | Where-Object { $_ -ne 'core' } | Select-Object -Unique)
    $known = @('core', 'office', 'ocr', 'web', 'voice', 'whisper-cuda')
    $invalid = @($selected | Where-Object { $_ -notin $known })
    if ($invalid.Count -gt 0) { throw ('Componentes desconhecidos: ' + ($invalid -join ', ')) }
    if ('whisper-cuda' -in $selected -and 'voice' -notin $selected) { throw 'whisper-cuda exige o componente voice.' }
    if ('whisper-cuda' -in $selected -and -not $NvidiaDriverOK) {
        if ($Raw) { throw 'Whisper CUDA foi selecionado, mas nvidia-smi não confirmou um driver NVIDIA funcional.' }
        Write-Host 'CUDA não será instalada: driver NVIDIA operacional não foi confirmado. Whisper usará CPU.' -ForegroundColor Yellow
        $selected = @($selected | Where-Object { $_ -ne 'whisper-cuda' })
    }
    return ,$selected
}

function Save-ComponentManifest([string[]]$Selected, [string]$Exe) {
    # Componentes desmarcados não são removidos. Preserve o que já estava
    # registrado e acrescente as novas seleções; só descarte CUDA se não houver
    # mais um driver NVIDIA operacional nesta máquina.
    $registrados = @('core') + @($Selected | Where-Object { $_ -ne 'core' })
    if (Test-Path -LiteralPath $Manifest) {
        try {
            $anterior = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($anterior.schema -in @(1, 2) -and $anterior.componentes) {
                $registrados += @($anterior.componentes | ForEach-Object { [string]$_ })
                if ($anterior.schema -eq 1) { $registrados += 'office' }
            }
        } catch {
            Write-Host 'Manifesto anterior inválido; será reconstruído com a seleção validada.' -ForegroundColor Yellow
        }
    }
    $registrados = @('core') + @($registrados | Where-Object { $_ -in @('office', 'ocr', 'web', 'voice', 'whisper-cuda') } | Select-Object -Unique)
    if (-not (Test-NvidiaDriver)) {
        $registrados = @($registrados | Where-Object { $_ -ne 'whisper-cuda' })
    }
    $version = & $Exe -c "import sys; print(sys.version.split()[0])"
    if ($LASTEXITCODE -ne 0) { $version = '3.13' }
    $dados = @{ schema = 2; componentes = @($registrados); python = (($version -join '').Trim()) }
    $temporary = "$Manifest.tmp"
    $json = $dados | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Manifest -Force
}

function Invoke-Requirement([string]$File, [bool]$Upgrade = $false) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $File))) { throw "Arquivo de dependências não encontrado: $File" }
    $pipArgs = @('-m','pip','--disable-pip-version-check','--retries','3','--timeout','30','install','-r',$File)
    if ($Upgrade) { $pipArgs += @('--upgrade','--upgrade-strategy','only-if-needed') }
    Write-Host "Instalando componente: $File"
    Invoke-Python $VenvPython $pipArgs
}

try {
    Write-Host ''
    Write-Host '             GAC.IA — INSTALADOR / GERENCIADOR' -ForegroundColor Cyan
    Write-Host 'A instalação modular não remove modelos, conversas, configurações nem dados.'

    if (-not [Environment]::Is64BitOperatingSystem) { throw 'A Gac.IA requer Windows x64 (AMD64).' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Este instalador é destinado ao Windows.' }
    try {
        $osRelease = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
        $buildNumber = [int]$osRelease.CurrentBuildNumber
        if ($osRelease.ProductName -match 'Windows 10' -and $buildNumber -lt 19045) {
            Write-Host 'AVISO: para usar Ollama, atualize o Windows 10 para a versão 22H2 (build 19045) ou mais recente.' -ForegroundColor Yellow
        }
    } catch { Write-Host 'Não foi possível verificar a versão exata do Windows; prossiga conferindo os requisitos do Ollama.' -ForegroundColor Yellow }

    if ($Mode -eq 'Status') {
        if (-not (Test-Path $VenvPython)) { Write-Host 'Ambiente Python ainda não instalado.'; exit 0 }
        Invoke-Python $VenvPython @('inventario_ambiente.py')
        exit 0
    }

    Write-Stage '1/6 — PYTHON E AMBIENTE ISOLADO'
    $VenvDir = Join-Path $Root '.venv'
    if (Test-Path -LiteralPath $VenvDir) {
        if (Test-Python313 $VenvPython) {
            Write-Host 'Ambiente Python 3.13 x64 válido: será preservado.' -ForegroundColor Green
        } else {
            # Também cobre .venv incompleta/corrompida sem Scripts\python.exe.
            # Nunca tente criar um novo venv por cima de diretório desconhecido.
            $backupBase = Join-Path $Root ('.venv_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
            $backup = $backupBase
            $suffix = 1
            while (Test-Path -LiteralPath $backup) { $backup = "${backupBase}_$suffix"; $suffix++ }
            Write-Host "Ambiente incompatível ou incompleto preservado em: $backup" -ForegroundColor Yellow
            Move-Item -LiteralPath $VenvDir -Destination $backup
        }
    }
    if (-not (Test-Path $VenvPython)) {
        $python = Ensure-Python313
        Write-Host 'Criando ambiente virtual .venv...'
        Invoke-Python $python.Launcher ($python.Args + @('-m','venv','.venv'))
    }
    if (-not (Test-Python313 $VenvPython)) { throw 'O ambiente virtual criado não passou na validação Python 3.13 x64.' }

    Write-Stage '2/6 — NÚCLEO OBRIGATÓRIO'
    Invoke-Python $VenvPython @('-m','pip','--disable-pip-version-check','install','--upgrade','pip')
    Invoke-Requirement 'requirements-core.txt' ($Mode -eq 'Update')

    Write-Stage '3/6 — DETECÇÃO DE HARDWARE'
    $hardware = Get-HardwareSummary $VenvPython
    Write-Host "CPU: $($hardware.cpu)"
    Write-Host "RAM: $($hardware.ram_gb) GB (disponível: $($hardware.ram_available_gb) GB)"
    foreach ($gpu in $hardware.gpus) { Write-Host "GPU: $($gpu.name) [$($gpu.vendor)] · VRAM $($gpu.vram_mb) MB" }
    $nvidiaDriverOK = Test-NvidiaDriver
    $nvidia = (@($hardware.gpus | Where-Object { $_.vendor -eq 'NVIDIA' }).Count -gt 0) -or $nvidiaDriverOK
    if ($nvidia -and $nvidiaDriverOK) {
        Write-Host 'Driver NVIDIA operacional detectado.' -ForegroundColor Green
    } elseif ($nvidia) {
        Write-Host 'NVIDIA detectada, mas sem confirmação de driver funcional. Não será forçada instalação CUDA.' -ForegroundColor Yellow
    } else {
        Write-Host 'Sem NVIDIA operacional. Whisper seguirá com CPU/INT8; Ollama seleciona seu backend independentemente.' -ForegroundColor Yellow
    }

    Write-Stage '4/6 — COMPONENTES OPCIONAIS'
    $selected = Select-Components $Components $Mode $hardware $nvidiaDriverOK
    foreach ($item in $selected) { Write-Host "[SELECIONADO] $item" -ForegroundColor Green }
    if ('office' -in $selected) { Invoke-Requirement 'requirements-office.txt' ($Mode -eq 'Update') }
    if ('ocr' -in $selected) { Invoke-Requirement 'requirements-ocr.txt' ($Mode -eq 'Update') }
    if ('web' -in $selected) { Invoke-Requirement 'requirements-web.txt' ($Mode -eq 'Update') }
    if ('voice' -in $selected) { Invoke-Requirement 'requirements-voice.txt' ($Mode -eq 'Update') }
    if ('whisper-cuda' -in $selected) { Invoke-Requirement 'requirements-nvidia-cuda.txt' ($Mode -eq 'Update') }

    Write-Stage '5/6 — VERIFICAÇÃO DOS COMPONENTES'
    Invoke-Python $VenvPython @('-m','pip','check')
    Invoke-Python $VenvPython @('preparar_verificar.py','--components',($selected -join ','))

    Write-Stage '6/6 — TESTES AUTOMATIZADOS E REGISTRO'
    Invoke-Python $VenvPython @('-m','unittest','discover','-s','tests','-v')
    # O manifesto é atualizado somente depois que instalação, imports, pip check
    # e testes terminaram corretamente.
    Save-ComponentManifest $selected $VenvPython

    Write-Stage 'OLLAMA — MOTOR DE MODELOS'
    $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
    $ollamaPath = if ($ollama) { $ollama.Source } else { $null }
    if (-not $ollamaPath) {
        $candidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'), (Join-Path $env:ProgramFiles 'Ollama\ollama.exe'))
        $ollamaPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if ($ollamaPath) {
        Write-Host "Ollama encontrado: $ollamaPath" -ForegroundColor Green
    } elseif ($Mode -eq 'Install' -and -not $Components -and (Ask-YesNo 'Ollama não foi encontrado. Deseja instalá-lo pelo winget agora?' $true)) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            & $winget.Source install --id Ollama.Ollama --exact --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Write-Host 'Ollama não foi instalado. Baixe pelo site oficial: https://ollama.com/download' -ForegroundColor Yellow }
        } else {
            Write-Host 'winget não está disponível. Baixe pelo site oficial: https://ollama.com/download' -ForegroundColor Yellow
        }
    } else {
        Write-Host 'Ollama não instalado. Instale pelo site oficial quando desejar: https://ollama.com/download' -ForegroundColor Yellow
    }

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ' PREPARAÇÃO CONCLUÍDA!' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ('Componentes registrados: ' + ($selected -join ', '))
    Write-Host 'Modelos de linguagem e Whisper não foram baixados automaticamente.'
    Write-Host 'O ComfyUI Desktop é instalado separadamente pelo site oficial: https://www.comfy.org/download'
    Write-Host 'Execute iniciar.bat para abrir a Gac.IA ou gerenciador.bat para gerenciar os componentes.'
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('FALHA: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Nenhuma conversa, configuração, banco de dados, modelo ou workspace foi apagado.' -ForegroundColor Yellow
    exit 1
}
