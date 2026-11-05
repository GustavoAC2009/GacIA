"""Leitura e edição de documentos de escritório dentro do workspace."""
from __future__ import annotations

import csv
import json
import os
import io
import tempfile
import shutil
import textwrap
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .workspace import WorkspaceManager, WorkspaceError


MAX_DOCUMENT_TEXT = 45000


def _truncate(text: str) -> str:
    texto = str(text)
    if len(texto) > MAX_DOCUMENT_TEXT:
        return texto[:MAX_DOCUMENT_TEXT] + "\n\n[Conteúdo truncado para caber no contexto do modelo.]"
    return texto


def _save_package_atomic(package, path: Path) -> None:
    """Salva DOCX/XLSX/PPTX em temporário e só então substitui o arquivo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    try:
        package.save(temporary)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_document(manager: WorkspaceManager, relative_path: str) -> str:
    path = manager.resolve(relative_path, must_exist=True)
    ext = path.suffix.lower()
    if ext in {".docx"}:
        try:
            from docx import Document
        except ImportError as erro:
            raise WorkspaceError("Dependência python-docx ausente. Execute preparar.bat.") from erro
        doc = Document(path)
        partes = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                partes.append(paragraph.text)
        for idx, table in enumerate(doc.tables, 1):
            partes.append(f"\n[Tabela {idx}]")
            for row in table.rows:
                partes.append(" | ".join(cell.text.replace("\n", " / ") for cell in row.cells))
        return _truncate("\n".join(partes) or "Documento Word sem texto extraível.")

    if ext in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as erro:
            raise WorkspaceError("Dependência openpyxl ausente. Execute preparar.bat.") from erro
        workbook = load_workbook(path, read_only=True, data_only=False, keep_vba=(ext == ".xlsm"))
        partes = []
        try:
            for sheet in workbook.worksheets:
                partes.append(f"[Planilha: {sheet.title} | dimensão: {sheet.max_row}x{sheet.max_column}]")
                for row in sheet.iter_rows():
                    values = [cell.value for cell in row]
                    while values and values[-1] is None:
                        values.pop()
                    if values:
                        partes.append(" | ".join("" if value is None else str(value) for value in values))
                    if len(partes) > 500:
                        partes.append("[Linhas restantes omitidas]")
                        break
        finally:
            workbook.close()
        return _truncate("\n".join(partes) or "Planilha sem conteúdo.")

    if ext == ".pptx":
        try:
            from pptx import Presentation
        except ImportError as erro:
            raise WorkspaceError("Dependência python-pptx ausente. Execute preparar.bat.") from erro
        presentation = Presentation(path)
        partes = []
        for indice, slide in enumerate(presentation.slides, 1):
            partes.append(f"[Slide {indice}]")
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    partes.append(shape.text)
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        partes.append(" | ".join(cell.text for cell in row.cells))
        return _truncate("\n".join(partes) or "Apresentação sem texto extraível.")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as erro:
            raise WorkspaceError("Dependência pypdf ausente. Execute preparar.bat.") from erro
        reader = PdfReader(str(path))
        partes = []
        for idx, page in enumerate(reader.pages[:80], 1):
            partes.append(f"[Página {idx}]\n{page.extract_text() or ''}")
        return _truncate("\n\n".join(partes) or "PDF sem texto extraível; pode ser digitalizado.")

    if ext in {".csv", ".tsv"}:
        delimiter = "\t" if ext == ".tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=delimiter))[:500]
        return _truncate("\n".join(" | ".join(row) for row in rows))

    if ext == ".epub":
        from .ebooks import read_ebook
        return read_ebook(manager, relative_path)

    if ext in {".txt", ".md", ".rtf"}:
        return manager.read_text(relative_path)

    raise WorkspaceError(
        f"Formato {ext or '(sem extensão)'} não suportado para leitura estruturada. "
        "Use DOCX, XLSX, XLSM, PPTX, PDF, EPUB, CSV, TSV ou texto. Arquivos .doc/.xls antigos precisam ser convertidos."
    )



def _adicionar_runs_markdown(paragraph, texto: str) -> None:
    """Aplica negrito, itálico e código inline sem interpretar HTML arbitrário."""
    import re
    partes = re.split(r"(\*\*.+?\*\*|(?<!\*)\*[^*]+\*(?!\*)|`[^`]+`)", str(texto))
    for parte in partes:
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**"):
            paragraph.add_run(parte[2:-2]).bold = True
        elif parte.startswith("*") and parte.endswith("*"):
            paragraph.add_run(parte[1:-1]).italic = True
        elif parte.startswith("`") and parte.endswith("`"):
            run = paragraph.add_run(parte[1:-1])
            run.font.name = "Consolas"
            run.font.size = __import__("docx").shared.Pt(9)
        else:
            paragraph.add_run(parte)


def create_word_document(
    manager: WorkspaceManager,
    relative_path: str,
    title: str = "",
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
    author: str = "Gac.IA",
) -> str:
    """Cria DOCX A4 com estilos, Markdown básico, tabelas e paginação."""
    path = manager.resolve(relative_path)
    if path.suffix.lower() != ".docx":
        raise WorkspaceError("Novos documentos Word devem usar a extensão .docx.")
    if path.exists():
        raise WorkspaceError("O arquivo já existe. Para evitar sobrescrita acidental, escolha outro nome.")
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError as erro:
        raise WorkspaceError("Dependência python-docx ausente. Execute preparar.bat.") from erro

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.75)
    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for nome_estilo, tamanho, cor in (("Title", 25, "17365D"), ("Heading 1", 17, "17365D"),
                                      ("Heading 2", 14, "2F5597"), ("Heading 3", 12, "4472C4")):
        estilo = doc.styles[nome_estilo]
        estilo.font.name = "Aptos Display"
        estilo.font.size = Pt(tamanho)
        estilo.font.bold = True
        estilo.font.color.rgb = __import__("docx").shared.RGBColor.from_string(cor)

    if title:
        heading = doc.add_paragraph(style="Title")
        heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _adicionar_runs_markdown(heading, str(title))
    for texto in paragraphs or []:
        linha = str(texto or "")
        if not linha.strip():
            doc.add_paragraph()
            continue
        match = __import__("re").match(r"^(#{1,3})\s+(.+)$", linha.strip())
        bullet = __import__("re").match(r"^[-*+]\s+(.+)$", linha.strip())
        numbered = __import__("re").match(r"^\d+[.)]\s+(.+)$", linha.strip())
        if match:
            p = doc.add_paragraph(style=f"Heading {len(match.group(1))}")
            _adicionar_runs_markdown(p, match.group(2))
        elif bullet:
            p = doc.add_paragraph(style="List Bullet")
            _adicionar_runs_markdown(p, bullet.group(1))
        elif numbered:
            p = doc.add_paragraph(style="List Number")
            _adicionar_runs_markdown(p, numbered.group(1))
        else:
            p = doc.add_paragraph()
            _adicionar_runs_markdown(p, linha)

    for indice, rows in enumerate(tables or [], 1):
        if not rows:
            continue
        if len(rows) > 1000 or any(not isinstance(row, (list, tuple)) for row in rows):
            raise WorkspaceError("Cada tabela pode ter no máximo 1.000 linhas e precisa usar listas de células.")
        columns = max((len(row) for row in rows), default=0)
        if not columns or columns > 50:
            raise WorkspaceError("Cada tabela precisa ter de 1 a 50 colunas.")
        if indice > 1:
            doc.add_paragraph()
        table = doc.add_table(rows=len(rows), cols=columns)
        try:
            table.style = "Light Shading Accent 1"
        except KeyError:
            table.style = "Table Grid"
        table.autofit = True
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                cell = table.cell(row_index, col_index)
                cell.text = str(value)
                if row_index == 0:
                    for run in cell.paragraphs[0].runs:
                        run.bold = True

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run(str(author or "Gac.IA")[:80])
    run.font.size = Pt(8)
    run.font.color.rgb = __import__("docx").shared.RGBColor.from_string("667085")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Página ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    doc.core_properties.title = str(title or path.stem)[:250]
    doc.core_properties.author = str(author or "Gac.IA")[:250]
    doc.core_properties.subject = "Documento criado pela Gac.IA"
    _save_package_atomic(doc, path)
    return f"Documento Word criado: {relative_path} (A4, estilos, listas, tabelas e numeração de página)."


def create_spreadsheet(
    manager: WorkspaceManager,
    relative_path: str,
    sheet_name: str = "Planilha1",
    rows: list[list[Any]] | None = None,
    freeze_header: bool = True,
    additional_sheets: list[dict[str, Any]] | None = None,
    charts: list[dict[str, Any]] | None = None,
) -> str:
    """Cria XLSX com várias abas, tabelas formatadas, filtros e gráficos simples.

    Cada gráfico especifica sheet_name, type (bar/line/pie), data_ref,
    categories_ref e anchor (ex.: E2). Os intervalos são referências A1.
    """
    path = manager.resolve(relative_path)
    if path.suffix.lower() != ".xlsx":
        raise WorkspaceError("Novas planilhas devem usar a extensão .xlsx.")
    if path.exists():
        raise WorkspaceError("O arquivo já existe. Para evitar sobrescrita acidental, escolha outro nome.")
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    except ImportError as erro:
        raise WorkspaceError("Dependência openpyxl ausente. Execute preparar.bat.") from erro

    extras = additional_sheets or []
    grafos = charts or []
    if not isinstance(extras, list) or len(extras) > 20:
        raise WorkspaceError("Informe até 20 abas adicionais.")
    if not isinstance(grafos, list) or len(grafos) > 20:
        raise WorkspaceError("Informe até 20 gráficos por planilha.")
    entradas = [(sheet_name or "Planilha1", rows or [])]
    for item in extras:
        if not isinstance(item, dict) or not isinstance(item.get("rows"), list):
            raise WorkspaceError("Cada aba adicional precisa conter name e rows.")
        entradas.append((item.get("name") or "Planilha", item["rows"]))

    workbook = Workbook()
    try:
        workbook.remove(workbook.active)
        nomes = set()
        total_cells = 0
        for index, (raw_name, conteudo) in enumerate(entradas, 1):
            nome = str(raw_name or f"Planilha{index}").strip()
            if not nome or len(nome) > 31 or any(ch in nome for ch in "[]:*?/\\"):
                raise WorkspaceError(f"Nome de aba inválido: {nome!r}. Use até 31 caracteres e evite []:*?/\\.")
            if nome.casefold() in nomes:
                raise WorkspaceError(f"Nome de aba duplicado: {nome}.")
            nomes.add(nome.casefold())
            if not isinstance(conteudo, list) or len(conteudo) > 10000:
                raise WorkspaceError(f"A aba '{nome}' deve ter até 10.000 linhas.")
            if any(not isinstance(row, (list, tuple)) for row in conteudo):
                raise WorkspaceError(f"Todas as linhas de '{nome}' precisam ser listas.")
            colunas = max((len(row) for row in conteudo), default=0)
            if colunas > 100:
                raise WorkspaceError(f"A aba '{nome}' ultrapassa 100 colunas.")
            total_cells += sum(len(row) for row in conteudo)
            if total_cells > 500000:
                raise WorkspaceError("A planilha ultrapassa 500.000 células; divida os dados em arquivos menores.")

            sheet = workbook.create_sheet(nome)
            for row_index, values in enumerate(conteudo, 1):
                for col_index, value in enumerate(values, 1):
                    sheet.cell(row=row_index, column=col_index, value=value)
            if conteudo and conteudo[0]:
                header_fill = PatternFill("solid", fgColor="243B53")
                header_font = Font(bold=True, color="FFFFFF")
                bottom = Side(style="thin", color="D9E2EC")
                for cell in sheet[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    cell.border = Border(bottom=bottom)
                sheet.row_dimensions[1].height = 24
                if freeze_header:
                    sheet.freeze_panes = "A2"
                if sheet.max_row >= 2:
                    sheet.auto_filter.ref = sheet.dimensions
                    headers = [str(sheet.cell(row=1, column=c).value or "").strip() for c in range(1, sheet.max_column + 1)]
                    if all(headers) and len({value.casefold() for value in headers}) == len(headers):
                        table = Table(displayName=f"TabelaDados{index}", ref=sheet.dimensions)
                        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False,
                            showLastColumn=False, showRowStripes=True, showColumnStripes=False)
                        sheet.add_table(table)
            for column_index in range(1, sheet.max_column + 1):
                values = [sheet.cell(row=r, column=column_index).value for r in range(1, min(sheet.max_row, 100) + 1)]
                width = max((len(str(value)) for value in values if value is not None), default=8)
                sheet.column_dimensions[get_column_letter(column_index)].width = min(max(width + 2, 10), 48)
            sheet.sheet_view.showGridLines = False

        for chart_data in grafos:
            if not isinstance(chart_data, dict):
                raise WorkspaceError("Cada gráfico precisa ser um objeto de configuração.")
            sheet_name_chart = str(chart_data.get("sheet_name") or sheet_name or "Planilha1")
            if sheet_name_chart not in workbook.sheetnames:
                raise WorkspaceError(f"Aba do gráfico não encontrada: {sheet_name_chart}.")
            kind = str(chart_data.get("type") or "bar").lower()
            chart_class = {"bar": BarChart, "line": LineChart, "pie": PieChart}.get(kind)
            if chart_class is None:
                raise WorkspaceError("Tipo de gráfico inválido. Use bar, line ou pie.")
            sheet = workbook[sheet_name_chart]
            try:
                data_ref = str(chart_data["data_ref"])
                categories_ref = str(chart_data["categories_ref"])
                min_col, min_row, max_col, max_row = __import__("openpyxl").utils.cell.range_boundaries(data_ref)
                cmin, rmin, cmax, rmax = __import__("openpyxl").utils.cell.range_boundaries(categories_ref)
                if min_row < 1 or min_col < 1 or max_row > sheet.max_row or max_col > sheet.max_column or rmax > sheet.max_row or cmax > sheet.max_column:
                    raise ValueError("intervalo fora dos dados")
            except (KeyError, TypeError, ValueError) as erro:
                raise WorkspaceError(f"Intervalos do gráfico inválidos na aba '{sheet_name_chart}'.") from erro
            chart = chart_class()
            chart.title = str(chart_data.get("title") or "Gráfico")[:120]
            chart.style = 10
            chart.height = 8
            chart.width = 14
            if kind == "pie":
                chart.add_data(Reference(sheet, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row), titles_from_data=True)
                chart.set_categories(Reference(sheet, min_col=cmin, min_row=rmin, max_col=cmax, max_row=rmax))
            else:
                chart.add_data(Reference(sheet, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row), titles_from_data=True)
                chart.set_categories(Reference(sheet, min_col=cmin, min_row=rmin, max_col=cmax, max_row=rmax))
                chart.y_axis.title = str(chart_data.get("y_axis_title") or "")[:80]
                chart.x_axis.title = str(chart_data.get("x_axis_title") or "")[:80]
            sheet.add_chart(chart, str(chart_data.get("anchor") or "E2"))

        workbook.properties.title = path.stem
        workbook.properties.creator = "Gac.IA"
        workbook.properties.subject = "Planilha criada pela Gac.IA"
        _save_package_atomic(workbook, path)
    finally:
        workbook.close()
    return f"Planilha criada: {relative_path} ({len(entradas)} aba(s), {len(grafos)} gráfico(s), até 500.000 células)."


def create_powerpoint(
    manager: WorkspaceManager,
    relative_path: str,
    title: str = "",
    slides: list[dict[str, Any]] | None = None,
    author: str = "Gac.IA",
    theme: str = "modern",
) -> str:
    """Cria apresentação 16:9 com temas visuais e layouts editáveis.

    Cada slide aceita layout: title, title_content, section, two_column, quote,
    metrics, image, table ou closing. Imagens devem estar no workspace ou nas exportações gerenciadas da Gac.IA.
    """
    path = manager.resolve(relative_path)
    if path.suffix.lower() != ".pptx":
        raise WorkspaceError("Novas apresentações devem usar a extensão .pptx.")
    if path.exists():
        raise WorkspaceError("O arquivo já existe. Escolha outro nome para evitar sobrescrita acidental.")
    if not isinstance(slides, list) or not slides:
        raise WorkspaceError("Informe ao menos um slide em slides.")
    if len(slides) > 100:
        raise WorkspaceError("A criação está limitada a 100 slides por operação.")
    themes = {
        "modern": {"bg": "F7F8FC", "fg": "152238", "muted": "526078", "accent": "4169E1", "panel": "E8EEFC", "white": "FFFFFF"},
        "dark": {"bg": "111827", "fg": "F9FAFB", "muted": "C2CAD6", "accent": "8B5CF6", "panel": "263247", "white": "FFFFFF"},
        "creative": {"bg": "FFF7F5", "fg": "35213A", "muted": "765B70", "accent": "E84A75", "panel": "FCE4EC", "white": "FFFFFF"},
        "minimal": {"bg": "FFFFFF", "fg": "171717", "muted": "525252", "accent": "171717", "panel": "F4F4F5", "white": "FFFFFF"},
        "corporate": {"bg": "F1F5F9", "fg": "102A43", "muted": "486581", "accent": "0F766E", "panel": "DCEFEB", "white": "FFFFFF"},
        "nvidia": {"bg": "0B0B0B", "fg": "F4F6F2", "muted": "AAB2A5", "accent": "76B900", "panel": "171A17", "white": "FFFFFF"},
    }
    theme_key = str(theme or "modern").lower().strip()
    if theme_key not in themes:
        theme_key = "modern"
    palette = themes[theme_key]
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
    except ImportError as erro:
        raise WorkspaceError("Dependência python-pptx ausente. Execute preparar.bat e selecione Documentos e produtividade.") from erro

    def color(value: str):
        return RGBColor.from_string(value)

    presentation = Presentation()
    presentation.slide_width = Inches(13.333333)
    presentation.slide_height = Inches(7.5)
    presentation.core_properties.title = str(title or "Apresentação")[:255]
    presentation.core_properties.author = str(author or "Gac.IA")[:255]
    presentation.core_properties.subject = f"Apresentação criada pela Gac.IA · tema {theme_key}"
    width, height = presentation.slide_width, presentation.slide_height

    def add_text(slide, x, y, w, h, text, size=18, fg=None, bold=False, align=None, font="Aptos", margin=0.03):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = shape.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.margin_left = Inches(margin)
        frame.margin_right = Inches(margin)
        frame.margin_top = Inches(margin)
        frame.margin_bottom = Inches(margin)
        paragraph = frame.paragraphs[0]
        if align is not None:
            paragraph.alignment = align
        run = paragraph.add_run()
        run.text = str(text or "")
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color(fg or palette["fg"])
        return shape

    def add_rect(slide, x, y, w, h, fill, rounded=False):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Inches(x), Inches(y), Inches(w), Inches(h),
        )
        shape.fill.solid(); shape.fill.fore_color.rgb = color(fill)
        shape.line.fill.background()
        if rounded:
            try:
                shape.adjustments[0] = 0.08
            except (IndexError, AttributeError):
                pass
        return shape

    def add_image_crop(slide, image_ref: str, box_x: float, box_y: float, box_w: float, box_h: float, slide_index: int):
        image_path = manager.resolve(str(image_ref), must_exist=True)
        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} or image_path.stat().st_size > 30 * 1024 * 1024:
            raise WorkspaceError(f"Imagem do slide {slide_index} inválida ou acima de 30 MiB.")
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                image_w, image_h = im.size
                if not image_w or not image_h:
                    raise ValueError("Dimensões inválidas")
                # WebP é comum em buscas online e imagens enviadas, mas não é
                # um formato de imagem universalmente suportado no PowerPoint.
                # Convertemos em memória para PNG sem alterar o original.
                if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    converted = io.BytesIO()
                    mode = "RGBA" if "A" in im.getbands() else "RGB"
                    im.convert(mode).save(converted, format="PNG")
                    converted.seek(0)
                    picture_source = converted
                else:
                    picture_source = str(image_path)
        except Exception as erro:
            raise WorkspaceError(f"Não foi possível validar a imagem do slide {slide_index}: {erro}") from erro
        pic = slide.shapes.add_picture(picture_source, Inches(box_x), Inches(box_y), Inches(box_w), Inches(box_h))
        target_ar, source_ar = box_w / box_h, image_w / image_h
        if source_ar > target_ar:
            crop = (1 - target_ar / source_ar) / 2
            pic.crop_left = crop
            pic.crop_right = crop
        elif source_ar < target_ar:
            crop = (1 - source_ar / target_ar) / 2
            pic.crop_top = crop
            pic.crop_bottom = crop
        return image_path

    def add_notes(slide, item):
        notes = str(item.get("notes") or "").strip()
        if notes:
            try:
                slide.notes_slide.notes_text_frame.text = notes
            except (AttributeError, ValueError):
                pass

    for index, item in enumerate(slides, 1):
        if not isinstance(item, dict):
            raise WorkspaceError(f"O slide {index} deve ser um objeto.")
        layout_kind = str(item.get("layout", "title_content")).lower().strip()
        aliases = {"title": "cover", "title_content": "content", "closing": "closing"}
        layout_kind = aliases.get(layout_kind, layout_kind)
        valid_layouts = {"cover", "content", "section", "two_column", "quote", "metrics", "image", "table", "closing"}
        if layout_kind not in valid_layouts:
            layout_kind = "content"
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        background = slide.background.fill
        background.solid(); background.fore_color.rgb = color(palette["bg"])
        slide_title = str(item.get("title") or (title if index == 1 else f"Slide {index}"))[:300]
        subtitle = str(item.get("subtitle") or "")[:500]
        content = item.get("content", item.get("bullets", []))
        if isinstance(content, str):
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        elif isinstance(content, list):
            lines = [str(line).strip() for line in content if line is not None and str(line).strip()]
        else:
            lines = []
        lines = lines[:20]

        if layout_kind == "cover":
            add_rect(slide, 0, 0, 0.32, 7.5, palette["accent"])
            cover_image = item.get("image_path")
            if cover_image:
                add_image_crop(slide, str(cover_image), 8.55, 0, 4.783, 7.5, index)
            else:
                add_rect(slide, 9.5, 0, 3.833, 7.5, palette["panel"])
                add_rect(slide, 10.15, 1.1, 2.15, 2.15, palette["accent"], rounded=True)
            add_text(slide, 0.95, 1.05, 7.6, 0.45, str(item.get("eyebrow") or "APRESENTAÇÃO" ).upper(), 12, palette["accent"], True)
            add_text(slide, 0.9, 1.85, 8.0, 2.45, slide_title, 34, palette["fg"], True)
            add_rect(slide, 0.95, 4.55, 1.0, 0.07, palette["accent"])
            if subtitle or lines:
                add_text(slide, 0.95, 4.85, 7.7, 1.0, subtitle or "\n".join(lines[:3]), 18, palette["muted"])
            add_text(slide, 0.95, 6.75, 7.4, 0.3, str(item.get("footer") or author or "Gac.IA"), 10, palette["muted"])
            if item.get("image_credit"):
                add_text(slide, 8.7, 7.12, 4.4, 0.22, str(item["image_credit"])[:180], 7, palette["white"], False)

        elif layout_kind == "section":
            background.solid(); background.fore_color.rgb = color(palette["accent"])
            add_text(slide, 0.85, 1.0, 11.5, 0.4, str(item.get("eyebrow") or "SEÇÃO").upper(), 12, palette["white"], True)
            add_text(slide, 0.8, 2.05, 11.4, 2.0, slide_title, 34, palette["white"], True)
            if subtitle or lines:
                add_text(slide, 0.85, 4.4, 10.8, 1.1, subtitle or "\n".join(lines[:3]), 19, palette["white"])

        elif layout_kind == "quote":
            add_rect(slide, 0.75, 0.7, 0.12, 5.9, palette["accent"])
            add_text(slide, 1.15, 0.85, 10.9, 0.55, slide_title, 16, palette["accent"], True)
            quote = str(item.get("quote") or (lines[0] if lines else subtitle))
            add_text(slide, 1.15, 1.8, 10.5, 3.4, "“" + quote + "”", 28, palette["fg"], True)
            add_text(slide, 1.2, 5.65, 9.8, 0.55, str(item.get("attribution") or (lines[1] if len(lines) > 1 else "")), 14, palette["muted"])

        elif layout_kind == "metrics":
            add_text(slide, 0.75, 0.55, 11.8, 0.7, slide_title, 28, palette["fg"], True)
            metrics = item.get("metrics") if isinstance(item.get("metrics"), list) else []
            if not metrics:
                metrics = [{"value": line, "label": ""} for line in lines[:4]]
            if len(metrics) > 4:
                metrics = metrics[:4]
            gap = 0.22
            card_w = (11.8 - gap * max(0, len(metrics) - 1)) / max(1, len(metrics))
            for metric_index, metric in enumerate(metrics):
                if isinstance(metric, dict):
                    value, label = str(metric.get("value", "")), str(metric.get("label", ""))
                else:
                    value, label = str(metric), ""
                x = 0.75 + metric_index * (card_w + gap)
                add_rect(slide, x, 2.0, card_w, 3.2, palette["panel"], rounded=True)
                add_text(slide, x + 0.18, 2.65, card_w - 0.36, 1.0, value[:60], 30, palette["accent"], True, PP_ALIGN.CENTER)
                add_text(slide, x + 0.18, 3.8, card_w - 0.36, 0.8, label[:140], 15, palette["fg"], False, PP_ALIGN.CENTER)
            if subtitle:
                add_text(slide, 0.85, 5.65, 11.4, 0.75, subtitle, 14, palette["muted"])

        elif layout_kind == "two_column":
            add_text(slide, 0.75, 0.55, 11.8, 0.65, slide_title, 27, palette["fg"], True)
            columns = item.get("columns") if isinstance(item.get("columns"), list) else None
            left = item.get("left", columns[0] if columns and len(columns) > 0 else lines[: (len(lines) + 1) // 2])
            right = item.get("right", columns[1] if columns and len(columns) > 1 else lines[(len(lines) + 1) // 2:])
            if isinstance(left, str): left = [left]
            if isinstance(right, str): right = [right]
            for col_index, (col_title, values) in enumerate(((item.get("left_title", "PONTOS PRINCIPAIS"), left), (item.get("right_title", "DETALHES"), right))):
                x = 0.75 + col_index * 6.0
                add_rect(slide, x, 1.65, 5.65, 4.85, palette["panel"], rounded=True)
                add_text(slide, x + 0.22, 1.95, 5.2, 0.5, col_title, 13, palette["accent"], True)
                vals = values if isinstance(values, list) else [values]
                y = 2.65
                for value in vals[:8]:
                    if isinstance(value, dict):
                        text_value = str(value.get("text") or value.get("title") or "")
                    else:
                        text_value = str(value)
                    add_text(slide, x + 0.25, y, 5.0, 0.62, "•  " + text_value, 15, palette["fg"])
                    y += 0.7

        elif layout_kind == "image":
            add_text(slide, 0.75, 0.55, 11.8, 0.65, slide_title, 27, palette["fg"], True)
            image_ref = item.get("image_path")
            if image_ref:
                box_x, box_y, box_w, box_h = 6.65, 1.55, 5.75, 4.9
                add_image_crop(slide, str(image_ref), box_x, box_y, box_w, box_h, index)
            else:
                add_rect(slide, 6.65, 1.55, 5.75, 4.9, palette["panel"], rounded=True)
                add_text(slide, 7.05, 3.55, 4.9, 0.6, "[Imagem não especificada]", 16, palette["muted"], False, PP_ALIGN.CENTER)
            add_rect(slide, 0.8, 1.55, 0.08, 4.9, palette["accent"])
            y = 1.7
            for line in lines[:7]:
                add_text(slide, 1.1, y, 5.0, 0.68, "•  " + line, 16, palette["fg"])
                y += 0.72
            if subtitle:
                add_text(slide, 1.1, 6.2, 5.0, 0.4, subtitle, 12, palette["muted"])
            if item.get("image_credit"):
                add_text(slide, 6.7, 6.55, 5.65, 0.26, str(item["image_credit"])[:180], 7, palette["muted"], False)

        elif layout_kind == "table" or item.get("table"):
            add_text(slide, 0.75, 0.55, 11.8, 0.65, slide_title, 27, palette["fg"], True)
            table_rows = item.get("table") or []
            if not isinstance(table_rows, list) or not table_rows or not all(isinstance(row, (list, tuple)) for row in table_rows):
                raise WorkspaceError(f"Tabela do slide {index} deve ser uma lista de linhas.")
            columns_count = max((len(row) for row in table_rows), default=0)
            if len(table_rows) > 20 or columns_count > 10 or columns_count == 0:
                raise WorkspaceError(f"Tabela do slide {index} excede 20 linhas ou 10 colunas, ou está vazia.")
            table_shape = slide.shapes.add_table(len(table_rows), columns_count, Inches(0.75), Inches(1.6), Inches(11.8), Inches(min(4.9, max(0.75, 0.42 * len(table_rows)))))
            table = table_shape.table
            for row_index, row in enumerate(table_rows):
                for col_index in range(columns_count):
                    cell = table.cell(row_index, col_index)
                    cell.text = str(row[col_index]) if col_index < len(row) else ""
                    cell.margin_left = Inches(0.08); cell.margin_right = Inches(0.08)
                    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = color(palette["accent"] if row_index == 0 else (palette["panel"] if row_index % 2 else palette["bg"]))
                    for paragraph in cell.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run.font.name = "Aptos"
                            run.font.size = Pt(12)
                            run.font.bold = row_index == 0
                            run.font.color.rgb = color(palette["white"] if row_index == 0 else palette["fg"])

        elif layout_kind == "closing":
            background.solid(); background.fore_color.rgb = color(palette["accent"])
            add_text(slide, 0.85, 1.8, 11.5, 1.4, slide_title or "Obrigado!", 36, palette["white"], True, PP_ALIGN.CENTER)
            if subtitle or lines:
                add_text(slide, 1.35, 3.55, 10.6, 1.1, subtitle or "\n".join(lines[:3]), 18, palette["white"], False, PP_ALIGN.CENTER)

        else:  # content, com distribuição limpa e texto editável
            add_rect(slide, 0.75, 1.35, 0.12, 5.5, palette["accent"])
            add_text(slide, 0.75, 0.48, 11.9, 0.72, slide_title, 27, palette["fg"], True)
            if subtitle:
                add_text(slide, 0.82, 1.55, 11.4, 0.55, subtitle, 14, palette["muted"])
            max_lines = 10
            visible_lines = lines[:max_lines]
            available_y = 2.2 if subtitle else 1.75
            if visible_lines:
                step = min(0.53, 4.9 / len(visible_lines))
                font_size = 19 if len(visible_lines) <= 6 else 16
                for line_index, line in enumerate(visible_lines):
                    y = available_y + line_index * step
                    add_rect(slide, 1.15, y + 0.14, 0.12, 0.12, palette["accent"], rounded=True)
                    add_text(slide, 1.48, y, 10.5, step - 0.02, line, font_size, palette["fg"])

        # Rodapé discreto e numeração ajudam a manter consistência visual.
        if layout_kind not in {"section", "closing"}:
            add_text(slide, 0.78, 7.08, 10.8, 0.2, str(item.get("footer") or author or "Gac.IA"), 8, palette["muted"])
            add_text(slide, 12.0, 7.04, 0.55, 0.25, f"{index:02d}", 9, palette["muted"], True, PP_ALIGN.RIGHT)
        add_notes(slide, item)

    _save_package_atomic(presentation, path)
    return f"Apresentação PowerPoint criada: {relative_path} ({len(presentation.slides)} slides, tema {theme_key}, proporção 16:9 e layouts editáveis)."


def edit_powerpoint(
    manager: WorkspaceManager,
    relative_path: str,
    replacements: dict[str, str] | None = None,
    append_slides: list[dict[str, Any]] | None = None,
    brand_palette: str = "",
) -> str:
    path = manager.resolve(relative_path, must_exist=True)
    if path.suffix.lower() != ".pptx":
        raise WorkspaceError("A edição estruturada de apresentações aceita .pptx.")
    palette_key = str(brand_palette or "").strip().lower()
    if palette_key not in {"", "nvidia"}:
        raise WorkspaceError("brand_palette aceita apenas 'nvidia' ou vazio.")
    if not replacements and not append_slides and not palette_key:
        raise WorkspaceError("Informe replacements, append_slides ou brand_palette.")
    if replacements is not None and not isinstance(replacements, dict):
        raise WorkspaceError("replacements deve ser um objeto texto_antigo: texto_novo.")
    try:
        from pptx import Presentation
    except ImportError as erro:
        raise WorkspaceError("Dependência python-pptx ausente. Execute preparar.bat.") from erro
    presentation = Presentation(path)
    altered = 0
    for slide in presentation.slides:
        for shape in slide.shapes:
            frames = []
            if getattr(shape, "has_text_frame", False):
                frames.append(shape.text_frame)
            if getattr(shape, "has_table", False):
                frames.extend(cell.text_frame for row in shape.table.rows for cell in row.cells)
            for frame in frames:
                for paragraph in frame.paragraphs:
                    for run in paragraph.runs:
                        original = run.text
                        updated = original
                        for old, new_value in (replacements or {}).items():
                            if str(old) and str(old) in updated:
                                updated = updated.replace(str(old), str(new_value))
                        if updated != original:
                            run.text = updated
                            altered += 1
    if append_slides:
        # Reutiliza o criador para manter a mesma formatação, depois importa
        # os slides para a apresentação existente por cópia XML controlada.
        if not isinstance(append_slides, list) or len(append_slides) > 100:
            raise WorkspaceError("append_slides deve ser uma lista com até 100 slides.")
        for item in append_slides:
            if not isinstance(item, dict):
                raise WorkspaceError("Cada novo slide deve ser um objeto.")
            layout_kind = str(item.get("layout", "title_content")).lower()
            layout_index = 0 if layout_kind == "title" else (2 if layout_kind == "section" else 1)
            layout_index = min(layout_index, len(presentation.slide_layouts) - 1)
            slide = presentation.slides.add_slide(presentation.slide_layouts[layout_index])
            if slide.shapes.title is not None:
                slide.shapes.title.text = str(item.get("title") or "Novo slide")
            content = item.get("content", item.get("bullets", []))
            lines = ([v.strip() for v in content.splitlines() if v.strip()] if isinstance(content, str)
                     else [str(v) for v in content if v is not None] if isinstance(content, list) else [])
            body = next((ph for ph in slide.placeholders if getattr(ph.placeholder_format, "idx", -1) == 1), None)
            if body is not None and getattr(body, "has_text_frame", False):
                body.text = "\n".join(lines)
            notes = str(item.get("notes") or "").strip()
            if notes:
                try:
                    slide.notes_slide.notes_text_frame.text = notes
                except (AttributeError, ValueError):
                    pass
    original_slide_count = len(presentation.slides) - len(append_slides or [])
    if palette_key == "nvidia":
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        green = RGBColor.from_string("76B900")
        black = RGBColor.from_string("0B0B0B")
        panel = RGBColor.from_string("171A17")
        white = RGBColor.from_string("F4F6F2")
        muted = RGBColor.from_string("AAB2A5")
        table_colors = (green, RGBColor.from_string("253020"), RGBColor.from_string("1B201A"))

        def paint_text(frame, header=False):
            for paragraph in frame.paragraphs:
                for run in paragraph.runs:
                    try:
                        size = run.font.size.pt if run.font.size else 0
                    except (AttributeError, TypeError, ValueError):
                        size = 0
                    run.font.color.rgb = (white if header or run.font.bold or size >= 22 else muted if size <= 9 else white)

        for slide in presentation.slides:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = black
            slide_area = max(1, presentation.slide_width * presentation.slide_height)
            for shape in slide.shapes:
                if getattr(shape, "has_table", False):
                    for row_index, row in enumerate(shape.table.rows):
                        for cell in row.cells:
                            cell.fill.solid()
                            cell.fill.fore_color.rgb = table_colors[min(row_index, len(table_colors) - 1)]
                            paint_text(cell.text_frame, header=row_index == 0)
                    altered += 1
                    continue
                if getattr(shape, "has_chart", False):
                    try:
                        for series_index, series in enumerate(shape.chart.series):
                            series.format.fill.solid()
                            series.format.fill.fore_color.rgb = (green, white, muted)[series_index % 3]
                    except (AttributeError, TypeError, ValueError):
                        pass
                    altered += 1
                    continue
                if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE:  # preserve the image itself
                    continue
                area_ratio = (max(0, shape.width) * max(0, shape.height)) / slide_area
                if shape.shape_type != MSO_SHAPE_TYPE.TEXT_BOX:
                    try:
                        shape.fill.solid()
                        shape.fill.fore_color.rgb = green if area_ratio < 0.035 else panel if area_ratio < 0.45 else black
                        altered += 1
                    except (AttributeError, TypeError, ValueError):
                        pass
                    try:
                        shape.line.color.rgb = green if area_ratio < 0.035 else RGBColor.from_string("343A32")
                    except (AttributeError, TypeError, ValueError):
                        pass
                if getattr(shape, "has_text_frame", False):
                    paint_text(shape.text_frame)
                altered += 1
        if len(presentation.slides) < original_slide_count:
            raise WorkspaceError("A contagem de slides mudou durante a aplicação da paleta; o arquivo não foi salvo.")
    _save_package_atomic(presentation, path)
    if palette_key == "nvidia":
        return f"Paleta NVIDIA verde/preto aplicada ao deck inteiro: {len(presentation.slides)} slide(s) preservados, imagens mantidas e conteúdo editável."
    return f"Apresentação atualizada: {altered} trecho(s) substituído(s), {len(append_slides or [])} slide(s) adicionado(s). Substituições não atravessam divisões entre runs do PowerPoint."


def create_pdf_document(
    manager: WorkspaceManager,
    relative_path: str,
    title: str = "",
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
    page_size: str = "A4",
) -> str:
    path = manager.resolve(relative_path)
    if path.suffix.lower() != ".pdf":
        raise WorkspaceError("Novos documentos PDF devem usar a extensão .pdf.")
    if path.exists():
        raise WorkspaceError("O arquivo já existe. Escolha outro nome para evitar sobrescrita acidental.")
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError as erro:
        raise WorkspaceError("Dependência reportlab ausente. Execute preparar.bat para habilitar a criação de PDF.") from erro

    if not str(title or "").strip() and not any(str(item).strip() for item in (paragraphs or [])) and not any(tables or []):
        raise WorkspaceError("Informe um título, ao menos um parágrafo ou uma tabela para gerar o PDF.")
    if len(paragraphs or []) > 500 or len(tables or []) > 50:
        raise WorkspaceError("Documento excede os limites de segurança (500 parágrafos e 50 tabelas).")
    tamanho = A4 if str(page_size).upper() == "A4" else letter if str(page_size).upper() in {"LETTER", "CARTA"} else None
    if tamanho is None:
        raise WorkspaceError("page_size deve ser A4 ou LETTER.")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="GacTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=25, textColor=colors.HexColor("#243B53"),
        alignment=TA_LEFT, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="GacBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=10, leading=15, spaceAfter=8,
    ))
    story = []
    if title:
        story.extend([Paragraph(escape(str(title)), styles["GacTitle"]), Spacer(1, 3 * mm)])
    for paragraph in paragraphs or []:
        text_value = escape(str(paragraph)).replace("\n", "<br/>")
        story.append(Paragraph(text_value or " ", styles["GacBody"]))
    for table_index, rows in enumerate(tables or [], 1):
        if not isinstance(rows, list) or not rows:
            continue
        max_columns = max((len(row) for row in rows if isinstance(row, (list, tuple))), default=0)
        if not max_columns:
            continue
        if len(rows) > 500 or max_columns > 12:
            raise WorkspaceError(f"Tabela {table_index} excede o limite de 500 linhas e 12 colunas.")
        data = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                raise WorkspaceError(f"A linha {len(data) + 1} da tabela {table_index} é inválida.")
            data.append([Paragraph(escape(str(value)).replace("\n", "<br/>"), styles["GacBody"]) for value in row] + [""] * (max_columns - len(row)))
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243B53")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 8 * mm)])

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".pdf", dir=path.parent)
    os.close(fd)
    try:
        doc = SimpleDocTemplate(temporary, pagesize=tamanho, rightMargin=20 * mm,
                                leftMargin=20 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                                title=str(title or "Documento Gac.IA"), author="Gac.IA")
        def footer(canvas, document):
            canvas.saveState()
            canvas.setTitle(str(title or "Documento Gac.IA"))
            canvas.setAuthor("Gac.IA")
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawRightString(tamanho[0] - 20 * mm, 10 * mm, f"Gac.IA  |  Página {document.page}")
            canvas.restoreState()
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        if path.exists():
            raise WorkspaceError("O arquivo surgiu durante a criação; a Gac.IA não o sobrescreveu.")
        os.replace(temporary, path)
    except Exception:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return f"PDF criado: {relative_path} (página {str(page_size).upper()}, {len(paragraphs or [])} parágrafo(s), {len(tables or [])} tabela(s))."


def manage_pdf(
    manager: WorkspaceManager,
    relative_path: str,
    action: str,
    output_path: str = "",
    source_paths: list[str] | None = None,
    pages: list[int] | None = None,
    rotation: int = 90,
    metadata: dict[str, str] | None = None,
) -> str:
    """Operações estruturais seguras; não promete editar o texto interno do PDF."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as erro:
        raise WorkspaceError("Dependência pypdf ausente. Execute preparar.bat.") from erro
    acao = str(action or "").lower().strip()
    if acao == "merge":
        destino = manager.resolve(relative_path)
        if destino.suffix.lower() != ".pdf" or destino.exists():
            raise WorkspaceError("Para mesclar, path deve ser um novo arquivo .pdf inexistente.")
        fontes = source_paths or []
        if len(fontes) < 2 or len(fontes) > 30:
            raise WorkspaceError("Informe de 2 a 30 PDFs em source_paths.")
        writer = PdfWriter()
        with ExitStack() as stack:
            for source_rel in fontes:
                source = manager.resolve(source_rel, must_exist=True)
                if source.suffix.lower() != ".pdf":
                    raise WorkspaceError(f"Arquivo não é PDF: {source_rel}")
                stream = stack.enter_context(source.open("rb"))
                reader = PdfReader(stream, strict=False)
                if reader.is_encrypted:
                    raise WorkspaceError(f"O PDF '{source_rel}' está protegido por senha e não pode ser mesclado.")
                writer.append(reader)
                if len(writer.pages) > 500:
                    raise WorkspaceError("A mesclagem está limitada a 500 páginas.")
            _write_pdf_atomic(writer, destino, require_new=True)
        return f"PDFs mesclados em {relative_path}: {len(fontes)} arquivo(s), {len(writer.pages)} página(s)."

    source = manager.resolve(relative_path, must_exist=True)
    if source.suffix.lower() != ".pdf":
        raise WorkspaceError("A operação selecionada aceita apenas arquivos .pdf.")
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        raise WorkspaceError("PDF protegido por senha: não é possível editá-lo sem a senha.")
    total = len(reader.pages)
    selecionadas = pages if pages is not None else list(range(1, total + 1))
    if not isinstance(selecionadas, list) or not selecionadas:
        raise WorkspaceError("Informe uma lista não vazia de páginas numeradas a partir de 1.")
    if any(type(page) is not int or page < 1 or page > total for page in selecionadas):
        raise WorkspaceError(f"Páginas inválidas. O documento possui {total} página(s), numeradas de 1 a {total}.")

    writer = PdfWriter()
    if acao == "extract_pages":
        if not output_path:
            raise WorkspaceError("Informe output_path para salvar as páginas extraídas.")
        destination = manager.resolve(output_path)
        if destination.suffix.lower() != ".pdf" or destination.exists():
            raise WorkspaceError("output_path deve ser um novo arquivo .pdf inexistente.")
        for page_number in selecionadas:
            writer.add_page(reader.pages[page_number - 1])
        _write_pdf_atomic(writer, destination, require_new=True)
        return f"Páginas {', '.join(map(str, selecionadas))} extraídas para {output_path}."

    if acao == "rotate":
        angulo = int(rotation)
        if angulo not in {90, 180, 270}:
            raise WorkspaceError("rotation deve ser 90, 180 ou 270 graus no sentido horário.")
        conjunto = set(selecionadas)
        for index, page in enumerate(reader.pages, 1):
            if index in conjunto:
                page.rotate(angulo)
            writer.add_page(page)
        writer.add_metadata(dict(reader.metadata or {}))
        _write_pdf_atomic(writer, source, require_new=False)
        return f"PDF atualizado: rotação de {angulo}° aplicada em {len(conjunto)} página(s)."

    if acao == "metadata":
        for page in reader.pages:
            writer.add_page(page)
        metadados = metadata or {}
        permitidas = {"title", "author", "subject", "creator", "producer", "keywords"}
        if not metadados or any(key not in permitidas for key in metadados):
            raise WorkspaceError("metadata deve conter campos entre title, author, subject, creator, producer e keywords.")
        permitidas = {"/Title", "/Author", "/Subject", "/Creator", "/Producer", "/Keywords"}
        novos = {
            str(key): str(value)
            for key, value in (reader.metadata or {}).items()
            if str(key) in permitidas and value is not None
        }
        novos.update({"/" + key.title(): str(value)[:1000] for key, value in metadados.items()})
        writer.add_metadata(novos)
        _write_pdf_atomic(writer, source, require_new=False)
        return f"Metadados do PDF atualizados: {', '.join(metadados)}."

    raise WorkspaceError("Ação PDF inválida. Use merge, extract_pages, rotate ou metadata.")


def add_image_pages_to_pdf(
    manager: WorkspaceManager,
    relative_path: str,
    images: list[dict[str, Any]],
) -> str:
    """Insere páginas ilustradas após páginas do PDF, preservando e copiando o original."""
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors
    except ImportError as erro:
        raise WorkspaceError("Dependências de PDF ausentes. Execute preparar.bat.") from erro
    source = manager.resolve(relative_path, must_exist=True)
    if source.suffix.lower() != ".pdf":
        raise WorkspaceError("A inserção de imagens aceita somente arquivos PDF.")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise WorkspaceError("PDF acima de 100 MiB; divida-o antes de adicionar imagens.")
    if not isinstance(images, list) or not images or len(images) > 5:
        raise WorkspaceError("Informe de 1 a 5 imagens pesquisadas para inserir no PDF.")
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted or not reader.pages:
        raise WorkspaceError("PDF protegido ou sem páginas legíveis.")

    insert_after: dict[int, list[dict[str, Any]]] = {}
    for item in images:
        if not isinstance(item, dict):
            continue
        page_number = int(item.get("page") or 1)
        image_path = Path(str(item.get("path") or "")).resolve()
        if page_number < 1 or page_number > len(reader.pages):
            raise WorkspaceError(f"Página {page_number} não existe; o PDF tem {len(reader.pages)} páginas.")
        if not image_path.is_file():
            raise WorkspaceError(f"Imagem pesquisada não foi encontrada: {image_path.name}.")
        insert_after.setdefault(page_number, []).append(item)

    writer = PdfWriter()
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items() if key and value is not None}
    if metadata:
        writer.add_metadata(metadata)
    original_page_count = len(reader.pages)
    visual_streams = []
    for page_number, page in enumerate(reader.pages, start=1):
        writer.add_page(page)
        for item in insert_after.get(page_number, []):
            image_path = Path(str(item["path"]))
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            stream = io.BytesIO()
            pdf_canvas = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1)
            margin = 42
            title = str(item.get("caption") or item.get("query") or "Imagem complementar")[:180]
            pdf_canvas.setFillColor(colors.HexColor("#76B900"))
            pdf_canvas.rect(0, height - 18, width, 18, fill=1, stroke=0)
            pdf_canvas.setFillColor(colors.HexColor("#111827"))
            pdf_canvas.setFont("Helvetica-Bold", 19)
            for line_index, line in enumerate(textwrap.wrap(title, width=64)[:2]):
                pdf_canvas.drawString(margin, height - 56 - line_index * 24, line)
            max_width = width - margin * 2
            max_height = height - 180
            image_reader = ImageReader(str(image_path))
            image_width, image_height = image_reader.getSize()
            scale = min(max_width / image_width, max_height / image_height)
            draw_width, draw_height = image_width * scale, image_height * scale
            draw_x = (width - draw_width) / 2
            draw_y = 92 + (max_height - draw_height) / 2
            pdf_canvas.drawImage(image_reader, draw_x, draw_y, draw_width, draw_height, preserveAspectRatio=True, mask="auto")
            pdf_canvas.setFillColor(colors.HexColor("#374151"))
            pdf_canvas.setFont("Helvetica", 8)
            credit = " · ".join(str(item.get(key) or "").strip() for key in ("title", "artist", "license", "description_url") if str(item.get(key) or "").strip())
            for line_index, line in enumerate(textwrap.wrap(credit, width=130)[:3]):
                pdf_canvas.drawString(margin, 58 - line_index * 11, line[:220])
            pdf_canvas.setFont("Helvetica", 8)
            pdf_canvas.drawRightString(width - margin, 28, f"Imagem complementar após a página {page_number}")
            pdf_canvas.save()
            stream.seek(0)
            visual_streams.append(stream)
            visual_page = PdfReader(stream, strict=False).pages[0]
            writer.add_page(visual_page)

    expected_count = original_page_count + sum(len(items) for items in insert_after.values())
    source_dir = (manager.base_dir / "data" / "exports").resolve()
    is_export = source.resolve() == source_dir or source_dir in source.resolve().parents
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if is_export:
        backup = manager.base_dir / "data" / "backups" / "exports" / stamp / source.resolve().relative_to(source_dir)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        backup_label = str(backup)
    else:
        backup = manager.backup_file(relative_path)
        backup_label = str(backup) if backup else "backup indisponível"

    fd, temporary = tempfile.mkstemp(prefix=f".{source.stem}_", suffix=".pdf", dir=source.parent)
    os.close(fd)
    try:
        writer.write(temporary)
        verified = PdfReader(temporary, strict=True)
        if len(verified.pages) != expected_count:
            raise WorkspaceError("A verificação do PDF alterado encontrou uma contagem de páginas inesperada.")
        if os.path.getsize(temporary) > 100 * 1024 * 1024:
            raise WorkspaceError("O PDF de origem excede o limite após a edição.")
        try:
            verified.stream.close()
            reader.stream.close()
            for visual_stream in visual_streams:
                visual_stream.close()
        except Exception:
            pass
        os.replace(temporary, source)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return (
        f"PDF atualizado no mesmo caminho: {relative_path}; {expected_count} página(s) no total, "
        f"{expected_count - original_page_count} página(s) ilustrada(s) inserida(s) após as páginas indicadas. "
        f"Backup do original: {backup_label}."
    )


def _write_pdf_atomic(writer, destination: Path, require_new: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.stem}_", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    try:
        writer.write(temporary)
        if require_new and destination.exists():
            raise WorkspaceError("O arquivo de destino já existe; nenhuma sobrescrita foi feita.")
        os.replace(temporary, destination)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def ocr_pdf(
    manager: WorkspaceManager,
    relative_path: str,
    pages: list[int] | None = None,
    language: str = "por+eng",
    dpi: int = 180,
) -> str:
    """Extrai texto de páginas digitalizadas via PDFium + Tesseract (componentes opcionais)."""
    path = manager.resolve(relative_path, must_exist=True)
    if path.suffix.lower() != ".pdf":
        raise WorkspaceError("OCR aceita somente arquivos PDF.")
    if path.stat().st_size > 150 * 1024 * 1024:
        raise WorkspaceError("PDF acima de 150 MiB; divida o arquivo antes de executar OCR.")
    try:
        dpi = int(dpi)
    except (TypeError, ValueError):
        raise WorkspaceError("DPI inválido. Use um valor entre 100 e 300.")
    if not 100 <= dpi <= 300:
        raise WorkspaceError("DPI fora do limite; use um valor entre 100 e 300.")
    language = str(language or "por+eng").strip().lower()
    if len(language) > 40 or not all(part.isalpha() and len(part) == 3 for part in language.split("+")):
        raise WorkspaceError("Código de idioma inválido. Exemplo: por+eng.")

    try:
        import pypdfium2 as pdfium
    except ImportError as erro:
        raise WorkspaceError("Componente OCR ausente. Selecione OCR para PDFs digitalizados em Configurações > Gerenciar recursos.") from erro
    try:
        import pytesseract
    except ImportError as erro:
        raise WorkspaceError("Biblioteca pytesseract ausente. Instale o componente OCR pelo Gerenciador.") from erro

    executavel = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if not executavel and os.name == "nt":
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
        if base.is_file():
            executavel = str(base)
    if not executavel:
        raise WorkspaceError(
            "O mecanismo Tesseract não foi encontrado. Instale o Tesseract 5.x e os dados de idioma Português/English; "
            "instruções: https://tesseract-ocr.github.io/tessdoc/Installation.html"
        )
    pytesseract.pytesseract.tesseract_cmd = executavel
    try:
        idiomas_disponiveis = set(pytesseract.get_languages(config=""))
    except Exception as erro:
        raise WorkspaceError(f"Não foi possível iniciar o Tesseract: {erro}") from erro
    faltantes = [parte for parte in language.split("+") if parte not in idiomas_disponiveis]
    if faltantes:
        raise WorkspaceError(
            "Dados de idioma ausentes no Tesseract: " + ", ".join(faltantes)
            + ". Instale os arquivos .traineddata correspondentes na pasta tessdata."
        )

    try:
        document = pdfium.PdfDocument(str(path))
    except Exception as erro:
        raise WorkspaceError(f"Não foi possível abrir/renderizar o PDF: {erro}") from erro
    try:
        total_pages = len(document)
        if total_pages == 0:
            raise WorkspaceError("O PDF não contém páginas para reconhecer.")
        if total_pages > 1000:
            raise WorkspaceError("PDF com mais de 1.000 páginas; divida o documento antes do OCR.")
        if pages is None:
            indices = list(range(min(total_pages, 30)))
        else:
            if not isinstance(pages, list) or not pages or len(pages) > 30:
                raise WorkspaceError("Informe de 1 a 30 páginas (numeração começa em 1).")
            if any(type(page) is not int or page < 1 or page > total_pages for page in pages):
                raise WorkspaceError(f"Páginas inválidas. Este PDF possui {total_pages} página(s).")
            indices = list(dict.fromkeys(page - 1 for page in pages))
        resultados: list[str] = []
        caracteres = 0
        for page_number in indices:
            page = None
            bitmap = None
            image = None
            try:
                page = document[page_number]
                escala = dpi / 72.0
                # Evita renderizações gigantes antes de alocar a imagem quando
                # PDFium consegue informar as dimensões vetoriais da página.
                dimensoes = page.get_size() if callable(getattr(page, "get_size", None)) else None
                if dimensoes and len(dimensoes) >= 2:
                    pixels_estimados = int(dimensoes[0] * escala) * int(dimensoes[1] * escala)
                    if pixels_estimados > 25_000_000:
                        raise WorkspaceError(f"A página {page_number + 1} ficaria grande demais em {dpi} DPI; reduza o DPI.")
                bitmap = page.render(scale=escala)
                image = bitmap.to_pil()
                if image.width * image.height > 25_000_000:
                    raise WorkspaceError(f"A página {page_number + 1} gerou uma imagem grande demais; reduza o DPI.")
                texto = str(pytesseract.image_to_string(image, lang=language, config="--psm 3") or "").strip()
                resultados.append(f"[Página {page_number + 1}]\n{texto or '[Nenhum texto reconhecido]'}")
                caracteres += len(texto)
                if caracteres > MAX_DOCUMENT_TEXT:
                    resultados.append("[Resultado truncado para caber no contexto da IA.]")
                    break
            except WorkspaceError:
                raise
            except Exception as erro:
                raise WorkspaceError(f"Falha no OCR da página {page_number + 1}: {erro}") from erro
            finally:
                if image is not None:
                    try: image.close()
                    except Exception: pass
                if bitmap is not None:
                    try: bitmap.close()
                    except Exception: pass
                if page is not None:
                    try: page.close()
                    except Exception: pass
        texto_resultado = "\n\n".join(resultados)
        if pages is None and total_pages > len(indices):
            texto_resultado += f"\n\n[OCR limitado às primeiras {len(indices)} de {total_pages} páginas. Informe pages para outras páginas.]"
        return f"OCR de {relative_path} concluído (idioma {language}, {len(indices)} página(s), {dpi} DPI).\n\n{texto_resultado}"
    finally:
        try: document.close()
        except Exception: pass

def replace_word_text(manager: WorkspaceManager, relative_path: str, replacements: dict[str, str]) -> str:
    path = manager.resolve(relative_path, must_exist=True)
    if path.suffix.lower() != ".docx":
        raise WorkspaceError("A edição estruturada do Word aceita .docx. Converta arquivos .doc antigos para .docx.")
    if not isinstance(replacements, dict) or not replacements:
        raise WorkspaceError("Informe um objeto replacements com texto original e texto novo.")
    try:
        from docx import Document
    except ImportError as erro:
        raise WorkspaceError("Dependência python-docx ausente. Execute preparar.bat.") from erro

    doc = Document(path)
    count = 0

    def process_paragraph(paragraph):
        nonlocal count
        original = paragraph.text
        novo = original
        for old, new in replacements.items():
            if str(old) and str(old) in novo:
                novo = novo.replace(str(old), str(new))
        if novo != original:
            # Reatribuir o texto do parágrafo pode simplificar a formatação interna dos runs.
            paragraph.text = novo
            count += 1

    for paragraph in doc.paragraphs:
        process_paragraph(paragraph)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    process_paragraph(paragraph)
    _save_package_atomic(doc, path)
    return f"Word atualizado: {count} parágrafo(s) alterado(s). Revise a formatação visual antes de distribuir."


def edit_spreadsheet(
    manager: WorkspaceManager,
    relative_path: str,
    sheet_name: str,
    cells: dict[str, Any],
) -> str:
    path = manager.resolve(relative_path, must_exist=True)
    ext = path.suffix.lower()
    if ext not in {".xlsx", ".xlsm"}:
        raise WorkspaceError("A edição de planilhas aceita .xlsx e .xlsm. Arquivos .xls antigos precisam ser convertidos.")
    if not isinstance(cells, dict) or not cells:
        raise WorkspaceError("Informe cells como um objeto, por exemplo {\"A1\": \"Nome\", \"B2\": 10}.")
    try:
        from openpyxl import load_workbook
    except ImportError as erro:
        raise WorkspaceError("Dependência openpyxl ausente. Execute preparar.bat.") from erro

    workbook = load_workbook(path, keep_vba=(ext == ".xlsm"))
    if sheet_name not in workbook.sheetnames:
        workbook.close()
        raise WorkspaceError(f"Planilha '{sheet_name}' não encontrada. Disponíveis: {', '.join(workbook.sheetnames)}")
    sheet = workbook[sheet_name]
    try:
        for address, value in cells.items():
            if not isinstance(address, str) or len(address) > 20:
                raise WorkspaceError(f"Referência de célula inválida: {address!r}")
            sheet[address] = value
        _save_package_atomic(workbook, path)
    finally:
        workbook.close()
    return f"Planilha '{sheet_name}' atualizada: {len(cells)} célula(s) modificada(s)."
