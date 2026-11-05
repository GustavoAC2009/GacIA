from __future__ import annotations

import unittest
from agent.commands import infer_command


class TestCommandInference(unittest.TestCase):
    def test_ocr_em_workspace_abre_agente(self):
        self.assertEqual(infer_command("faça OCR neste PDF escaneado", has_workspace=True), "analise")
        self.assertEqual(infer_command("extraia o texto do PDF", has_workspace=True), "analise")

    def test_ocr_sem_workspace_nao_dispara_agente(self):
        self.assertIsNone(infer_command("o que significa OCR?", has_workspace=False))
        self.assertIsNone(infer_command("me explique PDF escaneado"))

    def test_criacao_documental_permanece_deterministica(self):
        self.assertEqual(infer_command("crie um ebook com três capítulos"), "create")
        self.assertEqual(infer_command("gere um e-book PDF profissional sobre Python"), "create")
        self.assertEqual(infer_command("gere uma apresentação sobre redes"), "create")


if __name__ == "__main__":
    unittest.main()
