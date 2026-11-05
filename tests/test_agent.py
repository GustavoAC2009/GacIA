from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from agent.commands import parse_command, infer_command
from agent.workspace import WorkspaceManager, WorkspaceError
from agent.tools import ToolExecutor
from agent.documents import read_document, replace_word_text, edit_spreadsheet, create_word_document, create_spreadsheet
from image_generator import _validar_host_local, ImageGenerationError
from agent.orchestrator import AgentOrchestrator
from unittest.mock import Mock, patch


class TestAgentCommands(unittest.TestCase):
    def test_worker_qt_nao_sombrea_path_e_interface_e_qt(self):
        import ast

        source = (Path(__file__).resolve().parents[1] / "interface.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        worker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ChatTask")
        method = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == "run")
        imports_path_locally = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "pathlib"
            and any(alias.name == "Path" for alias in node.names)
            for node in ast.walk(method)
        )
        self.assertFalse(imports_path_locally, "Path não deve ser importado localmente no worker")
        imports_pyside = any(
            isinstance(node, ast.ImportFrom) and node.module == "PySide6.QtWidgets"
            for node in tree.body if isinstance(node, ast.ImportFrom)
        )
        self.assertTrue(imports_pyside, "A interface principal deve ser construída com PySide6")

    def test_parse_commands(self):
        self.assertEqual(parse_command("/analise revise o projeto"), ("analise", "revise o projeto"))
        self.assertEqual(parse_command("/AJUDA"), ("ajuda", ""))
        self.assertEqual(parse_command("/arquivo revise"), (None, "/arquivo revise"))
        self.assertIsNone(parse_command("/pesquisar python")[0])
        self.assertEqual(parse_command("Explique Python"), (None, "Explique Python"))

    def test_ajuda_lista_analise_e_nao_lista_arquivo(self):
        from agent.commands import help_text
        texto = help_text()
        self.assertIn("/analise", texto)
        self.assertNotIn("/arquivo", texto)
        self.assertNotIn("/analisar", texto)

    def test_inferencia_conservadora(self):
        self.assertEqual(infer_command("Analise meu projeto Python"), "analise")
        self.assertEqual(infer_command("Qual é a diferença entre lista e tupla?"), None)
        self.assertEqual(infer_command("Veja isso", has_attachments=True), "analise")
        self.assertEqual(infer_command("Adicione uma opção de exportar", has_workspace=True), "codigo")
        self.assertIsNone(infer_command("Qual é a diferença entre lista e tupla?", has_workspace=True))

    def test_comando_upscale_e_direcionado_para_modelo_neural(self):
        self.assertEqual(parse_command("/upscale imagens/foto.png"), ("upscale", "imagens/foto.png"))
        from agent.commands import help_text
        self.assertIn("/upscale", help_text())
        self.assertIn("super-resolução neural", help_text())

    def test_pedidos_de_criacao_de_documentos_acionam_agente(self):
        exemplos = (
            "Crie uma apresentação PowerPoint sobre redes",
            "Gere um PDF com o relatório",
            "Crie uma planilha de orçamento",
            "Crie um documento Word com a proposta",
        )
        exemplos = exemplos + (
            "Crie um arquivo TXT com um resumo sobre redes",
            "Gere um arquivo de texto com minhas anotações",
            "Crie um arquivo JSON com as configurações",
            "Quero criar ou editar um documento Word (.docx). Estruture e gere o arquivo final.",
            "Quero criar ou editar uma planilha Excel (.xlsx), com fórmulas e gráficos.",
            "Quero criar uma apresentação PowerPoint (.pptx) profissional e editável.",
            "Quero criar, analisar ou editar um arquivo PDF. Gere o arquivo final.",
            "Quero criar ou trabalhar em um e-book EPUB 3, com capítulos e sumário.",
        )
        for pedido in exemplos:
            with self.subTest(pedido=pedido):
                self.assertEqual(infer_command(pedido), "create")

    def test_upscale_natural_com_anexo_ativa_agente(self):
        self.assertEqual(infer_command("Aumente a resolução desta imagem", has_attachments=True), "analise")

    def test_upscale_sem_caminho_detecta_unica_imagem_anexada(self):
        with tempfile.TemporaryDirectory() as temp:
            imagem = Path(temp) / "foto.png"
            imagem.write_bytes(b"imagem-de-teste")
            agente = AgentOrchestrator(Path(temp) / "app")
            resposta = Mock()
            resposta.json.return_value = {"message": {"content": "Arquivo ampliado."}}
            with patch("agent.orchestrator.requests.post", return_value=resposta) as post:
                resultado = agente.execute(
                    prompt="/upscale", attachments=[str(imagem)], model="qwen-test",
                    host="http://127.0.0.1:11434",
                )
            self.assertEqual(resultado, "Arquivo ampliado.")
            payload = post.call_args.kwargs["json"]
            tarefa = payload["messages"][-1]["content"]
            self.assertIn("super-resolução neural", tarefa)
            self.assertIn("foto.png", tarefa)
            self.assertIn("workspace_upscale_image", tarefa)

    def test_upscale_sem_caminho_nao_escolhe_entre_varias_imagens(self):
        with tempfile.TemporaryDirectory() as temp:
            primeira = Path(temp) / "uma.png"
            segunda = Path(temp) / "duas.jpg"
            primeira.write_bytes(b"a")
            segunda.write_bytes(b"b")
            agente = AgentOrchestrator(Path(temp) / "app")
            resposta = agente.execute(
                prompt="/upscale", attachments=[str(primeira), str(segunda)],
                model="qwen-test", host="http://127.0.0.1:11434",
            )
            self.assertIn("mais de uma imagem", resposta)

    def test_upscale_sem_imagem_retorna_instrucao_clara(self):
        with tempfile.TemporaryDirectory() as temp:
            arquivo = Path(temp) / "notas.txt"
            arquivo.write_text("texto", encoding="utf-8")
            agente = AgentOrchestrator(Path(temp) / "app")
            resposta = agente.execute(
                prompt="/upscale", attachments=[str(arquivo)],
                model="qwen-test", host="http://127.0.0.1:11434",
            )
            self.assertIn("Nenhuma imagem compatível", resposta)


class TestWebSearchToolProfiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = WorkspaceManager(Path(self.temp.name))
        self.manager.create_empty("web-test")

    def tearDown(self):
        self.temp.cleanup()

    def test_pesquisa_disponivel_em_todos_os_perfis_com_limites(self):
        import pesquisa_web

        executor_desativado = ToolExecutor(self.manager, web_enabled=False)
        self.assertNotIn(
            "search_web",
            [item["function"]["name"] for item in executor_desativado.definitions],
        )

        for perfil, limite in (("rapido", 2), ("intermediario", 5), ("top", 8)):
            chamadas = {}
            def fake_search(query, max_resultados=None, *, perfil, idioma):
                chamadas.update(
                    query=query, max_resultados=max_resultados,
                    perfil=perfil, idioma=idioma,
                )
                return [{"titulo": "Fonte", "href": "https://example.com", "corpo": "Trecho"}]

            executor = ToolExecutor(
                self.manager, web_enabled=True,
                web_profile=perfil, web_language="en",
            )
            self.assertIn(
                "search_web",
                [item["function"]["name"] for item in executor.definitions],
            )
            with patch.object(pesquisa_web, "pesquisar_web", side_effect=fake_search), \
                 patch.object(pesquisa_web, "formatar_resultados", return_value="fonte"):
                self.assertEqual(executor.dispatch("search_web", {"query": "current topic", "quantity": 99}), "fonte")
            self.assertEqual(chamadas["max_resultados"], limite)
            self.assertEqual(chamadas["perfil"], perfil)
            self.assertEqual(chamadas["idioma"], "en")


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.manager = WorkspaceManager(self.base)

    def tearDown(self):
        self.temp.cleanup()

    def test_importa_zip_ignora_venv_e_lista_arquivos(self):
        arquivo_zip = self.base / "projeto.zip"
        with zipfile.ZipFile(arquivo_zip, "w") as zf:
            zf.writestr("Demo/main.py", "print('ok')")
            zf.writestr("Demo/.venv/Lib/ignored.py", "pass")
        root = self.manager.import_attachments([arquivo_zip])
        self.assertTrue((root / "main.py").exists())
        caminhos = [item["path"] for item in self.manager.list_files()]
        self.assertIn("main.py", caminhos)
        self.assertFalse(any(".venv" in item for item in caminhos))

    def test_bloqueia_zip_slip(self):
        arquivo_zip = self.base / "malicioso.zip"
        with zipfile.ZipFile(arquivo_zip, "w") as zf:
            zf.writestr("../fora.txt", "não escrever")
        with self.assertRaises(WorkspaceError):
            self.manager.import_attachments([arquivo_zip])
        self.assertFalse((self.base / "fora.txt").exists())

    def test_bloqueia_zip_slip_com_barra_invertida_windows(self):
        arquivo_zip = self.base / "malicioso_windows.zip"
        with zipfile.ZipFile(arquivo_zip, "w") as zf:
            zf.writestr(r"..\fora.txt", "não escrever")
        with self.assertRaises(WorkspaceError):
            self.manager.import_attachments([arquivo_zip])

    def test_nao_permite_path_traversal_e_escreve_arquivo(self):
        root = self.manager.create_empty()
        with self.assertRaises(WorkspaceError):
            self.manager.resolve("../segredo.txt")
        self.manager.write_text("src/app.py", "linha 1\nlinha 2\nlinha 3\n")
        self.assertEqual((root / "src" / "app.py").read_text(encoding="utf-8"), "linha 1\nlinha 2\nlinha 3\n")
        self.assertEqual(self.manager.read_text_lines("src/app.py", start_line=2, max_lines=1), "[Linhas 2-2 de 3]\nlinha 2")

    def test_lista_e_exportacao_ignoram_dados_runtime_da_gacia(self):
        root = self.manager.create_empty()
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
        (root / "data" / "workspaces" / "antigo").mkdir(parents=True)
        (root / "data" / "workspaces" / "antigo" / "copia.py").write_text("pass", encoding="utf-8")
        caminhos = [item["path"] for item in self.manager.list_files()]
        self.assertIn("src/app.py", caminhos)
        self.assertFalse(any("workspaces" in item for item in caminhos))
        output = self.manager.export_zip()
        with zipfile.ZipFile(output) as zf:
            self.assertFalse(any("workspaces" in name for name in zf.namelist()))

    def test_backup_automatico_antes_de_substituir_arquivo(self):
        self.manager.create_empty()
        self.manager.write_text("app.py", "versao antiga\n")
        resultado = self.manager.write_text("app.py", "versao nova\n")
        self.assertIn("Backup:", resultado)
        backups = list((self.base / "data" / "backups").rglob("app.py"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "versao antiga\n")
        self.assertEqual(self.manager.read_text("app.py"), "versao nova\n")

    def test_substituicao_exata_nao_altera_quando_ambigua(self):
        self.manager.create_empty()
        self.manager.write_text("app.py", "a = 1\na = 1\n")
        with self.assertRaises(WorkspaceError):
            self.manager.replace_text("app.py", {"a = 1": "a = 2"})
        self.assertEqual(self.manager.read_text("app.py"), "a = 1\na = 1\n")
        self.manager.replace_text("app.py", {"a = 1\na = 1\n": "a = 2\na = 2\n"})
        self.assertEqual(self.manager.read_text("app.py"), "a = 2\na = 2\n")

    def test_exporta_zip_atualizado(self):
        self.manager.create_empty()
        self.manager.write_text("README.md", "Projeto Gac")
        output = self.manager.export_zip()
        self.assertTrue(output.is_file())
        with zipfile.ZipFile(output) as zf:
            self.assertTrue(any(name.endswith("README.md") for name in zf.namelist()))


class TestOfficeDocuments(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.manager = WorkspaceManager(self.base)
        self.root = self.manager.create_empty()

    def tearDown(self):
        self.temp.cleanup()

    def test_cria_word_e_planilha(self):
        word_result = create_word_document(
            self.manager, "relatorio.docx", title="Relatório Gac",
            paragraphs=["Resumo do projeto."],
            tables=[[ ["Item", "Status"], ["Agente", "Implementado"] ]],
        )
        self.assertIn("Documento Word criado", word_result)
        self.assertIn("Agente", read_document(self.manager, "relatorio.docx"))

        excel_result = create_spreadsheet(
            self.manager, "controle.xlsx", sheet_name="Tarefas",
            rows=[["Tarefa", "Concluída"], ["Criar agente", True]],
        )
        self.assertIn("Planilha criada", excel_result)
        texto = read_document(self.manager, "controle.xlsx")
        self.assertIn("Criar agente", texto)

    def test_word_read_and_replace(self):
        from docx import Document
        path = self.root / "texto.docx"
        doc = Document()
        doc.add_paragraph("Olá Gac.IA")
        doc.save(path)
        texto = read_document(self.manager, "texto.docx")
        self.assertIn("Olá Gac.IA", texto)
        resultado = replace_word_text(self.manager, "texto.docx", {"Gac.IA": "Gac Pro"})
        self.assertIn("1 parágrafo", resultado)
        self.assertIn("Gac Pro", read_document(self.manager, "texto.docx"))

    def test_excel_read_and_edit(self):
        from openpyxl import Workbook, load_workbook
        path = self.root / "dados.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Alunos"
        ws["A1"] = "Nome"
        ws["A2"] = "Ana"
        wb.save(path)
        texto = read_document(self.manager, "dados.xlsx")
        self.assertIn("Ana", texto)
        resultado = edit_spreadsheet(self.manager, "dados.xlsx", "Alunos", {"A2": "Gu", "B2": "T.I"})
        self.assertIn("2 célula", resultado)
        check = load_workbook(path, data_only=False)
        self.assertEqual(check["Alunos"]["A2"].value, "Gu")
        self.assertEqual(check["Alunos"]["B2"].value, "T.I")
        check.close()


class TestAgentOrchestrator(unittest.TestCase):
    def test_loop_de_ferramentas_edita_workspace_e_exporta(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            source = base / "main.py"
            source.write_text("print('antigo')\n", encoding="utf-8")
            respostas = [
                {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "workspace_read_file", "arguments": {"path": "main.py"}}}
                ]}},
                {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "workspace_write_file", "arguments": {"path": "main.py", "content": "print('novo')\n"}}}
                ]}},
                {"message": {"role": "assistant", "content": "Alteração concluída e revisada.", "tool_calls": []}},
            ]

            class FakeResponse:
                def __init__(self, data):
                    self.data = data
                def raise_for_status(self):
                    return None
                def json(self):
                    return self.data

            agente = AgentOrchestrator(base)
            with patch("agent.orchestrator.requests.post", side_effect=[FakeResponse(item) for item in respostas]) as post:
                texto = agente.execute(
                    prompt="Modifique main.py", attachments=[str(source)], model="qwen2.5:7b-instruct",
                    host="http://localhost:11434", web_enabled=False,
                )
            self.assertIn("Alteração concluída", texto)
            self.assertIn("Projeto atualizado", texto)
            self.assertEqual(post.call_count, 3)
            workspace = agente.workspaces.current_path()
            self.assertEqual((workspace / "main.py").read_text(encoding="utf-8"), "print('novo')\n")
            self.assertTrue(any((base / "data" / "exports").glob("*.zip")))

    def test_modo_pensar_mais_envia_controle_ollama_e_contexto_limitado(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "leia.txt"
            arquivo.write_text("Conteúdo de teste", encoding="utf-8")

            class FakeResponse:
                def raise_for_status(self):
                    return None
                def json(self):
                    return {"message": {"role": "assistant", "content": "Análise concluída."}}

            with patch("agent.orchestrator.controle_pensamento", return_value={
                "supported": True, "value": "high", "values": ["low", "medium", "high"], "known": True,
            }), patch("agent.orchestrator.requests.post", return_value=FakeResponse()) as post:
                agente = AgentOrchestrator(Path(pasta) / "app")
                resultado = agente.execute(
                    prompt="/analise examine o arquivo", attachments=[str(arquivo)],
                    model="qwen3.5:9b", host="http://127.0.0.1:11434",
                    web_profile="top", thinking_mode=True,
                )
            self.assertIn("Análise concluída", resultado)
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["think"], "high")
            self.assertEqual(payload["options"]["num_ctx"], 8192)
            self.assertIn("MODO PENSAR MAIS ATIVADO", payload["messages"][0]["content"])

    def test_fallback_json_executa_ferramenta_quando_tool_call_nativo_vem_vazio(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            origem = raiz / "origem.txt"
            origem.write_text("material inicial", encoding="utf-8")
            respostas = [
                {"message": {"role": "assistant", "content": "", "tool_calls": []}},
                {"message": {"role": "assistant", "content": __import__("json").dumps({
                    "action": "tool", "tool": "workspace_write_file",
                    "arguments": {"path": "saida.txt", "content": "arquivo criado pela ferramenta\n"},
                })}},
                {"message": {"role": "assistant", "content": __import__("json").dumps({
                    "action": "final", "content": "Arquivo criado e verificado." 
                })}},
            ]

            class FakeResponse:
                def __init__(self, data): self.data = data
                def raise_for_status(self): return None
                def json(self): return self.data

            agente = AgentOrchestrator(raiz / "app")
            with patch("agent.orchestrator.requests.post", side_effect=[FakeResponse(item) for item in respostas]) as post:
                texto = agente.execute(
                    prompt="/analise crie uma cópia em saida.txt", attachments=[str(origem)],
                    model="modelo-sem-tool-calling", host="http://127.0.0.1:11434",
                )
            workspace = agente.workspaces.current_path()
            self.assertEqual((workspace / "saida.txt").read_text(encoding="utf-8"), "arquivo criado pela ferramenta\n")
            self.assertIn("Arquivo criado e verificado", texto)
            self.assertIn("Projeto atualizado", texto)
            self.assertEqual(post.call_count, 3)
            segunda_payload = post.call_args_list[1].kwargs["json"]
            self.assertEqual(segunda_payload["format"], "json")
            self.assertNotIn("tools", segunda_payload)


class TestImageGeneratorValidation(unittest.TestCase):
    def test_only_local_comfyui_is_allowed(self):
        self.assertEqual(_validar_host_local("http://127.0.0.1:8188/"), "http://127.0.0.1:8188")
        with self.assertRaises(ImageGenerationError):
            _validar_host_local("https://example.com")
        with self.assertRaises(ImageGenerationError):
            _validar_host_local("http://192.168.1.20:8188")


if __name__ == "__main__":
    unittest.main()
