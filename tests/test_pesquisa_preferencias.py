from __future__ import annotations

import unittest
from unittest.mock import patch

from pesquisa_web import pesquisar_web_com_preferencias


class TestPesquisaComPreferencias(unittest.TestCase):
    def _fake_search(self, calls):
        def fake_search(query, max_resultados=None, *, perfil="intermediario", idioma="pt-BR"):
            calls.append(query)
            return [{
                "titulo": f"Fonte {len(calls)}",
                "href": f"https://fonte{len(calls)}.example/pagina",
                "corpo": "Resumo de teste",
                "fonte": f"fonte{len(calls)}.example",
                "data": "",
            }]
        return fake_search

    def test_preferencias_respeitam_orcamento_do_perfil_rapido(self):
        chamadas = []
        with patch("pesquisa_web.pesquisar_web", side_effect=self._fake_search(chamadas)):
            resultados = pesquisar_web_com_preferencias(
                "tema atual", perfil="rapido", preferencias={
                    "oficiais": True, "cientificas": True, "noticias": True,
                },
            )

        self.assertLessEqual(len(resultados), 2)
        self.assertTrue(any("fontes oficiais" in query for query in chamadas))
        self.assertEqual(len({item["href"] for item in resultados}), len(resultados))

    def test_preferencias_cientificas_e_noticias_sao_incluidas_quando_ha_orcamento(self):
        chamadas = []
        with patch("pesquisa_web.pesquisar_web", side_effect=self._fake_search(chamadas)):
            resultados = pesquisar_web_com_preferencias(
                "tema acadêmico", perfil="intermediario", preferencias={
                    "oficiais": True, "cientificas": True, "noticias": True,
                },
            )

        self.assertLessEqual(len(resultados), 5)
        self.assertTrue(any("fontes oficiais" in query for query in chamadas))
        self.assertTrue(any("artigos científicos" in query for query in chamadas))
        self.assertTrue(any("notícias" in query for query in chamadas))


if __name__ == "__main__":
    unittest.main()
