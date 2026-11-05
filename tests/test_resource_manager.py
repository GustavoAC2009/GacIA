import unittest
from unittest.mock import patch

import resource_manager as rm


class TestResourceManager(unittest.TestCase):
    def status(self, temp=55, use=10, free=9000):
        return rm.GPUStatus("NVIDIA GeForce RTX 3060", temp, use, 12288, 12288-free, free, 0.0)

    def test_whisper_cpu_em_gpu_quente(self):
        backend, reason = rm.whisper_backend_decision(self.status(temp=89))
        self.assertEqual(backend, "cpu")
        self.assertIn("89", reason)

    def test_whisper_cpu_em_gpu_ocupada(self):
        backend, _ = rm.whisper_backend_decision(self.status(use=80))
        self.assertEqual(backend, "cpu")

    def test_whisper_cuda_em_gpu_livre_e_frio(self):
        backend, _ = rm.whisper_backend_decision(self.status(temp=60, use=10, free=8000))
        self.assertEqual(backend, "cuda")

    def test_whisper_cpu_quando_sensor_indisponivel(self):
        backend, _ = rm.whisper_backend_decision(None)
        self.assertEqual(backend, "cpu")

    def test_imagem_bloqueada_em_89_graus(self):
        allowed, reason = rm.image_gpu_decision(self.status(temp=89))
        self.assertFalse(allowed)
        self.assertIn("89", reason)

    def test_imagem_bloqueada_quando_gpu_muito_ocupada(self):
        allowed, _ = rm.image_gpu_decision(self.status(use=95))
        self.assertFalse(allowed)

    def test_imagem_liberada_em_condicao_normal(self):
        allowed, _ = rm.image_gpu_decision(self.status(temp=60, use=20, free=8000))
        self.assertTrue(allowed)


    def test_segunda_imagem_pode_reutilizar_checkpoint_ja_carregado(self):
        status = self.status(temp=72, use=35, free=2200)
        allowed, _ = rm.image_gpu_decision(status, reuse_loaded_model=True)
        self.assertTrue(allowed)
        allowed_first, _ = rm.image_gpu_decision(status, reuse_loaded_model=False)
        self.assertFalse(allowed_first)

    def test_reuso_do_checkpoint_nao_ignora_temperatura_ou_utilizacao(self):
        hot = self.status(temp=84, use=20, free=5000)
        busy = self.status(temp=65, use=90, free=5000)
        self.assertFalse(rm.image_gpu_decision(hot, reuse_loaded_model=True)[0])
        self.assertFalse(rm.image_gpu_decision(busy, reuse_loaded_model=True)[0])

    def test_monitor_consulta_somente_executavel_local(self):
        with patch.object(rm.shutil, "which", return_value=None), patch.object(rm.subprocess, "run") as run:
            self.assertIsNone(rm._query_nvidia_smi())
            run.assert_not_called()

    def test_parse_nvidia_smi_local(self):
        mock = unittest.mock.Mock()
        mock.returncode = 0
        mock.stdout = "NVIDIA GeForce RTX 3060, 89, 94, 12288, 9000, 3288, 78, 165.40, 180.00\n"
        with patch.object(rm.shutil, "which", return_value="nvidia-smi"), patch.object(rm.subprocess, "run", return_value=mock):
            status = rm._query_nvidia_smi()
        self.assertEqual(status.temperature_c, 89)
        self.assertEqual(status.utilization_percent, 94)
        self.assertEqual(status.memory_free_mb, 3288)
        self.assertEqual(status.fan_percent, 78)
        self.assertEqual(status.power_draw_w, 165.40)
        self.assertEqual(status.power_limit_w, 180.00)

class TestResourceProtectionIntegration(unittest.TestCase):
    def test_whisper_cuda_explicita_faz_fallback_com_gpu_quente(self):
        from voice import GerenciadorVoz
        voz = GerenciadorVoz(device_preferido="cuda")
        voz._carregar_dependencias_whisper = lambda: None
        voz._criar_modelo_cpu = lambda: "modelo-cpu"
        status = rm.GPUStatus("NVIDIA GeForce RTX 3060", 89, 90, 12288, 9000, 3288, 0.0)
        with patch("resource_manager.get_gpu_status", return_value=status):
            self.assertEqual(voz._carregar_whisper(), "modelo-cpu")

    def test_inicio_da_geracao_de_imagem_bloqueia_gpu_a_89c(self):
        from image_generator import _verificar_recursos_gpu_para_imagem, ImageGenerationError
        status = rm.GPUStatus("NVIDIA GeForce RTX 3060", 89, 90, 12288, 9000, 3288, 0.0)
        with patch("resource_manager.get_gpu_status", return_value=status):
            with self.assertRaises(ImageGenerationError) as ctx:
                _verificar_recursos_gpu_para_imagem()
        self.assertIn("89", str(ctx.exception))
