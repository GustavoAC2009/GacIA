"""Gerenciador de componentes da Gac.IA, também usando PySide6."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import webbrowser

try:
    from PySide6.QtCore import Qt, QProcess, QUrl, QThread, Signal
    from PySide6.QtGui import QDesktopServices, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QFrame, QCheckBox, QPushButton, QTextEdit, QMessageBox, QComboBox,
    )
except ImportError:  # permite importar os helpers em ambientes sem a GUI instalada
    Qt = QProcess = QUrl = QThread = Signal = QDesktopServices = QTextCursor = QApplication = None
    QMainWindow = object
    QWidget = QVBoxLayout = QHBoxLayout = QLabel = QFrame = QCheckBox = QComboBox = None
    QPushButton = QTextEdit = QMessageBox = None

import componentes

BASE_DIR = Path(__file__).resolve().parent
PS_SCRIPT = BASE_DIR / "instalador.ps1"
PYTHON_VENV = BASE_DIR / ".venv" / "Scripts" / "python.exe"


def selecoes_iniciais_componentes(estados: dict, tem_nvidia: bool) -> dict[str, bool]:
    """Marca apenas recursos já instalados/parciais; extras ausentes são opt-in."""
    selecoes = {}
    for nome in ("office", "ocr", "web", "voice", "whisper-cuda"):
        estado = estados.get(nome, {}) if isinstance(estados, dict) else {}
        presente = bool(estado.get("instalado") or estado.get("parcial"))
        if nome == "whisper-cuda":
            presente = presente and bool(tem_nvidia)
        selecoes[nome] = presente
    return selecoes


if QThread is not None:
    class OllamaPullThread(QThread):
        progress_text = Signal(str)
        succeeded = Signal(str)
        failed = Signal(str)

        def __init__(self, tag: str, host: str, parent=None):
            super().__init__(parent)
            self.tag = tag
            self.host = host

        def run(self):
            try:
                from ollama_manager import baixar_modelo
                ultimo_evento = {"chave": None, "tempo": 0.0}

                def atualizar(dados):
                    status = str(dados.get("status") or "Baixando")
                    total = int(dados.get("total") or 0)
                    completed = int(dados.get("completed") or 0)
                    if total > 0:
                        percent = max(0, min(100, int(completed * 100 / total)))
                        texto = f"{status}: {percent}%"
                    else:
                        texto = status
                    agora = time.monotonic()
                    if texto != ultimo_evento["chave"] or agora - ultimo_evento["tempo"] >= 1.0:
                        self.progress_text.emit(texto)
                        ultimo_evento.update(chave=texto, tempo=agora)

                resultado = baixar_modelo(self.tag, self.host, progress=atualizar)
                self.succeeded.emit(resultado)
            except Exception as error:
                self.failed.emit(str(error))


class GerenciadorGacia(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recursos e downloads — Gac.IA")
        self.resize(900, 820)
        self.setMinimumSize(740, 680)
        self._instalando = False
        self._baixando_modelo = False
        self._model_thread = None
        self._status_loaded = False
        self._variaveis: dict[str, QCheckBox] = {}
        self._processo: QProcess | None = None
        self._montar()
        self.atualizar_status()

    def closeEvent(self, event):
        if self._baixando_modelo or self._instalando:
            QMessageBox.information(
                self,
                "Tarefa em andamento",
                "Aguarde a instalação ou o download terminar antes de fechar esta janela.",
            )
            event.ignore()
            return
        event.accept()

    def _montar(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(11)
        title = QLabel("Recursos e downloads")
        title.setStyleSheet("font-size:22pt;font-weight:750;color:#1C2B42;")
        layout.addWidget(title)
        subtitle = QLabel("Veja o que já está pronto e escolha os recursos conforme o que você quer fazer. O básico é verificado automaticamente; itens grandes só são baixados quando você pede.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#64748B;")
        layout.addWidget(subtitle)
        self.hardware_label = QLabel("Detectando hardware…")
        self.hardware_label.setWordWrap(True)
        self.hardware_label.setStyleSheet("background:#EDF2FA;border:1px solid #D8E0EC;border-radius:10px;padding:10px;color:#26364F;")
        layout.addWidget(self.hardware_label)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Quero usar a Gac.IA para:"))
        self.preset = QComboBox()
        self.preset.addItem("Escolher manualmente", "manual")
        self.preset.addItem("Criar e editar documentos, planilhas, slides e PDFs", "office")
        self.preset.addItem("Pesquisar informações na internet", "web")
        self.preset.addItem("Falar e transcrever áudio", "voice")
        self.preset.addItem("Documentos e pesquisa", "office-web")
        self.preset.addItem("Documentos, pesquisa e voz", "office-web-voice")
        self.preset.currentIndexChanged.connect(self.aplicar_preset)
        preset_row.addWidget(self.preset, 1)
        layout.addLayout(preset_row)

        group = QFrame()
        group.setStyleSheet("QFrame{background:#FFFFFF;border:1px solid #DFE5ED;border-radius:12px;} QLabel{border:0;background:transparent;}")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 14, 16, 14)
        group_layout.setSpacing(8)
        group_title = QLabel("Componentes disponíveis")
        group_title.setStyleSheet("font-size:12pt;font-weight:700;color:#243247;")
        group_layout.addWidget(group_title)
        note = QLabel("O núcleo da interface é obrigatório. Marque apenas o que pretende usar; itens já instalados ou incompletos aparecem identificados. PDFs escaneados também precisam do Tesseract, um aplicativo separado.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#68778C;font-size:9pt;")
        group_layout.addWidget(note)
        definitions = [
            ("office", "Documentos e produtividade", "Word, Excel, PowerPoint e PDF."),
            ("ocr", "OCR para PDFs digitalizados", "Reconhecimento de texto; também requer Tesseract instalado no Windows."),
            ("web", "Pesquisa na web", "Pesquisa em fontes públicas quando necessária."),
            ("voice", "Voz e microfone", "Transcrição local, captura de áudio e síntese de voz; modelo Whisper baixado ao usar."),
            ("whisper-cuda", "Aceleração NVIDIA para Whisper", "Bibliotecas CUDA/cuDNN adicionais; exige Voz e driver NVIDIA operacional."),
        ]
        for key, name, description in definitions:
            checkbox = QCheckBox(name)
            checkbox.setStyleSheet("font-weight:650;color:#26364F;")
            if key == "voice":
                checkbox.toggled.connect(self._atualizar_habilitacao_cuda)
            group_layout.addWidget(checkbox)
            hint = QLabel(description)
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6B7788;font-size:9pt;padding-left:25px;")
            group_layout.addWidget(hint)
            self._variaveis[key] = checkbox
        self._cuda_check = self._variaveis["whisper-cuda"]
        layout.addWidget(group)

        self.status_label = QLabel("Verificando componentes…")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#64748B;")
        layout.addWidget(self.status_label)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Modelo de conversa:"))
        self.model_choice = QComboBox()
        self.model_choice.addItem("Leve · Qwen 3.5 2B", "rapido")
        self.model_choice.addItem("Intermediário · Qwen 3.5 4B", "intermediario")
        self.model_choice.addItem("Avançado · Qwen 3.5 9B", "top")
        model_row.addWidget(self.model_choice, 1)
        self.download_model_button = QPushButton("Baixar e usar modelo")
        self.download_model_button.clicked.connect(self.baixar_modelo_escolhido)
        model_row.addWidget(self.download_model_button)
        layout.addLayout(model_row)
        model_hint = QLabel("O download é feito pelo Ollama instalado no PC. Modelos maiores ocupam mais espaço e usam mais memória; a recomendação considera a RAM e a GPU detectadas.")
        model_hint.setWordWrap(True)
        model_hint.setStyleSheet("color:#68778C;font-size:9pt;")
        layout.addWidget(model_hint)
        buttons = QHBoxLayout()
        self.install_button = QPushButton("Instalar / atualizar selecionados")
        self.install_button.setStyleSheet("background:#4169D8;color:white;font-weight:700;padding:10px 14px;border-radius:8px;")
        self.install_button.clicked.connect(self.instalar_selecionados)
        buttons.addWidget(self.install_button)
        refresh = QPushButton("Verificar componentes")
        refresh.clicked.connect(self.atualizar_status)
        buttons.addWidget(refresh)
        diag = QPushButton("Diagnóstico")
        diag.clicked.connect(self.diagnostico)
        buttons.addWidget(diag)
        layout.addLayout(buttons)

        links = QHBoxLayout()
        open_app = QPushButton("Abrir Gac.IA")
        open_app.clicked.connect(self.abrir_gacia)
        links.addWidget(open_app)
        ollama = QPushButton("Instalar Ollama (site oficial)")
        ollama.clicked.connect(lambda: webbrowser.open("https://ollama.com/download"))
        links.addWidget(ollama)
        comfy = QPushButton("Preparar imagens (ComfyUI)")
        comfy.clicked.connect(lambda: webbrowser.open("https://www.comfy.org/download"))
        links.addWidget(comfy)
        data = QPushButton("Pasta de dados")
        data.clicked.connect(self.abrir_dados)
        links.addWidget(data)
        layout.addLayout(links)
        info = QLabel("Modelos de IA e o ComfyUI podem ocupar vários GB e não são baixados sem sua escolha. Componentes desmarcados não são removidos. O status mostra se o Ollama, seu modelo e o ComfyUI estão disponíveis.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#78869A;font-size:8pt;")
        layout.addWidget(info)
        self.diag_text = QTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setPlaceholderText("A saída do diagnóstico aparecerá aqui.")
        self.diag_text.setMinimumHeight(120)
        self.diag_text.setStyleSheet("background:#F8FAFC;border:1px solid #E1E7EF;border-radius:8px;font-family:Consolas;")
        layout.addWidget(self.diag_text, 1)
        self.setStyleSheet("QMainWindow,QWidget{background:#F4F6FA;color:#26364F;font-family:'Segoe UI';font-size:10pt;} QPushButton{padding:8px;border:1px solid #D7DFE9;border-radius:7px;background:white;} QPushButton:hover{background:#EAF0F8;} QCheckBox{spacing:8px;}")

    def atualizar_status(self):
        try:
            info = __import__("hardware").detectar_hardware()
            ram = info.get("ram_gb")
            gpus = info.get("gpus") or []
            gpu_text = ", ".join(f"{g.get('name', 'GPU')} [{g.get('vendor', '?')}]" for g in gpus)
            try:
                from config import carregar_config
                from ollama_manager import listar_modelos
                configuracao = carregar_config()
                modelos = listar_modelos(configuracao.get("ollama_host", "http://localhost:11434"), timeout=1.2)
                nomes_modelos = [str(m.get("name") or m.get("model") or "") for m in modelos]
                modelo_status = "Ollama: pronto" + (" · modelos: " + ", ".join(nomes_modelos[:3]) if nomes_modelos else " · nenhum modelo baixado")
            except Exception:
                app_local = shutil.which("ollama")
                if not app_local and os.name == "nt":
                    candidatos = [
                        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
                        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ollama" / "ollama.exe",
                    ]
                    app_local = next((str(path) for path in candidatos if path.is_file()), None)
                modelo_status = "Ollama instalado, mas fechado" if app_local else "Ollama não instalado"
            try:
                import requests
                from config import carregar_config
                cfg = carregar_config()
                base_url = str((cfg.get("gerador_imagens") or {}).get("url", "http://127.0.0.1:8188")).rstrip("/")
                response = requests.get(base_url + "/system_stats", timeout=0.7)
                if response.ok:
                    try:
                        from image_generator import listar_checkpoints
                        checkpoints = listar_checkpoints(base_url, timeout=0.8)
                    except Exception:
                        checkpoints = []
                    comfy_status = f"ComfyUI: conectado · {len(checkpoints)} modelo(s) de imagem" if checkpoints else "ComfyUI: conectado, mas sem modelo de imagem"
                else:
                    comfy_status = "ComfyUI: não conectado"
            except Exception:
                comfy_status = "ComfyUI: não conectado"
            self.hardware_label.setText(
                f"PC: {info.get('cpu', 'CPU não identificada')} · RAM {ram if ram is not None else '?'} GB · {gpu_text or 'GPU não identificada'}\n"
                f"{modelo_status} · {comfy_status}"
            )
            tem_nvidia = componentes._nvidia_driver_encontrado()
            try:
                from componentes import recomendar_componentes
                recomendado = recomendar_componentes(info).get("llm_profile", "intermediario")
                idx = self.model_choice.findData(recomendado)
                if idx >= 0:
                    self.model_choice.setCurrentIndex(idx)
            except Exception:
                pass
        except Exception as error:
            tem_nvidia = False
            self.hardware_label.setText(f"Hardware não identificado: {error}")
        states = componentes.detectar_componentes()
        if not self._status_loaded or (self._processo is not None and not self._instalando):
            for name, checked in selecoes_iniciais_componentes(states, tem_nvidia).items():
                self._variaveis[name].setChecked(checked)
            self._status_loaded = True
        self._cuda_check.setEnabled(bool(tem_nvidia and self._variaveis["voice"].isChecked()))
        lines = [f"Núcleo PySide6: {'OK' if states['core']['instalado'] else 'incompleto'}"]
        for name in ("office", "ocr", "web", "voice", "whisper-cuda"):
            state = states[name]
            condition = "instalado" if state["instalado"] else "incompleto — reparável" if state.get("parcial") else "não instalado"
            lines.append(f"{state['nome']}: {condition}")
        self.status_label.setText("\n".join(lines))

    def baixar_modelo_escolhido(self):
        if self._baixando_modelo:
            return
        try:
            from config import carregar_config
            from ollama_manager import MODELOS, listar_modelos
            config = carregar_config()
            host = str(config.get("ollama_host", "http://localhost:11434"))
            perfil = str(self.model_choice.currentData() or "intermediario")
            tag = MODELOS[perfil]["tag"]
            try:
                existentes = listar_modelos(host, timeout=2.0)
            except Exception as error:
                QMessageBox.warning(self, "Ollama indisponível", "Instale e abra o Ollama primeiro.\n\n" + str(error))
                return
            nomes = {str(item.get("name") or item.get("model") or "") for item in existentes}
            if tag in nomes:
                self._ativar_modelo(perfil, tag)
                QMessageBox.information(self, "Modelo já disponível", f"{tag} já está baixado e selecionado. Feche e abra a Gac.IA para começar a usá-lo.")
                return
            detalhes = MODELOS[perfil]
            aviso = (
                f"Baixar {tag} (aproximadamente {detalhes['tamanho_gb']:.1f} GB)?\n\n"
                "O espaço livre em disco e a velocidade da internet afetam o tempo. "
                "O uso de memória durante as respostas é maior que o tamanho do download."
            )
            if QMessageBox.question(self, "Confirmar download", aviso, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self._baixando_modelo = True
            self.download_model_button.setEnabled(False)
            self._append_diagnostic(f"Baixando {tag} pelo Ollama…\n")
            self._model_thread = OllamaPullThread(tag, host, self)
            self._perfil_download = perfil
            self._model_thread.progress_text.connect(self._append_diagnostic)
            self._model_thread.succeeded.connect(self._modelo_baixado)
            self._model_thread.failed.connect(self._falha_download_modelo)
            self._model_thread.start()
        except Exception as error:
            QMessageBox.warning(self, "Download", f"Não foi possível iniciar o download: {error}")

    def _modelo_baixado(self, tag: str):
        self._baixando_modelo = False
        self.download_model_button.setEnabled(True)
        self._ativar_modelo(getattr(self, "_perfil_download", "intermediario"), tag)
        self._append_diagnostic(f"\nDownload concluído: {tag}\n")
        self.atualizar_status()
        QMessageBox.information(self, "Modelo pronto", f"{tag} foi baixado e selecionado. Feche e abra a Gac.IA para começar a usá-lo.")

    @staticmethod
    def _ativar_modelo(perfil: str, tag: str):
        from config import carregar_config, salvar_config
        config = carregar_config()
        config["perfil_ativo"] = perfil
        config.setdefault("modelos", {})[perfil] = tag
        salvar_config(config)

    def _falha_download_modelo(self, erro: str):
        self._baixando_modelo = False
        self.download_model_button.setEnabled(True)
        self._append_diagnostic(f"\nDownload não concluído: {erro}\n")
        QMessageBox.warning(self, "Falha no download", "O Ollama não concluiu o download. Confira a conexão e tente novamente.\n\n" + erro)

    def aplicar_preset(self, _index: int):
        selecao = {
            "manual": None,
            "office": {"office"},
            "web": {"web"},
            "voice": {"voice"},
            "office-web": {"office", "web"},
            "office-web-voice": {"office", "web", "voice"},
        }.get(self.preset.currentData())
        if selecao is None:
            return
        for nome, caixa in self._variaveis.items():
            if nome != "whisper-cuda":
                caixa.setChecked(nome in selecao)
        self._atualizar_habilitacao_cuda()

    def _atualizar_habilitacao_cuda(self):
        enabled = self._variaveis["voice"].isChecked()
        try:
            enabled = enabled and componentes._nvidia_driver_encontrado()
        except Exception:
            enabled = False
        self._cuda_check.setEnabled(bool(enabled))
        if not enabled:
            self._cuda_check.setChecked(False)

    def instalar_selecionados(self):
        if self._instalando:
            return
        if os.name != "nt":
            QMessageBox.critical(self, "Gerenciador", "A instalação automática está preparada para Windows 10/11 x64.")
            return
        chosen = [name for name in ("office", "ocr", "web", "voice", "whisper-cuda") if self._variaveis[name].isChecked()]
        chosen.insert(0, "core")
        try:
            componentes.normalizar_componentes(chosen)
        except ValueError as error:
            QMessageBox.critical(self, "Componentes", str(error))
            return
        if "whisper-cuda" in chosen and not componentes._nvidia_driver_encontrado():
            QMessageBox.warning(self, "CUDA", "Não foi encontrado um driver NVIDIA operacional. Desmarque CUDA para usar Whisper pela CPU.")
            return
        confirm = QMessageBox.question(self, "Preparar Gac.IA", "O instalador adicionará/atualizará os componentes selecionados.\n\nNenhum modelo, conversa, configuração ou runtime será apagado. Continuar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        command = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS_SCRIPT), "-Mode", "Update", "-Components", ",".join(chosen)]
        process = QProcess(self)
        process.setProgram(command[0])
        process.setArguments(command[1:])
        process.setWorkingDirectory(str(BASE_DIR))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda p=process: self._append_diagnostic(bytes(p.readAllStandardOutput()).decode("utf-8", errors="replace"))
        )
        process.finished.connect(self._installer_finished)
        process.errorOccurred.connect(lambda _error: self._installer_error(process.errorString()))
        self._processo = process
        self._instalando = True
        self.install_button.setEnabled(False)
        self.status_label.setText("Instalando os itens selecionados. Acompanhe o progresso nesta janela; isso pode levar alguns minutos.")
        self.diag_text.clear()
        self._append_diagnostic("Preparando os recursos selecionados…\n\n")
        process.start()
        if not process.waitForStarted(5000):
            self._installer_error(process.errorString())

    def _installer_error(self, message: str):
        self._instalando = False
        self.install_button.setEnabled(True)
        QMessageBox.critical(self, "Instalador", "Não foi possível iniciar o PowerShell: " + message)

    def _installer_finished(self, code: int, _status):
        self._instalando = False
        self.install_button.setEnabled(True)
        self.atualizar_status()
        if code == 0:
            self._append_diagnostic("\nPreparação concluída.\n")
            QMessageBox.information(self, "Recursos prontos", "A preparação terminou. Os recursos selecionados já podem ser usados; alguns podem exigir reiniciar a Gac.IA.")
        else:
            self._append_diagnostic(f"\nA preparação terminou com código {code}.\n")
            QMessageBox.warning(self, "Não foi possível concluir", f"A preparação terminou com código {code}. Veja os detalhes nesta janela e confira sua conexão com a internet.")

    def diagnostico(self):
        python = str(PYTHON_VENV) if PYTHON_VENV.is_file() else sys.executable
        script = BASE_DIR / "inventario_ambiente.py"
        process = QProcess(self)
        process.setProgram(python)
        process.setArguments([str(script)])
        process.setWorkingDirectory(str(BASE_DIR))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self._append_diagnostic(bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")))
        process.finished.connect(lambda _code, _status: self._append_diagnostic("\nDiagnóstico finalizado.\n"))
        self.diag_text.clear()
        self._append_diagnostic("Executando inventário…\n")
        process.start()
        self._diagnostic_process = process

    def _append_diagnostic(self, text: str):
        self.diag_text.moveCursor(QTextCursor.End)
        self.diag_text.insertPlainText(text)

    def abrir_gacia(self):
        iniciar = BASE_DIR / "iniciar.bat"
        if not iniciar.is_file():
            QMessageBox.critical(self, "Gac.IA", "O arquivo iniciar.bat não foi encontrado.")
            return
        try:
            os.startfile(str(iniciar))
        except (AttributeError, OSError) as error:
            QMessageBox.critical(self, "Gac.IA", f"Não foi possível abrir a aplicação: {error}")

    def abrir_dados(self):
        folder = BASE_DIR / "data"
        folder.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def main() -> int:
    if QApplication is None:
        print("PySide6 não está instalado. Execute preparar.bat para instalar o núcleo da Gac.IA.")
        return 1
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Gerenciador Gac.IA")
    window = GerenciadorGacia()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
