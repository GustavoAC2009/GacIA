"""Configuração persistente da Gac.IA."""
from __future__ import annotations

import ipaddress
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

MODELOS_PADRAO = {
    # Modelos atuais e progressivos: 2B para máquinas modestas, 4B como
    # equilíbrio e 9B apenas quando RAM/VRAM disponíveis comportarem a carga.
    # Configurações antigas são preservadas pelo merge abaixo.
    "rapido": "qwen3.5:2b",
    "intermediario": "qwen3.5:4b",
    "top": "qwen3.5:9b",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "perfil_ativo": "intermediario",
    "modelos": deepcopy(MODELOS_PADRAO),
    "voz": "feminina",
    "pesquisa_web_ativa": False,
    "preferencias_fontes_web": {"oficiais": False, "cientificas": False, "noticias": False, "alertar_antigas": True},
    "linguagem": "pt-BR",
    "nome_usuario": "",
    "personalidade": "equilibrada",
    "ollama_host": "http://localhost:11434",
    "ollama_keep_alive": "2m",
    "modo_pensar_mais": False,
    "whisper_device": "auto",
    "whisper_model": "small",
    "modo_ao_vivo": False,
    "configuracao_inicial_concluida": False,
    "configuracao_componentes_concluida": False,
    "recursos_ativados": {"office": True, "ocr": False, "web": True, "voice": False, "image_generation": False},
    "tema": "Dark",
    "gerador_imagens": {
        "url": "http://127.0.0.1:8188",
        "checkpoint": "",
        "comfy_model_dir": "",
        "preferred_style": "photorealistic",
        "width": 768,
        "height": 768,
        "slides_width": 768,
        "slides_height": 432,
        "steps": 30,
        "steps_auto": True,
    },
}


def normalizar_host_ollama(valor: Any) -> str:
    """Normaliza uma URL-base do Ollama e remove sufixos de endpoint conhecidos."""
    padrao = "http://localhost:11434"
    texto = str(valor or padrao).strip().strip("\"'")
    if not texto:
        return padrao

    encontrado = re.search(r"https?://[^\s)\]]+", texto, flags=re.IGNORECASE)
    if encontrado:
        texto = encontrado.group(0)
    elif not re.match(r"^https?://", texto, flags=re.IGNORECASE):
        texto = "http://" + texto

    try:
        partes = urlsplit(texto)
        if partes.scheme.lower() not in {"http", "https"} or not partes.hostname:
            return padrao
        _ = partes.port  # Acessar .port valida valores/IPv6 malformados.
        if partes.username or partes.password:
            return padrao
        caminho = partes.path.rstrip("/")
        caminho_lower = caminho.lower()
        for sufixo in ("/api/chat", "/api/generate", "/api/tags", "/api"):
            if caminho_lower.endswith(sufixo):
                caminho = caminho[:-len(sufixo)]
                break
        normalizado = urlunsplit(
            partes._replace(path=caminho, query="", fragment="")
        ).rstrip("/")
        return normalizado or padrao
    except (TypeError, ValueError):
        return padrao


def _mesclar_config(dados: Any) -> dict[str, Any]:
    """Mescla defaults sem sobrescrever escolhas salvas pelo usuário."""
    config = deepcopy(DEFAULT_CONFIG)
    if isinstance(dados, dict):
        config.update(dados)

    modelos_salvos = dados.get("modelos", {}) if isinstance(dados, dict) else {}
    if not isinstance(modelos_salvos, dict):
        modelos_salvos = {}
    modelos = deepcopy(MODELOS_PADRAO)
    for perfil, nome in modelos_salvos.items():
        if perfil in modelos and isinstance(nome, str) and nome.strip():
            modelos[perfil] = nome.strip()
    config["modelos"] = modelos

    perfil = config.get("perfil_ativo")
    if not isinstance(perfil, str) or perfil not in MODELOS_PADRAO:
        perfil = "intermediario"
    config["perfil_ativo"] = perfil

    if not isinstance(config.get("voz"), str) or config["voz"] not in {"feminina", "masculina"}:
        config["voz"] = "feminina"
    if not isinstance(config.get("whisper_device"), str) or config["whisper_device"] not in {"auto", "cuda", "cpu"}:
        config["whisper_device"] = "auto"
    if not isinstance(config.get("tema"), str) or config["tema"] not in {"Dark", "Light", "System"}:
        config["tema"] = "Dark"
    if not isinstance(config.get("pesquisa_web_ativa"), bool):
        config["pesquisa_web_ativa"] = False
    preferencias_web = config.get("preferencias_fontes_web")
    if not isinstance(preferencias_web, dict):
        preferencias_web = {}
    config["preferencias_fontes_web"] = {
        "oficiais": bool(preferencias_web.get("oficiais", False)),
        "cientificas": bool(preferencias_web.get("cientificas", False)),
        "noticias": bool(preferencias_web.get("noticias", False)),
        "alertar_antigas": bool(preferencias_web.get("alertar_antigas", True)),
    }
    linguagem = config.get("linguagem", "pt-BR")
    config["linguagem"] = linguagem if isinstance(linguagem, str) and linguagem in {"pt-BR", "en"} else "pt-BR"
    nome_usuario = config.get("nome_usuario", "")
    config["nome_usuario"] = str(nome_usuario or "").strip()[:40]
    personalidade = config.get("personalidade", "equilibrada")
    personalidades_validas = {"equilibrada", "amigavel", "profissional", "didatica", "objetiva"}
    config["personalidade"] = personalidade if isinstance(personalidade, str) and personalidade in personalidades_validas else "equilibrada"
    if not isinstance(config.get("modo_ao_vivo"), bool):
        config["modo_ao_vivo"] = False
    if not isinstance(config.get("configuracao_inicial_concluida"), bool):
        config["configuracao_inicial_concluida"] = False
    if not isinstance(config.get("configuracao_componentes_concluida"), bool):
        config["configuracao_componentes_concluida"] = False
    recursos = config.get("recursos_ativados")
    if not isinstance(recursos, dict):
        recursos = {}
    config["recursos_ativados"] = {
        "office": bool(recursos.get("office", True)),
        "ocr": bool(recursos.get("ocr", False)),
        "web": bool(recursos.get("web", True)),
        "voice": bool(recursos.get("voice", False)),
        "image_generation": bool(recursos.get("image_generation", False)),
    }
    if not isinstance(config.get("ollama_keep_alive"), str) or not config["ollama_keep_alive"].strip():
        config["ollama_keep_alive"] = "2m"
    if not isinstance(config.get("modo_pensar_mais"), bool):
        config["modo_pensar_mais"] = False
    if not isinstance(config.get("whisper_model"), str) or not config["whisper_model"].strip():
        config["whisper_model"] = "small"

    imagens = config.get("gerador_imagens")
    if not isinstance(imagens, dict):
        imagens = {}
    padrao_imagens = deepcopy(DEFAULT_CONFIG["gerador_imagens"])
    padrao_imagens.update({k: v for k, v in imagens.items() if k in padrao_imagens})
    padrao_imagens["comfy_model_dir"] = str(padrao_imagens.get("comfy_model_dir", "") or "").strip()[:1000]
    estilos_imagem = {"photorealistic", "artistic", "anime", "versatile"}
    if padrao_imagens.get("preferred_style") not in estilos_imagem:
        padrao_imagens["preferred_style"] = "photorealistic"
    url_imagens = str(padrao_imagens.get("url", "")).strip().rstrip("/")
    try:
        partes_url = urlsplit(url_imagens)
        host_url = (partes_url.hostname or "").lower()
        _ = partes_url.port  # valida porta fora do intervalo e sintaxe inválida
        host_local = host_url == "localhost"
        if not host_local:
            try:
                host_local = ipaddress.ip_address(host_url).is_loopback
            except ValueError:
                host_local = False
        url_valida = (
            partes_url.scheme == "http" and host_local
            and not partes_url.username and not partes_url.password
            and partes_url.path in ("", "/")
            and not partes_url.query and not partes_url.fragment
        )
    except ValueError:
        url_valida = False
    if not url_valida:
        url_imagens = "http://127.0.0.1:8188"
    padrao_imagens["url"] = url_imagens
    padrao_imagens["checkpoint"] = str(padrao_imagens.get("checkpoint", "") or "").strip()
    for chave, minimo, maximo, padrao in (("width", 256, 1536, 768), ("height", 256, 1536, 768), ("steps", 1, 50, 30)):
        try:
            padrao_imagens[chave] = max(minimo, min(maximo, int(padrao_imagens.get(chave, padrao))))
        except (TypeError, ValueError):
            padrao_imagens[chave] = padrao
    if not isinstance(padrao_imagens.get("steps_auto"), bool):
        padrao_imagens["steps_auto"] = True
    config["gerador_imagens"] = padrao_imagens

    host_env = os.getenv("GACIA_OLLAMA_URL", "").strip()
    if host_env:
        config["ollama_host"] = host_env
    modelo_env = os.getenv("GACIA_OLLAMA_MODEL", "").strip()
    if modelo_env:
        config["modelos"][config["perfil_ativo"]] = modelo_env
    whisper_env = os.getenv("GACIA_WHISPER_MODEL", "").strip()
    if whisper_env:
        config["whisper_model"] = whisper_env

    return config


def carregar_config() -> dict[str, Any]:
    """Carrega o JSON com fallback seguro para os padrões."""
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except FileNotFoundError:
        dados = {}
    except (OSError, json.JSONDecodeError) as erro:
        # Não sobrescreve automaticamente um arquivo potencialmente recuperável.
        print(f"Aviso: não foi possível ler {CONFIG_FILE.name}: {erro}")
        dados = {}
    return _mesclar_config(dados)


def salvar_config(config: dict[str, Any]) -> bool:
    """Salva atomicamente para evitar JSON truncado após encerramento abrupto."""
    if not isinstance(config, dict):
        raise TypeError("A configuração precisa ser um dicionário.")

    temporario = CONFIG_FILE.with_suffix(".json.tmp")
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with temporario.open("w", encoding="utf-8", newline="\n") as arquivo:
            json.dump(config, arquivo, indent=4, ensure_ascii=False)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, CONFIG_FILE)
        return True
    except OSError as erro:
        print(f"Erro ao salvar configurações: {erro}")
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        return False
