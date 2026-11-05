"""Metadados mínimos de anexos persistidos junto às mensagens do chat.

Os caminhos absolutos nunca são gravados no banco; apenas nome, extensão e tamanho.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MARKER = "\n\n<!--GACIA_ATTACHMENTS_V1:"
_MARKER_END = "-->"
MAX_PERSISTED_ATTACHMENTS = 100


def serializar_metadados_anexos(texto: str, anexos: list[dict] | None) -> str:
    base = str(texto or "")
    if not anexos:
        return base
    seguros = []
    for item in anexos[:MAX_PERSISTED_ATTACHMENTS]:
        if not isinstance(item, dict):
            continue
        nome_bruto = str(item.get("name") or "arquivo").replace("\\", "/")
        nome = Path(nome_bruto).name
        nome = "".join(caractere for caractere in nome if caractere.isprintable())[:255] or "arquivo"
        extensao_bruta = str(item.get("extension") or "").lower()
        if extensao_bruta and not extensao_bruta.startswith("."):
            extensao_bruta = "." + extensao_bruta
        extensao = extensao_bruta if re.fullmatch(r"\.[a-z0-9]{1,12}", extensao_bruta) else ""
        tamanho = item.get("size_bytes")
        if type(tamanho) is not int or tamanho < 0:
            tamanho = None
        seguros.append({"name": nome, "extension": extensao, "size_bytes": tamanho})
    if not seguros:
        return base
    payload = json.dumps(seguros, ensure_ascii=False, separators=(",", ":"))
    return base + MARKER + payload + _MARKER_END


def anexar_metadados_anexos(texto: str, caminhos: list[str] | None) -> str:
    metadados = []
    for caminho in caminhos or []:
        arquivo = Path(caminho).expanduser()
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            tamanho = None
        metadados.append({
            "name": arquivo.name or "arquivo",
            "extension": arquivo.suffix.lower(),
            "size_bytes": tamanho,
        })
    return serializar_metadados_anexos(texto, metadados)


def extrair_metadados_anexos(conteudo: str) -> tuple[str, list[dict]]:
    texto = str(conteudo or "")
    inicio = texto.rfind(MARKER)
    if inicio < 0 or not texto.endswith(_MARKER_END):
        return texto, []
    payload = texto[inicio + len(MARKER):-len(_MARKER_END)]
    try:
        dados = json.loads(payload)
    except (TypeError, ValueError):
        return texto, []
    if not isinstance(dados, list) or len(dados) > MAX_PERSISTED_ATTACHMENTS:
        return texto, []
    resultado = []
    for item in dados:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        tamanho = item.get("size_bytes")
        if type(tamanho) is not int or tamanho < 0:
            tamanho = None
        nome_bruto = item["name"].replace("\\", "/")
        nome = Path(nome_bruto).name
        nome = "".join(caractere for caractere in nome if caractere.isprintable())[:255] or "arquivo"
        extensao_bruta = str(item.get("extension") or "").lower()
        if extensao_bruta and not extensao_bruta.startswith("."):
            extensao_bruta = "." + extensao_bruta
        extensao = extensao_bruta if re.fullmatch(r"\.[a-z0-9]{1,12}", extensao_bruta) else ""
        resultado.append({"name": nome, "extension": extensao, "size_bytes": tamanho})
    return texto[:inicio], resultado


def texto_sem_metadados_anexos(conteudo: str) -> str:
    return extrair_metadados_anexos(conteudo)[0]
