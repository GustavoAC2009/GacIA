"""Links seguros para consultar a versão e as releases da Gac.IA."""
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
        config = json.loads((BASE_DIR / "release_config.json").read_text(encoding="utf-8"))
        value = str(config.get("release_channel") or "stable").strip().lower()
    except (OSError, ValueError, TypeError):
        return "stable"
    return "development" if value in {"development", "dev", "preview", "prerelease"} else "stable"


def url_releases() -> str | None:
    try:
        config = json.loads((BASE_DIR / "release_config.json").read_text(encoding="utf-8"))
        slug = str(config.get("github_repository") or "").strip()
    except (OSError, ValueError, TypeError):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", slug):
        return None
    if canal_atualizacoes() == "development":
        return f"https://github.com/{slug}/releases"
    return f"https://github.com/{slug}/releases/latest"
