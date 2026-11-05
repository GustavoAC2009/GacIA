"""Gerenciador de componentes da Gac.IA, também usando PySide6."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import webbrowser

try:
    from PySide6.QtCore import Qt, QProcess, QUrl
    from PySide6.QtGui import QDesktopServices, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QFrame, QCheckBox, QPushButton, QTextEdit, QMessageBox,
    )
except ImportError:  # permite importar os helpers em ambientes sem a GUI instalada
    Qt = QProcess = QUrl = QDesktopServices = QTextCursor = QApplication = None
    QMainWindow = object
    QWidget = QVBoxLayout = QHBoxLayout = QLabel = QFrame = QCheckBox = None
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


class GerenciadorGacia(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerenciador — Gac.IA")
        self.resize(820, 760)
        self.setMinimumSize(700, 620)
        self._instalando = False
        self._variaveis: dict[str, QCheckBox] = {}
        self._processo: QProcess | None = None
        self._montar()
        self.atualizar_status()

    def _montar(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(11)
        title = QLabel("Gerenciador da Gac.IA")
        title.setStyleSheet("font-size:22pt;font-weight:750;color:#1C2B42;")
        layout.addWidget(title)
        subtitle = QLabel("Prepare, repare e atualize os recursos opcionais sem apagar suas conversas, modelos ou configurações.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#64748B;")
        layout.addWidget(subtitle)
        self.hardware_label = QLabel("Detectando hardware…")
        self.hardware_label.setWordWrap(True)
        self.hardware_label.setStyleSheet("background:#EDF2FA;border:1px solid #D8E0EC;border-radius:10px;padding:10px;color:#26364F;")
        layout.addWidget(self.hardware_label)

        group = QFrame()
        group.setStyleSheet("QFrame{background:#FFFFFF;border:1px solid #DFE5ED;border-radius:12px;} QLabel{border:0;background:transparent;}")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 14, 16, 14)
        group_layout.setSpacing(8)
        group_title = QLabel("Componentes disponíveis")
        group_title.setStyleSheet("font-size:12pt;font-weight:700;color:#243247;")
        group_layout.addWidget(group_title)
        note = QLabel("O núcleo PySide6 é obrigatório. Os módulos extras são instalados somente quando selecionados. Itens já instalados ou incompletos aparecem marcados para atualização/reparo.")
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
        ollama = QPushButton("Ollama oficial")
        ollama.clicked.connect(lambda: webbrowser.open("https://ollama.com/download"))
        links.addWidget(ollama)
        comfy = QPushButton("ComfyUI oficial")
        comfy.clicked.connect(lambda: webbrowser.open("https://www.comfy.org/download"))
        links.addWidget(comfy)
        data = QPushButton("Pasta de dados")
        data.clicked.connect(self.abrir_dados)
        links.addWidget(data)
        layout.addLayout(links)
        info = QLabel("Atualização do código: extraia uma nova versão sobre a pasta do projeto, mantendo config.json e a pasta data. Componentes desmarcados não são removidos automaticamente.")
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
            self.hardware_label.setText(f"{info.get('cpu', 'CPU não identificada')} · RAM {ram if ram is not None else '?'} GB · {gpu_text or 'GPU não identificada'}")
            tem_nvidia = componentes._nvidia_driver_encontrado()
        except Exception as error:
            tem_nvidia = False
            self.hardware_label.setText(f"Hardware não identificado: {error}")
        states = componentes.detectar_componentes()
        for name, checked in selecoes_iniciais_componentes(states, tem_nvidia).items():
            self._variaveis[name].setChecked(checked)
        self._cuda_check.setEnabled(bool(tem_nvidia and self._variaveis["voice"].isChecked()))
        lines = [f"Núcleo PySide6: {'OK' if states['core']['instalado'] else 'incompleto'}"]
        for name in ("office", "ocr", "web", "voice", "whisper-cuda"):
            state = states[name]
            condition = "instalado" if state["instalado"] else "incompleto — reparável" if state.get("parcial") else "não instalado"
            lines.append(f"{state['nome']}: {condition}")
        self.status_label.setText("  |  ".join(lines))

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
        process.finished.connect(self._installer_finished)
        process.errorOccurred.connect(lambda _error: self._installer_error(process.errorString()))
        self._processo = process
        self._instalando = True
        self.install_button.setEnabled(False)
        self.status_label.setText("Instalador em execução. Acompanhe a janela do PowerShell.")
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
            QMessageBox.information(self, "Gerenciador", "Preparação concluída. Feche e abra a Gac.IA novamente.")
        else:
            QMessageBox.warning(self, "Gerenciador", f"O instalador terminou com código {code}. Consulte os logs do PowerShell.")

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
