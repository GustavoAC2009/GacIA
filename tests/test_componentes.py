from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import componentes


class TestNormalizacaoComponentes(unittest.TestCase):
    def test_core_e_sempre_obrigatorio(self):
        self.assertEqual(componentes.normalizar_componentes([]), ["core"])
        self.assertEqual(componentes.normalizar_componentes("web"), ["core", "web"])

    def test_componentes_sao_normalizados_e_ordenados(self):
        self.assertEqual(
            componentes.normalizar_componentes("VOICE,web,core,voice"),
            ["core", "web", "voice"],
        )

    def test_rejeita_componente_desconhecido(self):
        with self.assertRaisesRegex(ValueError, "desconhecidos"):
            componentes.normalizar_componentes("core,foo")

    def test_cuda_exige_voz(self):
        with self.assertRaisesRegex(ValueError, "exige também"):
            componentes.normalizar_componentes("core,whisper-cuda")

    def test_cuda_pode_ser_selecionado_com_voz(self):
        self.assertEqual(
            componentes.normalizar_componentes("voice,whisper-cuda"),
            ["core", "voice", "whisper-cuda"],
        )


class TestManifestoComponentes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifesto = Path(self.temp.name) / ".gacia-components.json"
        self.patch_manifest = patch.object(componentes, "MANIFEST_FILE", self.manifesto)
        self.patch_manifest.start()
        self.addCleanup(self.patch_manifest.stop)

    def test_salva_manifesto_atomico_e_sem_caminho_pessoal(self):
        self.assertTrue(componentes.salvar_manifesto(["web", "voice"], python_version="3.13.1"))
        dados = json.loads(self.manifesto.read_text(encoding="utf-8"))
        self.assertEqual(dados["schema"], 2)
        self.assertEqual(dados["componentes"], ["core", "web", "voice"])
        self.assertEqual(dados["python"], "3.13.1")
        self.assertFalse(self.manifesto.with_suffix(".json.tmp").exists())
        self.assertNotIn(str(Path.home()), self.manifesto.read_text(encoding="utf-8"))

    def test_carrega_manifesto_valido(self):
        self.manifesto.write_text(
            json.dumps({"schema": 1, "componentes": ["web", "voice"]}),
            encoding="utf-8",
        )
        manifesto = componentes.carregar_manifesto()
        self.assertEqual(manifesto["componentes"], ["core", "office", "web", "voice"])

    def test_manifesto_corrompido_e_ignorado(self):
        self.manifesto.write_text("{isso não é json", encoding="utf-8")
        self.assertIsNone(componentes.carregar_manifesto())

    def test_manifesto_com_componente_invalido_e_ignorado(self):
        self.manifesto.write_text(
            json.dumps({"schema": 1, "componentes": ["core", "malware"]}),
            encoding="utf-8",
        )
        self.assertIsNone(componentes.carregar_manifesto())

    def test_atualizacao_respeita_manifesto_e_remove_cuda_sem_driver(self):
        componentes.salvar_manifesto(["web", "voice", "whisper-cuda"])
        with patch.object(componentes, "_nvidia_driver_encontrado", return_value=False):
            self.assertEqual(componentes.componentes_para_atualizacao(), ["core", "web", "voice"])

    def test_atualizacao_preserva_cuda_quando_driver_nvidia_funciona(self):
        componentes.salvar_manifesto(["web", "voice", "whisper-cuda"])
        with patch.object(componentes, "_nvidia_driver_encontrado", return_value=True):
            self.assertEqual(componentes.componentes_para_atualizacao(), ["core", "web", "voice", "whisper-cuda"])

    def test_manifesto_legado_preserva_office_que_antes_fazia_parte_do_core(self):
        self.manifesto.write_text(json.dumps({"schema": 1, "componentes": ["web"]}), encoding="utf-8")
        manifesto = componentes.carregar_manifesto()
        self.assertEqual(manifesto["schema"], 2)
        self.assertEqual(manifesto["componentes"], ["core", "office", "web"])

    def test_manifesto_schema_desconhecido_e_ignorado(self):
        self.manifesto.write_text(
            json.dumps({"schema": 999, "componentes": ["core"]}),
            encoding="utf-8",
        )
        self.assertIsNone(componentes.carregar_manifesto())

    def test_repara_componente_parcial_sem_manifesto(self):
        estados = {
            "core": {"instalado": False, "parcial": False},
            "web": {"instalado": False, "parcial": False},
            "voice": {"instalado": False, "parcial": True},
            "whisper-cuda": {"instalado": False, "parcial": False},
        }
        with patch.object(componentes, "detectar_componentes", return_value=estados):
            self.assertEqual(componentes.componentes_para_atualizacao(), ["core", "voice"])

    def test_localiza_nvidia_smi_em_caminho_padrao_windows(self):
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            smi = raiz / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"
            smi.parent.mkdir(parents=True)
            smi.write_bytes(b"stub")
            env = {"ProgramFiles": str(raiz), "WINDIR": str(raiz / "Windows")}
            with patch.object(componentes.sys, "platform", "win32"), \
                 patch.dict(componentes.os.environ, env, clear=False), \
                 patch.object(componentes.shutil, "which", return_value=None), \
                 patch.object(componentes.subprocess, "run") as run:
                run.return_value.returncode = 0
                self.assertTrue(componentes._nvidia_driver_encontrado())
                self.assertEqual(run.call_args.args[0], [str(smi), "-L"])

    def test_sem_manifesto_nao_instala_extras_ausentes(self):
        estados = {
            nome: {"instalado": False}
            for nome in componentes.COMPONENTES
        }
        with patch.object(componentes, "detectar_componentes", return_value=estados):
            self.assertEqual(componentes.componentes_para_atualizacao(), ["core"])


class TestRecomendacoesHardware(unittest.TestCase):
    def test_vram_livre_zero_nao_recomenda_comfy_por_vram_total(self):
        info = {"ram_gb": 32, "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 0}]}
        with patch("componentes._nvidia_driver_encontrado", return_value=True):
            resultado = componentes.recomendar_componentes(info)
        self.assertFalse(resultado["image_generation"])
        self.assertEqual(resultado["vram_gb"], 0.0)

    def test_vram_desconhecida_nao_impede_recomendacao_baseada_em_ram(self):
        info = {"ram_gb": 16, "gpus": [{"vendor": "AMD", "vram_mb": None}]}
        with patch("componentes._nvidia_driver_encontrado", return_value=False):
            resultado = componentes.recomendar_componentes(info)
        self.assertFalse(resultado["nvidia_driver_ok"])
        self.assertFalse(resultado["whisper-cuda"])
        self.assertEqual(resultado["llm_profile"], "intermediario")

    def test_vram_total_nao_e_tratada_como_livre_para_recomendar_imagens(self):
        info = {"ram_gb": 32, "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288}]}
        with patch("componentes._nvidia_driver_encontrado", return_value=True):
            resultado = componentes.recomendar_componentes(info)
        self.assertFalse(resultado["image_generation"])
        self.assertIn("VRAM livre não foi medida", resultado["notes"])

    def test_sdxl_exige_vram_livre_e_ram_suficientes(self):
        info = {"ram_gb": 16, "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 9000}]}
        with patch("componentes._nvidia_driver_encontrado", return_value=True):
            resultado = componentes.recomendar_componentes(info)
        self.assertTrue(resultado["image_generation"])


if __name__ == "__main__":
    unittest.main()
