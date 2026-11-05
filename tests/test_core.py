"""Testes unitários dos módulos atuais; não exigem microfone, GPU ou Ollama."""
from __future__ import annotations

import os
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
import types

import config
import memory.database as database
from memory.context import limitar_historico
from ferramentas import calcular, consultar_data_hora
from pesquisa_web import _url_publica, pesquisar_web, limite_do_perfil, formatar_resultados
import voice
import hardware
import inventario_ambiente
from memory.inteligencia import extrair_memoria_explicita


class TestConfiguracao(unittest.TestCase):
    def test_padrao_inicial_da_gacia(self):
        resultado = config._mesclar_config({})
        self.assertEqual(resultado["tema"], "Dark")
        self.assertEqual(resultado["whisper_device"], "auto")
        self.assertEqual(resultado["linguagem"], "pt-BR")
        self.assertEqual(resultado["personalidade"], "equilibrada")
        self.assertEqual(resultado["voz"], "feminina")

    def test_preserva_modelos_personalizados_e_completa_defaults(self):
        resultado = config._mesclar_config({
            "perfil_ativo": "top",
            "modelos": {"top": "meu-modelo:custom", "intermediario": "qwen-custom"},
        })
        self.assertEqual(resultado["modelos"]["top"], "meu-modelo:custom")
        self.assertEqual(resultado["modelos"]["intermediario"], "qwen-custom")
        self.assertEqual(resultado["modelos"]["rapido"], config.MODELOS_PADRAO["rapido"])

    def test_normaliza_endpoints_ollama(self):
        self.assertEqual(
            config.normalizar_host_ollama("http://localhost:11434/api/chat"),
            "http://localhost:11434",
        )
        self.assertEqual(
            config.normalizar_host_ollama("localhost:11434/api/"),
            "http://localhost:11434",
        )
        self.assertEqual(
            config.normalizar_host_ollama("http://localhost:11434/api/tags"),
            "http://localhost:11434",
        )
        self.assertEqual(
            config.normalizar_host_ollama("http://[ipv6-invalido"),
            "http://localhost:11434",
        )

    def test_url_comfy_local_personalizada_e_validada_sem_prefixos_enganosos(self):
        resultado = config._mesclar_config({
            "gerador_imagens": {"url": "http://127.0.0.2:8190"}
        })
        self.assertEqual(resultado["gerador_imagens"]["url"], "http://127.0.0.2:8190")
        for url in (
            "http://127.0.0.1.evil.test:8188",
            "http://localhost.evil.test:8188",
            "https://127.0.0.1:8188",
            "http://127.0.0.1:99999",
            "http://127.0.0.1:8188/path",
        ):
            with self.subTest(url=url):
                resultado = config._mesclar_config({"gerador_imagens": {"url": url}})
                self.assertEqual(resultado["gerador_imagens"]["url"], "http://127.0.0.1:8188")

    def test_valores_invalidos_voltam_aos_defaults(self):
        resultado = config._mesclar_config({
            "perfil_ativo": "perfil-inexistente",
            "voz": "robô",
            "whisper_device": "gpu-misteriosa",
            "tema": "neon",
        })
        self.assertEqual(resultado["perfil_ativo"], "intermediario")
        self.assertEqual(resultado["voz"], "feminina")
        self.assertEqual(resultado["whisper_device"], "auto")
        self.assertEqual(resultado["tema"], "Dark")
        tipos_invalidos = config._mesclar_config({
            "perfil_ativo": [], "voz": {}, "whisper_device": [], "tema": {},
            "pesquisa_web_ativa": "false", "modo_ao_vivo": "true",
        })
        self.assertEqual(tipos_invalidos["perfil_ativo"], "intermediario")
        self.assertEqual(tipos_invalidos["voz"], "feminina")
        self.assertFalse(tipos_invalidos["pesquisa_web_ativa"])
        self.assertFalse(tipos_invalidos["modo_ao_vivo"])

    def test_salvamento_e_carregamento_atomicos(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho_original = config.CONFIG_FILE
            try:
                config.CONFIG_FILE = Path(pasta) / "config.json"
                dados = config._mesclar_config({"perfil_ativo": "rapido"})
                self.assertTrue(config.salvar_config(dados))
                carregado = config.carregar_config()
                self.assertEqual(carregado["perfil_ativo"], "rapido")
                self.assertFalse(config.CONFIG_FILE.with_suffix(".json.tmp").exists())
            finally:
                config.CONFIG_FILE = caminho_original

    def test_preferencias_de_idioma_nome_e_personalidade(self):
        resultado = config._mesclar_config({
            "linguagem": "en", "nome_usuario": "  Alex  ", "personalidade": "didatica"
        })
        self.assertEqual(resultado["linguagem"], "en")
        self.assertEqual(resultado["nome_usuario"], "Alex")
        self.assertEqual(resultado["personalidade"], "didatica")
        invalido = config._mesclar_config({"linguagem": "es", "personalidade": "agressiva"})
        self.assertEqual(invalido["linguagem"], "pt-BR")
        self.assertEqual(invalido["personalidade"], "equilibrada")


class TestMemoriaExplicita(unittest.TestCase):
    def test_reconhece_pedidos_explicitos_pt_e_en(self):
        self.assertEqual(
            extrair_memoria_explicita("Lembre-se de que prefiro respostas curtas"),
            "prefiro respostas curtas",
        )
        self.assertEqual(
            extrair_memoria_explicita("Gac.IA, guarde na memória: meu projeto se chama GacIA"),
            "meu projeto se chama GacIA",
        )
        self.assertEqual(
            extrair_memoria_explicita("Remember that I prefer Python examples"),
            "I prefer Python examples",
        )

    def test_nao_salva_mensagem_sem_comando_explicito(self):
        self.assertIsNone(extrair_memoria_explicita("Eu prefiro respostas curtas"))
        self.assertIsNone(extrair_memoria_explicita("lembre-se"))


class TestBancoDeDados(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "memory.db"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original
        self.temp.cleanup()

    def test_salva_e_carrega_historico_ordenado(self):
        database.salvar_mensagem("sessao-1", "user", "Olá")
        database.salvar_mensagem("sessao-1", "assistant", "Oi")
        self.assertEqual(database.carregar_historico("sessao-1"), [
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Oi"},
        ])

    def test_historico_isola_sessoes_e_aplica_limite(self):
        for i in range(4):
            database.salvar_mensagem("a", "user", str(i))
        database.salvar_mensagem("b", "user", "outra sessão")
        self.assertEqual(database.carregar_historico("a", limite=2), [
            {"role": "user", "content": "2"},
            {"role": "user", "content": "3"},
        ])
        self.assertEqual(database.carregar_historico("b"), [
            {"role": "user", "content": "outra sessão"},
        ])

    def test_conversas_sao_persistidas_e_ordenadas(self):
        database.criar_conversa("sessao-a")
        database.salvar_mensagem("sessao-a", "user", "Como aprender Python?")
        database.atualizar_titulo_conversa("sessao-a", "Como aprender Python?")
        conversas = database.listar_conversas()
        self.assertEqual(conversas[0]["sessao_id"], "sessao-a")
        self.assertEqual(conversas[0]["titulo"], "Como aprender Python?")
        self.assertEqual(
            database.carregar_mensagens_usuario("sessao-a", limite=2),
            ["Como aprender Python?"],
        )

    def test_historico_detalhado_mantem_ordem_cronologica(self):
        database.salvar_mensagem("ordem", "user", "primeira")
        database.salvar_mensagem("ordem", "assistant", "segunda")
        database.salvar_mensagem("ordem", "user", "terceira")
        self.assertEqual(
            [item["content"] for item in database.carregar_mensagens_detalhadas("ordem")],
            ["primeira", "segunda", "terceira"],
        )

    def test_fixa_desafixa_e_apaga_mensagem_por_sessao(self):
        mensagem_id = database.salvar_mensagem("s", "user", "Lembre desta decisão")
        self.assertTrue(database.definir_mensagem_fixada(mensagem_id, "s", True))
        detalhadas = database.carregar_mensagens_detalhadas("s")
        self.assertEqual(detalhadas[0]["id"], mensagem_id)
        self.assertTrue(detalhadas[0]["pinned"])
        self.assertFalse(database.definir_mensagem_fixada(mensagem_id, "outra", False))
        self.assertTrue(database.definir_mensagem_fixada(mensagem_id, "s", False))
        self.assertFalse(database.carregar_mensagens_detalhadas("s")[0]["pinned"])
        self.assertTrue(database.apagar_mensagem(mensagem_id, "s"))
        self.assertEqual(database.carregar_mensagens_detalhadas("s"), [])
        self.assertFalse(database.apagar_mensagem(mensagem_id, "s"))

    def test_edita_somente_mensagem_do_usuario_na_sessao_correta(self):
        mensagem_id = database.salvar_mensagem("editar", "user", "texto original")
        resposta_id = database.salvar_mensagem("editar", "assistant", "resposta existente")
        self.assertFalse(database.atualizar_mensagem(mensagem_id, "outra", "não alterar"))
        self.assertFalse(database.atualizar_mensagem(resposta_id, "editar", "não editar resposta"))
        self.assertTrue(database.atualizar_mensagem(mensagem_id, "editar", "texto corrigido"))
        self.assertEqual(database.carregar_historico("editar"), [
            {"role": "user", "content": "texto corrigido"},
            {"role": "assistant", "content": "resposta existente"},
        ])

    def test_migra_banco_antigo_sem_apagar_mensagens(self):
        caminho = Path(self.temp.name) / "legado.db"
        with patch.object(database, "DB_PATH", caminho):
            import sqlite3
            conexao = sqlite3.connect(caminho)
            try:
                with conexao:
                    conexao.execute(
                        "CREATE TABLE historico (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "sessao_id TEXT NOT NULL, papel TEXT NOT NULL, conteudo TEXT NOT NULL, "
                        "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
                    )
                    conexao.execute(
                        "INSERT INTO historico (sessao_id, papel, conteudo) VALUES (?, ?, ?)",
                        ("legada", "user", "preservar esta mensagem"),
                    )
            finally:
                conexao.close()
            database.init_db()
            self.assertEqual(database.carregar_historico("legada"), [
                {"role": "user", "content": "preservar esta mensagem"}
            ])
            self.assertFalse(database.carregar_mensagens_detalhadas("legada")[0]["pinned"])

    def test_fixar_conversa_e_listar_fixadas_primeiro(self):
        database.criar_conversa("normal", "Normal")
        database.criar_conversa("importante", "Importante")
        self.assertTrue(database.definir_conversa_fixada("importante", True))
        conversas = database.listar_conversas()
        self.assertEqual(conversas[0]["sessao_id"], "importante")
        self.assertTrue(conversas[0]["fixada"])
        self.assertTrue(database.definir_conversa_fixada("importante", False))
        self.assertFalse(database.listar_conversas()[0]["fixada"])

    def test_apagar_conversa_preserva_memorias_e_mensagens_fixadas(self):
        database.criar_conversa("apagar", "Chat para excluir")
        database.criar_conversa("manter", "Chat que continua")
        database.salvar_mensagem("apagar", "user", "Contexto importante fixado")
        id_fixada = database.salvar_mensagem("apagar", "assistant", "Resposta importante fixada")
        database.definir_mensagem_fixada(id_fixada, "apagar", True)
        database.salvar_mensagem("apagar", "user", "Mensagem comum")
        database.salvar_mensagem("manter", "user", "Não apagar este outro chat")
        database.salvar_memoria("Preferência permanente do usuário")

        self.assertTrue(database.apagar_conversa("apagar"))
        self.assertEqual(database.carregar_historico("apagar"), [])
        self.assertNotIn("apagar", [c["sessao_id"] for c in database.listar_conversas()])
        self.assertEqual(database.carregar_historico("manter"), [
            {"role": "user", "content": "Não apagar este outro chat"}
        ])
        memorias = [m["content"] for m in database.carregar_memorias_salvas()]
        self.assertIn("Preferência permanente do usuário", memorias)
        self.assertIn("Resposta importante fixada", memorias)
        self.assertNotIn("Mensagem comum", memorias)

    def test_tombstone_impede_resposta_atrasada_recriar_chat_excluido(self):
        database.criar_conversa("apagada")
        database.salvar_mensagem("apagada", "user", "pedido")
        self.assertTrue(database.apagar_conversa("apagada"))
        with self.assertRaisesRegex(RuntimeError, "foi excluída"):
            database.salvar_mensagem("apagada", "assistant", "resposta atrasada")
        database.criar_conversa("apagada", "Nova conversa recriada")
        self.assertGreater(database.salvar_mensagem("apagada", "user", "novo pedido"), 0)

    def test_rejeita_papel_e_limite_invalidos(self):
        with self.assertRaises(ValueError):
            database.salvar_mensagem("s", "admin", "x")
        with self.assertRaises(ValueError):
            database.carregar_historico("s", limite=0)

    def test_entrada_com_sql_nao_e_executada(self):
        texto = "'; DROP TABLE historico; --"
        database.salvar_mensagem("s", "user", texto)
        self.assertEqual(database.carregar_historico("s")[0]["content"], texto)

    def test_init_nao_apaga_tabelas_legadas(self):
        with database.conectar() as conexao:
            conexao.execute("CREATE TABLE conversas (id INTEGER PRIMARY KEY, texto TEXT)")
            conexao.execute("INSERT INTO conversas (texto) VALUES (?)", ("preservar",))
        database.init_db()
        with database.conectar() as conexao:
            registro = conexao.execute("SELECT texto FROM conversas").fetchone()
        self.assertEqual(registro, ("preservar",))


class TestFerramentas(unittest.TestCase):
    def test_calculadora(self):
        self.assertEqual(calcular("25 * 4"), "Resultado: 100")
        self.assertEqual(calcular("1.5 + 2.5"), "Resultado: 4.0")
        self.assertIn("divisão por zero", calcular("10 / 0"))

    def test_calculadora_rejeita_codigo_e_limites(self):
        self.assertIn("Expressão não permitida", calcular("__import__('os')"))
        self.assertIn("Expoente muito grande", calcular("2 ** 101"))
        self.assertIn("fora do limite", calcular("1e999"))

    def test_data_hora_em_portugues(self):
        texto = consultar_data_hora()
        self.assertIn("Data:", texto)
        self.assertIn("Hora local:", texto)
        self.assertIn("Dia da semana:", texto)
        self.assertNotIn("Monday", texto)

    def test_urls_locais_e_esquemas_nao_http_sao_bloqueados(self):
        for url in (
            "http://127.0.0.1:11434/api/tags",
            "http://192.168.1.1/",
            "http://localhost/",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/arquivo",
        ):
            self.assertFalse(_url_publica(url), url)

    def test_url_publica_http_s(self):
        self.assertTrue(_url_publica("https://example.com/documentacao"))


class TestPesquisaWeb(unittest.TestCase):
    def test_usa_regiao_portugues_brasil_e_filtra_destinos_locais(self):
        chamadas = {}

        class FakeDDGS:
            def __init__(self, timeout):
                chamadas["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def text(self, termo, region, max_results):
                chamadas.update(termo=termo, region=region, max_results=max_results)
                return [
                    {"title": "Documentação", "href": "https://example.com/docs", "body": "Resumo"},
                    {"title": "Privado", "href": "http://127.0.0.1/", "body": "Não deve entrar"},
                ]

        modulo = types.ModuleType("ddgs")
        modulo.DDGS = FakeDDGS
        with patch.dict("sys.modules", {"ddgs": modulo}):
            resultados = pesquisar_web("Python", max_resultados=3)

        self.assertEqual(chamadas["region"], "br-pt")
        self.assertEqual(chamadas["timeout"], 8)
        self.assertEqual(chamadas["termo"], "Python")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["titulo"], "Documentação")

    def test_orcamento_de_fontes_por_perfil_e_idioma(self):
        self.assertEqual(limite_do_perfil("rapido"), 2)
        self.assertEqual(limite_do_perfil("intermediario"), 5)
        self.assertEqual(limite_do_perfil("top"), 8)
        self.assertEqual(limite_do_perfil("desconhecido"), 5)

        chamadas = {"consultas": []}
        class FakeDDGS:
            def __init__(self, timeout):
                chamadas["timeout"] = timeout
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def text(self, termo, region, max_results):
                chamadas.update(region=region)
                chamadas["consultas"].append((termo, max_results))
                prefixo = len(chamadas["consultas"])
                return [
                    {"title": f"Fonte {prefixo}-{i}", "href": f"https://source{prefixo}-{i}.example/article", "body": "Resumo"}
                    for i in range(max_results)
                ]
        modulo = types.ModuleType("ddgs")
        modulo.DDGS = FakeDDGS
        with patch.dict("sys.modules", {"ddgs": modulo}):
            leves = pesquisar_web("AI", perfil="rapido")
            self.assertEqual(len(leves), 2)
            self.assertEqual(chamadas["consultas"][-1][1], 2)
            self.assertEqual(chamadas["timeout"], 6)
            chamadas["consultas"].clear()
            top = pesquisar_web("AI", perfil="top", idioma="en")
            self.assertEqual(len(top), 8)
            self.assertEqual(chamadas["region"], "us-en")
            self.assertEqual([quantidade for _, quantidade in chamadas["consultas"]], [5, 3])
            self.assertIn("AI official sources", chamadas["consultas"][1][0])
            self.assertEqual(chamadas["timeout"], 12)
        texto = formatar_resultados(top, idioma="en")
        self.assertIn("not independently verified", texto)
        self.assertIn("https://source1-0.example/article", texto)


class TestHardware(unittest.TestCase):
    def test_normaliza_fabricantes_de_gpu(self):
        self.assertEqual(hardware._normalizar_fabricante("NVIDIA GeForce RTX 3060"), "NVIDIA")
        self.assertEqual(hardware._normalizar_fabricante("AMD Radeon RX 7600"), "AMD")
        self.assertEqual(hardware._normalizar_fabricante("Intel UHD Graphics"), "Intel")

    def test_backend_whisper_retorna_cpu_quando_cuda_nao_disponivel(self):
        modulo = types.ModuleType("ctranslate2")
        modulo.get_cuda_device_count = lambda: 0
        with patch.dict("sys.modules", {"ctranslate2": modulo}):
            backend, motivo = hardware.detectar_backend_whisper()
        self.assertEqual(backend, "cpu")
        self.assertIn("não encontrou", motivo)

    def test_backend_whisper_detecta_cuda_utilizavel(self):
        modulo = types.ModuleType("ctranslate2")
        modulo.get_cuda_device_count = lambda: 1
        with patch.dict("sys.modules", {"ctranslate2": modulo}):
            backend, motivo = hardware.detectar_backend_whisper()
        self.assertEqual(backend, "cuda")
        self.assertIn("1 dispositivo", motivo)

    def test_preparar_runtime_cuda_e_seguro_sem_windows(self):
        if sys.platform == "win32":
            self.skipTest("Teste específico para plataformas não Windows")
        self.assertEqual(hardware.preparar_runtime_cuda(), [])


class TestVozLazy(unittest.TestCase):
    def test_construtor_nao_importa_dependencias_pesadas(self):
        motor = voice.GerenciadorVoz()
        self.assertEqual(motor.device_preferido, "auto")
        self.assertIsNone(motor._np)
        self.assertIsNone(motor._sd)
        self.assertIsNone(motor._WhisperModel)
        self.assertIsNone(motor._pygame)

    def test_silenciar_microfone_descarta_audio_ja_enfileirado(self):
        import queue
        motor = voice.GerenciadorVoz()
        motor._audio_queue.put([0.1, 0.2, 0.3])
        motor.definir_microfone_silenciado(True)
        self.assertTrue(motor.microfone_silenciado)
        self.assertTrue(motor._audio_queue.empty())
        motor.definir_microfone_silenciado(False)
        self.assertFalse(motor.microfone_silenciado)

    def test_fala_cancelada_antes_de_iniciar_nao_carrega_audio(self):
        import threading
        motor = voice.GerenciadorVoz()
        cancelamento = threading.Event()
        cancelamento.set()
        motor.falar("texto que não deve tocar", cancel_event=cancelamento)
        self.assertIsNone(motor._pygame)
        self.assertFalse(motor.falando)

    def test_parar_sinaliza_evento_da_fala_ativa(self):
        motor = voice.GerenciadorVoz()
        evento_cancelamento = __import__("threading").Event()
        motor._active_tts_cancel = evento_cancelamento
        motor.parar()
        self.assertTrue(evento_cancelamento.is_set())

    def test_parar_fala_nao_manipula_pygame_na_thread_externa(self):
        motor = voice.GerenciadorVoz()
        evento_cancelamento = __import__("threading").Event()
        motor._active_tts_cancel = evento_cancelamento
        with patch.object(motor, "_descarregar_audio") as descarregar:
            motor.parar()
        self.assertTrue(evento_cancelamento.is_set())
        descarregar.assert_not_called()

    def test_fechar_nao_descarrega_mixer_fora_do_worker_de_tts(self):
        motor = voice.GerenciadorVoz()
        with patch.object(motor, "_descarregar_audio") as descarregar:
            motor.fechar()
        descarregar.assert_not_called()
        self.assertTrue(motor._tts_cancel.is_set())
        self.assertTrue(motor._escuta_stop.is_set())

    def test_cancelamento_pygame_faz_stop_e_unload_no_thread_de_reproducao(self):
        import threading
        motor = voice.GerenciadorVoz()
        iniciou = threading.Event()
        registros = {}
        class FakeMusic:
            def __init__(self): self.busy = False
            def load(self, _path): registros["load_thread"] = threading.get_ident()
            def play(self):
                self.busy = True
                registros["play_thread"] = threading.get_ident()
                iniciou.set()
            def get_busy(self): return self.busy
            def stop(self):
                registros["stop_thread"] = threading.get_ident()
                self.busy = False
            def unload(self): registros["unload_thread"] = threading.get_ident()
        music = FakeMusic()
        pygame_fake = types.SimpleNamespace(
            mixer=types.SimpleNamespace(get_init=lambda: True, music=music)
        )
        async def gerar(_texto, _genero, caminho, cancel_event=None):
            Path(caminho).write_bytes(b"fake-mp3")
        motor._gerar_audio = gerar
        motor._carregar_pygame = lambda: pygame_fake
        motor._pygame = pygame_fake
        cancelamento = threading.Event()
        trabalhador = threading.Thread(
            target=motor.falar,
            args=("resposta de teste",),
            kwargs={"cancel_event": cancelamento},
        )
        trabalhador.start()
        self.assertTrue(iniciou.wait(2), "a reprodução de teste não iniciou")
        thread_interface = threading.get_ident()
        motor.parar(cancel_event=cancelamento)
        trabalhador.join(2)
        self.assertFalse(trabalhador.is_alive(), "a fala não encerrou após cancelamento")
        self.assertNotEqual(registros["stop_thread"], thread_interface)
        self.assertEqual(registros["stop_thread"], registros["play_thread"])
        self.assertEqual(registros["unload_thread"], registros["play_thread"])

    def test_fallback_sapi_processa_cancelamento_no_proprio_worker(self):
        import threading
        motor = voice.GerenciadorVoz()
        chamada = []
        class FakeEngine:
            def __init__(self): self.busy = True
            def say(self, _texto): chamada.append("say")
            def startLoop(self, _use_driver_loop): chamada.append("start")
            def isBusy(self): return self.busy
            def iterate(self):
                chamada.append("iterate")
                self.busy = False
            def stop(self): chamada.append("stop")
            def endLoop(self): chamada.append("end")
        engine = FakeEngine()
        fake_pyttsx3 = types.ModuleType("pyttsx3")
        fake_pyttsx3.init = lambda: engine
        cancelamento = threading.Event()
        with patch.dict("sys.modules", {"pyttsx3": fake_pyttsx3}):
            motor.fallback_sapi("teste", cancel_event=cancelamento)
        self.assertEqual(chamada, ["say", "start", "iterate", "stop", "end"])

    def test_falha_cuda_ao_parar_a_captura_tenta_cpu(self):
        motor = voice.GerenciadorVoz(device_preferido="cuda")
        motor.whisper_device = "cuda"
        motor._escuta_stop.set()
        modelo_cpu = object()
        callback = []
        with patch.object(motor, "_executar_transcricao", side_effect=[RuntimeError("cuBLAS ausente"), "texto recuperado"]), \
             patch.object(motor, "_criar_modelo_cpu", return_value=modelo_cpu) as criar_cpu:
            motor._transcrever(object(), [0.0], callback.append, forcar=True)
        criar_cpu.assert_called_once()
        self.assertEqual(callback, ["texto recuperado"])

    def test_reamostragem_para_formato_do_whisper(self):
        import numpy as np
        motor = voice.GerenciadorVoz()
        motor._np = np
        audio = np.sin(np.linspace(0, 10, 48000)).astype("float32")
        resultado = motor._reamostrar_audio(audio, 48000, 16000)
        self.assertEqual(len(resultado), 16000)
        self.assertEqual(resultado.dtype, np.float32)

    def test_whisper_respeita_idioma_configurado(self):
        motor = voice.GerenciadorVoz(language="en-US")
        chamadas = {}

        class Segmento:
            text = "hello world"

        class Modelo:
            def transcribe(self, audio, **kwargs):
                chamadas.update(kwargs)
                return [Segmento()], object()

        self.assertEqual(motor._executar_transcricao(Modelo(), [0.0]), "hello world")
        self.assertEqual(chamadas["language"], "en")
        self.assertEqual(motor.voz_feminina, "en-US-AriaNeural")

    def test_vad_calibra_ruido_e_usa_histerese(self):
        inicio, fim = voice.GerenciadorVoz._calcular_limiares_vad(0.003)
        self.assertGreater(inicio, 0.003)
        self.assertGreater(fim, 0.003)
        self.assertLess(fim, inicio)

    def test_modo_continuo_transcreve_varias_falas_com_ruido_ambiente(self):
        import numpy as np
        motor = voice.GerenciadorVoz()
        transcricoes = []
        eventos = []

        class FakeStream:
            def __init__(self, callback):
                self.callback = callback
                self.closed = False

            def start(self):
                quieto = np.full((1600, 1), 0.002, dtype="float32")
                fala = np.full((1600, 1), 0.08, dtype="float32")
                for _ in range(8):
                    self.callback(quieto, 1600, None, None)
                for _ in range(2):
                    for _ in range(4):
                        self.callback(fala, 1600, None, None)
                    for _ in range(7):
                        self.callback(quieto, 1600, None, None)

            def stop(self):
                pass

            def close(self):
                self.closed = True

        streams = []

        class FakeSD:
            def InputStream(self, **kwargs):
                stream = FakeStream(kwargs["callback"])
                streams.append(stream)
                return stream

        motor._np = np
        motor._sd = FakeSD()
        motor._audio_queue = voice.queue.Queue(maxsize=64)
        motor._carregar_dependencias_audio = lambda: None
        motor._carregar_whisper = lambda: object()

        def transcrever(_modelo, _audio, callback, forcar=False):
            callback(f"fala {len(transcricoes) + 1}")
            if len(transcricoes) >= 2:
                motor._escuta_stop.set()
            return True

        def receber(texto):
            transcricoes.append(texto)

        motor._transcrever = transcrever
        motor._loop_escuta(
            receber, None, True,
            callback_pronto=lambda: eventos.append("ready"),
            callback_finalizado=lambda: eventos.append("finished"),
        )
        self.assertEqual(transcricoes, ["fala 1", "fala 2"])
        self.assertEqual(eventos, ["ready", "finished"])
        self.assertTrue(streams[0].closed)

    def test_captura_manual_e_uma_unica_fala_e_notifica_pronto_fim(self):
        import numpy as np
        motor = voice.GerenciadorVoz()
        transcricoes = []
        eventos = []

        class FakeStream:
            def __init__(self, callback):
                self.callback = callback
                self.closed = False

            def start(self):
                # Calibração com ruído ambiente, depois uma fala e seu silêncio.
                for _ in range(8):
                    self.callback(np.full((1600, 1), 0.002, dtype="float32"), 1600, None, None)
                for _ in range(4):
                    self.callback(np.full((1600, 1), 0.08, dtype="float32"), 1600, None, None)
                for _ in range(7):
                    self.callback(np.full((1600, 1), 0.002, dtype="float32"), 1600, None, None)

            def stop(self):
                pass

            def close(self):
                self.closed = True

        class FakeSD:
            def InputStream(self, **kwargs):
                stream = FakeStream(kwargs["callback"])
                streams.append(stream)
                return stream

        streams = []
        motor._np = np
        motor._sd = FakeSD()
        motor._carregar_dependencias_audio = lambda: None
        motor._carregar_whisper = lambda: object()

        def transcrever(_modelo, _audio, callback, forcar=False):
            callback("mensagem de teste")
            return True

        motor._transcrever = transcrever
        motor._loop_escuta(
            transcricoes.append, None, False,
            callback_pronto=lambda: eventos.append("ready"),
            callback_finalizado=lambda: eventos.append("finished"),
        )
        self.assertEqual(transcricoes, ["mensagem de teste"])
        self.assertEqual(eventos, ["ready", "finished"])
        self.assertTrue(streams[0].closed)
        self.assertFalse(motor.ouvindo)

    def test_limpa_markdown_e_omite_codigo(self):
        texto = voice.GerenciadorVoz.limpar_texto_voz(
            "**Olá!** [documentação](https://example.com)\n```python\nprint('segredo')\n```"
        )
        self.assertIn("Olá!", texto)
        self.assertIn("documentação", texto)
        self.assertIn("Trecho de código omitido", texto)
        self.assertNotIn("print", texto)
        self.assertNotIn("https://", texto)

    def test_context_manager_historico_sem_fragmentar_mensagem_antiga(self):
        historico = [
            {"role": "user", "content": "x" * 8},
            {"role": "assistant", "content": "y" * 8},
            {"role": "user", "content": "mensagem nova"},
        ]
        resultado = limitar_historico(historico, limite_caracteres=21)
        self.assertEqual(resultado, [
            {"role": "assistant", "content": "y" * 8},
            {"role": "user", "content": "mensagem nova"},
        ])

    def test_mensagens_fixadas_tem_prioridade_no_contexto(self):
        historico = [
            {"id": 1, "role": "user", "content": "decisão importante", "pinned": True},
            {"id": 2, "role": "assistant", "content": "resposta antiga", "pinned": False},
            {"id": 3, "role": "user", "content": "pergunta mais recente", "pinned": False},
        ]
        resultado = limitar_historico(historico, limite_caracteres=80)
        self.assertEqual(resultado[0]["content"], "decisão importante")
        self.assertEqual(resultado[-1]["content"], "pergunta mais recente")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestInventarioAmbiente(unittest.TestCase):
    def test_inventario_tem_secoes_esperadas_sem_exigir_ollama(self):
        dados = inventario_ambiente.coletar_inventario()
        self.assertIn("python", dados)
        self.assertIn("pacotes", dados)
        self.assertIn("hardware", dados)
        self.assertIn("ollama", dados)
        self.assertIn("modelos_huggingface", dados)
        self.assertIn("disco", dados)
        self.assertIsInstance(dados["modelos_huggingface"], list)

    def test_diretorios_cache_hf_respeitam_variaveis_de_ambiente(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch.dict(os.environ, {"HF_HUB_CACHE": pasta}, clear=False):
                caminhos = inventario_ambiente._diretorios_cache_hf()
            self.assertEqual(caminhos[0], Path(pasta))

    def test_detecta_modelo_huggingface_com_snapshot(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            repo = raiz / "models--Systran--faster-whisper-small"
            (repo / "snapshots" / "abc123").mkdir(parents=True)
            with patch.object(inventario_ambiente, "_diretorios_cache_hf", return_value=[raiz]):
                modelos = inventario_ambiente._modelos_huggingface()
            self.assertEqual(len(modelos), 1)
            self.assertEqual(modelos[0]["repositorio"], "Systran/faster-whisper-small")
            self.assertTrue(modelos[0]["disponivel_localmente"])

    def test_nao_considera_cache_sem_snapshot_pronto(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "models--org--modelo" / "blobs").mkdir(parents=True)
            with patch.object(inventario_ambiente, "_diretorios_cache_hf", return_value=[Path(pasta)]):
                modelos = inventario_ambiente._modelos_huggingface()
            self.assertFalse(modelos[0]["disponivel_localmente"])
