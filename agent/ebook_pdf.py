"""Geração de e-books em PDF com acabamento editorial e navegação.

O PDF é o formato padrão para distribuição/venda em plataformas de conteúdo.
EPUB refluível continua disponível no módulo agent.ebooks para solicitações
explícitas desse formato.
"""
from __future__ import annotations

from html import escape
import io
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any
from urllib.parse import urlsplit

from .workspace import WorkspaceManager, WorkspaceError

MAX_CHAPTERS = 120
MAX_CHAPTER_CHARS = 300_000
MAX_BOOK_CHARS = 2_000_000
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024


def _slug(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", "-", raw.encode("ascii", "ignore").decode().lower()).strip("-")[:64] or "capitulo"


def _inline_markup(value: str) -> str:
    """Converte marcação inline mínima em markup seguro do ReportLab."""
    raw = str(value)
    # Um marcador de imagem não processado nunca deve vazar como Markdown para
    # o leitor. O criador do e-book trata a busca/arquivo antes da renderização.
    raw = re.sub(r"(?:!\[([^\]]*)\]\(([^)]+)\)|\[\]\(([^)]+)\))", lambda m: m.group(1) or "", raw)
    text = escape(raw, quote=False)
    # Links externos: somente HTTP(S), nunca javascript:, file: ou esquemas locais.
    def link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return label
        safe_url = escape(url, quote=True)
        return f'<link href="{safe_url}" color="#2563EB"><u>{label}</u></link>'

    def markdown_link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        return link(match) if urlsplit(url).scheme.lower() in {"http", "https"} else label

    text = re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)", markdown_link, text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)", lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    return text


def _image_bytes(path: Path) -> tuple[bytes, str]:
    if not path.is_file():
        raise WorkspaceError(f"Imagem do e-book não encontrada: {path.name}")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise WorkspaceError(f"Imagem '{path.name}' excede 20 MiB.")
    try:
        from PIL import Image
        with Image.open(path) as source:
            source.load()
            image = source.convert("RGB")
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=90, optimize=True)
            return stream.getvalue(), "JPEG"
    except Exception as erro:
        raise WorkspaceError(f"Não foi possível processar a imagem '{path.name}': {type(erro).__name__}.") from erro


def create_ebook_pdf(
    manager: WorkspaceManager,
    relative_path: str,
    title: str,
    chapters: list[dict[str, Any]],
    author: str = "",
    language: str = "pt-BR",
    description: str = "",
    cover_path: str = "",
    subtitle: str = "",
    keywords: str | list[str] = "",
    page_size: str = "A4",
    accent_color: str = "#2563EB",
    include_toc: bool = True,
    target_pages: int | None = None,
) -> str:
    """Cria PDF de e-book: capa, expediente, sumário clicável e capítulos.

    Cada capítulo aceita {title, content, image_path?, image_caption?}.
    O conteúdo aceita Markdown básico; links HTTP(S) são preservados.
    """
    path = manager.resolve(relative_path)
    if path.suffix.lower() != ".pdf":
        raise WorkspaceError("E-books para distribuição devem usar a extensão .pdf.")
    if path.exists():
        raise WorkspaceError("O arquivo já existe. Escolha outro nome para evitar sobrescrita.")
    book_title = str(title or "").strip()[:250]
    if not book_title:
        raise WorkspaceError("Informe o título do e-book.")
    if not isinstance(chapters, list) or not chapters or len(chapters) > MAX_CHAPTERS:
        raise WorkspaceError(f"Informe de 1 a {MAX_CHAPTERS} capítulos.")
    total_chars = 0
    for index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict):
            raise WorkspaceError(f"O capítulo {index} precisa conter título e conteúdo.")
        content = str(chapter.get("content") or "")
        total_chars += len(content)
        if len(content) > MAX_CHAPTER_CHARS:
            raise WorkspaceError(f"O capítulo {index} excede {MAX_CHAPTER_CHARS:,} caracteres.")
    if total_chars > MAX_BOOK_CHARS:
        raise WorkspaceError(f"O e-book excede o limite de {MAX_BOOK_CHARS:,} caracteres.")

    page_key = str(page_size or "A4").upper()
    if page_key not in {"A4", "A5", "LETTER"}:
        raise WorkspaceError("page_size deve ser A4, A5 ou LETTER.")
    color_value = str(accent_color or "#2563EB")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color_value):
        raise WorkspaceError("accent_color deve ser uma cor hexadecimal, por exemplo #2563EB.")

    page_count = None
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.lib.pagesizes import A4, A5, letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            BaseDocTemplate, PageTemplate, Frame, Flowable, Paragraph, Spacer,
            PageBreak, NextPageTemplate, Image as RLImage, ListFlowable,
            ListItem, Preformatted, Table, TableStyle, KeepTogether,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
    except ImportError as erro:
        raise WorkspaceError("Dependência reportlab ausente. Execute preparar.bat e habilite Documentos e produtividade.") from erro

    sizes = {"A4": A4, "A5": A5, "LETTER": letter}
    width, height = sizes[page_key]
    margin_x = 18 * mm if page_key != "A5" else 15 * mm
    margin_top = 19 * mm if page_key != "A5" else 16 * mm
    margin_bottom = 18 * mm if page_key != "A5" else 15 * mm
    content_width = width - 2 * margin_x
    accent = colors.HexColor(color_value)
    is_nvidia_palette = color_value.casefold() == "#76b900"
    dark = colors.HexColor("#0B0B0B" if is_nvidia_palette else "#17243A")
    muted = colors.HexColor("#AAB2A5" if is_nvidia_palette else "#64748B")
    cover_panel = colors.HexColor("#171A17" if is_nvidia_palette else "#2C3D58")
    path.parent.mkdir(parents=True, exist_ok=True)

    cover_data: bytes | None = None
    if cover_path:
        cover_file = manager.resolve(cover_path, must_exist=True)
        cover_data, _ = _image_bytes(cover_file)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="BookTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=29 if page_key != "A5" else 24, leading=34 if page_key != "A5" else 29,
        alignment=TA_LEFT, textColor=dark, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="BookSubtitle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=14, leading=20, textColor=muted, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="BookChapter", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=22 if page_key != "A5" else 19, leading=27 if page_key != "A5" else 23,
        textColor=dark, spaceBefore=4, spaceAfter=17, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BookH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=15, leading=19, textColor=accent, spaceBefore=15, spaceAfter=8, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BookH3", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=12, leading=16, textColor=dark, spaceBefore=11, spaceAfter=6, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BookBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=10.5 if page_key != "A5" else 9.5,
        leading=16 if page_key != "A5" else 14.2, alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#263445"), spaceAfter=9, allowWidows=0, allowOrphans=0,
    ))
    styles.add(ParagraphStyle(
        name="BookLead", parent=styles["BookBody"], fontSize=12, leading=18,
        textColor=dark, spaceAfter=13,
    ))
    styles.add(ParagraphStyle(
        name="BookQuote", parent=styles["BookBody"], leftIndent=12, rightIndent=8,
        borderColor=accent, borderWidth=0, borderLeft=3, borderPadding=8,
        backColor=colors.HexColor("#F1F5F9"), alignment=TA_LEFT,
        spaceBefore=5, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="BookCaption", parent=styles["Normal"], fontName="Helvetica-Oblique",
        fontSize=8.5, leading=11, textColor=muted, alignment=TA_CENTER,
        spaceBefore=3, spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="BookSmall", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=12, textColor=muted, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="BookFrontHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=dark, spaceBefore=3, spaceAfter=10, keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BookTOC0", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=16, leftIndent=0, firstLineIndent=0,
        textColor=dark, spaceBefore=5,
    ))
    styles.add(ParagraphStyle(
        name="BookTOC1", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=13, leftIndent=14, firstLineIndent=0, textColor=muted,
    ))

    class CoverPage(Flowable):
        def __init__(self):
            super().__init__()
            self.width = width
            self.height = height

        def draw(self):
            canvas = self.canv
            canvas.saveState()
            canvas.setFillColor(dark)
            canvas.rect(0, 0, width, height, fill=1, stroke=0)
            canvas.setFillColor(accent)
            canvas.rect(0, 0, width, 9 * mm, fill=1, stroke=0)
            canvas.setFillColor(cover_panel)
            canvas.circle(width - 12 * mm, height - 15 * mm, 48 * mm, fill=1, stroke=0)
            left = 22 * mm
            text_y = height - 62 * mm
            if cover_data:
                try:
                    from reportlab.lib.utils import ImageReader
                    from PIL import Image
                    with Image.open(io.BytesIO(cover_data)) as image:
                        iw, ih = image.size
                    max_w, max_h = width - 44 * mm, height * 0.40
                    scale = min(max_w / iw, max_h / ih)
                    iw2, ih2 = iw * scale, ih * scale
                    canvas.drawImage(ImageReader(io.BytesIO(cover_data)), (width-iw2)/2,
                                     height - 27 * mm - ih2, width=iw2, height=ih2,
                                     preserveAspectRatio=True, mask="auto", anchor="c")
                    text_y = height - 40 * mm - ih2
                except Exception:
                    text_y = height - 70 * mm
            canvas.setFillColor(colors.HexColor("#76B900" if is_nvidia_palette else "#93C5FD"))
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(left, text_y, "E-BOOK  |  GAC.IA")
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 27 if page_key != "A5" else 22)
            max_chars = 34 if page_key != "A5" else 28
            title_lines = _wrap_words(book_title, max_chars, 3)
            y = text_y - 17 * mm
            for line in title_lines:
                canvas.setFont("Helvetica-Bold", 27 if page_key != "A5" else 22)
                canvas.drawString(left, y, line[:70])
                y -= 12 * mm
            if subtitle:
                canvas.setFillColor(colors.HexColor("#CBD5E1"))
                canvas.setFont("Helvetica", 13)
                for line in _wrap_words(str(subtitle), 55 if page_key != "A5" else 42, 3):
                    canvas.drawString(left, y - 2 * mm, line[:85])
                    y -= 8 * mm
            canvas.setFillColor(colors.HexColor("#CBD5E1"))
            canvas.setFont("Helvetica", 11)
            canvas.drawString(left, 24 * mm, (str(author).strip() or "Gac.IA")[:90])
            canvas.restoreState()

    class EbookDocTemplate(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if not isinstance(flowable, Paragraph):
                return
            style_name = flowable.style.name
            if style_name not in {"BookChapter", "BookH2"}:
                return
            text_value = flowable.getPlainText().strip()
            if not text_value:
                return
            key = f"{_slug(text_value)}-{id(flowable):x}"
            self.canv.bookmarkPage(key)
            level = 0 if style_name == "BookChapter" else 1
            try:
                self.canv.addOutlineEntry(text_value[:120], key, level=level, closed=False)
            except Exception:
                pass
            self.notify("TOCEntry", (level, text_value, self.page, key))

    def draw_body(canvas, document):
        canvas.saveState()
        canvas.setTitle(book_title)
        canvas.setAuthor(str(author or "Gac.IA")[:200])
        canvas.setSubject(str(description or "E-book digital")[:1000])
        canvas.setCreator("Gac.IA")
        canvas.setKeywords(", ".join(keywords) if isinstance(keywords, list) else str(keywords or ""))
        if document.page > 1:
            canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
            canvas.setLineWidth(0.5)
            canvas.setStrokeColor(accent if is_nvidia_palette else colors.HexColor("#E2E8F0"))
            canvas.line(margin_x, height - 11 * mm, width - margin_x, height - 11 * mm)
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(muted)
            canvas.drawString(margin_x, height - 8 * mm, book_title[:70])
            canvas.drawRightString(width - margin_x, height - 8 * mm, "E-BOOK")
            canvas.line(margin_x, 11 * mm, width - margin_x, 11 * mm)
            canvas.drawString(margin_x, 7 * mm, (str(author).strip() or "Gac.IA")[:70])
            canvas.drawRightString(width - margin_x, 7 * mm, f"{document.page - 1}")
        canvas.restoreState()

    doc = EbookDocTemplate(
        str(path), pagesize=sizes[page_key], title=book_title,
        author=str(author or "Gac.IA")[:200], subject=str(description or "E-book digital")[:1000],
        keywords=", ".join(keywords) if isinstance(keywords, list) else str(keywords or "")[:1000],
        pageCompression=1,
    )
    cover_frame = Frame(0, 0, width, height, id="cover", leftPadding=0, bottomPadding=0,
                        rightPadding=0, topPadding=0, showBoundary=0)
    body_frame = Frame(margin_x, margin_bottom, content_width, height-margin_top-margin_bottom,
                       id="body", leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0,
                       showBoundary=0)
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame]),
        PageTemplate(id="Body", frames=[body_frame], onPage=draw_body),
    ])

    story: list[Any] = [CoverPage(), NextPageTemplate("Body"), PageBreak()]
    story.extend([
        Paragraph("Sobre este e-book", styles["BookFrontHeading"]),
        Paragraph(_inline_markup(str(description or "Material digital criado com a Gac.IA.")), styles["BookBody"]),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>Título:</b> {_inline_markup(book_title)}", styles["BookSmall"]),
        Paragraph(f"<b>Autor:</b> {_inline_markup(str(author or 'Gac.IA'))}", styles["BookSmall"]),
        Paragraph(f"<b>Idioma:</b> {_inline_markup(str(language or 'pt-BR'))}", styles["BookSmall"]),
        Paragraph("Material digital. Os direitos e as condições de uso seguem as informações fornecidas pelo autor.", styles["BookSmall"]),
        PageBreak(),
    ])

    if include_toc:
        toc = TableOfContents()
        toc.levelStyles = [styles["BookTOC0"], styles["BookTOC1"]]
        toc.dotsMinLevel = 0
        story.extend([Paragraph("Sumário", styles["BookTitle"]), toc, PageBreak()])

    for index, chapter in enumerate(chapters, 1):
        chapter_title = str(chapter.get("title") or f"Capítulo {index}").strip()[:200]
        story.append(Paragraph(_inline_markup(chapter_title), styles["BookChapter"]))
        content = str(chapter.get("content") or "")
        story.extend(_markdown_story(content, styles, colors, mm, Paragraph, Spacer, Preformatted,
                                     ListFlowable, ListItem, Table, TableStyle, KeepTogether, accent))
        image_path = str(chapter.get("image_path") or "").strip()
        if image_path:
            image_file = manager.resolve(image_path, must_exist=True)
            image_data, _ = _image_bytes(image_file)
            from reportlab.lib.utils import ImageReader
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(image_data)) as picture:
                iw, ih = picture.size
            max_h = height * 0.32
            scale = min(content_width / iw, max_h / ih)
            story.append(Spacer(1, 4 * mm))
            story.append(RLImage(io.BytesIO(image_data), width=iw*scale, height=ih*scale))
            caption = str(chapter.get("image_caption") or "").strip()
            if caption:
                story.append(Paragraph(_inline_markup(caption), styles["BookCaption"]))
        if index < len(chapters):
            story.append(PageBreak())

    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".pdf", dir=path.parent)
    os.close(fd)
    try:
        doc.filename = temporary
        doc.multiBuild(story, maxPasses=5)
        if not os.path.isfile(temporary) or os.path.getsize(temporary) < 500:
            raise WorkspaceError("O PDF do e-book foi gerado vazio ou incompleto.")
        if os.path.getsize(temporary) > MAX_PDF_BYTES:
            raise WorkspaceError("O PDF ultrapassa 100 MiB, limite recomendado para anexos da Kiwify.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(temporary, strict=True)
            page_count = len(reader.pages)
            if len(reader.pages) < 3:
                raise WorkspaceError("O e-book gerado tem páginas insuficientes; verifique o conteúdo dos capítulos.")
            if not reader.metadata or not reader.metadata.title:
                raise WorkspaceError("Os metadados do e-book não foram gravados corretamente.")
            if include_toc and not reader.outline:
                raise WorkspaceError("A navegação do sumário não foi registrada no PDF.")
        except ImportError:
            pass
        if path.exists():
            raise WorkspaceError("O arquivo de destino apareceu durante a criação; nada foi sobrescrito.")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

    return (
        f"E-book PDF profissional criado: {relative_path} "
        f"({page_count if page_count is not None else 'páginas não verificadas'} páginas; "
        f"meta: {max(3, min(int(target_pages), 100)) if target_pages else 'não especificada'}; "
        f"{len(chapters)} capítulo(s), capa editorial, expediente, "
        f"{'sumário clicável' if include_toc else 'sem sumário'}, paginação e metadados; formato {page_key})."
    )


def _wrap_words(value: str, max_chars: int, max_lines: int) -> list[str]:
    words = str(value or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and words and " ".join(lines) != " ".join(words):
        last = lines[-1]
        lines[-1] = (last[:max(1, max_chars - 3)].rstrip() + "...")
    return lines or [""]


def _markdown_story(content, styles, colors, mm, Paragraph, Spacer, Preformatted,
                    ListFlowable, ListItem, Table, TableStyle, KeepTogether, accent):
    lines = str(content or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    story: list[Any] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    numbers: list[str] = []
    quote_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph():
        if paragraph:
            story.append(Paragraph(_inline_markup(" ".join(x.strip() for x in paragraph)), styles["BookBody"]))
            paragraph.clear()

    def flush_lists():
        if bullets:
            items = [ListItem(Paragraph(_inline_markup(item), styles["BookBody"]), leftIndent=12) for item in bullets]
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=18,
                                      bulletFontName="Helvetica", bulletFontSize=7, spaceAfter=10))
            bullets.clear()
        if numbers:
            items = [ListItem(Paragraph(_inline_markup(item), styles["BookBody"]), leftIndent=12) for item in numbers]
            story.append(ListFlowable(items, bulletType="1", leftIndent=20, spaceAfter=10))
            numbers.clear()

    def flush_quote():
        if quote_lines:
            story.append(Paragraph(_inline_markup(" ".join(quote_lines)), styles["BookQuote"]))
            quote_lines.clear()

    def flush_code():
        if code_lines:
            safe_lines = "\n".join(code_lines)
            story.append(Preformatted(safe_lines, styles["Code"]))
            code_lines.clear()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph(); flush_lists(); flush_quote()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph(); flush_lists(); flush_quote()
            continue
        if stripped.startswith("> ") or stripped == ">":
            flush_paragraph(); flush_lists()
            quote_lines.append(stripped[2:] if stripped.startswith("> ") else "")
            continue
        if stripped.startswith("---") and len(stripped) >= 3:
            flush_paragraph(); flush_lists(); flush_quote()
            story.extend([Spacer(1, 2*mm), Table([[""]], colWidths=[65*mm], rowHeights=[1.2], style=TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), accent), ("LINEBELOW", (0,0), (-1,-1), 0.5, accent)
            ])), Spacer(1, 3*mm)])
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph(); flush_lists(); flush_quote()
            level = len(heading.group(1))
            style = styles["BookH2"] if level <= 2 else styles["BookH3"]
            story.append(Paragraph(_inline_markup(heading.group(2)), style))
            continue
        bullet = re.match(r"^(?:[-*+] )(.+)$", stripped)
        number = re.match(r"^\d+[.)] (.+)$", stripped)
        if bullet:
            flush_paragraph(); flush_quote(); numbers.clear()
            bullets.append(bullet.group(1))
            continue
        if number:
            flush_paragraph(); flush_quote(); bullets.clear()
            numbers.append(number.group(1))
            continue
        flush_lists(); flush_quote()
        paragraph.append(stripped)
    flush_paragraph(); flush_lists(); flush_quote()
    if in_code:
        flush_code()
    return story
