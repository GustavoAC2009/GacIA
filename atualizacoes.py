"""Consulta e valida releases públicas da Gac.IA."""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def versao_atual() -> str:
    try:
        value = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
        return value[:40] if value else "desenvolvimento"
    except OSError:
        return "desenvolvimento"


def canal_atualizacoes() -> str:
    """Retorna o canal embutido no pacote: estável ou desenvolvimento."""
    try:
        config = json.loads((BASE_DIR / "release_config.json").read_text(encoding="utf-8-sig"))
        value = str(config.get("release_channel") or "stable").strip().lower()
    except (OSError, ValueError, TypeError):
        return "stable"
    return "development" if value in {"development", "dev", "preview", "prerelease"} else "stable"


def repositorio_github() -> str | None:
    try:
        config = json.loads((BASE_DIR / "release_config.json").read_text(encoding="utf-8-sig"))
        slug = str(config.get("github_repository") or "").strip()
    except (OSError, ValueError, TypeError):
        return None
    return slug if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", slug) else None


def url_releases() -> str | None:
    slug = repositorio_github()
    if not slug:
        return None
    if canal_atualizacoes() == "development":
        return f"https://github.com/{slug}/releases"
    return f"https://github.com/{slug}/releases/latest"


_VERSION_RE = re.compile(r"^v?(\\d+)\\.(\\d+)\\.(\\d+)(?:[-.]([A-Za-z]+)(?:[.-]?(\\d+))?)?$")


def comparar_versoes(instalada: str, publicada: str) -> int | None:
    """Compara versões semver simples; retorna None para versão local não reconhecida."""
    def chave(value: str):
        match = _VERSION_RE.fullmatch(str(value or "").strip())
        if not match:
            return None
        major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
        label = (match.group(4) or "").lower()
        number = int(match.group(5) or 0)
        ranks = {"dev": 0, "preview": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}
        if not label:
            return major, minor, patch, 4, 0, ""
        return major, minor, patch, ranks.get(label, 0), number, label

    left = chave(instalada)
    right = chave(publicada)
    if left is None or right is None:
        return None
    return (left > right) - (left < right)
