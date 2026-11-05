import ast
import unittest
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "interface.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method_source(class_name: str, method_name: str) -> str:
    cls = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name)
    return ast.get_source_segment(SOURCE, method) or ""


class TestInterfaceQtLayout(unittest.TestCase):
    def test_reabrir_sidebar_fica_fora_da_sidebar_colapsada(self):
        code = method_source("GacIAApp", "_build_ui")
        self.assertIn("self.sidebar_open_button", code)
        self.assertIn("self.sidebar_open_button.clicked.connect(self.toggle_sidebar)", code)
        self.assertIn("self.sidebar_open_button.setVisible(self.sidebar_collapsed)", code)
        self.assertIn("self.sidebar_open_button.setVisible(self.sidebar_collapsed)", method_source("GacIAApp", "toggle_sidebar"))

    def test_menu_superior_tem_apenas_nome_conta_e_tema(self):
        code = method_source("GacIAApp", "_build_ui")
        self.assertIn('self.user_button.setToolButtonStyle(Qt.ToolButtonTextOnly)', code)
        self.assertIn('self.user_menu.addAction("Alterar nome")', code)
        self.assertIn('self.user_menu.addAction("Configurações da conta")', code)
        self.assertIn('self.user_menu.addMenu("Tema")', code)

    def test_perfil_da_ia_fica_antes_de_pensar_mais_e_icone_e_cerebro(self):
        code = method_source("GacIAApp", "_build_ui")
        self.assertLess(code.index("controls.addWidget(self.model_profile)"), code.index("controls.addWidget(self.thinking_button)"))
        self.assertIn('self.thinking_button.setText("🧠  Pensar mais")', code)

    def test_mais_abre_janela_horizontal_com_todas_as_ferramentas_sem_scroll(self):
        code = method_source("GacIAApp", "_show_tools_menu")
        self.assertIn("QDialog(self, Qt.Popup | Qt.FramelessWindowHint)", code)
        self.assertIn("QGridLayout()", code)
        self.assertIn("popup.exec()", code)
        self.assertIn("columns = 5", code)
        self.assertNotIn("QScrollArea", code)
        self.assertNotIn("ScrollBarAsNeeded", code)
        self.assertIn("CRIAR E EDITAR", SOURCE)

    def test_respostas_de_geracao_mostram_previa_e_acao_para_abrir_pasta(self):
        build = method_source("MessageCard", "_build")
        populate = method_source("MessageCard", "_populate_output_previews")
        self.assertIn("self.output_preview", build)
        self.assertIn("self._populate_output_previews()", build)
        self.assertIn(".pptx", populate)
        self.assertIn(".epub", populate)
        self.assertIn("Abrir diretório do arquivo", populate)
        self.assertIn("Abrir arquivo", populate)

    def test_caminho_na_resposta_e_convertido_em_link_para_pasta(self):
        code = method_source("MessageCard", "_linkify_local_paths")
        self.assertIn("gacia-path://open/", code)
        self.assertIn("directory = candidate.parent", code)

    def test_chat_ao_vivo_e_cancelamento_compartilham_slot_condicional(self):
        build = method_source("GacIAApp", "_build_ui")
        send = method_source("GacIAApp", "send_message")
        finish = method_source("GacIAApp", "_finish_request")
        self.assertIn("self.voice_stop_stack.addWidget(self.live_button)", build)
        self.assertIn("self.voice_stop_stack.addWidget(self.stop_button)", build)
        self.assertIn("self.voice_stop_stack.setCurrentIndex(1)", send)
        self.assertIn("self.voice_stop_stack.setCurrentIndex(0)", finish)
        self.assertIn('self.live_button.setText("🎧")', build)

    def test_usuario_direita_assistente_esquerda_e_azul_padrao(self):
        code = method_source("GacIAApp", "_append_card")
        self.assertIn("Qt.AlignRight", code)
        self.assertIn("Qt.AlignLeft", code)
        self.assertIn('"accent": "#2563EB"', SOURCE)
        self.assertIn('"user": "#2563EB"', SOURCE)

    def test_scroll_horizontal_de_conversas_desativado_e_barras_estilizadas(self):
        code = method_source("GacIAApp", "_build_ui")
        self.assertIn("self.conversation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)", code)
        self.assertIn("QScrollBar::handle:horizontal", method_source("GacIAApp", "_apply_theme"))
