from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import patch

import requests

import ollama_manager


class _Response:
    def __init__(self, payload=None, lines=None, status=200):
        self._payload = payload
        self._lines = lines or []
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_lines(self, **kwargs):
        return iter(self._lines)


class TestOllamaManager(unittest.TestCase):
    def test_recomenda_perfil_por_ram_e_vram(self):
        self.assertEqual(ollama_manager.recomendar_perfil({"ram_gb": 8}), "rapido")
        self.assertEqual(ollama_manager.recomendar_perfil({"ram_gb": 16, "ram_available_gb": 10,
            "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 9000}]}), "intermediario")
        self.assertEqual(ollama_manager.recomendar_perfil({"ram_gb": 64, "ram_available_gb": 48,
            "gpus": [{"vendor": "NVIDIA", "vram_mb": 24576, "vram_free_mb": 20000}]}), "top")
        self.assertEqual(ollama_manager.recomendar_perfil({"ram_gb": 16, "ram_available_gb": 10,
            "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288, "vram_free_mb": 11264}]}), "top")

    def test_catalogo_atual_e_contexto_limitado_por_perfil(self):
        self.assertEqual(ollama_manager.MODELOS["rapido"]["tag"], "qwen3.5:2b")
        self.assertEqual(ollama_manager.MODELOS["intermediario"]["tag"], "qwen3.5:4b")
        self.assertEqual(ollama_manager.MODELOS["top"]["tag"], "qwen3.5:9b")
        self.assertEqual(ollama_manager.contexto_recomendado("rapido"), 4096)
        self.assertEqual(ollama_manager.contexto_recomendado("intermediario"), 8192)
        self.assertEqual(ollama_manager.contexto_recomendado("top"), 8192)

    def test_capacidade_local_alerta_hardware_insuficiente(self):
        avaliacao = ollama_manager.avaliar_capacidade_local({"ram_gb": 4, "ram_available_gb": 2})
        self.assertFalse(avaliacao["supported"])
        self.assertEqual(avaliacao["profile"], "rapido")
        self.assertTrue(any("abaixo do mínimo" in aviso for aviso in avaliacao["warnings"]))

    def test_vram_total_nao_e_confundida_com_vram_livre_para_perfil_top(self):
        hardware = {"ram_gb": 32, "ram_available_gb": 24,
                    "gpus": [{"vendor": "NVIDIA", "vram_mb": 12288}]}
        self.assertEqual(ollama_manager.recomendar_perfil(hardware), "intermediario")
        avaliacao = ollama_manager.avaliar_capacidade_local(hardware)
        self.assertTrue(any("VRAM livre" in aviso for aviso in avaliacao["warnings"]))

    def test_controle_pensamento_descobre_nivel_high_e_usa_cache(self):
        ollama_manager._THINK_CACHE.clear()
        payload = {"thinking": {"values": ["low", "medium", "high"], "default": "medium"}}
        with patch.object(ollama_manager.requests, "post", return_value=_Response(payload=payload)) as post:
            primeiro = ollama_manager.controle_pensamento("qwen3.5:9b")
            segundo = ollama_manager.controle_pensamento("qwen3.5:9b")
        self.assertTrue(primeiro["supported"])
        self.assertEqual(primeiro["value"], "high")
        self.assertEqual(segundo, primeiro)
        self.assertEqual(post.call_count, 1)
        ollama_manager._THINK_CACHE.clear()

    def test_controle_pensamento_respeita_modelo_sem_suporte(self):
        ollama_manager._THINK_CACHE.clear()
        payload = {"thinking": {"values": [False], "default": False}}
        with patch.object(ollama_manager.requests, "post", return_value=_Response(payload=payload)):
            resultado = ollama_manager.controle_pensamento("modelo-sem-thinking")
        self.assertTrue(resultado["known"])
        self.assertFalse(resultado["supported"])
        self.assertIsNone(resultado["value"])
        ollama_manager._THINK_CACHE.clear()

    def test_falha_transitoria_nao_fica_em_cache(self):
        ollama_manager._THINK_CACHE.clear()
        falha = requests.ConnectionError("offline")
        sucesso = _Response(payload={"thinking": {"values": [True], "default": False}})
        with patch.object(ollama_manager.requests, "post", side_effect=[falha, sucesso]) as post:
            primeira = ollama_manager.controle_pensamento("modelo-recuperado")
            segunda = ollama_manager.controle_pensamento("modelo-recuperado")
        self.assertFalse(primeira["supported"])
        self.assertTrue(segunda["supported"])
        self.assertEqual(post.call_count, 2)
        ollama_manager._THINK_CACHE.clear()

    def test_lista_modelos_instalados(self):
        payload = {"models": [{"name": "qwen2.5:7b-instruct", "size": 4_700_000_000}]}
        with patch.object(ollama_manager.requests, "get", return_value=_Response(payload=payload)):
            self.assertTrue(ollama_manager.modelo_instalado("qwen2.5:7b-instruct"))
            self.assertFalse(ollama_manager.modelo_instalado("qwen2.5:14b-instruct"))

    def test_pull_valida_tag_e_consume_progresso_ate_sucesso(self):
        lines = [
            json.dumps({"status": "pulling manifest"}),
            json.dumps({"status": "downloading", "total": 100, "completed": 40}),
            json.dumps({"status": "success"}),
        ]
        events = []
        with patch.object(ollama_manager.requests, "post", return_value=_Response(lines=lines)) as post:
            result = ollama_manager.baixar_modelo("qwen2.5:7b-instruct", progress=events.append)
        self.assertEqual(result, "qwen2.5:7b-instruct")
        self.assertEqual(len(events), 3)
        self.assertIn("/api/pull", post.call_args.args[0])
        with self.assertRaisesRegex(ollama_manager.OllamaModelError, "fora do catálogo"):
            ollama_manager.baixar_modelo("unknown/model:latest")

    def test_pull_cancela_e_nao_declara_sucesso_indevido(self):
        event = threading.Event(); event.set()
        lines = [json.dumps({"status": "downloading"})]
        with patch.object(ollama_manager.requests, "post", return_value=_Response(lines=lines)):
            with self.assertRaisesRegex(ollama_manager.OllamaModelError, "cancelado"):
                ollama_manager.baixar_modelo("qwen2.5:1.5b-instruct", cancel_event=event)

    def test_formato_invalido_da_api_e_tratado(self):
        with patch.object(ollama_manager.requests, "get", return_value=_Response(payload={"items": []})):
            with self.assertRaisesRegex(ollama_manager.OllamaModelError, "formato inesperado"):
                ollama_manager.listar_modelos()


if __name__ == "__main__":
    unittest.main()
