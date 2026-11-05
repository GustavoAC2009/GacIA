from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import inventario_ambiente
import gerenciador
import preparar_verificar

BASE = Path(__file__).resolve().parents[1]


class TestDependenciasModulares(unittest.TestCase):
    def _linhas(self, nome: str) -> str:
        return (BASE / nome).read_text(encoding="utf-8").lower()

    def test_nucleo_nao_instala_voz_ou_pesquisa_web(self):
        texto = self._linhas("requirements-core.txt")
        self.assertNotIn("ddgs", texto)
        self.assertNotIn("faster-whisper", texto)
        self.assertNotIn("sounddevice", texto)
        self.assertNotIn("requirements-office.txt", texto)
        office = self._linhas("requirements-office.txt")
        self.assertIn("python-docx", office)
        self.assertIn("python-pptx", office)
        self.assertIn("openpyxl", office)

    def test_iniciar_repara_nucleo_quando_venv_existe_sem_pyside6(self):
        texto = self._linhas("iniciar.bat")
        self.assertIn("import pyside6.qtcore, pyside6.qtwidgets, requests, pil", texto)
        self.assertIn("-mode prepare -components core", texto)
        self.assertIn("if errorlevel 1 goto erro_preparacao", texto)
        self.assertLess(
            texto.index("-mode prepare -components core"),
            texto.index('".venv\\scripts\\python.exe" main.py'),
        )

    def test_main_exibe_orientacao_quando_pyside6_ausente(self):
        texto = self._linhas("main.py")
        self.assertIn("abra a gac.ia por iniciar.bat", texto)
        self.assertIn('if erro.name == "pyside6"', texto)

    def test_voz_nao_puxa_cuda_automaticamente(self):
        texto = self._linhas("requirements-voice.txt")
        self.assertIn("faster-whisper", texto)
        self.assertNotIn("nvidia-cublas", texto)
        self.assertNotIn("nvidia-cudnn", texto)

    def test_cuda_fica_em_arquivo_separado(self):
        texto = self._linhas("requirements-nvidia-cuda.txt")
        self.assertIn("nvidia-cublas-cu12", texto)
        self.assertIn("nvidia-cudnn-cu12", texto)

    def test_gerenciador_exige_driver_operacional_para_cuda(self):
        texto = self._linhas("gerenciador.py")
        self.assertIn("componentes._nvidia_driver_encontrado()", texto)

    def test_manifesto_preserva_componentes_desmarcados(self):
        texto = self._linhas("instalador.ps1")
        self.assertIn("$registrados += @($anterior.componentes", texto.lower())
        self.assertIn("move-item -literalpath $venvdir -destination $backup", texto)

    def test_python_64_bits_arm_nao_e_confundido_com_x64(self):
        self.assertTrue(preparar_verificar.python_compativel((3, 13, 5), 64, "AMD64"))
        self.assertTrue(preparar_verificar.python_compativel((3, 13, 5), 64, "x86_64"))
        self.assertFalse(preparar_verificar.python_compativel((3, 13, 5), 64, "ARM64"))
        self.assertFalse(preparar_verificar.python_compativel((3, 12, 9), 64, "AMD64"))
        self.assertFalse(preparar_verificar.python_compativel((3, 13, 5), 32, "AMD64"))

    def test_instalador_powershell_tem_bom_utf8_para_windows_powershell_51(self):
        caminho = BASE / "instalador.ps1"
        self.assertTrue(caminho.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_instalador_preserva_venv_incompleta_antes_de_recriar(self):
        texto = self._linhas("instalador.ps1").lower()
        self.assertIn("platform.machine().lower() in ('amd64','x86_64')", texto)
        self.assertIn("$venvdir = join-path $root '.venv'", texto)
        self.assertIn("if (test-path -literalpath $venvdir)", texto)
        self.assertIn("ambiente incompatível ou incompleto preservado", texto)
        self.assertIn("move-item -literalpath $venvdir -destination $backup", texto)

    def test_gerenciador_nao_preseleciona_extras_ausentes(self):
        estados = {
            "office": {"instalado": False, "parcial": False},
            "ocr": {"instalado": False, "parcial": False},
            "web": {"instalado": False, "parcial": False},
            "voice": {"instalado": False, "parcial": False},
            "whisper-cuda": {"instalado": False, "parcial": False},
        }
        self.assertEqual(
            gerenciador.selecoes_iniciais_componentes(estados, tem_nvidia=True),
            {"office": False, "ocr": False, "web": False, "voice": False, "whisper-cuda": False},
        )

    def test_gerenciador_marca_componentes_parciais_para_reparo(self):
        estados = {
            "web": {"instalado": True, "parcial": False},
            "voice": {"instalado": False, "parcial": True},
            "whisper-cuda": {"instalado": True, "parcial": False},
        }
        self.assertEqual(
            gerenciador.selecoes_iniciais_componentes(estados, tem_nvidia=False),
            {"office": False, "ocr": False, "web": True, "voice": True, "whisper-cuda": False},
        )

    def test_instalacao_inicial_deixa_voz_opcional_por_padrao(self):
        texto = self._linhas("instalador.ps1").lower()
        self.assertIn("$voicedefault = $false", texto)
        self.assertIn("pode adicionar depois no gerenciador", texto)

    def test_inventario_diferencia_componente_parcial(self):
        dados = {
            "python": {"versao": "3.13", "arquitetura_bits": 64},
            "pacotes": {},
            "componentes": {"voice": {
                "nome": "Voz", "instalado": False, "parcial": True,
                "faltantes": ["faster-whisper"],
            }},
            "manifesto_componentes": None,
            "comfyui": {},
            "ollama": {"instalado": False, "servidor_ativo": False,
                       "host_configurado": "http://127.0.0.1:11434", "modelos": []},
            "modelos_huggingface": [],
            "disco": None,
        }
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            inventario_ambiente.imprimir_inventario(dados)
        self.assertIn("PARCIAL — reparável", saida.getvalue())
        self.assertIn("faster-whisper", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
