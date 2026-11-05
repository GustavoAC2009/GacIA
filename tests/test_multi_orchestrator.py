import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent.multi_orchestrator import (
    MultiAgentCoordinator, dispatch_readonly_batch,
    is_presentation_creation_request, normalize_presentation_plan,
    requested_slide_count, _primary_visual_anchors,
)
from agent.workspace import WorkspaceManager
from agent.tools import ToolExecutor


class TestMultiOrchestrator(unittest.TestCase):
    def test_detecta_criacao_natural_e_prompt_do_menu(self):
        self.assertTrue(is_presentation_creation_request("Crie uma apresentação sobre redes de computadores"))
        self.assertTrue(is_presentation_creation_request("Quero criar uma apresentação PowerPoint (.pptx). Pedido: segurança de redes"))
        self.assertTrue(is_presentation_creation_request("Gere 10 slides sobre banco de dados"))

    def test_nao_confunde_edicao_de_apresentacao_existente(self):
        self.assertFalse(is_presentation_creation_request("Edite os slides da apresentação anexada"))

    def test_contagem_de_slides_respeita_intervalo(self):
        self.assertEqual(requested_slide_count("Crie 12 slides sobre Python"), 12)
        self.assertEqual(requested_slide_count("Crie 40 slides"), 20)
        self.assertEqual(requested_slide_count("Crie slides"), 8)

    def test_apresentacoes_usam_imagens_por_padrao_e_respeitam_pedido_sem_imagens(self):
        coordinator = MultiAgentCoordinator(Mock(), Mock(), "modelo", "http://127.0.0.1:11434")
        self.assertEqual(coordinator._visual_policy("Crie slides sobre redes", False), (True, True, "auto"))
        self.assertEqual(coordinator._visual_policy("Crie slides sem imagens", True), (False, True, "auto"))
        self.assertEqual(coordinator._visual_policy("Crie slides com fotos da internet", False), (True, True, "commons"))

    def test_normaliza_plano_e_garante_capa_e_encerramento(self):
        plan = normalize_presentation_plan({
            "title": "Redes",
            "theme": "nao-existe",
            "slides": [
                {"layout": "content", "title": "Introdução", "content": "A;B"},
                {"layout": "errado", "title": "Camadas", "content": ["TCP/IP"]},
                {"layout": "content", "title": "Conclusão", "content": ["Resumo"]},
            ],
        }, requested_count=8)
        self.assertEqual(plan["theme"], "modern")
        self.assertEqual(plan["slides"][0]["layout"], "cover")
        self.assertEqual(plan["slides"][-1]["layout"], "closing")
        self.assertEqual(plan["slides"][1]["layout"], "content")

    def test_imagem_so_e_inserida_se_estiver_no_workspace(self):
        plan = normalize_presentation_plan({
            "title": "Álbum",
            "slides": [
                {"layout": "cover", "title": "Álbum"},
                {"layout": "image", "title": "Foto válida", "image_path": "imagens/foto.png"},
                {"layout": "image", "title": "Foto inventada", "image_path": "C:/fora/foto.png"},
                {"layout": "closing", "title": "Fim"},
            ],
        }, requested_count=8, available_images={"imagens/foto.png"})
        self.assertEqual(plan["slides"][1].get("image_path"), "imagens/foto.png")
        self.assertEqual(plan["slides"][2]["layout"], "content")
        self.assertNotIn("image_path", plan["slides"][2])

    def test_normalizacao_rejeita_plano_sem_slides(self):
        with self.assertRaises(ValueError):
            normalize_presentation_plan({"title": "Vazio", "slides": []})

    def test_insere_imagens_do_commons_com_credito_nas_notas(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = WorkspaceManager(Path(temp) / "app")
            manager.create_empty("slides")
            executor = ToolExecutor(manager)
            output_dir = executor.start_output_session("apresentacao")
            asset_dir = output_dir / "recursos_visuais"
            asset_dir.mkdir(parents=True)
            image = asset_dir / "commons_rede.png"
            image.write_bytes(b"imagem-de-teste")
            coordinator = MultiAgentCoordinator(manager, executor, "modelo", "http://127.0.0.1:11434")
            plan = {"title": "Redes", "slides": [
                {"layout": "cover", "title": "Redes", "content": []},
                {"layout": "content", "title": "Topologia", "content": ["Estrela"], "image_source": "none"},
                {"layout": "closing", "title": "Fim", "content": []},
            ]}
            result = [{"path": str(image), "title": "File:rede.png", "artist": "Autor",
                       "license": "CC BY-SA 4.0", "description_url": "https://commons.wikimedia.org/wiki/File:rede.png"}]
            safe_briefs = [
                {"query_en": "computer networks star topology", "prompt_en": "Computer networks, star topology", "negative_prompt_en": "text"},
                {"query_en": "computer networks", "prompt_en": "Computer networks", "negative_prompt_en": "text"},
            ]
            with patch.object(coordinator, "_translate_visual_briefs", return_value=safe_briefs), \
                 patch("agent.media_assets.search_commons_images", return_value=result) as search_images:
                count, notes = coordinator._add_presentation_visuals(
                    plan, "Crie slides sobre redes", output_dir=output_dir,
                    allow_commons=True, preference="auto",
                )
            self.assertGreaterEqual(count, 1)
            self.assertTrue(plan["slides"][0]["image_path"].startswith("@output/"))
            self.assertIn("CC BY-SA 4.0", plan["slides"][0]["image_credit"])
            self.assertIn("CC BY-SA 4.0", plan["slides"][0]["notes"])
            credits = asset_dir / "CREDITOS_E_LICENCAS.txt"
            self.assertTrue(credits.is_file())
            self.assertIn("Autor", credits.read_text(encoding="utf-8"))
            self.assertIn("Alteração:", credits.read_text(encoding="utf-8"))
            self.assertTrue(notes)
            self.assertEqual(search_images.call_args.kwargs.get("required_terms"), ["redes"])

    def test_insere_imagem_gerada_localmente_e_guarda_na_pasta_da_apresentacao(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = WorkspaceManager(Path(temp) / "app")
            manager.create_empty("slides")
            executor = ToolExecutor(manager)
            output_dir = executor.start_output_session("apresentacao")
            coordinator = MultiAgentCoordinator(manager, executor, "modelo", "http://127.0.0.1:11434")
            plan = {"title": "Redes", "slides": [
                {"layout": "cover", "title": "Redes", "content": []},
                {"layout": "content", "title": "Topologia", "content": ["Estrela"], "image_source": "none"},
                {"layout": "closing", "title": "Fim", "content": []},
            ]}
            generated = output_dir / "recursos_visuais" / "rede.png"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"imagem-local")
            safe_briefs = [
                {"query_en": "computer networks star topology", "prompt_en": "Computer networks, star topology", "negative_prompt_en": "text"},
                {"query_en": "computer networks", "prompt_en": "Computer networks", "negative_prompt_en": "text"},
            ]
            with patch.object(coordinator, "_translate_visual_briefs", return_value=safe_briefs), \
                 patch.object(coordinator, "_unload_ollama_model_for_visuals", return_value=True), \
                 patch.object(coordinator, "_prepare_gpu_for_local_visuals", return_value=(True, "GPU livre")), \
                 patch("image_generator.liberar_memoria_comfyui", return_value=(True, "liberado")), \
                 patch.object(coordinator, "_generate_local_visual", return_value=generated) as generate:
                count, notes = coordinator._add_presentation_visuals(
                    plan, "Crie slides com imagens geradas por IA", output_dir=output_dir,
                    allow_commons=False, preference="generated",
                )
            self.assertGreaterEqual(count, 1)
            self.assertEqual(plan["slides"][0]["image_source"], "generated")
            self.assertTrue(plan["slides"][0]["image_path"].startswith("@output/"))
            self.assertTrue(notes)
            generate.assert_called_once()
            self.assertFalse(generate.call_args.kwargs.get("reuse_loaded_model"))

    def test_ancoras_ignoram_cortesia_e_instrucoes_comuns_em_portugues(self):
        self.assertEqual(
            _primary_visual_anchors("Por favor, pode criar uma apresentação bonita sobre Minecraft com shaders?")[:2],
            ["minecraft", "shaders"],
        )
        self.assertEqual(
            _primary_visual_anchors("Gostaria de slides sobre redes de computadores")[:2],
            ["redes", "computadores"],
        )

    def test_extrai_ancora_principal_e_descarta_hint_de_outro_assunto(self):
        self.assertEqual(_primary_visual_anchors("Crie slides sobre Minecraft com shaders")[:2], ["minecraft", "shaders"])
        coordinator = MultiAgentCoordinator(Mock(), Mock(), "modelo", "http://127.0.0.1:11434")
        plan = {"title": "Minecraft com shaders", "slides": [{
            "title": "Iluminação e reflexos", "content": ["Shaders melhoram a iluminação do jogo"],
            "image_query": "syphilis medical rash", "image_prompt": "Clinical image of syphilis",
        }]}
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"message": {"content": __import__("json").dumps({
            "topic_en": "Minecraft shaders",
            "slides": [{"index": 0, "query_en": "Minecraft shader gameplay screenshot",
                        "prompt_en": "A Minecraft gameplay screenshot with realistic shaders and reflections",
                        "negative_prompt_en": "text, watermark"}],
        })}}
        with patch("agent.multi_orchestrator.requests.post", return_value=fake_response) as post:
            result = coordinator._translate_visual_briefs("Crie slides sobre Minecraft com shaders", plan, plan["slides"])
        self.assertIn("Minecraft", result[0]["query_en"])
        self.assertIn("Minecraft", result[0]["prompt_en"])
        request_text = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("syphilis", request_text.casefold())
        self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], coordinator.keep_alive)

    def test_multiorquestrador_gera_imagens_em_sequencia_e_no_maximo_duas(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = WorkspaceManager(Path(temp) / "app")
            manager.create_empty("slides")
            executor = ToolExecutor(manager)
            output_dir = executor.start_output_session("apresentacao")
            coordinator = MultiAgentCoordinator(manager, executor, "modelo", "http://127.0.0.1:11434")
            slides = [
                {"layout": "cover", "title": "Minecraft", "content": []},
                {"layout": "content", "title": "Shaders", "content": ["Iluminação"]},
                {"layout": "content", "title": "Reflexos", "content": ["Água"]},
                {"layout": "closing", "title": "Fim", "content": []},
            ]
            plan = {"title": "Minecraft com shaders", "slides": slides}
            briefs = [{"query_en": "Minecraft shaders", "prompt_en": "Minecraft with shaders", "negative_prompt_en": "text"} for _ in range(3)]
            generated_paths = []
            for i in range(2):
                path = output_dir / "recursos_visuais" / f"minecraft_{i}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"image")
                generated_paths.append(path)
            calls = []
            with patch.object(coordinator, "_translate_visual_briefs", return_value=briefs), \
                 patch.object(coordinator, "_unload_ollama_model_for_visuals", return_value=True), \
                 patch.object(coordinator, "_prepare_gpu_for_local_visuals", return_value=(True, "GPU livre")), \
                 patch("image_generator.liberar_memoria_comfyui", return_value=(True, "liberado")), \
                 patch.object(coordinator, "_generate_local_visual", side_effect=generated_paths) as generate:
                count, _ = coordinator._add_presentation_visuals(
                    plan, "Crie slides sobre Minecraft com shaders", output_dir=output_dir,
                    allow_commons=False, preference="generated",
                )
            self.assertEqual(count, 2)
            self.assertEqual(generate.call_count, 2)
            self.assertEqual([call.kwargs["reuse_loaded_model"] for call in generate.call_args_list], [False, True])

    def test_batch_paraleliza_somente_leituras_locais(self):
        executor = Mock()
        executor.dispatch.side_effect = ["um", "dois"]
        calls = [
            {"function": {"name": "workspace_read_file", "arguments": {"path": "a.txt"}}},
            {"function": {"name": "workspace_list_files", "arguments": {}}},
        ]
        results = dispatch_readonly_batch(executor, calls)
        self.assertEqual(results, {0: "um", 1: "dois"})
        self.assertEqual(executor.dispatch.call_count, 2)

    def test_batch_nao_paraleliza_escrita_ou_web(self):
        executor = Mock()
        calls = [
            {"function": {"name": "workspace_read_file", "arguments": {"path": "a.txt"}}},
            {"function": {"name": "workspace_write_file", "arguments": {"path": "b.txt", "content": "x"}}},
        ]
        self.assertEqual(dispatch_readonly_batch(executor, calls), {})
        executor.dispatch.assert_not_called()


    def test_agent_orchestrator_encaminha_slide_para_rota_deterministica(self):
        import json
        from agent.orchestrator import AgentOrchestrator
        with tempfile.TemporaryDirectory() as temp:
            agent = AgentOrchestrator(Path(temp) / "app")
            payload = {
                "title": "Segurança de Redes",
                "theme": "modern",
                "slides": [
                    {"layout": "cover", "title": "Segurança de Redes", "subtitle": "Fundamentos", "content": []},
                    {"layout": "content", "title": "Ameaças", "content": ["Malware", "Phishing"]},
                    {"layout": "closing", "title": "Conclusão", "content": ["Prevenção é essencial"]},
                ],
            }
            response = Mock()
            response.json.return_value = {"message": {"content": json.dumps(payload)}}
            with patch("agent.multi_orchestrator.requests.post", return_value=response) as post, \
                 patch("agent.multi_orchestrator.MultiAgentCoordinator._add_presentation_visuals", return_value=(0, [])):
                result = agent.execute(
                    prompt="Crie uma apresentação PowerPoint sobre segurança de redes",
                    attachments=[], model="modelo-teste", host="http://127.0.0.1:11434",
                )
            self.assertIn("3 slides", result)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.kwargs["json"]["format"], "json")
            self.assertIn("Verificação", result)

    def test_fluxo_especializado_cria_e_reabre_pptx(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = WorkspaceManager(Path(temp) / "app")
            manager.create_empty("slides")
            executor = ToolExecutor(manager)
            model_plan = {
                "title": "Fundamentos de Redes",
                "theme": "modern",
                "slides": [
                    {"layout": "cover", "title": "Fundamentos de Redes", "subtitle": "Conceitos essenciais", "content": []},
                    {"layout": "content", "title": "O que é uma rede?", "content": ["Dispositivos conectados", "Troca de dados por protocolos"]},
                    {"layout": "closing", "title": "Conclusão", "content": ["Redes conectam sistemas e pessoas"]},
                ],
            }
            response = Mock()
            response.json.return_value = {"message": {"content": __import__("json").dumps(model_plan)}}
            with patch("agent.multi_orchestrator.requests.post", return_value=response):
                coordinator = MultiAgentCoordinator(manager, executor, "modelo-teste", "http://127.0.0.1:11434")
                with patch.object(coordinator, "_add_presentation_visuals", return_value=(0, [])):
                    result = coordinator.create_presentation("Crie slides sobre redes")
            self.assertIn("3 slides", result)
            pptx_files = [path for path in executor.created_outputs if path.suffix.lower() == ".pptx"]
            self.assertEqual(len(pptx_files), 1)
            self.assertTrue(pptx_files[0].is_file())
            self.assertIn("data/exports", pptx_files[0].as_posix())

