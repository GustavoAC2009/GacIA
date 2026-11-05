"""Diagnóstico geométrico da interface PySide6.

Abra a Gac.IA, ajuste o tamanho da janela e pressione F8 para salvar a geometria
real dos principais widgets. Também captura automaticamente após 45 segundos.
Não altera preferências, conversas ou arquivos do usuário.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

BASE_DIR = Path(__file__).resolve().parent


def geometry(widget: QWidget | None) -> dict | None:
    if widget is None:
        return None
    rect = widget.rect()
    frame = widget.frameGeometry()
    return {
        "classe": type(widget).__name__,
        "visivel": widget.isVisible(),
        "x": rect.x(), "y": rect.y(),
        "largura": rect.width(), "altura": rect.height(),
        "root_x": frame.x(), "root_y": frame.y(),
        "largura_minima": widget.minimumWidth(),
        "altura_minima": widget.minimumHeight(),
        "largura_maxima": widget.maximumWidth(),
        "altura_maxima": widget.maximumHeight(),
    }


def collect(app: QMainWindow) -> dict:
    names = (
        "sidebar", "main_panel", "chat_container", "chat_scroll",
        "composer_shell", "composer", "attachment_row", "conversation_host",
    )
    components = {"janela": geometry(app)}
    components.update({name: geometry(getattr(app, name, None)) for name in names})
    screen = app.screen().availableGeometry() if app.screen() else None
    composer = components.get("composer_shell") or {}
    window = components.get("janela") or {}
    spaces = {}
    if composer and window:
        spaces["fim_da_janela_apos_composer_px"] = (
            window.get("altura", 0) - composer.get("y", 0) - composer.get("altura", 0)
        )
    return {
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sistema": sys.platform,
        "tela_disponivel": ({"largura": screen.width(), "altura": screen.height()} if screen else {}),
        "componentes": components,
        "espacos_calculados": spaces,
        "observacao": "Relatório geométrico da interface Qt; não captura pixels nem altera o layout.",
    }


def main() -> int:
    app = QApplication(sys.argv)
    import interface

    # Impede o popup inicial de interceptar a sessão de diagnóstico.
    original = interface.carregar_config
    def config_for_diagnostic():
        config = dict(original())
        config["configuracao_inicial_concluida"] = True
        config["modo_ao_vivo"] = False
        return config

    interface.carregar_config = config_for_diagnostic
    window = interface.GacIAApp()
    done = False

    def capture():
        nonlocal done
        if done:
            return
        done = True
        try:
            destination = BASE_DIR / "data" / "diagnostico_layout.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            report = collect(window)
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[OK] Diagnóstico salvo em: {destination}")
            print(json.dumps(report["espacos_calculados"], ensure_ascii=False, indent=2))
        except Exception as error:
            print(f"[FALHA] {type(error).__name__}: {error}")
        app.quit()

    shortcut = QShortcut(QKeySequence("F8"), window)
    shortcut.activated.connect(capture)
    window.show()
    print("Ajuste a janela e pressione F8 para capturar a geometria. Captura automática em 45 segundos.")
    QTimer.singleShot(45_000, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
