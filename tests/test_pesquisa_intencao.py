from unittest.mock import patch
import unittest
from pesquisa_web import detectar_intencao_pesquisa


class TestIntencaoPesquisa(unittest.TestCase):
    def test_pedidos_explicitos_em_portugues(self):
        for texto in (
            "Pesquise na internet os preços atuais",
            "Busque na web as notícias de hoje",
            "Procure na internet a documentação",
            "Confira na internet a versão mais recente",
            "Pesquise fontes atuais sobre Python",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(detectar_intencao_pesquisa(texto))

    def test_pedidos_explicitos_em_ingles(self):
        self.assertTrue(detectar_intencao_pesquisa("Search the web for current releases"))
        self.assertTrue(detectar_intencao_pesquisa("Look up online the latest docs"))

    def test_pergunta_conceitual_nao_dispara_busca(self):
        for texto in (
            "Explique como funciona uma lista em Python",
            "Qual é a diferença entre RAM e VRAM?",
            "Me ajude a resolver esta equação",
            "O que é HTTP?",
            "",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(detectar_intencao_pesquisa(texto))

    def test_detecta_perguntas_que_dependem_de_dados_atuais(self):
        for texto in (
            "Quais são os preços de SSD NVMe?",
            "Qual é a versão mais recente do Python?",
            "Quais notícias temos hoje?",
            "Esse driver tem compatibilidade atual com Windows?",
            "Quanto custa uma RTX 5060 agora?",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(detectar_intencao_pesquisa(texto))

class TestExtracaoPaginas(unittest.TestCase):
    def test_extrator_ignora_scripts_e_estilos(self):
        from pesquisa_web import _ExtratorTextoHTML
        parser = _ExtratorTextoHTML()
        parser.feed("<html><head><title>Fonte oficial</title><script>segredo()</script><style>.x{}</style></head><body><h1>Título</h1><p>Conteúdo útil.</p></body></html>")
        texto = " ".join(parser.partes)
        self.assertIn("Conteúdo útil", texto)
        self.assertNotIn("segredo", texto)
        self.assertNotIn(".x", texto)
        self.assertEqual(" ".join(parser.titulo_partes), "Fonte oficial")

    def test_bloqueia_url_local_e_ip_privado(self):
        from pesquisa_web import _ler_pagina_publica
        for url in ("http://127.0.0.1/admin", "http://localhost/", "http://192.168.0.1/"):
            item = {"href": url, "titulo": "teste", "corpo": "trecho"}
            with self.subTest(url=url):
                self.assertEqual(_ler_pagina_publica(item), item)

    def test_bloqueia_dns_que_resolve_para_ip_privado(self):
        from pesquisa_web import _host_publico_resolve
        with patch("pesquisa_web.socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 0))]):
            self.assertFalse(_host_publico_resolve("evil.example"))
