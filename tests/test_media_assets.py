import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from agent.media_assets import _license_allowed, search_commons_images


class TestMediaAssets(unittest.TestCase):
    def test_licencas_permitidas_e_restritas(self):
        self.assertTrue(_license_allowed("CC0 1.0 Universal"))
        self.assertTrue(_license_allowed("CC BY-SA 4.0"))
        self.assertTrue(_license_allowed("CC BY 4.0"))
        self.assertTrue(_license_allowed("Public domain"))
        self.assertFalse(_license_allowed("CC BY-NC 4.0"))
        self.assertFalse(_license_allowed("CC BY-NC-SA 4.0"))
        self.assertFalse(_license_allowed("CC BY-ND 4.0"))
        self.assertFalse(_license_allowed("CC BY-SA-NC 4.0"))

    def test_pesquisa_baixa_imagem_e_preserva_credito(self):
        payload = {
            "query": {"pages": {"123": {
                "title": "File:rede.png",
                "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/wikipedia/commons/a/a1/rede.png",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:rede.png",
                    "mime": "image/png", "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                        "Artist": {"value": "Autor de teste"},
                    },
                }],
            }}}}
        metadata_response = Mock()
        metadata_response.json.return_value = payload
        metadata_response.raise_for_status.return_value = None
        image_response = Mock()
        image_response.headers = {"Content-Type": "image/png"}
        image_response.iter_content.return_value = [b"\x89PNG\r\n\x1a\n" + b"x" * 400]
        image_response.raise_for_status.return_value = None
        client = Mock()
        client.get.side_effect = [metadata_response, image_response]
        with tempfile.TemporaryDirectory() as temp:
            results = search_commons_images("rede de computadores", Path(temp), session=client)
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertTrue(Path(result["path"]).is_file())
            self.assertEqual(result["artist"], "Autor de teste")
            self.assertEqual(result["license"], "CC BY-SA 4.0")
            image_response.close.assert_called_once()


    def test_descarta_imagem_com_licenca_valida_mas_assunto_incorreto(self):
        payload = {
            "query": {"pages": {"123": {
                "title": "File:Syphilis medical illustration.png",
                "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/wikipedia/commons/a/a1/syphilis.png",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Syphilis_medical_illustration.png",
                    "mime": "image/png", "extmetadata": {
                        "LicenseShortName": {"value": "CC BY 4.0"},
                        "ImageDescription": {"value": "Medical illustration of syphilis"},
                    },
                }],
            }}}}
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        client = Mock()
        client.get.return_value = response
        with tempfile.TemporaryDirectory() as temp:
            results = search_commons_images(
                "Minecraft shaders screenshot", Path(temp), session=client,
                required_terms=["minecraft"],
            )
            self.assertEqual(results, [])
            # O resultado é rejeitado pelos metadados; nunca chega ao download.
            client.get.assert_called_once()

    def test_aceita_somente_imagem_cujos_metadados_contem_a_ancora(self):
        payload = {
            "query": {"pages": {"123": {
                "title": "File:Minecraft screenshot.png",
                "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/wikipedia/commons/a/a1/minecraft.png",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Minecraft_screenshot.png",
                    "mime": "image/png", "extmetadata": {
                        "LicenseShortName": {"value": "CC BY 4.0"},
                        "ImageDescription": {"value": "A screenshot from Minecraft"},
                    },
                }],
            }}}}
        metadata_response = Mock()
        metadata_response.json.return_value = payload
        metadata_response.raise_for_status.return_value = None
        image_response = Mock()
        image_response.headers = {"Content-Type": "image/png"}
        image_response.iter_content.return_value = [b"\x89PNG\r\n\x1a\n" + b"x" * 400]
        image_response.raise_for_status.return_value = None
        client = Mock()
        client.get.side_effect = [metadata_response, image_response]
        with tempfile.TemporaryDirectory() as temp:
            results = search_commons_images(
                "Minecraft shader screenshot", Path(temp), session=client,
                required_terms=["minecraft"],
            )
            self.assertEqual(len(results), 1)
            self.assertIn("Minecraft", results[0]["title"])

    def test_nao_baixa_imagem_com_licenca_nc(self):
        payload = {
            "query": {"pages": {"123": {
                "title": "File:restrita.jpg",
                "imageinfo": [{
                    "url": "https://upload.wikimedia.org/wikipedia/commons/a/a1/restrita.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:restrita.jpg",
                    "mime": "image/jpeg", "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-NC 4.0"},
                    },
                }],
            }}}}
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        client = Mock()
        client.get.return_value = response
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(search_commons_images("paisagem urbana", Path(temp), session=client), [])
            client.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
