"""Diagnóstico local. Não instala, altera ou apaga arquivos do usuário."""
from __future__ import annotations

import importlib
from importlib import metadata
import json
import platform
import struct
import sys
import urllib.error
import urllib.request

from config import carregar_config, normalizar_host_ollama
from hardware import detectar_hardware, resumir_hardware, detectar_backend_whisper


def linha(titulo: str, estado: bool, detalhe: str = "", aviso: bool = False) -> None:
    if estado:
        simbolo = "OK"
    else:
        simbolo = "AVISO" if aviso else "FALHA"
    sufixo = f" — {detalhe}" if detalhe else ""
    print(f"[{simbolo}] {titulo}{sufixo}")


def verificar_pacote(nome: str, modulo: str | None = None) -> bool:
    modulo = modulo or nome.replace("-", "_")
    try:
        importlib.import_module(modulo)
        try:
            versao = metadata.version(nome)
        except metadata.PackageNotFoundError:
            versao = "versão não identificada"
        linha(nome, True, versao)
        return True
    except Exception as erro:
        linha(nome, False, str(erro))
        return False



def verificar_ollama(config: dict) -> bool:
    host = normalizar_host_ollama(config.get("ollama_host"))
    url = f"{host}/api/tags"
    perfil = config.get("perfil_ativo", "intermediario")
    modelo = config.get("modelos", {}).get(perfil, "")
    try:
        requisicao = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(requisicao, timeout=3) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        if not isinstance(dados, dict):
            raise ValueError("resposta inesperada da API /api/tags")
        nomes = {
            str(item.get("name") or item.get("model") or "")
            for item in dados.get("models", [])
            if isinstance(item, dict)
        }
        linha("API Ollama", True, url)
        modelo_ok = bool(modelo and modelo in nomes)
        linha("Modelo configurado", modelo_ok, modelo or "nenhum", aviso=not modelo_ok)
        return modelo_ok
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as erro:
        linha("API Ollama", False, f"{url} — {erro}", aviso=True)
        return False


def verificar_microfone() -> bool:
    try:
        sounddevice = importlib.import_module("sounddevice")
        dispositivo = sounddevice.query_devices(kind="input")
        linha(
            "Microfone padrão", True,
            f"{dispositivo.get('name', 'desconhecido')} | "
            f"{dispositivo.get('default_samplerate', '?')} Hz",
        )
        return True
    except Exception as erro:
        linha("Microfone padrão", False, str(erro), aviso=True)
        return False


def verificar_cuda() -> bool:
    try:
        ctranslate2 = importlib.import_module("ctranslate2")
        quantidade = int(ctranslate2.get_cuda_device_count())
        linha(
            "CTranslate2 / CUDA", quantidade > 0,
            f"dispositivos detectados: {quantidade}", aviso=quantidade == 0,
        )
        return quantidade > 0
    except Exception as erro:
        linha("CTranslate2 / CUDA", False, str(erro), aviso=True)
        return False


def main() -> int:
    config = carregar_config()
    perfil = config.get("perfil_ativo", "intermediario")
    modelo = config.get("modelos", {}).get(perfil, "não configurado")

    print("=" * 60)
    print("DIAGNÓSTICO DA GAC.IA")
    print("=" * 60)
    print(f"Sistema: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]} | {struct.calcsize('P') * 8}-bit")
    print(f"Perfil/modelo: {perfil} / {modelo}")
    print(f"Endpoint: {config.get('ollama_host', 'http://localhost:11434')}")
    print("-" * 60)
    print("HARDWARE DETECTADO")
    for item in resumir_hardware(detectar_hardware()):
        print(item)
    backend, motivo = detectar_backend_whisper()
    linha("Backend recomendado para Faster-Whisper", True, f"{backend.upper()} — {motivo}", aviso=(backend == "cpu"))
    print("Ollama possui detecção de GPU independente; veja os logs do próprio Ollama para confirmar aceleração.")
    print("-" * 60)

    python_ok = sys.version_info[:2] == (3, 13) and struct.calcsize("P") == 8
    linha("Python recomendado", python_ok, "use Python 3.13 x64" if not python_ok else "Python 3.13 x64")

    pacotes_ok = True
    for pacote, modulo in (
        ("PySide6", "PySide6"),
        ("requests", "requests"),
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("faster-whisper", "faster_whisper"),
        ("ctranslate2", "ctranslate2"),
        ("pygame", "pygame"),
        ("edge-tts", "edge_tts"),
        ("pyttsx3", "pyttsx3"),
        ("ddgs", "ddgs"),
    ):
        resultado = verificar_pacote(pacote, modulo)
        pacotes_ok = resultado and pacotes_ok

    if sys.platform == "win32":
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
            linha("pywin32 / SAPI", True)
        except Exception as erro:
            linha("pywin32 / SAPI", False, str(erro))
            pacotes_ok = False

    print("-" * 60)
    verificar_cuda()
    verificar_microfone()
    verificar_ollama(config)
    print("-" * 60)
    if python_ok and pacotes_ok:
        print("Diagnóstico concluído. Dependências essenciais estão importáveis.")
        return 0
    print("Diagnóstico encontrou falhas essenciais. Execute preparar.bat e revise os erros.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
