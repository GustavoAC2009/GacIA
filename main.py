"""Ponto de entrada da aplicação desktop Gac.IA (PySide6)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            RotatingFileHandler(BASE_DIR / "gacia.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

def main() -> int:
    configurar_logging()
    try:
        try:
            import PySide6  # noqa: F401
        except ModuleNotFoundError as erro:
            if erro.name == "PySide6":
                mensagem = (
                    "PySide6 não está instalado neste ambiente Python. "
                    "Abra a Gac.IA por iniciar.bat para que o núcleo seja "
                    "verificado e reparado automaticamente."
                )
                logging.error(mensagem)
                print(mensagem, file=sys.stderr)
                return 2
            raise

        from interface import main as executar_interface
        logging.info("Iniciando Gac.IA com PySide6...")
        codigo = executar_interface()
        logging.info("Gac.IA encerrada.")
        return int(codigo or 0)
    except KeyboardInterrupt:
        logging.info("Encerramento solicitado pelo usuário.")
        return 0
    except Exception:
        logging.exception("Erro fatal ao iniciar ou executar a Gac.IA.")
        raise

if __name__ == "__main__":
    raise SystemExit(main())
