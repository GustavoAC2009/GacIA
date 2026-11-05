from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import comfy_models
from comfy_models import ComfyModelError


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload
        self._content = content
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self._content), min(chunk_size, 8192)):
            yield self._content[i:i + min(chunk_size, 8192)]


class TestComfyModelManager(unittest.TestCase):
    def test_catalogo_tem_varios_estilos_e_recomendacao_hardware(self):
        info = {"gpus": [{"vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 10000}], "ram_gb": 16}
        catalogo = comfy_models.obter_catalogo(info)
        ids = {item["id"] for item in catalogo}
        self.assertTrue({"juggernaut-xl-v9", "dreamshaper-xl-turbo", "animagine-xl-4-opt", "realvis-xl-v5"}.issubset(ids))
        self.assertTrue(all(item["recommended"] for item in catalogo))
        dreamshaper = next(item for item in catalogo if item["id"] == "dreamshaper-xl-turbo")
        self.assertEqual(dreamshaper["repo"], "Lykon/dreamshaper-xl-turbo")
        self.assertIn("openrail++", dreamshaper["license"])
        low = comfy_models.obter_catalogo({"gpus": [{"vendor": "NVIDIA", "vram_mb": 4096}], "ram_gb": 8})
        self.assertTrue(all(not item["recommended"] for item in low))
        unknown_free = comfy_models.obter_catalogo({"gpus": [{"vendor": "NVIDIA", "vram_mb": 12288}], "ram_gb": 16})
        self.assertTrue(all(not item["recommended"] for item in unknown_free))
        self.assertTrue(all("VRAM total informada não garante" in item["hardware_note"] for item in unknown_free))

    def test_diretorios_sao_resolvidos_e_categoria_validada(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            (root / "models").mkdir(parents=True)
            destination = comfy_models.diretorio_modelos(root, "checkpoints")
            self.assertEqual(destination, root / "models" / "checkpoints")
            with self.assertRaises(ComfyModelError):
                comfy_models.diretorio_modelos(root, "../../outside")

    def test_lista_apenas_arquivos_de_modelo_nao_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "models" / "loras"
            folder.mkdir(parents=True)
            (folder / "style.safetensors").write_bytes(b"abc")
            (folder / "readme.txt").write_text("not a model")
            result = comfy_models.listar_modelos_instalados(root, ["loras"])
            self.assertEqual([x["name"] for x in result["loras"]], ["style.safetensors"])

    def test_metadados_exigem_arquivo_safetensors_listado(self):
        payload = {"siblings": [{"rfilename": "model.safetensors", "lfs": {"size": 2_000_000, "sha256": "a" * 64}}]}
        with patch.object(comfy_models.requests, "get", return_value=_FakeResponse(payload=payload)):
            meta = comfy_models._metadados_hf("org/repo", "model.safetensors")
            self.assertEqual(meta["size"], 2_000_000)
            self.assertEqual(meta["sha256"], "a" * 64)
            with self.assertRaises(ComfyModelError):
                comfy_models._metadados_hf("org/repo", "missing.safetensors")
            with self.assertRaises(ComfyModelError):
                comfy_models._metadados_hf("org/repo", "../../evil.safetensors")

    def test_download_verifica_tamanho_hash_e_nao_sobrescreve(self):
        content = b"A" * (1024 * 1024)
        checksum = hashlib.sha256(content).hexdigest()
        payload = {"siblings": [{"rfilename": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors", "lfs": {"size": len(content), "sha256": checksum}}]}

        def fake_get(url, **kwargs):
            if "/api/models/" in url:
                return _FakeResponse(payload=payload)
            return _FakeResponse(status_code=200, content=content)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            (root / "models").mkdir(parents=True)
            with patch.object(comfy_models.requests, "get", side_effect=fake_get):
                path = comfy_models.baixar_modelo_catalogo("juggernaut-xl-v9", root)
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, len(content))
                with self.assertRaises(ComfyModelError):
                    comfy_models.baixar_modelo_catalogo("juggernaut-xl-v9", root)


    def test_remover_apaga_somente_modelo_regular_da_categoria(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            folder = root / "models" / "loras"
            folder.mkdir(parents=True)
            model = folder / "style.safetensors"
            model.write_bytes(b"model")
            resultado = comfy_models.remover_modelo_instalado(root, "loras", "style.safetensors")
            self.assertEqual(resultado["size_bytes"], 5)
            self.assertFalse(model.exists())
            with self.assertRaises(ComfyModelError):
                comfy_models.remover_modelo_instalado(root, "loras", "../outside.safetensors")

    def test_remover_recusa_links_simbolicos(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            folder = root / "models" / "loras"
            folder.mkdir(parents=True)
            outside = Path(temp) / "important.safetensors"
            outside.write_bytes(b"do not remove")
            link = folder / "linked.safetensors"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("Criação de symlink não disponível neste ambiente")
            with self.assertRaisesRegex(ComfyModelError, "Links simbólicos"):
                comfy_models.remover_modelo_instalado(root, "loras", "linked.safetensors")
            self.assertTrue(outside.exists())

    def test_checkpoint_preferido_respeita_estilo(self):
        disponiveis = [
            "DreamShaperXL_Turbo_SFWdpmppSde_half_pruned.safetensors",
            "animagine-xl-4.0-opt.safetensors",
            "RealVisXL_V5.0_fp16.safetensors",
        ]
        self.assertEqual(
            comfy_models.selecionar_checkpoint_preferido(disponiveis, "anime"),
            "animagine-xl-4.0-opt.safetensors",
        )
        self.assertEqual(
            comfy_models.selecionar_checkpoint_preferido(disponiveis, "photorealistic"),
            "RealVisXL_V5.0_fp16.safetensors",
        )

    def test_hash_incorreto_remove_download_invalido(self):
        content = b"B" * (1024 * 1024)
        payload = {"siblings": [{"rfilename": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors", "lfs": {"size": len(content), "sha256": "0" * 64}}]}

        def fake_get(url, **kwargs):
            return _FakeResponse(payload=payload) if "/api/models/" in url else _FakeResponse(content=content)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            (root / "models").mkdir(parents=True)
            with patch.object(comfy_models.requests, "get", side_effect=fake_get):
                with self.assertRaisesRegex(ComfyModelError, "SHA-256"):
                    comfy_models.baixar_modelo_catalogo("juggernaut-xl-v9", root)
            self.assertFalse(list((root / "models" / "checkpoints").glob("*.safetensors")))


    def test_vram_livre_zero_nao_reutiliza_total_para_recomendar_modelo(self):
        catalogo = comfy_models.obter_catalogo({"gpus": [{
            "vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 0
        }]})
        self.assertTrue(all(not item["recommended"] for item in catalogo))
        self.assertTrue(all(item["hardware_note"] for item in catalogo))

    def test_sobrescrita_preserva_backups_sem_colisao(self):
        old = b"arquivo antigo"
        content_one = b"A" * (1024 * 1024)
        content_two = b"B" * (1024 * 1024)
        filename = "meu-estilo.safetensors"

        def fake_get_for(content):
            checksum = hashlib.sha256(content).hexdigest()
            payload = {"siblings": [{"rfilename": filename, "lfs": {"size": len(content), "sha256": checksum}}]}
            def fake_get(url, **kwargs):
                if "/api/models/" in url:
                    return _FakeResponse(payload=payload)
                return _FakeResponse(content=content)
            return fake_get

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ComfyUI"
            folder = root / "models" / "loras"
            folder.mkdir(parents=True)
            destination = folder / filename
            destination.write_bytes(old)
            with patch.object(comfy_models.requests, "get", side_effect=fake_get_for(content_one)):
                comfy_models.baixar_modelo_hf("org/repo", filename, "loras", root, overwrite=True)
            self.assertEqual(destination.read_bytes(), content_one)
            self.assertEqual((folder / (filename + ".bak")).read_bytes(), old)
            with patch.object(comfy_models.requests, "get", side_effect=fake_get_for(content_two)):
                comfy_models.baixar_modelo_hf("org/repo", filename, "loras", root, overwrite=True)
            self.assertEqual(destination.read_bytes(), content_two)
            self.assertEqual((folder / (filename + ".bak.1")).read_bytes(), content_one)



if __name__ == "__main__":
    unittest.main()
