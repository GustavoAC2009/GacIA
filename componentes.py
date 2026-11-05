"""Inventário e planejamento dos componentes opcionais da Gac.IA.

Este módulo usa somente a biblioteca padrão: também pode ser executado antes
que as dependências da interface tenham sido instaladas.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
MANIFEST_FILE = BASE_DIR / ".gacia-components.json"

COMPONENTES: dict[str, dict[str, Any]] = {
    "core": {
        "nome": "Núcleo da Gac.IA",
        "descricao": "Interface desktop PySide6, comunicação com Ollama e suporte básico a imagens.",
        "arquivo": "requirements-core.txt",
        "modulos": ("PySide6", "requests", "PIL"),
        "obrigatorio": True,
    },
    "office": {
        "nome": "Documentos e produtividade",
        "descricao": "Word, Excel, PowerPoint e PDF (criação, leitura e edição).",
        "arquivo": "requirements-office.txt",
        "modulos": ("docx", "openpyxl", "pptx", "pypdf", "reportlab"),
    },
    "ocr": {
        "nome": "OCR para PDFs digitalizados",
        "descricao": "Reconhecimento de texto em PDFs escaneados; também exige o aplicativo Tesseract instalado no sistema.",
        "arquivo": "requirements-ocr.txt",
        "modulos": ("pypdfium2", "pytesseract"),
    },
    "web": {
        "nome": "Pesquisa na web",
        "descricao": "Pesquisa em fontes públicas quando solicitada.",
        "arquivo": "requirements-web.txt",
        "modulos": ("ddgs",),
    },
    "voice": {
        "nome": "Voz e microfone",
        "descricao": "Whisper local, entrada de áudio e síntese de voz.",
        "arquivo": "requirements-voice.txt",
        "modulos": ("numpy", "sounddevice", "faster_whisper", "ctranslate2", "pygame", "edge_tts", "pyttsx3"),
        "modulos_windows": ("pythoncom", "win32com"),
    },
    "whisper-cuda": {
        "nome": "Aceleração NVIDIA do Whisper",
        "descricao": "CuBLAS 12 e cuDNN 9 isolados no ambiente Python da Gac.IA.",
        "arquivo": "requirements-nvidia-cuda.txt",
        "distribuicoes": ("nvidia-cublas-cu12", "nvidia-cudnn-cu12"),
    },
}


def normalizar_componentes(componentes: Iterable[str] | str | None) -> list[str]:
    """Valida e ordena componentes, sempre incluindo o núcleo obrigatório."""
    if componentes is None:
        valores: list[str] = []
    elif isinstance(componentes, str):
        valores = [parte.strip().lower() for parte in componentes.split(",") if parte.strip()]
    else:
        valores = [str(parte).strip().lower() for parte in componentes if str(parte).strip()]
    desconhecidos = sorted(set(valores) - set(COMPONENTES))
    if desconhecidos:
        raise ValueError("Componentes desconhecidos: " + ", ".join(desconhecidos))
    selecionados = set(valores)
    selecionados.add("core")
    if "whisper-cuda" in selecionados and "voice" not in selecionados:
        raise ValueError("O componente whisper-cuda exige também o componente voice.")
    return [nome for nome in COMPONENTES if nome in selecionados]


def _modulo_instalado(modulo: str) -> bool:
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _distribuicao_instalada(nome: str) -> bool:
    try:
        importlib.metadata.version(nome)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def estado_componente(nome: str) -> dict[str, Any]:
    if nome not in COMPONENTES:
        raise ValueError(f"Componente desconhecido: {nome}")
    definicao = COMPONENTES[nome]
    modulos = list(definicao.get("modulos", ()))
    if sys.platform == "win32":
        modulos.extend(definicao.get("modulos_windows", ()))
    presentes_modulos = [modulo for modulo in modulos if _modulo_instalado(modulo)]
    faltantes = [modulo for modulo in modulos if modulo not in presentes_modulos]
    distribuicoes = list(definicao.get("distribuicoes", ()))
    presentes_dist = [item for item in distribuicoes if _distribuicao_instalada(item)]
    faltantes_dist = [item for item in distribuicoes if item not in presentes_dist]
    ok = not faltantes and not faltantes_dist
    parcial = bool(presentes_modulos or presentes_dist) and not ok
    return {
        "id": nome,
        "nome": definicao["nome"],
        "descricao": definicao["descricao"],
        "instalado": ok,
        "parcial": parcial,
        "presentes": presentes_modulos + presentes_dist,
        "faltantes": faltantes + faltantes_dist,
        "arquivo": definicao["arquivo"],
    }


def detectar_componentes() -> dict[str, dict[str, Any]]:
    return {nome: estado_componente(nome) for nome in COMPONENTES}


def carregar_manifesto() -> dict[str, Any] | None:
    try:
        dados = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(dados, dict) or dados.get("schema") not in {1, 2}:
        return None
    if not isinstance(dados.get("componentes"), (list, str)):
        return None
    componentes_salvos = dados.get("componentes", ["core"])
    # Schema 1 agrupava Office no núcleo. Ao atualizar, preservar esse recurso
    # explicitamente como componente opcional evita que uma instalação antiga
    # perca bibliotecas em reparos futuros.
    if dados.get("schema") == 1:
        valores = componentes_salvos.split(",") if isinstance(componentes_salvos, str) else list(componentes_salvos)
        componentes_salvos = list(valores) + ["office"]
    try:
        dados["componentes"] = normalizar_componentes(componentes_salvos)
    except (TypeError, ValueError):
        return None
    dados["schema"] = 2
    return dados


def salvar_manifesto(componentes: Iterable[str], *, python_version: str | None = None) -> bool:
    """Salva a seleção instalada de forma atômica, sem registrar dados pessoais."""
    selecionados = normalizar_componentes(componentes)
    temporario = MANIFEST_FILE.with_suffix(MANIFEST_FILE.suffix + ".tmp")
    dados = {
        "schema": 2,
        "componentes": selecionados,
        "python": python_version or sys.version.split()[0],
    }
    try:
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporario, MANIFEST_FILE)
        return True
    except OSError:
        temporario.unlink(missing_ok=True)
        return False



def _nvidia_driver_encontrado() -> bool:
    """Localiza nvidia-smi também nos diretórios padrão do Windows."""
    candidatos = [shutil.which("nvidia-smi"), shutil.which("nvidia-smi.exe")]
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        windir = os.environ.get("WINDIR", r"C:\Windows")
        candidatos.extend([
            str(Path(program_files) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"),
            str(Path(windir) / "System32" / "nvidia-smi.exe"),
        ])
    for candidato in candidatos:
        if not candidato or not Path(candidato).is_file():
            continue
        try:
            resultado = subprocess.run(
                [candidato, "-L"], capture_output=True, text=True,
                timeout=3, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if resultado.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False

def componentes_para_atualizacao() -> list[str]:
    """Recupera a seleção registrada; sem manifesto, não instala extras às cegas."""
    manifesto = carregar_manifesto()
    if manifesto:
        selecionados = manifesto["componentes"]
        # Evita reinstalar CUDA num equipamento que mudou de GPU/driver.
        if "whisper-cuda" in selecionados and not _nvidia_driver_encontrado():
            selecionados = [item for item in selecionados if item != "whisper-cuda"]
        return selecionados
    estados = detectar_componentes()
    # Sem manifesto (ex.: atualização de uma versão antiga), repara grupos
    # parcialmente presentes em vez de deixá-los silenciosamente quebrados.
    selecionados = [nome for nome, estado in estados.items()
                    if estado["instalado"] or estado.get("parcial") or nome == "core"]
    if "core" in selecionados and estados.get("office", {}).get("instalado"):
        selecionados.append("office")
    return normalizar_componentes(selecionados)


def recomendar_componentes(info_hardware: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sugere recursos sem instalar nada e sem confundir GPU detectada com driver pronto."""
    try:
        from hardware import detectar_hardware
        info = info_hardware or detectar_hardware()
    except Exception:
        info = info_hardware or {}
    gpus = info.get("gpus") or []
    gpu = next((item for item in gpus if item.get("vendor") in {"NVIDIA", "AMD", "Intel"}), {})
    vendor = gpu.get("vendor", "Desconhecido")
    # Para recomendar geração SDXL, use VRAM realmente livre. A VRAM total
    # não representa o que resta após Windows, navegador, Ollama ou outros apps.
    vram_free_mb = gpu.get("vram_free_mb")
    vram_total_mb = gpu.get("vram_mb")
    vram_gb = (float(vram_free_mb) / 1024) if vram_free_mb is not None else None
    vram_total_gb = (float(vram_total_mb) / 1024) if vram_total_mb is not None else None
    ram = info.get("ram_gb")
    try:
        ram_gb = float(ram) if ram is not None else None
    except (TypeError, ValueError):
        ram_gb = None
    tem_nvidia = False
    try:
        tem_nvidia = bool(vendor == "NVIDIA" and _nvidia_driver_encontrado())
    except Exception:
        pass
    try:
        from ollama_manager import recomendar_perfil
        perfil_llm = recomendar_perfil(info)
    except Exception:
        perfil_llm = "intermediario"
    return {
        "office": True,
        "ocr": False,
        "web": True,
        "voice": False,
        "whisper-cuda": False,
        "llm_profile": perfil_llm,
        "image_generation": bool(vram_gb is not None and vram_gb >= 8 and ram_gb is not None and ram_gb >= 16),
        "image_style": "photorealistic",
        "gpu_vendor": vendor,
        "vram_gb": round(vram_gb, 1) if vram_gb is not None else None,
        "ram_gb": ram,
        "nvidia_driver_ok": tem_nvidia,
        "notes": (
            ("GPU detectada; aceleração CUDA para Whisper disponível."
             if tem_nvidia else
             "GPU não NVIDIA, ou driver NVIDIA não confirmado; Whisper usará CPU quando instalado.")
            + (" VRAM livre não foi medida; geração SDXL não será pré-selecionada automaticamente."
               if vram_gb is None else
               " VRAM livre abaixo de 8 GB; geração SDXL não será pré-selecionada automaticamente."
               if vram_gb < 8 else
               " RAM abaixo de 16 GB; geração SDXL não será pré-selecionada automaticamente."
               if ram_gb is None or ram_gb < 16 else "")
        ),
    }


def resumo_componentes() -> list[str]:
    return [
        f"{'[OK]' if item['instalado'] else '[PARCIAL]' if item.get('parcial') else '[--]'} {item['nome']}"
        + (f" — ausente: {', '.join(item['faltantes'])}" if item['faltantes'] else "")
        for item in detectar_componentes().values()
    ]
