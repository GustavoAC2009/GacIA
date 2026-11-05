from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.documents import create_word_document, create_spreadsheet, read_document
from agent.workspace import WorkspaceManager, WorkspaceError


class TestWordAdvanced(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("word")

    def tearDown(self):
        self.temp.cleanup()

    def test_word_a4_estilos_markdown_tabela_cabecalho_e_paginacao(self):
        msg = create_word_document(self.manager, "guia.docx", title="Guia de Tecnologia",
            author="Gac.IA", paragraphs=["# Introdução", "Texto com **negrito**, *itálico* e `código`.",
            "- Primeiro item", "2. Segundo item", "## Conclusão"],
            tables=[[['Recurso', 'Função'], ['CPU', 'Processamento']]])
        self.assertIn("numeração de página", msg)
        from docx import Document
        doc = Document(self.root / "guia.docx")
        self.assertEqual(round(doc.sections[0].page_width / 914400, 2), 8.27)
        self.assertEqual(doc.core_properties.author, "Gac.IA")
        self.assertTrue(any(p.style.name == "Heading 1" and p.text == "Introdução" for p in doc.paragraphs))
        self.assertTrue(any(run.bold for p in doc.paragraphs for run in p.runs))
        self.assertTrue(any(run.italic for p in doc.paragraphs for run in p.runs))
        self.assertEqual(doc.tables[0].cell(1, 0).text, "CPU")
        self.assertIn("Guia de Tecnologia", read_document(self.manager, "guia.docx"))
        self.assertIn("Processamento", read_document(self.manager, "guia.docx"))

    def test_word_recusa_sobrescrita_e_tabela_invalida(self):
        create_word_document(self.manager, "a.docx", title="A")
        with self.assertRaises(WorkspaceError):
            create_word_document(self.manager, "a.docx", title="B")
        with self.assertRaises(WorkspaceError):
            create_word_document(self.manager, "b.docx", tables=[[['x'] * 51]])


class TestSpreadsheetAdvanced(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.root = self.manager.create_empty("excel")

    def tearDown(self):
        self.temp.cleanup()

    def test_multiplas_abas_tabelas_e_grafico(self):
        mensagem = create_spreadsheet(self.manager, "relatorio.xlsx", sheet_name="Vendas",
            rows=[["Mês", "Receita"], ["Jan", 100], ["Fev", 140], ["Mar", 160]],
            additional_sheets=[{"name": "Custos", "rows": [["Categoria", "Valor"], ["Pessoal", 50], ["Infra", 30]]}],
            charts=[{"sheet_name": "Vendas", "type": "bar", "title": "Receita mensal",
                     "data_ref": "B1:B4", "categories_ref": "A2:A4", "anchor": "D2"}])
        self.assertIn("2 aba(s), 1 gráfico(s)", mensagem)
        from openpyxl import load_workbook
        workbook = load_workbook(self.root / "relatorio.xlsx")
        self.assertEqual(workbook.sheetnames, ["Vendas", "Custos"])
        self.assertEqual(workbook["Vendas"].freeze_panes, "A2")
        self.assertEqual(len(workbook["Vendas"]._charts), 1)
        self.assertEqual(workbook["Vendas"]["B3"].value, 140)
        self.assertEqual(len(workbook["Vendas"].tables), 1)
        workbook.close()
        self.assertIn("Receita", read_document(self.manager, "relatorio.xlsx"))

    def test_planilha_recusa_abas_duplicadas_e_intervalos_invalidos(self):
        with self.assertRaisesRegex(WorkspaceError, "duplicado"):
            create_spreadsheet(self.manager, "dupe.xlsx", rows=[["A"]], additional_sheets=[{"name": "Planilha1", "rows": [["B"]]}])
        with self.assertRaisesRegex(WorkspaceError, "Intervalos do gráfico"):
            create_spreadsheet(self.manager, "bad.xlsx", rows=[["Mês", "Valor"], ["Jan", 1]],
                charts=[{"type": "line", "data_ref": "B1:B20", "categories_ref": "A2:A20"}])


if __name__ == "__main__":
    unittest.main()
