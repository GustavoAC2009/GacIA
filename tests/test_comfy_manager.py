from __future__ import annotations
import unittest
from unittest.mock import patch
import comfy_manager
from agent.commands import parse_command, COMMAND_MAP


class TestComfyManager(unittest.TestCase):
    def test_desktop_oficial_e_recomendado_para_nvidia(self):
        info = {"ram_gb": 16, "gpus": [{"vendor": "NVIDIA", "name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288}]}
        with patch.object(comfy_manager.platform, "system", return_value="Windows"):
            rec = comfy_manager.recomendar_pacote(info)
        self.assertTrue(rec["supported"])
        self.assertEqual(rec["method"], "desktop")
        self.assertIn("comfy.org/download", rec["url"])
        self.assertIn("NVIDIA", rec["variant"])
        self.assertEqual(comfy_manager.recomendar_parametros(info)["width"], 768)

    def test_desktop_oficial_e_recomendado_para_amd_e_intel(self):
        for vendor in ("AMD", "Intel"):
            info = {"ram_gb": 16, "gpus": [{"vendor": vendor, "name": vendor + " GPU", "vram_mb": 8192}]}
            with patch.object(comfy_manager.platform, "system", return_value="Windows"):
                rec = comfy_manager.recomendar_pacote(info)
            self.assertTrue(rec["supported"])
            self.assertEqual(rec["method"], "desktop")
            self.assertIn(vendor, rec["variant"])

    def test_desktop_nao_bloqueia_download_por_ram_baixa(self):
        info = {"ram_gb": 6, "gpus": [{"vendor": "NVIDIA", "name": "RTX 3060", "vram_mb": 12288}]}
        with patch.object(comfy_manager.platform, "system", return_value="Windows"):
            rec = comfy_manager.recomendar_pacote(info)
        self.assertTrue(rec["supported"])
        self.assertIn("depende", rec["reason"].lower())

    def test_portatil_legado_seleciona_cuda126_para_gtx10(self):
        info = {"ram_gb": 16, "gpus": [{"vendor": "NVIDIA", "name": "NVIDIA GeForce GTX 1060", "vram_mb": 6144}]}
        with patch.object(comfy_manager.platform, "system", return_value="Windows"):
            rec = comfy_manager.recomendar_pacote_portatil(info)
        self.assertIn("cu126", rec["archive"])

    def test_portatil_legado_nao_windows_nao_e_suportado(self):
        info = {"ram_gb": 16, "gpus": []}
        with patch.object(comfy_manager.platform, "system", return_value="Linux"):
            rec = comfy_manager.recomendar_pacote_portatil(info)
        self.assertFalse(rec["supported"])
        self.assertIn("manual", rec["reason"].lower())

    def test_parametros_de_resolucao_sao_reduzidos_em_hardware_limitado(self):
        info = {"ram_gb": 8, "gpus": [{"vendor": "NVIDIA", "name": "GTX 1050", "vram_mb": 2048}]}
        self.assertEqual(comfy_manager.recomendar_parametros(info)["width"], 512)


class TestComandoProjeto(unittest.TestCase):
    def test_projeto_e_comando_separado(self):
        self.assertIn("projeto", COMMAND_MAP)
        self.assertEqual(parse_command("/projeto refatore o código")[0], "projeto")
        self.assertEqual(parse_command("/analise leia este PDF")[0], "analise")


if __name__ == "__main__":
    unittest.main()

class TestComfyHealthCheck(unittest.TestCase):
    def test_servidor_rejeita_http_400(self):
        class Response:
            status_code = 400
        with patch("requests.get", return_value=Response()):
            self.assertFalse(comfy_manager.servidor_responde())

    def test_servidor_rejeita_json_invalido(self):
        class Response:
            status_code = 200
            def json(self):
                raise ValueError("json inválido")
        with patch("requests.get", return_value=Response()):
            self.assertFalse(comfy_manager.servidor_responde())

    def test_servidor_exige_estrutura_system_stats(self):
        class Response:
            status_code = 200
            def json(self):
                return {"system": {}, "devices": []}
        with patch("requests.get", return_value=Response()):
            self.assertTrue(comfy_manager.servidor_responde())

    def test_servidor_rejeita_json_de_outro_endpoint(self):
        class Response:
            status_code = 200
            def json(self):
                return {"message": "not comfy"}
        with patch("requests.get", return_value=Response()):
            self.assertFalse(comfy_manager.servidor_responde())

class TestComfyMemoriaDisponivel(unittest.TestCase):
    def test_recomendacao_considera_vram_livre_em_vez_da_total(self):
        info = {
            "ram_gb": 32, "ram_available_gb": 20,
            "gpus": [{"vendor": "NVIDIA", "name": "RTX", "vram_mb": 12288, "vram_free_mb": 3072}],
        }
        recomendacao = comfy_manager.recomendar_parametros(info)
        self.assertEqual(recomendacao["width"], 512)

    def test_vram_livre_zero_nao_reutiliza_vram_total(self):
        info = {
            "ram_gb": 32, "ram_available_gb": 0,
            "gpus": [{"vendor": "NVIDIA", "name": "RTX", "vram_mb": 12288, "vram_free_mb": 0}],
        }
        recomendacao = comfy_manager.recomendar_parametros(info)
        self.assertEqual(recomendacao["width"], 512)

    def test_recomendacao_usa_vram_livre_quando_suficiente(self):
        info = {
            "ram_gb": 32, "ram_available_gb": 20,
            "gpus": [{"vendor": "NVIDIA", "name": "RTX", "vram_mb": 12288, "vram_free_mb": 10240}],
        }
        recomendacao = comfy_manager.recomendar_parametros(info)
        self.assertEqual(recomendacao["width"], 768)


class TestComfyDesktopExterno(unittest.TestCase):
    def test_desktop_ativo_funciona_sem_pasta_portatil_local(self):
        with patch.object(comfy_manager, "servidor_responde", return_value=True), \
             patch.object(comfy_manager, "comfy_instalado", return_value=False):
            self.assertIsNone(comfy_manager.garantir_comfyui_ativo())

    def test_sem_api_e_sem_portatil_detalha_como_conectar_desktop(self):
        with patch.object(comfy_manager, "servidor_responde", return_value=False), \
             patch.object(comfy_manager, "comfy_instalado", return_value=False):
            with self.assertRaisesRegex(comfy_manager.ComfyManagerError, "ComfyUI Desktop"):
                comfy_manager.garantir_comfyui_ativo()


class TestPromocaoComfyPreservandoDados(unittest.TestCase):
    def test_substituicao_preserva_diretorio_anterior_em_backup(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            raiz = Path(temp)
            destino = raiz / "ComfyUI"
            staged = raiz / "ComfyUI_installing"
            destino.mkdir()
            (destino / "models.safetensors").write_text("modelo antigo", encoding="utf-8")
            staged.mkdir()
            (staged / "main.py").write_text("novo", encoding="utf-8")

            backup = comfy_manager._promover_instalacao_preservando(destino, staged)

            self.assertIsNotNone(backup)
            self.assertTrue((backup / "models.safetensors").is_file())
            self.assertTrue((destino / "main.py").is_file())
            self.assertFalse(staged.exists())

    def test_falha_na_promocao_restaura_diretorio_anterior(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            raiz = Path(temp)
            destino = raiz / "ComfyUI"
            staged = raiz / "ComfyUI_installing"
            destino.mkdir()
            (destino / "dados.txt").write_text("original", encoding="utf-8")
            staged.mkdir()
            original_replace = Path.replace

            def replace_com_falha(self, target):
                if self == staged:
                    raise OSError("falha simulada na promoção")
                return original_replace(self, target)

            with patch.object(Path, "replace", new=replace_com_falha):
                with self.assertRaisesRegex(OSError, "falha simulada"):
                    comfy_manager._promover_instalacao_preservando(destino, staged)

            self.assertTrue(destino.is_dir())
            self.assertEqual((destino / "dados.txt").read_text(encoding="utf-8"), "original")



class TestComfyURLPersonalizada(unittest.TestCase):
    def test_aceita_endpoint_loopback_com_porta_personalizada(self):
        self.assertEqual(
            comfy_manager.validar_url_comfy_local("http://127.0.0.2:8190/"),
            "http://127.0.0.2:8190",
        )
        self.assertEqual(
            comfy_manager.validar_url_comfy_local("http://localhost:8189"),
            "http://localhost:8189",
        )

    def test_rejeita_endereco_externo_e_url_com_path(self):
        for url in ("https://127.0.0.1:8188", "http://127.0.0.1.evil.test:8188",
                    "http://example.com:8188", "http://127.0.0.1:8188/path"):
            with self.subTest(url=url):
                with self.assertRaises(comfy_manager.ComfyManagerError):
                    comfy_manager.validar_url_comfy_local(url)

    def test_garantir_comfyui_encaminha_porta_personalizada_ao_launcher(self):
        url = "http://127.0.0.1:8190"
        with patch.object(comfy_manager, "servidor_responde", return_value=False), \
             patch.object(comfy_manager, "comfy_instalado", return_value=True), \
             patch.object(comfy_manager, "iniciar_comfyui") as iniciar:
            comfy_manager.garantir_comfyui_ativo(url)
        iniciar.assert_called_once_with(progress=None, base_url=url)

    def test_status_nao_tenta_consultar_host_externo(self):
        with patch("requests.get") as get:
            self.assertFalse(comfy_manager.servidor_responde("http://example.com:8188"))
        get.assert_not_called()


    def test_launcher_portatil_nao_finge_suportar_porta_personalizada(self):
        with patch.object(comfy_manager, "servidor_responde", return_value=False):
            with self.assertRaisesRegex(comfy_manager.ComfyManagerError, "porta 8188"):
                comfy_manager.iniciar_comfyui(base_url="http://127.0.0.1:8190")
