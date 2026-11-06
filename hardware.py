"""Detecção portátil de hardware e capacidades da Gac.IA.

A detecção é informativa: encontrar uma GPU não garante que qualquer motor
consiga utilizá-la. Cada backend deve validar suas próprias bibliotecas/runtime.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _executar(comando: list[str], timeout: float = 5.0) -> str:
    try:
        resultado = subprocess.run(
            comando, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode == 0:
            return (resultado.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _normalizar_fabricante(nome: str) -> str:
    texto = nome.lower()
    if any(p in texto for p in ("nvidia", "geforce", "quadro")):
        return "NVIDIA"
    if any(p in texto for p in ("amd", "radeon", "advanced micro devices")):
        return "AMD"
    if "intel" in texto:
        return "Intel"
    return "Desconhecido"


def _detectar_gpus_windows() -> list[dict[str, Any]]:
    script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"
    )
    saida = _executar([
        "powershell", "-NoProfile", "-NonInteractive", "-Command", script
    ], timeout=8.0)
    gpus: list[dict[str, Any]] = []
    if saida:
        try:
            dados = json.loads(saida)
            if isinstance(dados, dict):
                dados = [dados]
            for item in dados if isinstance(dados, list) else []:
                if not isinstance(item, dict) or not item.get("Name"):
                    continue
                try:
                    memoria = int(item.get("AdapterRAM") or 0) // (1024 * 1024)
                except (TypeError, ValueError):
                    memoria = 0
                nome = str(item["Name"]).strip()
                gpus.append({
                    "name": nome,
                    "vendor": _normalizar_fabricante(nome),
                    "vram_mb": memoria or None,
                    "driver": str(item.get("DriverVersion") or "") or None,
                })
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # nvidia-smi fornece VRAM real, inclusive acima do limite de 4 GB
    # da propriedade AdapterRAM em algumas versões do Windows.
    smi = shutil.which("nvidia-smi")
    if smi:
        linhas = _executar([
            smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"
        ], timeout=5.0)
        for linha in linhas.splitlines():
            partes = [p.strip() for p in linha.split(",")]
            if len(partes) < 3:
                continue
            nome = partes[0]
            try:
                vram = int(float(partes[1]))
            except ValueError:
                vram = None
            existente = next((g for g in gpus if g["name"].lower() == nome.lower()), None)
            if existente:
                existente["vram_mb"] = vram or existente["vram_mb"]
                existente["driver"] = partes[2] or existente["driver"]
            else:
                gpus.append({"name": nome, "vendor": "NVIDIA", "vram_mb": vram, "driver": partes[2] or None})
    return gpus


def _detectar_gpus_posix() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    lspci = shutil.which("lspci")
    if lspci:
        saida = _executar([lspci, "-nn"], timeout=4.0)
        for linha in saida.splitlines():
            if "vga compatible controller" in linha.lower() or "3d controller" in linha.lower() or "display controller" in linha.lower():
                nome = linha.split(":", 2)[-1].strip() or linha.strip()
                gpus.append({"name": nome, "vendor": _normalizar_fabricante(nome), "vram_mb": None, "driver": None})
    if not gpus and sys.platform == "darwin":
        saida = _executar(["system_profiler", "SPDisplaysDataType", "-json"], timeout=10.0)
        try:
            dados = json.loads(saida)
            for item in dados.get("SPDisplaysDataType", []):
                nome = str(item.get("sppci_model") or item.get("_name") or "GPU Apple")
                gpus.append({"name": nome, "vendor": _normalizar_fabricante(nome), "vram_mb": None, "driver": None})
        except (json.JSONDecodeError, AttributeError):
            pass
    return gpus


def _memoria_status_gb() -> tuple[float | None, float | None]:
    """Retorna RAM total e disponível, sem exigir psutil como dependência."""
    if sys.platform == "win32":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            estado = MEMORYSTATUSEX()
            estado.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
                divisor = 1024 ** 3
                return round(estado.ullTotalPhys / divisor, 1), round(estado.ullAvailPhys / divisor, 1)
        except Exception:
            pass
    try:
        valores = {}
        with open("/proc/meminfo", encoding="ascii") as arquivo:
            for linha in arquivo:
                if linha.startswith(("MemTotal:", "MemAvailable:")):
                    chave, valor = linha.split(":", 1)
                    valores[chave] = int(valor.split()[0])
        total = valores.get("MemTotal")
        disponivel = valores.get("MemAvailable")
        return (round(total / (1024 ** 2), 1) if total else None,
                round(disponivel / (1024 ** 2), 1) if disponivel else None)
    except (OSError, ValueError, IndexError):
        return None, None


def _memoria_total_gb() -> float | None:
    """Compatibilidade com chamadas anteriores que precisam apenas da RAM total."""
    return _memoria_status_gb()[0]


def memoria_disponivel_gb() -> float | None:
    """RAM física disponível no momento, para validar cargas locais pesadas."""
    return _memoria_status_gb()[1]


def _vram_disponivel_nvidia() -> dict[str, int]:
    """Consulta VRAM total/livre por GPU NVIDIA; outras APIs não são presumidas."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {}
    saida = _executar([smi, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"], timeout=5.0)
    resultado = {}
    for linha in saida.splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) != 3:
            continue
        try:
            resultado[partes[0].lower()] = {"total": int(float(partes[1])), "free": int(float(partes[2]))}
        except ValueError:
            continue
    return resultado


def detectar_hardware() -> dict[str, Any]:
    """Retorna um resumo sem instalar drivers, pacotes ou alterar o sistema."""
    gpus = _detectar_gpus_windows() if sys.platform == "win32" else _detectar_gpus_posix()
    vram_nvidia = _vram_disponivel_nvidia()
    for gpu in gpus:
        dados_vram = vram_nvidia.get(str(gpu.get("name", "")).lower())
        if dados_vram:
            gpu["vram_mb"] = dados_vram["total"]
            gpu["vram_free_mb"] = dados_vram["free"]
    if not gpus:
        gpus = [{"name": "GPU não identificada (pode ser integrada ou driver ausente)",
                 "vendor": "Desconhecido", "vram_mb": None, "driver": None}]
    ram_total, ram_disponivel = _memoria_status_gb()
    return {
        "system": platform.platform(),
        "os": platform.system(),
        "architecture": platform.machine() or platform.architecture()[0],
        "cpu": platform.processor() or platform.machine() or "CPU não identificada",
        "logical_cores": os.cpu_count() or 1,
        "ram_gb": ram_total,
        "ram_available_gb": ram_disponivel,
        "gpus": gpus,
    }


_DLL_DIRETORIOS_NVIDIA: list[object] = []


def preparar_runtime_cuda() -> list[str]:
    """Registra DLLs CUDA/cuDNN instaladas via pip, sem alterar o PATH global.

    O pacote NVIDIA instala bibliotecas em site-packages/nvidia/*/bin.
    No Windows, os diretórios precisam ser registrados antes de importar
    CTranslate2. Os handles são mantidos vivos durante todo o processo.
    """
    adicionados: list[str] = []
    if sys.platform != "win32":
        return adicionados

    try:
        import sysconfig
        raiz_site = Path(sysconfig.get_paths().get("purelib", "")) / "nvidia"
        if not raiz_site.is_dir():
            return adicionados
        for pacote in raiz_site.iterdir():
            if not pacote.is_dir():
                continue
            for nome in ("bin", "lib"):
                diretorio = pacote / nome
                if not diretorio.is_dir():
                    continue
                caminho = str(diretorio.resolve())
                if caminho not in os.environ.get("PATH", "").split(os.pathsep):
                    os.environ["PATH"] = caminho + os.pathsep + os.environ.get("PATH", "")
                try:
                    handle = os.add_dll_directory(caminho)
                    _DLL_DIRETORIOS_NVIDIA.append(handle)
                    adicionados.append(caminho)
                except (AttributeError, OSError):
                    pass
    except Exception:
        # O runtime CUDA é opcional; a aplicação deve continuar em CPU.
        pass
    return adicionados


def detectar_backend_whisper() -> tuple[str, str]:
    """Faster-Whisper/CTranslate2 usa CUDA NVIDIA; demais casos usam CPU.

    A tentativa CUDA ainda é protegida por fallback na inicialização e durante
    a inferência, pois a presença do runtime pode ser incompleta.
    """
    try:
        preparar_runtime_cuda()
        import ctranslate2
        quantidade = int(ctranslate2.get_cuda_device_count())
        if quantidade > 0:
            return "cuda", f"CTranslate2 detectou {quantidade} dispositivo(s) CUDA"
        return "cpu", "CTranslate2 não encontrou um dispositivo CUDA utilizável"
    except Exception as erro:
        return "cpu", f"CUDA indisponível para Faster-Whisper: {erro}"


def resumir_hardware(info: dict[str, Any] | None = None) -> list[str]:
    info = info or detectar_hardware()
    ram = f"{info['ram_gb']} GB" if info.get("ram_gb") else "não identificada"
    linhas = [
        f"Sistema: {info.get('system', 'não identificado')}",
        f"CPU: {info.get('cpu', 'não identificada')} ({info.get('logical_cores', '?')} threads)",
        f"RAM: {ram}",
        "GPUs:",
    ]
    for gpu in info.get("gpus", []):
        vram = f", VRAM reportada: {gpu['vram_mb']} MB" if gpu.get("vram_mb") else ""
        linhas.append(f"  - {gpu.get('name', 'GPU')} [{gpu.get('vendor', 'Desconhecido')}{vram}]")
    return linhas
