from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory.attachments import (
    MARKER,
    anexar_metadados_anexos,
    extrair_metadados_anexos,
    serializar_metadados_anexos,
    texto_sem_metadados_anexos,
)


class TestAttachmentMetadata(unittest.TestCase):
    def test_persiste_apenas_nome_extensao_e_tamanho_sem_caminho(self):
        with tempfile.TemporaryDirectory() as temp:
            pasta = Path(temp) / "privado"
            pasta.mkdir()
            arquivo = pasta / "foto.teste.png"
            arquivo.write_bytes(b"123456")
            salvo = anexar_metadados_anexos("Analise esta imagem", [str(arquivo)])

        self.assertNotIn(temp, salvo)
        texto, anexos = extrair_metadados_anexos(salvo)
        self.assertEqual(texto, "Analise esta imagem")
        self.assertEqual(anexos, [{
            "name": "foto.teste.png", "extension": ".png", "size_bytes": 6,
        }])

    def test_nao_grava_caminhos_mesmo_quando_recebe_nome_absoluto(self):
        salvo = serializar_metadados_anexos("texto", [{
            "name": r"C:\Users\Gu\Documents\privado.pdf",
            "extension": "pdf", "size_bytes": 12,
        }])
        self.assertNotIn("C:\\Users", salvo)
        self.assertNotIn("Documents", salvo)
        _, anexos = extrair_metadados_anexos(salvo)
        self.assertEqual(anexos[0]["name"], "privado.pdf")
        self.assertEqual(anexos[0]["extension"], ".pdf")

    def test_texto_sem_metadados_preserva_texto_original(self):
        conteudo = serializar_metadados_anexos("mensagem", [{
            "name": "a.docx", "extension": ".docx", "size_bytes": 10,
        }])
        self.assertEqual(texto_sem_metadados_anexos(conteudo), "mensagem")

    def test_metadados_invalidos_nao_apagam_conteudo(self):
        invalido = "mensagem" + MARKER + "{nao-json}--->"
        texto, anexos = extrair_metadados_anexos(invalido)
        self.assertEqual(texto, invalido)
        self.assertEqual(anexos, [])

    def test_limita_quantidade_e_saneia_tamanho_e_extensao(self):
        itens = [{"name": "../arquivo?.pdf", "extension": "../../pdf", "size_bytes": -1}]
        salvo = serializar_metadados_anexos("x", itens)
        _, anexos = extrair_metadados_anexos(salvo)
        self.assertEqual(anexos[0]["name"], "arquivo?.pdf")
        self.assertEqual(anexos[0]["extension"], "")
        self.assertIsNone(anexos[0]["size_bytes"])

    def test_mensagem_sem_anexos_nao_recebe_marcador(self):
        self.assertEqual(anexar_metadados_anexos("normal", []), "normal")
        self.assertEqual(serializar_metadados_anexos("normal", None), "normal")


if __name__ == "__main__":
    unittest.main()
