"""Gera um ZIP limpo do código da Gac.IA, sem dados locais ou runtimes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import fnmatch
import zipfile

BASE_DIR = Path(__file__).resolve().parent
NOME_PACOTE = "Gac.IA"

DIRETORIOS_IGNORADOS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "runtime", "workspaces", "backups",
    "exports", "generated_images",
}
ARQUIVOS_IGNORADOS = {
    "config.json",  # Preferências locais; o aplicativo usa DEFAULT_CONFIG se ausente.
    "gacia.log",
    ".gacia-components.json",  # Estado de módulos instalados nesta máquina.
}
PADROES_IGNORADOS = (
    "*.pyc", "*.pyo", "*.log", "*.tmp", "*.db", "*.db-shm", "*.db-wal",
    ".venv_backup_*",
)


def _ignorar_diretorio(nome: str) -> bool:
    normalizado = nome.casefold()
    return normalizado in DIRETORIOS_IGNORADOS or normalizado.startswith(".venv_backup_")


def arquivo_deve_ser_incluido(caminho: Path, base_dir: Path = BASE_DIR) -> bool:
    """Política central de inclusão, exposta para testes."""
    base = Path(base_dir).resolve()
    arquivo = Path(caminho)
    if not arquivo.is_absolute():
        arquivo = base / arquivo
    try:
        relativo = arquivo.resolve().relative_to(base)
    except (OSError, ValueError):
        return False
    if arquivo.is_symlink() or not arquivo.is_file():
        return False
    partes = relativo.parts
    if any(_ignorar_diretorio(parte) for parte in partes[:-1]):
        return False
    nome = relativo.name
    if nome in ARQUIVOS_IGNORADOS:
        return False
    if any(fnmatch.fnmatchcase(nome.casefold(), padrao.casefold()) for padrao in PADROES_IGNORADOS):
        return False
    # Dados de usuário não são parte do código distribuível. Mantém apenas o
    # marcador para que a pasta exista após a extração.
    if partes and partes[0].casefold() == "data":
        return partes == ("data", ".gitkeep")
    return True


def listar_arquivos_pacote(base_dir: Path = BASE_DIR) -> list[Path]:
    base = Path(base_dir).resolve()
    incluidos: list[Path] = []
    for pasta_atual, pastas, nomes in os.walk(base, topdown=True, followlinks=False):
        pastas[:] = sorted(nome for nome in pastas if not _ignorar_diretorio(nome))
        for nome in nomes:
            arquivo = Path(pasta_atual) / nome
            if arquivo_deve_ser_incluido(arquivo, base):
                incluidos.append(arquivo)
    return sorted(incluidos)


def criar_pacote(destino: Path, base_dir: Path = BASE_DIR) -> tuple[Path, int, int]:
    base = Path(base_dir).resolve()
    saida = Path(destino).expanduser().resolve()
    if saida == base:
        raise ValueError("O destino do ZIP precisa ser um arquivo, não a raiz do projeto.")
    if base in saida.parents:
        relativo_saida = saida.relative_to(base)
        if not any(_ignorar_diretorio(parte) for parte in relativo_saida.parts[:-1]):
            raise ValueError(
                "Quando o ZIP ficar dentro do projeto, coloque-o em uma pasta ignorada, como dist/."
            )
    arquivos = listar_arquivos_pacote(base)
    if not arquivos:
        raise RuntimeError("Nenhum arquivo elegível foi encontrado para empacotamento.")

    saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = saida.with_name(saida.name + ".tmp")
    try:
        with zipfile.ZipFile(
            temporario, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as pacote:
            for arquivo in arquivos:
                relativo = arquivo.relative_to(base)
                nome_interno = (Path(NOME_PACOTE) / relativo).as_posix()
                pacote.write(arquivo, nome_interno)
        temporario.replace(saida)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise
    return saida, len(arquivos), saida.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=BASE_DIR / "dist" / "Gac.IA-source.zip",
        help="Caminho do ZIP de saída (padrão: dist/Gac.IA-source.zip).",
    )
    args = parser.parse_args()
    destino, quantidade, tamanho = criar_pacote(args.output)
    print(f"[OK] Pacote criado: {destino}")
    print(f"[OK] Arquivos incluídos: {quantidade}")
    print(f"[OK] Tamanho: {tamanho / (1024 * 1024):.2f} MiB")
    print("Dados locais, configurações pessoais, workspaces, modelos, logs e caches foram excluídos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
