import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.tools import ToolExecutor
from agent.workspace import WorkspaceManager


class TestGenerationIsolation(unittest.TestCase):
    def test_documentos_de_solicitacoes_diferentes_ficam_em_pastas_separadas(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "app"
            manager = WorkspaceManager(base)
            manager.create_empty("teste")
            first = ToolExecutor(manager)
            second = ToolExecutor(manager)
            result_a = first.workspace_create_word("relatorio.docx", title="Relatório A", paragraphs=["Conteúdo A"])
            result_b = second.workspace_create_word("relatorio.docx", title="Relatório B", paragraphs=["Conteúdo B"])
            folder_a = first.created_outputs[0].parent
            folder_b = second.created_outputs[0].parent
            self.assertNotEqual(folder_a, folder_b)
            self.assertTrue(first.created_outputs[0].is_file())
            self.assertTrue(second.created_outputs[0].is_file())
            self.assertIn("Caminho completo:", result_a)
            self.assertIn("Pasta desta geração:", result_b)
            self.assertFalse(first.project_modified)
            self.assertEqual(list((base / "data" / "exports").glob("*.zip")), [])

    def test_upscale_salva_em_pasta_visual_separada_sem_modificar_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "app"
            manager = WorkspaceManager(base)
            workspace = manager.create_empty("imagens")
            source = workspace / "foto.png"
            source.write_bytes(b"imagem-falsa")
            executor = ToolExecutor(manager)

            def fake_upscale(source_path, output_dir, **kwargs):
                destination = Path(output_dir) / "foto_upscaled.png"
                destination.write_bytes(b"imagem-gerada")
                return destination

            with patch("config.carregar_config", return_value={}), patch("image_generator.upscale_image", side_effect=fake_upscale):
                result = executor.workspace_upscale_image("foto.png")
            self.assertTrue((base / "data" / "generated_images").exists())
            generated = next((base / "data" / "generated_images").rglob("foto_upscaled.png"))
            self.assertTrue(generated.is_file())
            self.assertNotEqual(generated.parent, workspace)
            self.assertIn(str(generated), result)
            self.assertFalse(executor.project_modified)


if __name__ == "__main__":
    unittest.main()
