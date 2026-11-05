from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.documents import ocr_pdf
from agent.tools import ToolExecutor, TOOL_DEFINITIONS
from agent.workspace import WorkspaceManager, WorkspaceError


class _FakeImage:
    width = 180
    height = 180
    def close(self):
        pass


class _FakeBitmap:
    def to_pil(self):
        return _FakeImage()
    def close(self):
        pass


class _FakePage:
    def get_size(self):
        return (72, 72)
    def render(self, scale):
        self.scale = scale
        return _FakeBitmap()
    def close(self):
        pass


class _FakePDF:
    def __init__(self, _path):
        self.pages = [_FakePage(), _FakePage()]
    def __len__(self):
        return len(self.pages)
    def __getitem__(self, index):
        return self.pages[index]
    def close(self):
        pass


class TestOCRPDF(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("ocr")
        (self.root / "scan.pdf").write_bytes(b"pdf mock")

    def tearDown(self):
        self.temp.cleanup()

    def _modules(self, languages=("por", "eng")):
        pdfium = types.ModuleType("pypdfium2")
        pdfium.PdfDocument = _FakePDF
        pytesseract = types.ModuleType("pytesseract")
        pytesseract.pytesseract = types.SimpleNamespace(tesseract_cmd="")
        pytesseract.get_languages = lambda config="": list(languages)
        pytesseract.image_to_string = lambda image, lang, config: "Texto reconhecido de teste"
        return {"pypdfium2": pdfium, "pytesseract": pytesseract}

    def test_ocr_ler_pdf_escaneado_com_ferramentas_mockadas(self):
        with patch.dict(sys.modules, self._modules()), patch("agent.documents.shutil.which", return_value="tesseract"):
            resultado = ocr_pdf(self.manager, "scan.pdf", pages=[2], language="por", dpi=180)
        self.assertIn("OCR de scan.pdf concluído", resultado)
        self.assertIn("[Página 2]", resultado)
        self.assertIn("Texto reconhecido de teste", resultado)

    def test_ocr_informa_dados_de_idioma_ausentes(self):
        with patch.dict(sys.modules, self._modules(languages=("eng",))), patch("agent.documents.shutil.which", return_value="tesseract"):
            with self.assertRaisesRegex(WorkspaceError, "Dados de idioma ausentes"):
                ocr_pdf(self.manager, "scan.pdf", language="por")

    def test_ocr_recusa_dpi_e_paginas_invalidos(self):
        with self.assertRaisesRegex(WorkspaceError, "DPI fora do limite"):
            ocr_pdf(self.manager, "scan.pdf", dpi=600)
        with patch.dict(sys.modules, self._modules()), patch("agent.documents.shutil.which", return_value="tesseract"):
            with self.assertRaisesRegex(WorkspaceError, "Páginas inválidas"):
                ocr_pdf(self.manager, "scan.pdf", pages=[3], language="por")

    def test_tool_de_ocr_esta_registrada_para_o_agente(self):
        self.assertIn("workspace_ocr_pdf", {item["function"]["name"] for item in TOOL_DEFINITIONS})
        executor = ToolExecutor(self.manager)
        with patch("agent.tools.ocr_pdf", return_value="OCR executado") as mocked:
            self.assertEqual(executor.dispatch("workspace_ocr_pdf", {"path": "scan.pdf"}), "OCR executado")
            mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
