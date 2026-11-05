from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pypdf import PdfReader

from agent.ebook_pdf import create_ebook_pdf
from agent.ebooks import create_ebook as create_epub
from agent.tools import ToolExecutor, TOOL_DEFINITIONS
from agent.workspace import WorkspaceManager, WorkspaceError


class TestEbookPDF(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("ebooks")

    def tearDown(self):
        self.temp.cleanup()

    def test_cria_pdf_editorial_com_sumario_capitulos_e_metadados(self):
        message = create_ebook_pdf(
            self.manager, "guia.pdf", title="Guia de T.I.", author="Gu",
            subtitle="Do básico à prática", description="Um guia de demonstração.",
            keywords="tecnologia, Python",
            chapters=[
                {"title": "Introdução", "content": "# Começando\n\nEste é um **guia** em português.\n\n- Item A\n- Item B"},
                {"title": "Prática", "content": "## Código\n\nUse `Python` para automatizar.\n\n> Uma observação importante."},
            ],
        )
        self.assertIn("E-book PDF profissional criado", message)
        path = self.root / "guia.pdf"
        self.assertTrue(path.is_file())
        reader = PdfReader(str(path), strict=True)
        self.assertGreaterEqual(len(reader.pages), 5)
        self.assertEqual(reader.metadata.title, "Guia de T.I.")
        self.assertEqual(reader.metadata.author, "Gu")
        self.assertTrue(reader.outline)
        outline_titles = [item.get("/Title") for item in reader.outline if isinstance(item, dict)]
        self.assertIn("Introdução", outline_titles)
        self.assertNotIn("Sobre este e-book", outline_titles)
        self.assertGreater(sum(len(page.get("/Annots") or []) for page in reader.pages), 0)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        for expected in ("Guia de T.I.", "Sumário", "Introdução", "Prática", "Item A", "Python"):
            self.assertIn(expected, text)

    def test_tool_ebook_padrao_forca_pdf_mesmo_se_modelo_pedir_epub(self):
        executor = ToolExecutor(self.manager)
        response = executor.dispatch("workspace_create_ebook", {
            "path": "livro.epub", "title": "Livro",
            "chapters": [{"title": "Capítulo 1", "content": "Texto do capítulo."}],
        })
        self.assertIn("E-book PDF profissional criado", response)
        self.assertEqual(len(executor.created_outputs), 1)
        generated = executor.created_outputs[0]
        self.assertTrue(generated.is_file())
        self.assertEqual(generated.suffix, ".pdf")
        self.assertTrue(PdfReader(str(generated)).pages)
        names = {item["function"]["name"] for item in TOOL_DEFINITIONS}
        self.assertIn("workspace_create_ebook", names)
        self.assertIn("workspace_create_epub", names)

    def test_epub_continua_disponivel_somente_na_ferramenta_especifica(self):
        executor = ToolExecutor(self.manager)
        response = executor.dispatch("workspace_create_epub", {
            "path": "livro.pdf", "title": "Livro refluível",
            "chapters": [{"title": "Capítulo 1", "content": "Texto."}],
        })
        self.assertIn("EPUB 3 criado", response)
        self.assertEqual(executor.created_outputs[0].suffix, ".epub")
        with zipfile.ZipFile(executor.created_outputs[0]) as epub:
            self.assertEqual(epub.namelist()[0], "mimetype")
            self.assertEqual(epub.read("mimetype"), b"application/epub+zip")

    def test_capa_webp_ou_png_e_imagem_de_capitulo_sao_processadas(self):
        from PIL import Image
        cover = self.root / "capa.webp"
        chapter_image = self.root / "capitulo.png"
        Image.new("RGB", (500, 700), "#2563EB").save(cover, "WEBP")
        Image.new("RGB", (800, 450), "#16A34A").save(chapter_image, "PNG")
        create_ebook_pdf(
            self.manager, "ilustrado.pdf", "Livro ilustrado",
            [{"title": "Capítulo visual", "content": "Texto antes da imagem.",
              "image_path": "capitulo.png", "image_caption": "Figura 1 - Ilustração."}],
            cover_path="capa.webp",
        )
        reader = PdfReader(str(self.root / "ilustrado.pdf"), strict=True)
        self.assertGreaterEqual(len(reader.pages), 4)
        self.assertTrue(any(getattr(page, "images", []) for page in reader.pages))

    def test_nao_sobrescreve_arquivo_existente_e_rejeita_entrada_invalida(self):
        create_ebook_pdf(self.manager, "livro.pdf", "Livro", [{"title": "Capítulo", "content": "A"}])
        with self.assertRaises(WorkspaceError):
            create_ebook_pdf(self.manager, "livro.pdf", "Outro", [{"title": "Capítulo", "content": "B"}])
        with self.assertRaises(WorkspaceError):
            create_ebook_pdf(self.manager, "vazio.pdf", "", [{"title": "A", "content": "x"}])
        with self.assertRaises(WorkspaceError):
            create_ebook_pdf(self.manager, "sem-capitulos.pdf", "Livro", [])
        with self.assertRaises(WorkspaceError):
            create_ebook_pdf(self.manager, "extensao.epub", "Livro", [{"title": "A", "content": "x"}])


if __name__ == "__main__":
    unittest.main()
