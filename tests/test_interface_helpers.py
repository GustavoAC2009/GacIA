"""Testes isolados de comportamentos da interface sem abrir janela gráfica."""
from __future__ import annotations

import importlib
import sys
import tkinter as tk
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


# Testes de regressão dos helpers da implementação anterior preservada em legacy/.
# A janela principal da aplicação é agora PySide6; estes testes cobrem lógica
# de persistência/contexto que foi mantida durante a migração.
ctk_stub = types.ModuleType("customtkinter")
ctk_stub.CTk = tk.Tk
ctk_stub.set_appearance_mode = lambda *_args, **_kwargs: None
ctk_stub.set_default_color_theme = lambda *_args, **_kwargs: None
with patch.dict(sys.modules, {"customtkinter": ctk_stub}):
    interface = importlib.import_module("legacy.interface_customtkinter")


class FakeWidget:
    def __init__(self, path, children=()):
        self.path = path
        self._children = list(children)
        self.bindings = []
        self._bindtags = ("widget", "class", "toplevel", "all")
        self.master = None
        for child in self._children:
            child.master = self

    def __str__(self):
        return self.path

    def bind(self, sequence, callback, add=None):
        self.bindings.append((sequence, callback, add))

    def winfo_children(self):
        return list(self._children)

    def bindtags(self, tags=None):
        if tags is not None:
            self._bindtags = tuple(tags)
        return self._bindtags


class FakeApp:
    def __init__(self):
        self._message_context_items = {}
        self._conversation_context_items = {}
        self._context_bound_paths = set()
        self._message_context_bindtag = "GacIAMessageContext"
        self._fechando = False
        self.sessao_id = "sessao-teste"
        self.menu_args = None

    def _encontrar_contexto_conversa(self, alvo):
        atual = alvo
        while atual is not None:
            dados = self._conversation_context_items.get(str(atual))
            if dados:
                return dados
            atual = getattr(atual, "master", None)
        return None

    def _mostrar_menu_conversa(self, event, sessao_id, titulo, fixada=False):
        self.conversation_menu_args = (sessao_id, titulo, fixada)
        return "break"

    def _mostrar_menu_mensagem(self, event, mensagem_id, sessao_id, fixada=False, papel="assistant"):
        self.menu_args = (mensagem_id, sessao_id, fixada)
        return "break"

    def winfo_containing(self, *_args):
        return None


class TestInterfaceHelpers(unittest.TestCase):
    def test_comando_e_destacado_sem_colorir_o_resto_da_frase(self):
        class FakeText:
            def __init__(self): self.parts = []
            def insert(self, _where, texto, tags=()): self.parts.append((texto, tags))

        widget = FakeText()
        interface.GacIAApp._inserir_texto_com_destaques(
            None, widget, "Use /analise neste arquivo", None
        )
        marcados = [texto for texto, tags in widget.parts if "command" in tags]
        sem_marca = "".join(texto for texto, tags in widget.parts if "command" not in tags)
        self.assertEqual(marcados, ["/analise"])
        self.assertEqual(sem_marca, "Use  neste arquivo")

    def test_caminho_com_espacos_e_marcado_por_inteiro_para_abrir(self):
        class FakeText:
            def __init__(self): self.parts = []
            def insert(self, _where, texto, tags=()): self.parts.append((texto, tags))

        widget = FakeText()
        caminho = r"C:\Program Files\Gac IA\saida.zip"
        interface.GacIAApp._inserir_texto_com_destaques(
            None, widget, caminho, "inline_code"
        )
        marcados = [texto for texto, tags in widget.parts if "path" in tags]
        self.assertEqual(marcados, [caminho])

    def test_clique_simples_abre_caminho_mas_arrastar_preserva_selecao(self):
        widget = SimpleNamespace(_gacia_path_click_origin=None)
        app = SimpleNamespace(_abrir_caminho_por_tag=Mock(return_value="break"))
        pressionar = SimpleNamespace(widget=widget, x_root=100, y_root=200)
        interface.GacIAApp._marcar_clique_caminho(pressionar)

        clique = SimpleNamespace(widget=widget, x_root=101, y_root=201)
        resultado = interface.GacIAApp._abrir_caminho_se_clique(app, clique)
        self.assertEqual(resultado, "break")
        app._abrir_caminho_por_tag.assert_called_once_with(clique)

        app._abrir_caminho_por_tag.reset_mock()
        interface.GacIAApp._marcar_clique_caminho(pressionar)
        arrasto = SimpleNamespace(widget=widget, x_root=120, y_root=205)
        resultado = interface.GacIAApp._abrir_caminho_se_clique(app, arrasto)
        self.assertIsNone(resultado)
        app._abrir_caminho_por_tag.assert_not_called()

    def test_rotulo_de_anexo_exibe_nome_e_tipo_e_limita_nome_longo(self):
        self.assertEqual(interface._rotulo_anexo("C:/docs/relatorio.pdf"), "relatorio.pdf · PDF")
        rotulo = interface._rotulo_anexo("C:/docs/um_nome_de_arquivo_muito_longo.xlsx")
        self.assertIn("…", rotulo)
        self.assertTrue(rotulo.endswith("· XLSX"))

    def test_contexto_direito_em_conversa_abre_menu_do_chat_inteiro(self):
        interno = FakeWidget(".sidebar.chat.label")
        botao = FakeWidget(".sidebar.chat", [interno])
        app = FakeApp()
        interface.GacIAApp._anexar_menu_contexto_conversa(
            app, botao, "sessao-chat", "Chat de teste", True
        )
        evento = SimpleNamespace(widget=interno, x_root=10, y_root=20)
        resultado = interface.GacIAApp._on_contexto_direito_global(app, evento)
        self.assertEqual(resultado, "break")
        self.assertEqual(app.conversation_menu_args, ("sessao-chat", "Chat de teste", True))

    def test_anexar_contexto_conversa_registra_widgets_internos(self):
        interno = FakeWidget(".sidebar.chat.label")
        botao = FakeWidget(".sidebar.chat", [interno])
        app = FakeApp()
        interface.GacIAApp._anexar_menu_contexto_conversa(
            app, botao, "sessao-chat", "Chat", False
        )
        self.assertEqual(app._conversation_context_items[str(interno)]["sessao_id"], "sessao-chat")
        self.assertFalse(app._conversation_context_items[str(interno)]["fixada"])

    def test_menu_contexto_registra_widgets_internos_e_abre_menu(self):
        texto_interno = FakeWidget(".chat.bubble.text.internal")
        texto = FakeWidget(".chat.bubble.text", [texto_interno])
        canvas = FakeWidget(".chat.bubble.canvas", [texto])
        bubble = FakeWidget(".chat.bubble", [canvas])
        app = FakeApp()
        app._on_contexto_direito_global = lambda _event=None: None

        interface.GacIAApp._anexar_menu_contexto_mensagem(
            app, bubble, 123, "sessao-teste", True
        )

        self.assertIn(str(texto_interno), app._message_context_items)
        self.assertIn("GacIAMessageContext", texto_interno.bindtags())
        self.assertEqual(len(texto_interno.bindings), 0)
        evento = SimpleNamespace(widget=texto_interno, x_root=100, y_root=200)
        resultado = interface.GacIAApp._on_contexto_direito_global(app, evento)
        self.assertEqual(resultado, "break")
        self.assertEqual(app.menu_args, (123, "sessao-teste", True))

    def test_bindtag_de_contexto_e_reaplicado_a_widgets_recriados(self):
        app = FakeApp()
        antigo = FakeWidget(".chat.bubble.text")
        interface.GacIAApp._anexar_menu_contexto_mensagem(
            app, antigo, 10, "sessao-teste", False
        )
        novo = FakeWidget(".chat.bubble.text")
        interface.GacIAApp._anexar_menu_contexto_mensagem(
            app, novo, 11, "sessao-teste", True
        )
        self.assertIn("GacIAMessageContext", antigo.bindtags())
        self.assertIn("GacIAMessageContext", novo.bindtags())
        self.assertEqual(app._message_context_items[str(novo)]["mensagem_id"], 11)
        self.assertTrue(app._message_context_items[str(novo)]["fixada"])

    def test_menu_de_mensagem_exibe_fixar_e_apagar_em_vermelho(self):
        class FakeMenu:
            def __init__(self, *_args, **_kwargs):
                self.commands = []
                self.popup = None

            def add_command(self, **kwargs):
                self.commands.append(kwargs)

            def tk_popup(self, x, y):
                self.popup = (x, y)

            def grab_release(self):
                pass

            def destroy(self):
                pass

        app = SimpleNamespace(
            _fechando=False,
            card_bg="#222222",
            fg_text="#FFFFFF",
            option_button="#336699",
            _texto=lambda pt, en: pt,
            _alternar_fixacao_mensagem=Mock(),
            _apagar_mensagem_historico=Mock(),
        )
        event = SimpleNamespace(x_root=150, y_root=250)
        with patch.object(interface.tk, "Menu", FakeMenu):
            resultado = interface.GacIAApp._mostrar_menu_mensagem(
                app, event, 44, "sessao-teste", False
            )
        self.assertEqual(resultado, "break")
        menu = app._menu_mensagem_contexto
        self.assertIn("Fixar", menu.commands[0]["label"])
        self.assertEqual(menu.commands[1]["label"], "Copiar mensagem")
        self.assertEqual(menu.commands[2]["label"], "Apagar mensagem")
        self.assertEqual(menu.commands[2]["foreground"], "#E53935")
        menu.commands[0]["command"]()
        menu.commands[2]["command"]()
        app._alternar_fixacao_mensagem.assert_called_once_with(44, "sessao-teste", True)
        app._apagar_mensagem_historico.assert_called_once_with(44, "sessao-teste")

    def test_menu_de_mensagem_do_usuario_inclui_editar(self):
        class FakeMenu:
            def __init__(self, *_args, **_kwargs): self.commands = []
            def add_command(self, **kwargs): self.commands.append(kwargs)
            def tk_popup(self, *_args): pass
            def grab_release(self): pass
            def destroy(self): pass

        app = SimpleNamespace(
            _fechando=False, card_bg="#222", fg_text="#fff", option_button="#369",
            _texto=lambda pt, en: pt, _alternar_fixacao_mensagem=Mock(),
            _apagar_mensagem_historico=Mock(), _obter_conteudo_mensagem=Mock(return_value="texto"),
            _abrir_editor_mensagem_por_id=Mock(), copiar_texto=Mock(),
        )
        with patch.object(interface.tk, "Menu", FakeMenu):
            interface.GacIAApp._mostrar_menu_mensagem(
                app, SimpleNamespace(x_root=1, y_root=2), 45, "sessao-teste", False, "user"
            )
        labels = [item.get("label") for item in app._menu_mensagem_contexto.commands]
        self.assertIn("Editar mensagem", labels)
        self.assertIn("Copiar mensagem", labels)

    def test_menu_de_mensagem_mostra_desafixar_quando_ja_fixada(self):
        class FakeMenu:
            def __init__(self, *_args, **_kwargs): self.commands = []
            def add_command(self, **kwargs): self.commands.append(kwargs)
            def tk_popup(self, *_args): pass
            def grab_release(self): pass
            def destroy(self): pass

        app = SimpleNamespace(
            _fechando=False, card_bg="#222", fg_text="#fff", option_button="#369",
            _texto=lambda pt, en: pt,
            _alternar_fixacao_mensagem=Mock(), _apagar_mensagem_historico=Mock(),
        )
        with patch.object(interface.tk, "Menu", FakeMenu):
            interface.GacIAApp._mostrar_menu_mensagem(
                app, SimpleNamespace(x_root=1, y_root=2), 44, "sessao-teste", True
            )
        self.assertIn("Desafixar", app._menu_mensagem_contexto.commands[0]["label"])

    def test_controle_de_mute_altera_somente_entrada_do_microfone(self):
        voz = SimpleNamespace(definir_microfone_silenciado=Mock())
        app = SimpleNamespace(
            modo_ao_vivo=True, voz=voz, _live_microphone_muted=False,
            _atualizar_controle_silencio_live=Mock(),
            atualizar_status=Mock(), _texto=lambda pt, en: pt,
        )
        interface.GacIAApp.alternar_silencio_microfone(app)
        self.assertTrue(app._live_microphone_muted)
        voz.definir_microfone_silenciado.assert_called_once_with(True)
        app._atualizar_controle_silencio_live.assert_called_once()

    def test_botao_de_fala_alterna_entre_alto_falante_e_mudo(self):
        class FakeButton:
            def __init__(self): self.config = {}
            def winfo_exists(self): return True
            def configure(self, **kwargs): self.config.update(kwargs)
        class FakeTooltip:
            def set_text(self, text): self.text = text
        app = SimpleNamespace(_texto=lambda pt, en: pt)
        button = FakeButton()
        button._gacia_voice_tooltip = FakeTooltip()
        interface.GacIAApp._atualizar_botao_fala(app, button, True)
        self.assertEqual(button.config["text"], "🔇")
        self.assertEqual(button._gacia_voice_tooltip.text, "Interromper reprodução")
        interface.GacIAApp._atualizar_botao_fala(app, button, False)
        self.assertEqual(button.config["text"], "🔊")
        self.assertEqual(button._gacia_voice_tooltip.text, "Ouvir resposta")

    def test_apagar_conversa_ativa_limpa_chat_e_volta_para_inicio(self):
        app = SimpleNamespace(
            _texto=lambda pt, en: pt,
            sessao_id="sessao-remover",
            _request_session_id=None,
            _request_id=4,
            _busy=False,
            _request_cancel=None,
            _limpar_area_chat=Mock(),
            exibir_bem_vindo=Mock(),
            atualizar_lista_conversas=Mock(),
            atualizar_status=Mock(),
        )
        with patch.object(interface.messagebox, "askyesno", return_value=True), \
             patch.object(interface, "apagar_conversa", return_value=True) as apagar:
            interface.GacIAApp._apagar_conversa_historico(app, "sessao-remover", "Teste")
        apagar.assert_called_once_with("sessao-remover", preservar_fixadas=True)
        self.assertIsNone(app.sessao_id)
        app._limpar_area_chat.assert_called_once()
        app.exibir_bem_vindo.assert_called_once()
        app.atualizar_lista_conversas.assert_called_once()

    def test_menu_da_conversa_tem_fixar_e_apagar_chat_em_vermelho(self):
        class FakeMenu:
            def __init__(self, *_args, **_kwargs):
                self.commands = []
            def add_command(self, **kwargs): self.commands.append(kwargs)
            def add_separator(self): self.commands.append({"separator": True})
            def tk_popup(self, *_args): pass
            def grab_release(self): pass
            def destroy(self): pass

        app = SimpleNamespace(
            _fechando=False, card_bg="#222", fg_text="#fff", option_button="#369",
            _texto=lambda pt, en: pt,
            _alternar_fixacao_conversa=Mock(), _apagar_conversa_historico=Mock(),
        )
        with patch.object(interface.tk, "Menu", FakeMenu):
            resultado = interface.GacIAApp._mostrar_menu_conversa(
                app, SimpleNamespace(x_root=1, y_root=2), "sessao-1", "Meu chat", False
            )
        self.assertEqual(resultado, "break")
        menu = app._menu_conversa_contexto
        self.assertIn("Fixar conversa", menu.commands[0]["label"])
        self.assertEqual(menu.commands[2]["label"], "Apagar conversa")
        self.assertEqual(menu.commands[2]["foreground"], "#E53935")
        menu.commands[0]["command"]()
        menu.commands[2]["command"]()
        app._alternar_fixacao_conversa.assert_called_once_with("sessao-1", True)
        app._apagar_conversa_historico.assert_called_once_with("sessao-1", "Meu chat")

    def test_stream_de_outra_versao_visual_e_ignorado(self):
        app = SimpleNamespace(
            sessao_id="sessao-teste",
            _request_id=9,
            _request_view_generations={9: 3},
            _chat_view_generation=4,
            _stream_text="",
            _stream_text_widget=None,
        )
        interface.GacIAApp._adicionar_trecho_stream(
            app, "resposta atrasada", session_id="sessao-teste", request_id=9
        )
        self.assertEqual(app._stream_text, "")

    def test_click_global_nao_toma_o_foco_dos_campos(self):
        app = SimpleNamespace(_suggestion_window=None)
        evento = SimpleNamespace(widget=object())
        # Não exige focus_set/after_idle: clicar fora deve deixar o Tk decidir
        # naturalmente qual widget recebe o foco.
        resultado = interface.GacIAApp._on_clique_global(app, evento)
        self.assertIsNone(resultado)

    def test_botao_salvar_so_aparece_quando_configuracao_muda(self):
        class FakeButton:
            def __init__(self):
                self.manager = ""
                self.pack_calls = 0
                self.forget_calls = 0

            def winfo_manager(self):
                return self.manager

            def pack(self, **_kwargs):
                self.manager = "pack"
                self.pack_calls += 1

            def pack_forget(self):
                self.manager = ""
                self.forget_calls += 1

        app = SimpleNamespace(
            btn_salvar_config=FakeButton(),
            _configuracoes_sujas=False,
        )
        interface.GacIAApp._atualizar_botao_salvar_config(app)
        self.assertEqual(app.btn_salvar_config.pack_calls, 0)

        app._configuracoes_sujas = True
        interface.GacIAApp._atualizar_botao_salvar_config(app)
        self.assertEqual(app.btn_salvar_config.pack_calls, 1)
        self.assertEqual(app.btn_salvar_config.manager, "pack")

        # Chamadas repetidas não empilham o mesmo botão novamente.
        interface.GacIAApp._atualizar_botao_salvar_config(app)
        self.assertEqual(app.btn_salvar_config.pack_calls, 1)

        app._configuracoes_sujas = False
        interface.GacIAApp._atualizar_botao_salvar_config(app)
        self.assertEqual(app.btn_salvar_config.forget_calls, 2)  # oculto na criação e ao voltar ao estado salvo
        self.assertEqual(app.btn_salvar_config.manager, "")

    def test_primeiro_clique_inicia_microfone_sem_exigir_segundo(self):
        class FakeVoice:
            def __init__(self):
                self.calls = 0
                self.callbacks = {}

            def iniciar_escuta(self, **kwargs):
                self.calls += 1
                self.callbacks = kwargs
                return True

        voz = FakeVoice()
        fila = []
        estados = []
        app = SimpleNamespace(
            _voice_starting_mode=None,
            gravando_manual=False,
            modo_ao_vivo=False,
            _voice_error=None,
            voz=voz,
            _eventos=SimpleNamespace(put=fila.append),
            _callback_voz_pronto=lambda modo, generation: fila.append(("voice_ready", modo, generation)),
            _texto=lambda pt, en: pt,
            atualizar_estilo_live=lambda: estados.append("estilo"),
            atualizar_status=lambda *args: estados.append(args),
            _obter_gerenciador_voz=lambda: voz,
        )

        interface.GacIAApp.toggle_live(app)
        self.assertEqual(voz.calls, 1)
        self.assertEqual(app._voice_starting_mode, "live")
        self.assertIn("Carregando Whisper", estados[-1][1])

        voz.callbacks["callback_pronto"]()
        self.assertEqual(fila, [("voice_ready", "live", 1)])

    def test_callback_de_voz_de_geracao_antiga_e_ignorado(self):
        app = SimpleNamespace(_voice_generation=8)
        self.assertFalse(interface.GacIAApp._geracao_voz_atual(app, 7))
        self.assertTrue(interface.GacIAApp._geracao_voz_atual(app, 8))


if __name__ == "__main__":
    unittest.main(verbosity=2)
