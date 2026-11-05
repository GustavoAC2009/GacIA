"""Verifica dependências Python, imports e sintaxe sem abrir a interface."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import os
import platform
from pathlib import Path
import struct
import sys
import tokenize

import componentes

BASE_DIR = Path(__file__).resolve().parent

PACOTES_COMPONENTES = {
    "core": (
        ("PySide6", "PySide6"),
        ("requests", "requests"),
        ("Pillow", "PIL"),
    ),
    "office": (
        ("python-docx", "docx"),
        ("openpyxl", "openpyxl"),
        ("python-pptx", "pptx"),
        ("pypdf", "pypdf"),
        ("reportlab", "reportlab"),
    ),
    "ocr": (("pypdfium2", "pypdfium2"), ("pytesseract", "pytesseract")),
    "web": (("ddgs", "ddgs"),),
    "voice": (
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("faster-whisper", "faster_whisper"),
        ("ctranslate2", "ctranslate2"),
        ("pygame", "pygame"),
        ("edge-tts", "edge_tts"),
        ("pyttsx3", "pyttsx3"),
    ),
    "whisper-cuda": (
        ("nvidia-cublas-cu12", None),
        ("nvidia-cudnn-cu12", None),
    ),
}


# Pastas com código-fonte ativo ficam incluídas. Conteúdo de execução e cópias
# importadas pelo agente nunca deve participar da verificação do aplicativo.
DIRETORIOS_IGNORADOS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "runtime",
    "workspaces",
    "backups",
    "exports",
    "generated_images",
}


def _ignorar_diretorio(nome: str) -> bool:
    nome_normalizado = nome.casefold()
    return (
        nome_normalizado in DIRETORIOS_IGNORADOS
        or nome_normalizado.startswith(".venv_backup_")
    )


def listar_arquivos_python(base_dir: Path = BASE_DIR) -> list[Path]:
    """Lista apenas fontes Python ativas, podando diretórios de runtime."""
    base = Path(base_dir).resolve()
    arquivos: list[Path] = []
    for pasta_atual, pastas, nomes in os.walk(base, topdown=True, followlinks=False):
        pastas[:] = sorted(nome for nome in pastas if not _ignorar_diretorio(nome))
        for nome in nomes:
            if nome.endswith(".py"):
                caminho = Path(pasta_atual) / nome
                if not caminho.is_symlink():
                    arquivos.append(caminho)
    return sorted(arquivos)


def verificar_imports(selecionados: list[str] | None = None) -> bool:
    selecionados = componentes.normalizar_componentes(
        selecionados if selecionados is not None else componentes.componentes_para_atualizacao()
    )
    print("Verificando dependências dos componentes: " + ", ".join(selecionados))
    falhas = []
    modulos_verificados: set[str] = set()
    for componente in selecionados:
        for nome, modulo in PACOTES_COMPONENTES.get(componente, ()):
            if modulo is None:
                try:
                    importlib.metadata.version(nome)
                    print(f"[OK] {nome}")
                except importlib.metadata.PackageNotFoundError:
                    falhas.append(nome)
                    print(f"[FALHA] {nome}: distribuição não instalada")
                continue
            if modulo in modulos_verificados:
                continue
            modulos_verificados.add(modulo)
            try:
                importlib.import_module(modulo)
                print(f"[OK] {nome}")
            except Exception as erro:
                falhas.append(nome)
                print(f"[FALHA] {nome}: {type(erro).__name__}: {erro}")
    if "voice" in selecionados and sys.platform == "win32":
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
            print("[OK] pywin32 / SAPI")
        except Exception as erro:
            falhas.append("pywin32")
            print(f"[FALHA] pywin32 / SAPI: {erro}")
    if falhas:
        print("Dependências não importáveis: " + ", ".join(falhas))
        return False
    return True


def python_compativel(version_info=None, pointer_bits: int | None = None, machine: str | None = None) -> bool:
    """Valida CPython 3.13 x64; 64-bit ARM não é confundido com AMD64."""
    version_info = version_info if version_info is not None else sys.version_info
    pointer_bits = pointer_bits if pointer_bits is not None else struct.calcsize("P") * 8
    machine = (machine if machine is not None else platform.machine()).casefold()
    return (
        tuple(version_info[:2]) == (3, 13)
        and pointer_bits == 64
        and machine in {"amd64", "x86_64"}
    )


def verificar_python() -> bool:
    bits = struct.calcsize("P") * 8
    arquitetura = platform.machine() or "desconhecida"
    correto = python_compativel()
    print(
        f"{'[OK]' if correto else '[FALHA]'} Python {sys.version.split()[0]} "
        f"({bits}-bit, {arquitetura}) — esperado: CPython 3.13 x64/AMD64"
    )
    return correto


def verificar_sintaxe(base_dir: Path = BASE_DIR) -> bool:
    """Compila fontes em memória, sem gerar __pycache__ ou tocar em workspaces."""
    base = Path(base_dir).resolve()
    arquivos = listar_arquivos_python(base)
    print(f"Verificando sintaxe de {len(arquivos)} arquivos Python ativos...")
    falhas = []
    for arquivo in arquivos:
        try:
            # tokenize.open respeita declarações de codificação no próprio arquivo.
            with tokenize.open(str(arquivo)) as fonte:
                codigo = fonte.read()
            compile(codigo, str(arquivo), "exec")
        except (SyntaxError, OSError, UnicodeError) as erro:
            falhas.append((arquivo, erro))
            try:
                relativo = arquivo.relative_to(base)
            except ValueError:
                relativo = arquivo
            if isinstance(erro, SyntaxError):
                detalhe = f"linha {erro.lineno}: {erro.msg}"
            else:
                detalhe = f"{type(erro).__name__}: {erro}"
            print(f"[FALHA] {relativo}: {detalhe}")
    if falhas:
        print(f"[FALHA] {len(falhas)} arquivo(s) com problema de leitura/sintaxe.")
        return False
    print(f"[OK] {len(arquivos)} arquivos Python ativos verificados; nenhum bytecode foi gerado.")
    return True


def verificar_hardware(voice_enabled: bool = False) -> bool:
    print("Detectando hardware (somente leitura)...")
    try:
        from hardware import detectar_hardware, resumir_hardware, detectar_backend_whisper
        info = detectar_hardware()
        for linha in resumir_hardware(info):
            print(linha)
        if voice_enabled:
            backend, motivo = detectar_backend_whisper()
            print(f"Backend inicial do Faster-Whisper: {backend.upper()} — {motivo}")
        else:
            print("Voz/Whisper não selecionados; nenhuma biblioteca de inferência foi carregada.")
        print("Ollama seleciona seu próprio backend de GPU, independentemente do Whisper.")
        return True
    except Exception as erro:
        print(f"[AVISO] Não foi possível concluir a detecção de hardware: {erro}")
        return True  # Hardware não deve bloquear a preparação.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--components", default="",
        help="Lista separada por vírgulas: core,office,web,voice,whisper-cuda. Padrão: manifesto local.",
    )
    args = parser.parse_args()
    try:
        selecionados = componentes.normalizar_componentes(
            args.components if args.components else componentes.componentes_para_atualizacao()
        )
    except ValueError as erro:
        print(f"[FALHA] {erro}")
        return 2

    print("=" * 58)
    print("VERIFICAÇÃO DA PREPARAÇÃO — GAC.IA")
    print("=" * 58)
    verificar_hardware(voice_enabled=("voice" in selecionados))
    resultados = (
        verificar_python(),
        verificar_imports(selecionados),
        verificar_sintaxe(),
    )
    print("-" * 58)
    if all(resultados):
        print("[OK] Todas as verificações dos componentes selecionados foram concluídas.")
        return 0
    print("[FALHA] A preparação encontrou problemas.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
