"""Testes para não misturar código ativo com dados locais de execução."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import empacotar_distribuicao as empacotador
import preparar_verificar as verificador


class TestVerificadorDeFontes(unittest.TestCase):
    def test_lista_fontes_ativas_sem_copias_de_workspace_ou_runtime(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            (raiz / "main.py").write_text("print('ativo')\n", encoding="utf-8")
            (raiz / "agent").mkdir()
            (raiz / "agent" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
            (raiz / "data" / "workspaces" / "projeto_antigo").mkdir(parents=True)
            (raiz / "data" / "workspaces" / "projeto_antigo" / "broken.py").write_text(
                "isto nao e python !!!\n", encoding="utf-8"
            )
            (raiz / "runtime" / "comfyui").mkdir(parents=True)
            (raiz / "runtime" / "comfyui" / "vendor.py").write_text(
                "isto tambem nao e python !!!\n", encoding="utf-8"
            )
            (raiz / ".venv_backup_20261103" / "Lib").mkdir(parents=True)
            (raiz / ".venv_backup_20261103" / "Lib" / "old.py").write_text(
                "syntax error !!!\n", encoding="utf-8"
            )

            encontrados = verificador.listar_arquivos_python(raiz)
            relativos = {p.relative_to(raiz).as_posix() for p in encontrados}

            self.assertEqual(relativos, {"main.py", "agent/tool.py"})
            self.assertTrue(verificador.verificar_sintaxe(raiz))

    def test_verificacao_de_sintaxe_nao_cria_pycache(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            fonte = raiz / "modulo.py"
            fonte.write_text("valor = 42\n", encoding="utf-8")

            self.assertTrue(verificador.verificar_sintaxe(raiz))
            self.assertFalse((raiz / "__pycache__").exists())


class TestEmpacotador(unittest.TestCase):
    def test_politica_exclui_dados_locais_e_preserva_codigo(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            arquivos = {
                "main.py": "print('app')\n",
                "README.md": "documentacao\n",
                "config.example.json": "{}\n",
                "config.json": "{personalizado}\n",
                ".gacia-components.json": "{\"componentes\":[\"core\"]}\n",
                "gacia.log": "log\n",
                "data/.gitkeep": "",
                "data/memory.db": "database",
                "data/agent_state.json": "{}",
                "data/workspaces/old/app.py": "versao antiga\n",
                "data/generated_images/image.png": "imagem",
                ".venv/Lib/site-packages/vendor.py": "dependencia\n",
                "runtime/comfyui/main.py": "runtime\n",
                "tests/test_app.py": "assert True\n",
            }
            for nome, conteudo in arquivos.items():
                destino = raiz / nome
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(conteudo, encoding="utf-8")

            incluidos = {
                p.relative_to(raiz).as_posix()
                for p in empacotador.listar_arquivos_pacote(raiz)
            }
            self.assertIn("main.py", incluidos)
            self.assertIn("README.md", incluidos)
            self.assertIn("config.example.json", incluidos)
            self.assertIn("tests/test_app.py", incluidos)
            self.assertIn("data/.gitkeep", incluidos)
            self.assertNotIn("config.json", incluidos)
            self.assertNotIn(".gacia-components.json", incluidos)
            self.assertNotIn("data/memory.db", incluidos)
            self.assertNotIn("data/agent_state.json", incluidos)
            self.assertFalse(any("workspaces" in nome for nome in incluidos))
            self.assertFalse(any("generated_images" in nome for nome in incluidos))
            self.assertFalse(any(".venv" in nome for nome in incluidos))
            self.assertFalse(any("runtime" in nome for nome in incluidos))

    def test_cria_zip_com_raiz_padronizada_e_sem_segredos_locais(self):
        with tempfile.TemporaryDirectory() as temporario:
            base = Path(temporario) / "projeto"
            base.mkdir()
            (base / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (base / "config.json").write_text("{nome: privado}\n", encoding="utf-8")
            saida = Path(temporario) / "release.zip"

            destino, quantidade, tamanho = empacotador.criar_pacote(saida, base)

            self.assertEqual(destino, saida)
            self.assertEqual(quantidade, 1)
            self.assertGreater(tamanho, 0)
            with zipfile.ZipFile(saida) as pacote:
                self.assertEqual(pacote.namelist(), ["Gac.IA/main.py"])


if __name__ == "__main__":
    unittest.main()
