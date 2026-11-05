"""Criação e leitura básica de EPUB 3 usando somente a biblioteca padrão.

O módulo escreve um EPUB válido (mimetype sem compressão e primeiro no ZIP,
container.xml, OPF, navegação e capítulos XHTML). Não baixa livros nem remove DRM.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import mimetypes
import re
import uuid
from pathlib import Path, PurePosixPath
import tempfile
import os
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from .workspace import WorkspaceManager, WorkspaceError

MAX_CHAPTERS = 200
MAX_CHAPTER_CHARS = 500_000
MAX_EPUB_UNCOMPRESSED = 100 * 1024 * 1024


def _slug(text: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_text.strip()).strip("-").lower()
    return (value or fallback)[:64]


def _markdown_to_xhtml(text: str) -> str:
    """Converte um subconjunto seguro de Markdown para XHTML sem HTML arbitrário."""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_open = False

    def inline(value: str) -> str:
        safe = escape(value, quote=False)
        safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", safe)
        return safe

    def flush_paragraph() -> None:
        if paragraph:
            out.append("<p>" + " ".join(inline(part.strip()) for part in paragraph) + "</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        bullet = re.match(r"^(?:[-*+] |\d+\. )(.+)$", stripped)
        if heading:
            flush_paragraph(); close_list()
            level = len(heading.group(1)) + 1
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
        elif bullet:
            flush_paragraph()
            if not list_open:
                out.append("<ul>"); list_open = True
            out.append("<li>" + inline(bullet.group(1)) + "</li>")
        else:
            close_list()
            paragraph.append(stripped)
    flush_paragraph(); close_list()
    return "\n".join(out) if out else "<p></p>"


class _TextoHTML(HTMLParser):
    _BLOCKS = {"p", "div", "br", "h1", "h2", "h3", "li", "tr", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip += 1
        elif not self.skip and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def create_ebook(
    manager: WorkspaceManager,
    relative_path: str,
    title: str,
    chapters: list[dict[str, Any]],
    author: str = "",
    language: str = "pt-BR",
    description: str = "",
    publisher: str = "Gac.IA",
    cover_path: str = "",
) -> str:
    """Cria um EPUB 3 sem dependências externas; chapters: [{title, content}]."""
    destino = manager.resolve(relative_path)
    if destino.suffix.lower() != ".epub":
        raise WorkspaceError("E-books devem usar a extensão .epub.")
    if destino.exists():
        raise WorkspaceError("O arquivo já existe; escolha outro nome para evitar sobrescrita.")
    if not str(title or "").strip():
        raise WorkspaceError("Informe o título do e-book.")
    if not isinstance(chapters, list) or not chapters or len(chapters) > MAX_CHAPTERS:
        raise WorkspaceError(f"Informe de 1 a {MAX_CHAPTERS} capítulos.")

    identificador = "urn:uuid:" + str(uuid.uuid4())
    itens_manifesto = []
    itens_spine = []
    itens_nav = []
    conteudos: dict[str, bytes] = {}
    cover_manifest = ""
    cover_spine = ""
    if cover_path:
        cover_file = manager.resolve(cover_path, must_exist=True)
        if not cover_file.is_file() or cover_file.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise WorkspaceError("A capa precisa ser uma imagem PNG ou JPEG dentro do workspace.")
        if cover_file.stat().st_size > 15 * 1024 * 1024:
            raise WorkspaceError("A imagem de capa ultrapassa o limite de 15 MiB.")
        cover_data = cover_file.read_bytes()
        assinatura_ok = (cover_file.suffix.lower() == ".png" and cover_data.startswith(b"\x89PNG\r\n\x1a\n")) or (
            cover_file.suffix.lower() in {".jpg", ".jpeg"} and cover_data.startswith(b"\xff\xd8\xff")
        )
        if not assinatura_ok:
            raise WorkspaceError("O conteúdo da imagem não corresponde à extensão PNG/JPEG informada.")
        suffix = ".jpg" if cover_file.suffix.lower() in {".jpg", ".jpeg"} else ".png"
        media = "image/jpeg" if suffix == ".jpg" else "image/png"
        conteudos[f"EPUB/cover{suffix}"] = cover_data
        conteudos["EPUB/cover.xhtml"] = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'lang="' + escape(language, quote=True) + '"><head><meta charset="utf-8"/><title>Capa</title>'
            '<link rel="stylesheet" href="styles.css"/></head><body epub:type="cover">'
            f'<img src="cover{suffix}" alt="Capa de {escape(str(title), quote=True)}" style="display:block;max-width:100%;height:auto;margin:0 auto;"/>'
            '</body></html>'
        ).encode("utf-8")
        cover_manifest = f'<item id="cover-image" href="cover{suffix}" media-type="{media}" properties="cover-image"/><item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        cover_spine = '<itemref idref="cover-page"/>'
    for index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict):
            raise WorkspaceError(f"O capítulo {index} deve ser um objeto com title e content.")
        cap_title = str(chapter.get("title") or f"Capítulo {index}").strip()[:250]
        content = str(chapter.get("content") or "")
        if len(content) > MAX_CHAPTER_CHARS:
            raise WorkspaceError(f"O capítulo {index} excede o limite de {MAX_CHAPTER_CHARS} caracteres.")
        filename = f"chapter-{index:03d}-{_slug(cap_title, f'capitulo-{index}')}.xhtml"
        body = _markdown_to_xhtml(content)
        xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="'
            + escape(language, quote=True) + '" xml:lang="' + escape(language, quote=True) + '">\n'
            '<head><meta charset="utf-8"/><title>' + escape(cap_title) + '</title>'
            '<link rel="stylesheet" type="text/css" href="styles.css"/></head>\n'
            '<body><section epub:type="chapter"><h1>' + escape(cap_title) + '</h1>' + body + '</section></body></html>'
        )
        conteudos[f"EPUB/{filename}"] = xhtml.encode("utf-8")
        itens_manifesto.append(f'<item id="chapter{index}" href="{filename}" media-type="application/xhtml+xml"/>')
        itens_spine.append(f'<itemref idref="chapter{index}"/>')
        itens_nav.append(f'<li><a href="{filename}">{escape(cap_title)}</a></li>')

    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="'
        + escape(language, quote=True) + '"><head><meta charset="utf-8"/><title>Sumário</title>'
        '<link rel="stylesheet" href="styles.css"/></head><body><nav epub:type="toc" id="toc">'
        '<h1>Sumário</h1><ol>' + "".join(itens_nav) + '</ol></nav></body></html>'
    )
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="'
        + escape(language, quote=True) + '"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="book-id">' + identificador + '</dc:identifier>'
        '<dc:title>' + escape(str(title)[:250]) + '</dc:title>'
        '<dc:language>' + escape(language[:35]) + '</dc:language>'
        '<dc:creator>' + escape(str(author or "Gac.IA")[:250]) + '</dc:creator>'
        '<dc:publisher>' + escape(str(publisher or "Gac.IA")[:250]) + '</dc:publisher>'
        + ('<dc:description>' + escape(str(description)[:2000]) + '</dc:description>' if description else '')
        + '</metadata><manifest><item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
        + '<item id="css" href="styles.css" media-type="text/css"/>' + cover_manifest
        + ''.join(itens_manifesto) + '</manifest><spine>' + cover_spine + ''.join(itens_spine) + '</spine></package>'
    )
    css = "body{font-family:serif;line-height:1.55;margin:5%;}h1,h2,h3{line-height:1.2;}p{margin:0 0 1em;}li{margin:.35em 0;}code{font-family:monospace;}"
    conteudos.update({
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>'
        ).encode("utf-8"),
        "EPUB/package.opf": opf.encode("utf-8"),
        "EPUB/nav.xhtml": nav.encode("utf-8"),
        "EPUB/styles.css": css.encode("utf-8"),
    })

    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=f".{destino.stem}_", suffix=".epub", dir=destino.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporario, "w") as epub:
            epub.writestr("mimetype", conteudos.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for nome, dados in conteudos.items():
                epub.writestr(nome, dados, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temporario, "r") as epub:
            if epub.testzip() is not None or epub.namelist()[0] != "mimetype":
                raise WorkspaceError("A validação estrutural do EPUB falhou.")
            ET.fromstring(epub.read("META-INF/container.xml"))
            ET.fromstring(epub.read("EPUB/package.opf"))
        if destino.exists():
            raise WorkspaceError("O arquivo de destino apareceu durante a criação; nada foi sobrescrito.")
        os.replace(temporario, destino)
    except Exception:
        Path(temporario).unlink(missing_ok=True)
        raise
    detalhe_capa = ", capa incluída" if cover_path else ""
    return f"E-book EPUB 3 criado: {relative_path} ({len(chapters)} capítulo(s), sumário e estilos{detalhe_capa})."


def read_ebook(manager: WorkspaceManager, relative_path: str) -> str:
    """Extrai metadados e texto dos capítulos do EPUB (sem executar conteúdo)."""
    path = manager.resolve(relative_path, must_exist=True)
    if path.suffix.lower() != ".epub":
        raise WorkspaceError("A leitura de e-books aceita arquivos .epub.")
    try:
        with zipfile.ZipFile(path, "r") as epub:
            infos = epub.infolist()
            total = sum(info.file_size for info in infos)
            if total > MAX_EPUB_UNCOMPRESSED:
                raise WorkspaceError("O EPUB ultrapassa o limite de extração de 100 MiB.")
            if epub.testzip() is not None:
                raise WorkspaceError("O EPUB contém um arquivo interno corrompido.")
            root = ET.fromstring(epub.read("META-INF/container.xml"))
            rootfile = next((item.attrib.get("full-path") for item in root.iter() if item.tag.endswith("rootfile")), None)
            if not rootfile:
                raise WorkspaceError("EPUB inválido: pacote OPF não encontrado.")
            opf_path = PurePosixPath(rootfile)
            opf_root = ET.fromstring(epub.read(str(opf_path)))
            ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
            base = opf_path.parent
            manifest = {}
            for item in opf_root.findall("opf:manifest/opf:item", ns):
                if item.get("id") and item.get("href"):
                    href = item.get("href")
                    href_path = PurePosixPath(href)
                    target_path = base / href_path
                    if (href_path.is_absolute() or "\\" in href
                            or any(part in {"..", ""} for part in href_path.parts)
                            or any(part == ".." for part in target_path.parts)):
                        raise WorkspaceError("EPUB inválido: caminho interno inseguro.")
                    target = target_path.as_posix()
                    manifest[item.get("id")] = target
            title_el = opf_root.find(".//dc:title", ns)
            author_el = opf_root.find(".//dc:creator", ns)
            title = title_el.text.strip() if title_el is not None and title_el.text else path.stem
            author = author_el.text.strip() if author_el is not None and author_el.text else "Autor não informado"
            parts = [f"Título: {title}", f"Autor: {author}"]
            spine = opf_root.find("opf:spine", ns)
            if spine is not None:
                for ref in spine.findall("opf:itemref", ns):
                    href = manifest.get(ref.get("idref"))
                    if not href:
                        continue
                    parser = _TextoHTML()
                    parser.feed(epub.read(href).decode("utf-8", errors="replace"))
                    text = " ".join(" ".join(parser.parts).split())
                    if text:
                        parts.append(text)
                    if sum(map(len, parts)) > 45000:
                        parts.append("[Conteúdo truncado para caber no contexto do modelo.]")
                        break
            return "\n\n".join(parts)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as erro:
        if isinstance(erro, WorkspaceError):
            raise
        raise WorkspaceError(f"Não foi possível ler este EPUB: {type(erro).__name__}: {erro}") from erro
