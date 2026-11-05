from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from image_generator import ImageGenerationError, listar_modelos_upscale, upscale_image


class FakeResponse:
    def __init__(self, data=None, content=b"", status_code=200):
        self._data = data or {}
        self.content = content
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestImageUpscale(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "entrada.png"
        image = Image.new("RGB", (16, 12), "white")
        image.save(self.source)
        image.close()
        output = Image.new("RGB", (64, 48), "gray")
        buffer = io.BytesIO()
        output.save(buffer, format="PNG")
        output.close()
        self.output_bytes = buffer.getvalue()

    def tearDown(self):
        self.temp.cleanup()

    def test_lista_modelos_upscale_expostos_pelo_comfy(self):
        response = FakeResponse({
            "UpscaleModelLoader": {
                "input": {"required": {"model_name": [["4x-UltraSharp.pth", "RealESRGAN_x4plus.pth"]]}}
            }
        })
        with patch("image_generator.requests.get", return_value=response):
            self.assertEqual(
                listar_modelos_upscale("http://127.0.0.1:8188"),
                ["4x-UltraSharp.pth", "RealESRGAN_x4plus.pth"],
            )

    def test_executa_workflow_real_com_api_mockada_e_valida_saida(self):
        modelos = FakeResponse({
            "UpscaleModelLoader": {
                "input": {"required": {"model_name": [["4x-UltraSharp.pth"]]}}
            }
        })
        historico = FakeResponse({
            "prompt-12345678": {
                "outputs": {"4": {"images": [{"filename": "result.png", "subfolder": "", "type": "output"}]}},
                "status": {"status_str": "success", "completed": True},
            }
        })
        view = FakeResponse(content=self.output_bytes)

        def fake_get(url, *args, **kwargs):
            if url.endswith("/object_info/UpscaleModelLoader"):
                return modelos
            if "/history/" in url:
                return historico
            if url.endswith("/view"):
                return view
            raise AssertionError(f"GET inesperado: {url}")

        upload = FakeResponse({"name": "entrada.png", "subfolder": "", "type": "input"})
        prompt = FakeResponse({"prompt_id": "prompt-12345678"})
        with patch("comfy_manager.garantir_comfyui_ativo", return_value=True), \
             patch("image_generator.requests.get", side_effect=fake_get), \
             patch("image_generator.requests.post", side_effect=[upload, prompt]), \
             patch("image_generator.time.sleep", return_value=None):
            result = upscale_image(self.source, self.root / "out", base_url="http://127.0.0.1:8188")
        self.assertTrue(result.is_file())
        self.assertEqual(result.suffix, ".png")
        with Image.open(result) as image:
            self.assertEqual(image.size, (64, 48))
        self.assertTrue(self.source.is_file(), "O original não pode ser sobrescrito")

    def test_falha_com_mensagem_clara_quando_nao_ha_modelos(self):
        response = FakeResponse({
            "UpscaleModelLoader": {"input": {"required": {"model_name": [[]]}}}
        })
        with patch("comfy_manager.garantir_comfyui_ativo", return_value=True), \
             patch("image_generator.requests.get", return_value=response):
            with self.assertRaisesRegex(ImageGenerationError, "Nenhum modelo de upscale"):
                upscale_image(self.source, self.root / "out")

    def test_recusa_host_remoto(self):
        with self.assertRaises(ImageGenerationError):
            upscale_image(self.source, self.root / "out", base_url="http://example.com:8188")


if __name__ == "__main__":
    unittest.main()
