"""Detecção e download explícito de modelos pelo servidor Ollama configurado.

O módulo não instala o Ollama nem inicia downloads sozinho. O chamador deve
solicitar o pull após consentimento explícito do usuário.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

import requests

from config import MODELOS_PADRAO, normalizar_host_ollama

MODELOS = {
    "rapido": {"tag": MODELOS_PADRAO["rapido"], "tamanho_gb": 3.1, "ram_gb": 8, "vram_gb": 4,
               "descricao": "Qwen 3.5 2B: perfil leve para PCs modestos; contexto reduzido recomendado."},
    "intermediario": {"tag": MODELOS_PADRAO["intermediario"], "tamanho_gb": 4.0, "ram_gb": 12, "vram_gb": 6,
                      "descricao": "Qwen 3.5 4B: equilíbrio entre qualidade, velocidade e consumo."},
    "top": {"tag": MODELOS_PADRAO["top"], "tamanho_gb": 7.6, "ram_gb": 16, "vram_gb": 10,
            "descricao": "Qwen 3.5 9B: melhor capacidade local desta seleção; exige memória livre suficiente."},
}

# Mantém a possibilidade de reparar instalações que já utilizam estes tags.
MODELOS_LEGADOS = {
    "qwen2.5:1.5b-instruct", "qwen2.5:7b-instruct", "qwen2.5:14b-instruct",
}


class OllamaModelError(RuntimeError):
    pass


_THINK_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_THINK_CACHE_LOCK = threading.Lock()


def controle_pensamento(modelo: str, host: str = "http://localhost:11434", *, timeout=(1.0, 1.5)) -> dict:
    """Descobre o controle de raciocínio anunciado pelo Ollama (/api/show).

    O resultado fica em cache por 10 minutos para não adicionar uma consulta
    de metadados a cada mensagem. Em falha, devolve suporte desconhecido sem
    impedir a conversa.
    """
    nome = str(modelo or "").strip()
    if not nome:
        return {"supported": False, "value": None, "values": [], "known": False}
    base = normalizar_host_ollama(host)
    chave = (base, nome)
    agora = time.monotonic()
    with _THINK_CACHE_LOCK:
        salvo = _THINK_CACHE.get(chave)
        if salvo and agora - salvo[0] < 600:
            return dict(salvo[1])

    resultado = {"supported": False, "value": None, "values": [], "known": False}
    consulta_concluida = False
    try:
        response = requests.post(base + "/api/show", json={"model": nome}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        consulta_concluida = True
        thinking = payload.get("thinking") if isinstance(payload, dict) else None
        if isinstance(thinking, dict) and isinstance(thinking.get("values"), list):
            valores = thinking["values"]
            resultado["known"] = True
            resultado["values"] = valores
            if any(isinstance(item, str) and item.lower() == "high" for item in valores):
                resultado.update(supported=True, value="high")
            elif True in valores:
                resultado.update(supported=True, value=True)
            else:
                niveis = [item for item in valores if isinstance(item, str) and item.strip()]
                if niveis:
                    resultado.update(supported=True, value=niveis[-1])
    except (requests.RequestException, ValueError, TypeError):
        # Nem todas as versões do Ollama/modelos publicam metadados de thinking.
        pass
    # Não armazena falhas transitórias: Ollama pode estar iniciando na primeira
    # tentativa e deve ser consultado novamente na próxima ativação do modo.
    if consulta_concluida:
        with _THINK_CACHE_LOCK:
            _THINK_CACHE[chave] = (agora, dict(resultado))
    return resultado


def recomendar_perfil(hardware: dict | None) -> str:
    """Recomenda um perfil conservador com base em memória realmente disponível."""
    hardware = hardware or {}
    ram = hardware.get("ram_gb")
    free_ram = hardware.get("ram_available_gb", hardware.get("ram_livre_gb", ram))
    gpus = [gpu for gpu in (hardware.get("gpus") or []) if isinstance(gpu, dict)]
    vram_livre_values = [
        float(gpu["vram_free_mb"]) / 1024
        for gpu in gpus
        if gpu.get("vram_free_mb") is not None
    ]
    vram_total_values = [
        float(gpu["vram_mb"]) / 1024
        for gpu in gpus
        if gpu.get("vram_mb") is not None
    ]
    vram_livre = max(vram_livre_values) if vram_livre_values else None
    vram_total = max(vram_total_values) if vram_total_values else None
    try:
        ram_total = float(ram) if ram is not None else None
        ram_livre = float(free_ram) if free_ram is not None else ram_total
    except (TypeError, ValueError):
        ram_total, ram_livre = None, None

    # O 9B só é recomendado com VRAM livre medida. Se não houver medição,
    # usa-se uma margem muito maior para CPU-only, sem assumir que VRAM total
    # equivale a VRAM livre.
    if ram_total is not None and ram_total >= 16 and ram_livre >= 8 and (
        (vram_livre is not None and vram_livre >= 10)
        or (vram_livre is None and vram_total is None and ram_total >= 32 and ram_livre >= 20)
    ):
        return "top"

    # Intermediário: GPU com ao menos 5 GB realmente livres; sem medição de
    # VRAM, exige pelo menos 8 GB totais, ou 16 GB de RAM para CPU-only.
    intermediario_viavel = (
        (vram_livre is not None and vram_livre >= 5)
        or (vram_livre is None and vram_total is not None and vram_total >= 8)
        or (vram_livre is None and vram_total is None and ram_total is not None and ram_total >= 16 and ram_livre >= 8)
    )
    if ram_total is not None and ram_total >= 12 and ram_livre >= 6 and intermediario_viavel:
        return "intermediario"
    return "rapido"


def contexto_recomendado(perfil: str = "intermediario") -> int:
    """Limites conservadores para evitar contextos enormes e picos de VRAM/RAM."""
    return {"rapido": 4096, "intermediario": 8192, "top": 8192}.get(str(perfil), 8192)


def avaliar_capacidade_local(hardware: dict | None) -> dict:
    """Descreve limites de execução local sem confundir compatibilidade com desempenho."""
    dados = hardware or {}
    try:
        ram = float(dados.get("ram_gb") or 0)
        livre = float(dados.get("ram_available_gb", dados.get("ram_livre_gb", ram)) or 0)
    except (TypeError, ValueError):
        ram = livre = 0.0
    perfil = recomendar_perfil(dados)
    avisos = []
    suportado = ram >= 6 and livre >= 3
    if ram and ram < 8:
        avisos.append("Memória limitada: somente um modelo muito pequeno, com contexto reduzido, é recomendável.")
    if ram and ram < 6:
        avisos.append("Este computador está abaixo do mínimo recomendado para uma experiência local aceitável.")
    elif not ram:
        avisos.append("Não foi possível medir a RAM. A recomendação de modelo pode estar incorreta; verifique o hardware antes de baixar modelos grandes.")
    if ram and livre < 3:
        avisos.append("Há pouca RAM livre; feche outros programas antes de iniciar o modelo.")
    gpus = [gpu for gpu in (dados.get("gpus") or []) if isinstance(gpu, dict)]
    vram_total = [float(gpu["vram_mb"]) / 1024 for gpu in gpus if gpu.get("vram_mb") is not None]
    vram_livre = [float(gpu["vram_free_mb"]) / 1024 for gpu in gpus if gpu.get("vram_free_mb") is not None]
    if not vram_total:
        avisos.append("Sem VRAM dedicada identificável: o modelo dependerá da CPU/RAM e poderá responder mais lentamente.")
    elif not vram_livre:
        avisos.append("A VRAM total foi identificada, mas a VRAM livre não pôde ser medida; a recomendação será conservadora.")
    elif max(vram_livre) < 4:
        avisos.append("Há menos de 4 GB de VRAM livres; use o perfil Leve ou feche aplicativos que utilizam a GPU.")
    return {"supported": suportado, "profile": perfil, "context_tokens": contexto_recomendado(perfil), "warnings": avisos}


def listar_modelos(host: str = "http://localhost:11434", timeout: float = 4.0) -> list[dict]:
    base = normalizar_host_ollama(host)
    try:
        response = requests.get(base + "/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as erro:
        raise OllamaModelError(f"Não foi possível consultar o Ollama em {base}: {erro}") from erro
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise OllamaModelError("O Ollama retornou uma lista de modelos em formato inesperado.")
    return [item for item in models if isinstance(item, dict)]


def modelo_instalado(tag: str, host: str = "http://localhost:11434", timeout: float = 4.0) -> bool:
    target = str(tag or "").strip()
    if not target:
        return False
    nomes = set()
    for model in listar_modelos(host, timeout):
        nome = str(model.get("name") or model.get("model") or "").strip()
        if nome:
            nomes.add(nome)
    return target in nomes


def baixar_modelo(
    tag: str,
    host: str = "http://localhost:11434",
    *,
    progress: Callable[[dict], None] | None = None,
    cancel_event=None,
    timeout: tuple[float, float] = (5.0, 30.0),
) -> str:
    """Executa `/api/pull` em streaming e retorna quando Ollama declarar sucesso."""
    tag = str(tag or "").strip()
    permitidas = {item["tag"] for item in MODELOS.values()} | MODELOS_LEGADOS
    if tag not in permitidas:
        raise OllamaModelError("Modelo fora do catálogo aprovado pela Gac.IA.")
    base = normalizar_host_ollama(host)
    try:
        with requests.post(
            base + "/api/pull", json={"name": tag, "stream": True},
            headers={"Accept": "application/x-ndjson"}, stream=True, timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1024, decode_unicode=True):
                if cancel_event is not None and cancel_event.is_set():
                    raise OllamaModelError("Download cancelado. O Ollama pode manter camadas já baixadas para retomada.")
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if progress:
                    progress(data)
                if data.get("error"):
                    raise OllamaModelError(str(data["error"]))
                if data.get("status") == "success":
                    return tag
    except requests.RequestException as erro:
        raise OllamaModelError(f"Falha de comunicação com Ollama: {erro}") from erro
    raise OllamaModelError("A conexão terminou antes de o Ollama confirmar a conclusão do download.")
