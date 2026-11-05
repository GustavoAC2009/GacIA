"""Inventário somente leitura do ambiente Gac.IA.

Detecta dependências, caches de modelos e disponibilidade do Ollama sem baixar,
remover ou alterar componentes. Pode ser executado repetidamente com segurança.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PACOTES = (
    "PySide6", "requests", "Pillow", "python-docx", "openpyxl",
    "python-pptx", "pypdf", "reportlab", "ddgs", "numpy", "sounddevice",
    "faster-whisper", "ctranslate2", "pygame", "edge-tts", "pyttsx3",
    "pywin32", "nvidia-cublas-cu12", "nvidia-cudnn-cu12",
)


def _versoes_instaladas() -> dict[str, str | None]:
    resultado: dict[str, str | None] = {}
    for nome in PACOTES:
        try:
            resultado[nome] = importlib.metadata.version(nome)
        except importlib.metadata.PackageNotFoundError:
            resultado[nome] = None
    return resultado


def _localizar_ollama() -> str | None:
    executavel = shutil.which("ollama") or shutil.which("ollama.exe")
    if executavel:
        return executavel
    if os.name == "nt":
        candidatos = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Ollama" / "ollama.exe",
        ]
        for candidato in candidatos:
            if candidato.is_file():
                return str(candidato)
    return None


def _ollama_info() -> dict:
    executavel = _localizar_ollama()
    host = os.environ.get("GACIA_OLLAMA_URL", "").strip()
    if not host:
        try:
            config_path = Path(__file__).resolve().parent / "config.json"
            if config_path.is_file():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(config, dict):
                    host = str(config.get("ollama_host") or "").strip()
        except (OSError, json.JSONDecodeError):
            pass
    host = host or "http://127.0.0.1:11434"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    host = host.rstrip("/")
    info = {"instalado": bool(executavel), "executavel": executavel,
            "host_configurado": host, "servidor_ativo": False,
            "modelos": [], "erro": None}
    try:
        partes = urlsplit(host)
        if partes.scheme not in {"http", "https"} or not partes.hostname:
            raise ValueError("endereço Ollama inválido")
        endpoint = host + "/api/tags"
        req = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0) as resposta:
            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
        info["servidor_ativo"] = True
        for modelo in dados.get("models", []):
            if isinstance(modelo, dict):
                info["modelos"].append({
                    "nome": modelo.get("name") or modelo.get("model") or "modelo sem nome",
                    "tamanho_bytes": modelo.get("size"),
                })
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as erro:
        info["erro"] = f"Servidor Ollama indisponível/não verificável: {type(erro).__name__}"
    return info


def _diretorios_cache_hf() -> list[Path]:
    candidatos = []
    for chave in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(chave):
            candidatos.append(Path(os.environ[chave]).expanduser())
    if os.environ.get("HF_HOME"):
        candidatos.append(Path(os.environ["HF_HOME"]).expanduser() / "hub")
    candidatos.append(Path.home() / ".cache" / "huggingface" / "hub")
    unicos: list[Path] = []
    vistos = set()
    for caminho in candidatos:
        chave = os.path.normcase(os.path.abspath(str(caminho)))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(caminho)
    return unicos


def _modelos_huggingface() -> list[dict[str, str]]:
    encontrados = []
    vistos = set()
    for cache in _diretorios_cache_hf():
        if not cache.is_dir():
            continue
        try:
            pastas = cache.iterdir()
            for pasta in pastas:
                if not pasta.is_dir() or not pasta.name.startswith("models--"):
                    continue
                chave = os.path.normcase(os.path.abspath(str(pasta)))
                if chave in vistos:
                    continue
                vistos.add(chave)
                # Um repositório sem snapshots não está pronto para reutilização.
                snapshots = pasta / "snapshots"
                pronto = snapshots.is_dir() and any(p.is_dir() for p in snapshots.iterdir())
                nome = pasta.name.removeprefix("models--").replace("--", "/")
                encontrados.append({"repositorio": nome, "disponivel_localmente": pronto,
                                     "caminho": str(pasta)})
        except OSError:
            continue
    return sorted(encontrados, key=lambda item: item["repositorio"].lower())


def coletar_inventario() -> dict:
    try:
        import hardware
        dados_hardware = hardware.detectar_hardware()
    except Exception as erro:
        dados_hardware = {"erro": f"{type(erro).__name__}: {erro}"}
    try:
        import componentes
        estado_componentes = componentes.detectar_componentes()
        manifesto_componentes = componentes.carregar_manifesto()
    except Exception as erro:
        estado_componentes = {"erro": f"{type(erro).__name__}: {erro}"}
        manifesto_componentes = None
    try:
        from comfy_manager import comfy_instalado, servidor_responde
        estado_comfy = {"instalado_portatil": comfy_instalado(), "api_ativa": servidor_responde()}
    except Exception as erro:
        estado_comfy = {"erro": f"{type(erro).__name__}: {erro}"}
    try:
        disco = shutil.disk_usage(Path(__file__).resolve().parent)
        espaco = {"livre_bytes": disco.free, "total_bytes": disco.total}
    except OSError:
        espaco = None
    return {
        "python": {"versao": sys.version.split()[0], "arquitetura_bits": 64 if sys.maxsize > 2**32 else 32,
                   "executavel": sys.executable},
        "pacotes": _versoes_instaladas(),
        "hardware": dados_hardware,
        "componentes": estado_componentes,
        "manifesto_componentes": manifesto_componentes,
        "comfyui": estado_comfy,
        "ollama": _ollama_info(),
        "modelos_huggingface": _modelos_huggingface(),
        "disco": espaco,
    }


def imprimir_inventario(dados: dict | None = None) -> None:
    dados = dados or coletar_inventario()
    print("\n--- INVENTÁRIO LOCAL (somente leitura) ---")
    print(f"Python: {dados['python']['versao']} ({dados['python']['arquitetura_bits']}-bit)")
    print("Pacotes:")
    for nome, versao in dados["pacotes"].items():
        print(f"  {'[OK]' if versao else '[--]'} {nome}: {versao or 'não instalado'}")
    componentes_estado = dados.get("componentes", {})
    manifesto = dados.get("manifesto_componentes")
    if manifesto:
        print("Componentes registrados: " + ", ".join(manifesto.get("componentes", [])))
    for nome, estado in componentes_estado.items():
        if isinstance(estado, dict):
            situacao = (
                "OK" if estado.get("instalado") else
                "PARCIAL — reparável" if estado.get("parcial") else
                "não instalado"
            )
            faltantes = estado.get("faltantes") or []
            detalhe = f"; ausentes: {', '.join(faltantes)}" if faltantes else ""
            print(f"Componente {estado.get('nome', nome)}: {situacao}{detalhe}")
    comfy = dados.get("comfyui", {})
    if comfy:
        print(f"ComfyUI: portátil {'instalado' if comfy.get('instalado_portatil') else 'não encontrado'}; API {'ativa' if comfy.get('api_ativa') else 'inativa'}")
    ollama = dados["ollama"]
    print(f"Ollama: {'executável encontrado' if ollama['instalado'] else 'executável não encontrado'}; "
          f"servidor {'ativo' if ollama['servidor_ativo'] else 'inativo/não verificado'} ({ollama['host_configurado']})")
    for modelo in ollama["modelos"]:
        tamanho = modelo.get("tamanho_bytes")
        tamanho_txt = f" ({tamanho / (1024**3):.1f} GB)" if isinstance(tamanho, (int, float)) else ""
        print(f"  Modelo Ollama: {modelo['nome']}{tamanho_txt}")
    caches = dados["modelos_huggingface"]
    print(f"Caches Hugging Face encontrados: {len(caches)}")
    for modelo in caches:
        estado = "pronto" if modelo["disponivel_localmente"] else "incompleto"
        print(f"  Modelo HF: {modelo['repositorio']} [{estado}]")
    disco = dados.get("disco")
    if disco:
        print(f"Espaço livre no disco do projeto: {disco['livre_bytes'] / (1024**3):.1f} GB")
    print("Nenhum modelo, configuração ou cache foi alterado.")


if __name__ == "__main__":
    imprimir_inventario()
