"""Pesquisa e obtenção controlada de imagens para materiais visuais.

A pesquisa externa usa somente Wikimedia Commons e conserva autoria, licença
compatível e página de origem para atribuição no material final.
"""
from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
import socket
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

LOGGER = logging.getLogger("GacIA.MediaAssets")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_HOSTS = {"upload.wikimedia.org"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 18 * 1024 * 1024
LICENSE_ALLOWLIST = (
    "cc0", "public domain", "cc by", "cc-by", "cc by-sa", "cc-by-sa",
)


def _plain(value: object, max_len: int = 400) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return " ".join(text.split())[:max_len]


def _license_allowed(label: str) -> bool:
    normalized = _plain(label, 120).casefold().replace("_", " ")
    if not normalized or "noncommercial" in normalized or "non-commercial" in normalized:
        return False
    # Os rótulos do Commons frequentemente usam as siglas BY-NC e BY-ND;
    # não basta procurar a palavra completa "noncommercial".
    if re.search(r"(?:^|[-\s])nc(?:[-\s]|$)", normalized):
        return False
    if "no derivatives" in normalized or re.search(r"(?:^|[-\s])nd(?:[-\s]|$)", normalized):
        return False
    return any(token in normalized for token in LICENSE_ALLOWLIST)


def _safe_public_https(url: str) -> bool:
    """Restringe downloads a URLs HTTPS públicas; bloqueia SSRF e redirecionamentos internos."""
    try:
        parts = urlparse(str(url or ""))
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return False
        host = parts.hostname.rstrip(".").lower()
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)}
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except (OSError, TypeError, ValueError):
        return False


def _download_remote_image(url: str, destination: Path, filename: str, timeout=(5, 12)) -> str | None:
    """Baixa imagem pública validando redirecionamentos, MIME, assinatura e tamanho."""
    current = url
    headers = {"User-Agent": "GacIA/1.0 (image attribution enabled)", "Accept": "image/*"}
    for _ in range(4):
        if not _safe_public_https(current):
            return None
        try:
            response = requests.get(current, headers=headers, timeout=timeout, stream=True, allow_redirects=False)
            if response.is_redirect:
                redirected = urljoin(current, response.headers.get("Location", ""))
                response.close()
                current = redirected
                continue
            response.raise_for_status()
            mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if mime not in ALLOWED_MIME:
                response.close()
                return None
            chunks = []
            total = 0
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    response.close()
                    return None
                chunks.append(chunk)
            response.close()
            data = b"".join(chunks)
            signatures = {
                "image/png": (".png", data.startswith(b"\x89PNG\r\n\x1a\n")),
                "image/jpeg": (".jpg", data.startswith(b"\xff\xd8\xff")),
                "image/webp": (".webp", data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
            }
            suffix, valid = signatures.get(mime, ("", False))
            if not valid or len(data) < 256:
                return None
            target = destination / f"{filename}{suffix}"
            target.write_bytes(data)
            return str(target.resolve())
        except (requests.RequestException, OSError):
            return None
    return None


def _verified_page_license(url: str, timeout=(4, 8)) -> tuple[str, str] | None:
    """Confirma licença reutilizável declarada na página de origem."""
    current = url
    try:
        for _ in range(4):
            if not _safe_public_https(current):
                return None
            response = requests.get(current, headers={"User-Agent": "GacIA/1.0 (license verification)"},
                                    timeout=timeout, stream=True, allow_redirects=False)
            if response.is_redirect:
                current = urljoin(current, response.headers.get("Location", ""))
                response.close()
                continue
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(32 * 1024):
                if not chunk:
                    continue
                data.extend(chunk)
                if len(data) >= 1024 * 1024:
                    break
            response.close()
            break
        else:
            return None
        source = data.decode("utf-8", errors="replace")
    except (requests.RequestException, OSError, UnicodeError):
        return None
    candidates = []
    for tag in re.findall(r"<(?:meta|link)\b[^>]*>", source, re.I):
        if not re.search(r"(?:name|property|itemprop|rel)\s*=\s*['\"](?:license|dc\.rights|dcterms\.rights)['\"]", tag, re.I):
            continue
        candidates.extend(re.findall(r"(?:content|href)\s*=\s*['\"]([^'\"]+)['\"]", tag, re.I))
    candidates.extend(re.findall(r"['\"]license['\"]\s*:\s*['\"](https?://[^'\"]+)", source, re.I))
    for candidate in candidates:
        value = html.unescape(candidate).strip()
        normalized = value.casefold()
        if "creativecommons.org/publicdomain/zero" in normalized:
            label = "CC0"
        elif "creativecommons.org/licenses/by-sa/" in normalized:
            label = "CC BY-SA"
        elif "creativecommons.org/licenses/by/" in normalized:
            label = "CC BY"
        elif "creativecommons.org/publicdomain/mark" in normalized:
            label = "Public domain"
        else:
            label = _plain(value, 120)
        if _license_allowed(label):
            return label, value
    return None


def search_google_cse_images(
    query: str, output_dir: str | Path, *, limit: int = 1,
    timeout=(5, 15),
) -> list[dict[str, str]]:
    """Busca no Google Images pela API oficial, quando chaves de clientes existentes estiverem configuradas."""
    api_key = os.environ.get("GACIA_GOOGLE_CSE_API_KEY", "").strip()
    engine_id = os.environ.get("GACIA_GOOGLE_CSE_ID", "").strip()
    term = " ".join(str(query or "").split())[:180]
    if not api_key or not engine_id or len(term) < 3:
        return []
    try:
        response = requests.get(
            "https://customsearch.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": engine_id, "q": term, "searchType": "image",
                    "rights": "cc_publicdomain|cc_attribute|cc_sharealike", "safe": "active", "num": min(10, max(3, limit * 5))},
            timeout=timeout,
        )
        response.raise_for_status()
        items = response.json().get("items") or []
    except (requests.RequestException, ValueError, TypeError) as exc:
        LOGGER.info("Google Custom Search não disponível para imagens: %s", exc)
        return []
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        context_url = str((item.get("image") or {}).get("contextLink") or "")
        image_url = str(item.get("link") or "")
        verified = _verified_page_license(context_url)
        if not verified:
            continue
        filename = f"google_{index + 1}_{re.sub(r'[^A-Za-z0-9_-]+', '_', str(item.get('title') or 'imagem'))[:36]}"
        local_path = _download_remote_image(image_url, destination, filename, timeout=timeout)
        if not local_path:
            continue
        license_name, license_url = verified
        meta_tags = ((item.get("pagemap") or {}).get("metatags") or [])
        author = next((tag.get("author") for tag in meta_tags if isinstance(tag, dict) and tag.get("author")), None)
        results.append({
            "title": _plain(item.get("title") or "Imagem encontrada no Google Images", 220),
            "path": local_path, "artist": _plain(author or "Autor não informado", 240),
            "license": license_name, "license_url": license_url, "description_url": context_url,
            "provider": "Google Images",
        })
        if len(results) >= max(1, min(int(limit), 5)):
            break
    return results


def search_online_images(
    query: str, output_dir: str | Path, *, limit: int = 1,
    required_terms: tuple[str, ...] | list[str] = (),
) -> list[dict[str, str]]:
    """Prioriza Google Images via API oficial configurada; usa Commons licenciado como fallback."""
    google_results = search_google_cse_images(query, output_dir, limit=limit)
    if google_results:
        return google_results[:max(1, min(int(limit), 5))]
    return search_commons_images(
        query, output_dir, limit=limit, required_terms=required_terms,
    )


def search_commons_images(
    query: str,
    output_dir: str | Path,
    *,
    limit: int = 1,
    timeout: tuple[float, float] = (6, 25),
    session: requests.Session | None = None,
    required_terms: tuple[str, ...] | list[str] = (),
    min_term_matches: int = 1,
) -> list[dict[str, str]]:
    """Busca imagens no Commons e baixa apenas resultados com licença permitida.

    A função não faz buscas genéricas em motores externos. Limita resultados,
    tamanho dos arquivos e hosts de download, e retorna metadados para crédito.
    """
    term = " ".join(str(query or "").split())[:180]
    if len(term) < 3:
        return []
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    headers = {"User-Agent": "GacIA/1.0 (desktop assistant; image attribution enabled)"}
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {term}", "gsrnamespace": 6,
        "gsrlimit": max(3, min(int(limit) * 5, 15)),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": 1600,
        "iiextmetadatafilter": "LicenseShortName|UsageTerms|Artist|Credit|LicenseUrl|ImageDescription",
    }
    try:
        response = client.get(COMMONS_API, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"Pesquisa de imagens no Wikimedia Commons falhou: {exc}") from exc

    pages = (payload.get("query") or {}).get("pages") or {}
    # A licença é um requisito jurídico; a busca do Commons já ranqueia pelo
    # assunto. Âncoras literais ajudam a ordenar resultados sem eliminar fotos
    # pertinentes cujo nome de arquivo omite a marca consultada.
    def tokens(value: object) -> set[str]:
        normalized = unicodedata.normalize("NFKD", _plain(value, 1200)).encode("ascii", "ignore").decode("ascii").casefold()
        return set(re.findall(r"[a-z0-9]{3,}", normalized))

    anchors = set().union(*(tokens(term) for term in required_terms if str(term or "").strip()))
    min_matches = max(1, min(len(anchors), int(min_term_matches))) if anchors else 0
    candidates = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info_list = page.get("imageinfo") or []
        if not info_list or not isinstance(info_list[0], dict):
            continue
        info = info_list[0]
        ext = info.get("extmetadata") or {}
        license_name = _plain((ext.get("LicenseShortName") or {}).get("value", ""), 120)
        if not _license_allowed(license_name):
            continue
        title = _plain(page.get("title", "Imagem"), 220)
        description = _plain((ext.get("ImageDescription") or {}).get("value", ""), 500)
        matched_anchors = anchors.intersection(tokens(f"{title} {description}"))
        mime = str(info.get("mime") or "").lower()
        if mime not in ALLOWED_MIME:
            continue
        image_url = str(info.get("thumburl") or info.get("url") or "")
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            continue
        description_url = str(info.get("descriptionurl") or "")
        if urlparse(description_url).hostname != "commons.wikimedia.org":
            continue
        candidates.append({
            "_relevance": len(matched_anchors),
            "title": title,
            "url": image_url,
            "description_url": description_url,
            "mime": mime,
            "license": license_name,
            "license_url": _plain((ext.get("LicenseUrl") or {}).get("value", ""), 300),
            "artist": _plain((ext.get("Artist") or {}).get("value", ""), 300) or _plain((ext.get("Credit") or {}).get("value", ""), 300) or "Autor não informado",
            "description": description[:240],
        })

    if anchors and any(item.get("_relevance", 0) >= min_matches for item in candidates):
        candidates = [item for item in candidates if item.get("_relevance", 0) >= min_matches]
    elif anchors and candidates:
        LOGGER.info("Nenhum arquivo do Commons repetiu a âncora literal; usando resultados ranqueados pela consulta: %s", term)
    candidates.sort(key=lambda item: item.get("_relevance", 0), reverse=True)

    downloaded: list[dict[str, str]] = []
    for index, item in enumerate(candidates):
        if len(downloaded) >= max(1, min(int(limit), 5)):
            break
        image_response = None
        try:
            image_response = client.get(item["url"], headers=headers, timeout=timeout, stream=True)
            image_response.raise_for_status()
            content_type = image_response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in ALLOWED_MIME:
                continue
            chunks = []
            total = 0
            for chunk in image_response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
            if total > MAX_IMAGE_BYTES or len(data) < 256:
                continue
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                suffix = ".png"
            elif data.startswith(b"\xff\xd8\xff"):
                suffix = ".jpg"
            elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                suffix = ".webp"
            else:
                continue
            base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(item["title"]).stem).strip("_")[:36] or "imagem"
            target = destination / f"commons_{index + 1}_{base}{suffix}"
            target.write_bytes(data)
            item["path"] = str(target.resolve())
            item.pop("_relevance", None)
            downloaded.append(item)
        except (requests.RequestException, OSError) as exc:
            LOGGER.debug("Não foi possível baixar uma imagem do Commons: %s", exc)
        finally:
            if image_response is not None:
                try:
                    image_response.close()
                except AttributeError:
                    pass
    return downloaded
