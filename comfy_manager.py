"""Integração com ComfyUI Desktop/API e suporte legado ao pacote portátil.

A experiência padrão recomenda o ComfyUI Desktop oficial. A instalação portátil
continua disponível apenas como mecanismo legado/avançado; modelos/checkpoints
não são baixados automaticamente.
"""
from __future__ import annotations

import ipaddress
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path
from typing import Callable

from hardware import detectar_hardware

BASE_DIR = Path(__file__).resolve().parent
COMFY_DIR = BASE_DIR / "runtime" / "ComfyUI"
COMFY_URL = "http://127.0.0.1:8188"


class ComfyManagerError(RuntimeError):
    pass


def recomendar_pacote_portatil(info: dict | None = None) -> dict:
    """Recomendação LEGADA para instalação portátil; não é o caminho padrão.

    Os pacotes portáteis continuam úteis em instalações avançadas. O ComfyUI
    oficial, porém, recomenda Desktop para usuários regulares do Windows.
    """
    info = info or detectar_hardware()
    gpus = info.get("gpus") or []
    gpu = next((g for g in gpus if g.get("vendor") in {"NVIDIA", "AMD", "Intel"}), None)
    ram = info.get("ram_gb")
    nome = str((gpu or {}).get("name", ""))
    fabricante = (gpu or {}).get("vendor", "CPU")
    vram = (gpu or {}).get("vram_mb")
    if fabricante == "NVIDIA":
        antiga = any(token in nome.lower() for token in ("gtx 10", "gtx 9", "gtx 7", "gtx 6", "quadro p", "quadro m"))
        arquivo = "ComfyUI_windows_portable_nvidia_cu126.7z" if antiga else "ComfyUI_windows_portable_nvidia.7z"
        variante = "NVIDIA CUDA 12.6 / Python 3.12 (GPU NVIDIA antiga)" if antiga else "NVIDIA CUDA 13.0 / Python 3.13"
    elif fabricante == "AMD":
        arquivo = "ComfyUI_windows_portable_amd.7z"
        variante = "AMD Radeon (pacote portátil)"
    elif fabricante == "Intel":
        arquivo = "ComfyUI_windows_portable_intel.7z"
        variante = "Intel GPU (pacote portátil)"
    else:
        arquivo = "ComfyUI_windows_portable_nvidia.7z"
        variante = "CPU (pacote portátil; sem aceleração de GPU garantida)"
    url = f"https://github.com/comfyanonymous/ComfyUI/releases/latest/download/{arquivo}"
    if platform.system() != "Windows":
        return {"supported": False, "reason": "O pacote portátil legado é exclusivo do Windows. Consulte a instalação manual oficial.", "url": "https://github.com/Comfy-Org/ComfyUI#installing", "vendor": fabricante, "variant": variante, "archive": arquivo, "ram_gb": ram, "vram_mb": vram, "url_download": url}
    if ram is not None and float(ram) < 8:
        return {"supported": False, "reason": "A máquina tem menos de 8 GB de RAM. A instalação portátil automática foi desaconselhada.", "url": "https://www.comfy.org/download", "vendor": fabricante, "variant": variante, "archive": arquivo, "ram_gb": ram, "vram_mb": vram, "url_download": url}
    return {"supported": True, "reason": "Pacote portátil legado. Para usuários comuns, prefira o ComfyUI Desktop oficial.", "url": "https://www.comfy.org/download", "vendor": fabricante, "variant": variante, "archive": arquivo, "ram_gb": ram, "vram_mb": vram, "url_download": url}


def recomendar_pacote(info: dict | None = None) -> dict:
    """Recomenda o Desktop oficial como caminho padrão no Windows.

    O ComfyUI Desktop seleciona/gerencia a instalação e os backends. A Gac.IA
    apenas abre o site oficial; não executa instaladores externos em silêncio.
    """
    info = info or detectar_hardware()
    gpus = info.get("gpus") or []
    gpu = next((g for g in gpus if g.get("vendor") in {"NVIDIA", "AMD", "Intel"}), None)
    fabricante = (gpu or {}).get("vendor", "Desconhecido")
    ram = info.get("ram_gb")
    vram = (gpu or {}).get("vram_mb")
    nome = str((gpu or {}).get("name") or "GPU não identificada")
    if fabricante == "NVIDIA":
        variante = f"ComfyUI Desktop · GPU NVIDIA ({nome})"
    elif fabricante == "AMD":
        variante = f"ComfyUI Desktop · AMD Radeon ({nome})"
    elif fabricante == "Intel":
        variante = f"ComfyUI Desktop · Intel ({nome})"
    else:
        variante = "ComfyUI Desktop · GPU não identificada; backend deve ser confirmado pelo instalador oficial"
    suportado = platform.system() == "Windows"
    return {
        "supported": suportado,
        "method": "desktop",
        "reason": (
            "O Desktop é o caminho recomendado para usuários comuns do Windows. A disponibilidade de aceleração depende do modelo da GPU, driver e backend escolhido; modelos/checkpoints são instalados separadamente."
            if suportado else "O ComfyUI Desktop oficial não oferece instalador para este sistema. Use a instalação manual oficial para seu sistema operacional."
        ),
        "url": "https://www.comfy.org/download",
        "vendor": fabricante,
        "variant": variante,
        "archive": None,
        "ram_gb": ram,
        "vram_mb": vram,
        "url_download": None,
    }


def recomendar_parametros(info: dict | None = None) -> dict:
    """Resolução conservadora sugerida conforme VRAM/RAM, sem forçar a escolha."""
    info = info or detectar_hardware()
    gpus = info.get("gpus") or []
    gpu = next((g for g in gpus if g.get("vram_mb")), None)
    # Quando a API NVIDIA fornece VRAM livre, ela prevalece sobre a capacidade
    # total. Para GPUs sem telemetria suportada, usa-se a capacidade reportada
    # como estimativa, nunca como garantia de memória disponível.
    vram_mb = 0
    if gpu:
        vram_livre = gpu.get("vram_free_mb")
        vram_mb = vram_livre if vram_livre is not None else (gpu.get("vram_mb") or 0)
    vram_gb = float(vram_mb) / 1024
    ram_livre = info.get("ram_available_gb")
    ram = float(ram_livre if ram_livre is not None else (info.get("ram_gb") or 0))
    if vram_gb >= 10 and ram >= 16:
        return {"width": 768, "height": 768, "steps": 8, "label": "Alto desempenho (memória disponível ≥ 10 GB)"}
    if vram_gb >= 6 and ram >= 12:
        return {"width": 640, "height": 640, "steps": 8, "label": "Desempenho intermediário (memória disponível ≥ 6 GB)"}
    return {"width": 512, "height": 512, "steps": 6, "label": "Baixo consumo (CPU/VRAM limitada)"}


def comfy_instalado() -> bool:
    if not COMFY_DIR.exists():
        return False
    return any(COMFY_DIR.rglob("main.py")) and any(COMFY_DIR.rglob("run_*.bat"))


def _baixar_arquivo(url: str, destino: Path, progress: Callable[[str], None] | None = None, min_size: int = 1024 * 1024) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "GacIA-ComfyUI-Installer"})
    with urllib.request.urlopen(request, timeout=60) as response, destino.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        recebido = 0
        while True:
            bloco = response.read(1024 * 1024)
            if not bloco:
                break
            output.write(bloco)
            recebido += len(bloco)
            if progress and total:
                progress(f"Baixando ComfyUI: {recebido / total * 100:.0f}%")
        output.flush()
        os.fsync(output.fileno())
    if not destino.exists() or destino.stat().st_size < min_size:
        raise ComfyManagerError("O download do ComfyUI ficou incompleto ou inválido.")


def _localizar_7zip(progress=None) -> Path:
    for nome in ("7z.exe", "7za.exe", "7zr.exe"):
        encontrado = shutil.which(nome)
        if encontrado:
            return Path(encontrado)
    destino = BASE_DIR / "runtime" / "tools" / "7zr.exe"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        if progress:
            progress("Obtendo extrator 7-Zip oficial...")
        _baixar_arquivo("https://www.7-zip.org/a/7zr.exe", destino, progress, min_size=64 * 1024)
    return destino


def _promover_instalacao_preservando(destino: Path, staged: Path) -> Path | None:
    """Promove uma pasta preparada sem apagar uma instalação preexistente.

    Se a troca falhar, tenta restaurar automaticamente a pasta original.
    Retorna o caminho do backup quando havia conteúdo anterior.
    """
    destino = Path(destino)
    staged = Path(staged)
    backup: Path | None = None
    if destino.exists():
        base_backup = destino.with_name(
            destino.name + "_backup_" + time.strftime("%Y%m%d_%H%M%S")
        )
        backup = base_backup
        sufixo = 1
        while backup.exists():
            backup = base_backup.with_name(f"{base_backup.name}_{sufixo}")
            sufixo += 1
        destino.replace(backup)
    try:
        staged.replace(destino)
    except Exception:
        if backup is not None and backup.exists() and not destino.exists():
            backup.replace(destino)
        raise
    return backup


def instalar_comfyui(progress: Callable[[str], None] | None = None, info: dict | None = None) -> Path:
    if platform.system() != "Windows":
        raise ComfyManagerError("A instalação automática está disponível apenas no Windows.")
    recomendacao = recomendar_pacote_portatil(info)
    if not recomendacao["supported"]:
        raise ComfyManagerError(recomendacao["reason"])
    if comfy_instalado():
        return COMFY_DIR
    COMFY_DIR.parent.mkdir(parents=True, exist_ok=True)
    uso = shutil.disk_usage(COMFY_DIR.parent)
    if uso.free < 12 * 1024 ** 3:
        raise ComfyManagerError("São necessários pelo menos 12 GB livres para instalar o ComfyUI portátil com margem de segurança.")
    if progress:
        progress(f"Preparando pacote: {recomendacao['variant']}")
    with tempfile.TemporaryDirectory(prefix="gacia_comfy_") as temp:
        temp_dir = Path(temp)
        archive = temp_dir / recomendacao["archive"]
        _baixar_arquivo(recomendacao["url_download"], archive, progress)
        extrator = _localizar_7zip(progress)
        extracted = temp_dir / "extraido"
        extracted.mkdir()
        if progress:
            progress("Extraindo ComfyUI...")
        resultado = subprocess.run(
            [str(extrator), "x", str(archive), f"-o{extracted}", "-y"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode != 0:
            raise ComfyManagerError("Falha ao extrair o pacote ComfyUI: " + (resultado.stderr or resultado.stdout)[-1200:])
        # Acha a pasta portátil pelo launcher, não assume o nome do diretório do arquivo.
        launchers = list(extracted.rglob("run_*.bat"))
        if not launchers:
            raise ComfyManagerError("O pacote foi extraído, mas não contém um inicializador run_*.bat.")
        source_root = launchers[0].parent
        if not any(source_root.rglob("main.py")):
            raise ComfyManagerError("A extração não contém o main.py esperado do ComfyUI.")
        staged = COMFY_DIR.with_name("ComfyUI_installing")
        if staged.exists():
            # Nome reservado exclusivamente para extração intermediária da Gac.IA.
            shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(source_root, staged)
        backup = _promover_instalacao_preservando(COMFY_DIR, staged)
        if backup and progress:
            progress(f"Instalação portátil anterior preservada em: {backup.name}")
    if not comfy_instalado():
        raise ComfyManagerError("A instalação terminou, mas a validação do ComfyUI falhou.")
    if progress:
        progress("ComfyUI instalado. O checkpoint/modelo de imagem deve ser adicionado separadamente.")
    return COMFY_DIR


def _launcher_preferido(info: dict | None = None) -> Path:
    info = info or detectar_hardware()
    arquivos = list(COMFY_DIR.rglob("run_*.bat"))
    if not arquivos:
        raise ComfyManagerError("Nenhuma instalação portátil local do ComfyUI foi encontrada. Instale/inicie o ComfyUI Desktop oficial ou configure uma instalação portátil existente.")
    vendor = next((g.get("vendor") for g in info.get("gpus", []) if g.get("vendor") in {"NVIDIA", "AMD", "Intel"}), "CPU")
    preferencias = {
        "NVIDIA": ("run_nvidia_gpu.bat", "run_nvidia_gpu_fast_fp16_accumulation.bat", "run_cpu.bat"),
        "AMD": ("run_amd_gpu.bat", "run_cpu.bat"),
        "Intel": ("run_intel_gpu.bat", "run_ipex_gpu.bat", "run_cpu.bat"),
        "CPU": ("run_cpu.bat", "run_nvidia_gpu.bat"),
    }.get(vendor, ("run_cpu.bat",))
    for nome in preferencias:
        achado = next((p for p in arquivos if p.name.lower() == nome.lower()), None)
        if achado:
            return achado
    return arquivos[0]


def validar_url_comfy_local(base_url: str = COMFY_URL) -> str:
    """Aceita somente endpoint HTTP local, sem credenciais, query ou fragmento."""
    texto = str(base_url or COMFY_URL).strip().rstrip("/")
    try:
        partes = urlsplit(texto)
        host = (partes.hostname or "").lower()
        # Acessar .port também valida portas malformadas.
        _ = partes.port
        local = host == "localhost"
        if not local:
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = False
        if (partes.scheme != "http" or not host or not local
                or partes.username or partes.password
                or partes.path not in ("", "/") or partes.query or partes.fragment):
            raise ValueError
    except ValueError as erro:
        raise ComfyManagerError(
            "Use o endereço HTTP local do ComfyUI, por exemplo http://127.0.0.1:8188."
        ) from erro
    return texto


def servidor_responde(base_url: str = COMFY_URL, timeout: float = 1.5) -> bool:
    try:
        import requests
        base = validar_url_comfy_local(base_url)
        response = requests.get(base + "/system_stats", timeout=timeout)
        if response.status_code != 200:
            return False
        dados = response.json()
        return isinstance(dados, dict) and "system" in dados and "devices" in dados
    except Exception:
        return False


def iniciar_comfyui(
    progress: Callable[[str], None] | None = None,
    wait_seconds: int = 120,
    base_url: str = COMFY_URL,
) -> bool:
    base = validar_url_comfy_local(base_url)
    if servidor_responde(base):
        return True
    porta = urlsplit(base).port or 80
    if porta != 8188:
        raise ComfyManagerError(
            "A instalação portátil legada inicia na porta 8188. Para usar outra porta, "
            "inicie o ComfyUI Desktop já configurado nela ou ajuste o endereço para http://127.0.0.1:8188."
        )
    info = detectar_hardware()
    vendor = next((g.get("vendor") for g in info.get("gpus", []) if g.get("vendor") in {"NVIDIA", "AMD", "Intel"}), "CPU")
    arquivos = list(COMFY_DIR.rglob("run_*.bat"))
    cpu_launcher = next((p for p in arquivos if p.name.lower() == "run_cpu.bat"), None)
    if vendor == "CPU" and cpu_launcher is None:
        python_embed = next(COMFY_DIR.rglob("python.exe"), None)
        main_py = next(COMFY_DIR.rglob("main.py"), None)
        if python_embed is None or main_py is None:
            raise ComfyManagerError("O pacote portátil não contém run_cpu.bat nem o Python incorporado para iniciar em CPU.")
        if progress:
            progress("Iniciando ComfyUI em modo CPU; a geração será mais lenta.")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen([str(python_embed), "-s", str(main_py), "--cpu"], cwd=str(main_py.parent), creationflags=flags)
    else:
        launcher = cpu_launcher if vendor == "CPU" and cpu_launcher else _launcher_preferido(info)
        if progress:
            progress(f"Iniciando ComfyUI por {launcher.name}...")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(["cmd.exe", "/c", str(launcher)], cwd=str(launcher.parent), creationflags=flags)
    deadline = time.monotonic() + max(10, int(wait_seconds))
    while time.monotonic() < deadline:
        if servidor_responde(base, timeout=2.0):
            if progress:
                progress(f"ComfyUI está pronto em {base}")
            return True
        time.sleep(2)
    raise ComfyManagerError(f"O ComfyUI foi iniciado, mas a API local não respondeu em {base}. Verifique a janela do ComfyUI e os drivers da GPU.")


def garantir_comfyui_ativo(base_url: str = COMFY_URL, progress: Callable[[str], None] | None = None) -> None:
    base = validar_url_comfy_local(base_url)
    if servidor_responde(base):
        return
    if not comfy_instalado():
        raise ComfyManagerError(f"A API do ComfyUI não respondeu em {base} e não há instalação portátil local. Instale e inicie o ComfyUI Desktop oficial (ou inicie sua instalação portátil) e tente novamente.")
    iniciar_comfyui(progress=progress, base_url=base)
