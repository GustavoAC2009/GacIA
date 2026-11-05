from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.documents import (
    create_powerpoint,
    edit_powerpoint,
    create_pdf_document,
    manage_pdf,
    read_document,
)
from agent.tools import ToolExecutor, TOOL_DEFINITIONS
from agent.workspace import WorkspaceManager, WorkspaceError


class TestPowerPointAdvanced(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("pptx")

    def tearDown(self):
        self.temp.cleanup()

    def test_cria_apresentacao_com_texto_tabela_e_notas(self):
        result = create_powerpoint(
            self.manager,
            "apresentacao.pptx",
            title="Tecnologia",
            slides=[
                {"layout": "title", "title": "Tecnologia", "subtitle": "Visão geral", "notes": "Introdução"},
                {
                    "title": "Componentes",
                    "content": ["Processador", "Memória"],
                    "table": [["Item", "Exemplo"], ["CPU", "Ryzen"]],
                },
            ],
        )
        self.assertIn("2 slides", result)
        self.assertIn("Visão geral", read_document(self.manager, "apresentacao.pptx"))
        self.assertIn("Ryzen", read_document(self.manager, "apresentacao.pptx"))
        from pptx import Presentation
        presentation = Presentation(self.root / "apresentacao.pptx")
        self.assertEqual(len(presentation.slides), 2)
        self.assertEqual(presentation.slides[0].notes_slide.notes_text_frame.text, "Introdução")

    def test_imagens_webp_sao_convertidas_para_formato_compativel_com_pptx(self):
        from PIL import Image
        from pptx import Presentation
        image_path = self.root / "imagem.webp"
        Image.new("RGB", (640, 360), (40, 90, 160)).save(image_path, format="WEBP")
        create_powerpoint(
            self.manager, "com-imagem.pptx", title="Apresentação com imagem",
            slides=[
                {"layout": "cover", "title": "Capa", "image_path": "imagem.webp"},
                {"layout": "content", "title": "Conteúdo", "content": ["Texto"]},
            ],
        )
        presentation = Presentation(self.root / "com-imagem.pptx")
        pictures = [shape for shape in presentation.slides[0].shapes if getattr(shape, "shape_type", None) == 13]
        self.assertEqual(len(pictures), 1)
        self.assertEqual(pictures[0].image.ext, "png")

    def test_edita_texto_e_acrescenta_slide_com_backup_pelo_executor(self):
        create_powerpoint(
            self.manager, "apresentacao.pptx", title="Demo",
            slides=[{"title": "Título", "content": ["Versão antiga"]}],
        )
        executor = ToolExecutor(self.manager)
        result = executor.dispatch(
            "workspace_edit_powerpoint",
            {
                "path": "apresentacao.pptx",
                "replacements": {"Versão antiga": "Versão nova"},
                "append_slides": [{"title": "Conclusão", "content": ["Final"]}],
            },
        )
        self.assertIn("1 trecho(s) substituído(s)", result)
        texto = read_document(self.manager, "apresentacao.pptx")
        self.assertIn("Versão nova", texto)
        self.assertIn("Conclusão", texto)
        backups = list((self.manager.base_dir / "data" / "backups").rglob("apresentacao.pptx"))
        self.assertEqual(len(backups), 1)

    def test_nao_sobrescreve_apresentacao(self):
        create_powerpoint(self.manager, "a.pptx", slides=[{"title": "A"}])
        with self.assertRaises(WorkspaceError):
            create_powerpoint(self.manager, "a.pptx", slides=[{"title": "B"}])
        self.assertIn("A", read_document(self.manager, "a.pptx"))

    def test_nove_layouts_e_temas_sao_gerados_em_arquivo_editavel(self):
        slides = [
            {"layout": "cover", "title": "Capa", "subtitle": "Subtítulo"},
            {"layout": "content", "title": "Conteúdo", "content": ["Ponto um", "Ponto dois"]},
            {"layout": "section", "title": "Seção", "subtitle": "Divisão"},
            {"layout": "two_column", "title": "Duas colunas", "left": ["Esquerda"], "right": ["Direita"]},
            {"layout": "quote", "title": "Citação", "quote": "Texto citado", "attribution": "Autoria"},
            {"layout": "metrics", "title": "Indicadores", "metrics": [{"value": "98%", "label": "Disponibilidade"}]},
            {"layout": "image", "title": "Imagem", "content": ["Legenda"], "subtitle": "Contexto"},
            {"layout": "table", "title": "Tabela", "table": [["Item", "Valor"], ["CPU", "Ryzen"]]},
            {"layout": "closing", "title": "Encerramento", "subtitle": "Obrigado"},
        ]
        result = create_powerpoint(self.manager, "layouts.pptx", title="Teste visual", slides=slides, theme="creative")
        self.assertIn("9 slides", result)
        from pptx import Presentation
        presentation = Presentation(self.root / "layouts.pptx")
        self.assertEqual(len(presentation.slides), 9)
        self.assertEqual(presentation.core_properties.subject, "Apresentação criada pela Gac.IA · tema creative")
        textos = [shape.text for slide in presentation.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False)]
        textos.extend(cell.text for slide in presentation.slides for shape in slide.shapes
                      if getattr(shape, "has_table", False) for row in shape.table.rows for cell in row.cells)
        extracted = "\n".join(textos)
        for expected in ("Capa", "Ponto um", "Seção", "Esquerda", "Texto citado", "98%", "Legenda", "Ryzen", "Encerramento"):
            self.assertIn(expected, extracted)


class TestPDFAdvanced(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("pdf")

    def tearDown(self):
        self.temp.cleanup()

    def test_cria_pdf_com_texto_e_tabela_legiveis(self):
        result = create_pdf_document(
            self.manager,
            "relatorio.pdf",
            title="Relatório técnico",
            paragraphs=["Olá, relatório de T.I.", "Segunda seção com conteúdo."],
            tables=[[['Item', 'Valor'], ['Processador', 'Ryzen 5']]],
        )
        self.assertIn("PDF criado", result)
        texto = read_document(self.manager, "relatorio.pdf")
        self.assertIn("Relatório técnico", texto)
        self.assertIn("Processador", texto)
        self.assertIn("Ryzen 5", texto)

    def test_mescla_extrai_gira_e_atualiza_metadados(self):
        create_pdf_document(self.manager, "um.pdf", title="Um", paragraphs=["Página um"])
        create_pdf_document(self.manager, "dois.pdf", title="Dois", paragraphs=["Página dois"])
        merge_result = manage_pdf(
            self.manager, "final.pdf", action="merge", source_paths=["um.pdf", "dois.pdf"]
        )
        self.assertIn("2 arquivo(s), 2 página(s)", merge_result)
        extract_result = manage_pdf(
            self.manager, "final.pdf", action="extract_pages", pages=[2], output_path="pagina2.pdf"
        )
        self.assertIn("pagina2.pdf", extract_result)
        from pypdf import PdfReader
        self.assertEqual(len(PdfReader(self.root / "pagina2.pdf").pages), 1)

        executor = ToolExecutor(self.manager)
        rotation = executor.dispatch(
            "workspace_manage_pdf", {"path": "final.pdf", "action": "rotate", "pages": [1], "rotation": 90}
        )
        self.assertIn("rotação de 90°", rotation)
        metadata = executor.dispatch(
            "workspace_manage_pdf", {"path": "final.pdf", "action": "metadata", "metadata": {"title": "Final Gac"}}
        )
        self.assertIn("Metadados", metadata)
        reader = PdfReader(self.root / "final.pdf")
        self.assertEqual(reader.metadata.title, "Final Gac")
        self.assertEqual(reader.pages[0].rotation, 90)
        backups = list((self.manager.base_dir / "data" / "backups").rglob("final.pdf"))
        self.assertEqual(len(backups), 2)

    def test_rejeita_paginas_invalidas_e_traversal(self):
        create_pdf_document(self.manager, "origem.pdf", title="Origem", paragraphs=["Texto"])
        with self.assertRaises(WorkspaceError):
            manage_pdf(self.manager, "origem.pdf", action="extract_pages", pages=[99], output_path="x.pdf")
        with self.assertRaises(WorkspaceError):
            manage_pdf(self.manager, "origem.pdf", action="extract_pages", pages=[1], output_path="../fora.pdf")
        self.assertFalse((self.manager.base_dir / "fora.pdf").exists())

    def test_nao_sobrescreve_pdf_existente(self):
        create_pdf_document(self.manager, "existente.pdf", title="Original")
        with self.assertRaises(WorkspaceError):
            create_pdf_document(self.manager, "existente.pdf", title="Novo")
        self.assertIn("Original", read_document(self.manager, "existente.pdf"))


class TestOfficeToolsRegistration(unittest.TestCase):
    def test_novas_ferramentas_estao_registradas(self):
        names = {item["function"]["name"] for item in TOOL_DEFINITIONS}
        self.assertTrue({
            "workspace_create_powerpoint", "workspace_edit_powerpoint",
            "workspace_create_pdf", "workspace_manage_pdf", "workspace_upscale_image",
            "workspace_create_ebook", "workspace_ocr_pdf",
        }.issubset(names))
        read_tool = next(item for item in TOOL_DEFINITIONS
                         if item["function"]["name"] == "workspace_read_document")
        self.assertIn("EPUB", read_tool["function"]["description"])


if __name__ == "__main__":
    unittest.main()
