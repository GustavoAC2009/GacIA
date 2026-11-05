import threading
import time
import unittest
from unittest.mock import Mock, patch

from image_generator import (
    fila_comfyui_ocupada,
    liberar_memoria_comfyui,
    serializar_trabalho_comfyui,
)


class TestComfyResourceCoordination(unittest.TestCase):
    def test_workflows_sao_serializados_globalmente(self):
        active = 0
        maximum = 0
        guard = threading.Lock()

        @serializar_trabalho_comfyui
        def fake_work(value):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.025)
            with guard:
                active -= 1
            return value

        results = []
        threads = [threading.Thread(target=lambda n=n: results.append(fake_work(n))) for n in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(sorted(results), list(range(5)))
        self.assertEqual(maximum, 1)

    def test_memoria_comfyui_so_e_liberada_com_fila_vazia(self):
        queue_response = Mock()
        queue_response.json.return_value = {"queue_running": [], "queue_pending": []}
        queue_response.raise_for_status.return_value = None
        free_response = Mock()
        free_response.raise_for_status.return_value = None
        with patch("image_generator.requests.get", return_value=queue_response), \
             patch("image_generator.requests.post", return_value=free_response) as post:
            released, message = liberar_memoria_comfyui("http://127.0.0.1:8188")

        self.assertTrue(released)
        self.assertIn("descarregados", message)
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8188/free")
        self.assertEqual(post.call_args.kwargs["json"], {"unload_models": True, "free_memory": True})

    def test_memoria_nao_e_liberada_se_houver_workflow_ativo(self):
        queue_response = Mock()
        queue_response.json.return_value = {"queue_running": [[1, "prompt"]], "queue_pending": []}
        queue_response.raise_for_status.return_value = None
        with patch("image_generator.requests.get", return_value=queue_response), \
             patch("image_generator.requests.post") as post:
            released, message = liberar_memoria_comfyui("http://127.0.0.1:8188")

        self.assertFalse(released)
        self.assertIn("fila", message.casefold())
        post.assert_not_called()

    def test_fila_indisponivel_e_tratada_como_ocupada(self):
        with patch("image_generator.requests.get", side_effect=__import__("requests").ConnectionError("offline")):
            self.assertTrue(fila_comfyui_ocupada("http://127.0.0.1:8188"))


if __name__ == "__main__":
    unittest.main()
