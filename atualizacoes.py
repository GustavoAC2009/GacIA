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


def url_releases() -> str | None:
    try:
        config = json.loads((BASE_DIR / "release_config.json").read_text(encoding="utf-8"))
        slug = str(config.get("github_repository") or "").strip()
    except (OSError, ValueError, TypeError):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", slug):
        return None
    return f"https://github.com/{slug}/releases/latest"
