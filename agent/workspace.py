"""Workspaces isolados para projetos enviados à Gac.IA."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable
import uuid


EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".idea", ".vscode", "coverage", ".next", ".cache",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".py", ".pyw", ".pyi", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".less", ".json", ".jsonc", ".xml", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".java", ".kt", ".kts",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".sql",
    ".sh", ".bat", ".cmd", ".ps1", ".dockerfile", ".gitignore", ".env.example",
    ".vue", ".svelte", ".gradle", ".make", ".mk", ".csv", ".tsv", ".sql", ".log",
}
MAX_ARCHIVE_BYTES = 300 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024


class WorkspaceError(RuntimeError):
    pass


class WorkspaceManager:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir).resolve()
        self.root_dir = self.base_dir / "data" / "workspaces"
        self.state_file = self.base_dir / "data" / "agent_state.json"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.current_id, self.current_root_rel = self._load_state()

    def _load_state(self) -> tuple[str | None, str]:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            workspace_id = data.get("current_workspace_id") if isinstance(data, dict) else None
            root_rel = data.get("current_root_rel", "") if isinstance(data, dict) else ""
            if isinstance(workspace_id, str) and re.fullmatch(r"[a-f0-9]{32}", workspace_id):
                path = self.root_dir / workspace_id
                if path.is_dir() and isinstance(root_rel, str):
                    candidate = (path / Path(*PurePosixPath(root_rel).parts)).resolve() if root_rel else path.resolve()
                    if path.resolve() in candidate.parents or candidate == path.resolve():
                        if candidate.is_dir():
                            return workspace_id, root_rel
        except (OSError, ValueError, TypeError):
            pass
        return None, ""

    def _save_current_id(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps({
            "current_workspace_id": self.current_id,
            "current_root_rel": self.current_root_rel,
        }, indent=2), encoding="utf-8")
        os.replace(temp, self.state_file)

    @staticmethod
    def _is_runtime_data(relative_path: Path) -> bool:
        parts = tuple(part.lower() for part in relative_path.parts)
        return (
            any(part in EXCLUDED_DIRS for part in parts)
            or parts[:2] in {("data", "workspaces"), ("data", "backups"),
                              ("data", "exports"), ("data", "generated_images")}
        )

    @staticmethod
    def _safe_name(value: str) -> str:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "projeto")).strip("._-")
        return (name or "projeto")[:70]

    def create_empty(self, name: str = "projeto") -> Path:
        workspace_id = uuid.uuid4().hex
        folder = self.root_dir / workspace_id
        folder.mkdir(parents=True, exist_ok=False)
        self.current_id = workspace_id
        self.current_root_rel = ""
        self._save_current_id()
        return folder

    def current_path(self) -> Path | None:
        if not self.current_id:
            return None
        workspace = (self.root_dir / self.current_id).resolve()
        if workspace.parent != self.root_dir.resolve() or not workspace.is_dir():
            return None
        path = (workspace / Path(*PurePosixPath(self.current_root_rel).parts)).resolve() if self.current_root_rel else workspace
        if workspace not in path.parents and path != workspace:
            return None
        return path if path.is_dir() else None

    def import_attachments(self, attachments: Iterable[str | Path]) -> Path:
        files = [Path(item).expanduser().resolve() for item in attachments]
        if not files:
            current = self.current_path()
            if current is None:
                raise WorkspaceError("Anexe um arquivo/ZIP ou use /create para começar um projeto novo.")
            return current
        tamanho_total = 0
        for item in files:
            if not item.is_file():
                raise WorkspaceError(f"Arquivo não encontrado: {item.name}")
            tamanho_total += item.stat().st_size
        if len(files) > MAX_ARCHIVE_FILES:
            raise WorkspaceError(f"Anexe no máximo {MAX_ARCHIVE_FILES} arquivos por vez.")
        if tamanho_total > MAX_ARCHIVE_BYTES:
            raise WorkspaceError("O total dos arquivos anexados excede 300 MB.")

        workspace_id = uuid.uuid4().hex
        folder = self.root_dir / workspace_id
        folder.mkdir(parents=True, exist_ok=False)
        try:
            for source in files:
                if source.suffix.lower() == ".zip":
                    self._extract_zip_safely(source, folder)
                else:
                    dest_name = self._safe_name(source.name)
                    dest = folder / dest_name
                    if dest.exists():
                        dest = folder / f"{source.stem}_{uuid.uuid4().hex[:6]}{source.suffix}"
                    shutil.copy2(source, dest)
            top_dirs = [p for p in folder.iterdir() if p.is_dir() and p.name not in EXCLUDED_DIRS]
            top_files = [p for p in folder.iterdir() if p.is_file()]
            self.current_id = workspace_id
            self.current_root_rel = top_dirs[0].name if len(top_dirs) == 1 and not top_files else ""
            self._save_current_id()
            return self.current_path() or folder
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def _extract_zip_safely(self, archive: Path, destination: Path) -> None:
        try:
            with zipfile.ZipFile(archive) as zf:
                infos = [item for item in zf.infolist() if not item.is_dir()]
                if len(infos) > MAX_ARCHIVE_FILES:
                    raise WorkspaceError(f"O ZIP contém mais de {MAX_ARCHIVE_FILES} arquivos.")
                total = sum(item.file_size for item in infos)
                if total > MAX_ARCHIVE_BYTES:
                    raise WorkspaceError("O conteúdo descompactado do ZIP excede 300 MB.")
                for info in zf.infolist():
                    normalized_name = str(info.filename).replace("\\", "/")
                    raw = PurePosixPath(normalized_name)
                    if (
                        raw.is_absolute() or ".." in raw.parts or not raw.parts
                        or re.match(r"^[A-Za-z]:", normalized_name)
                        or "\x00" in normalized_name
                    ):
                        raise WorkspaceError("O ZIP contém um caminho inseguro e foi recusado.")
                    if any(part in EXCLUDED_DIRS for part in raw.parts):
                        continue
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        continue
                    target = (destination / Path(*raw.parts)).resolve()
                    if destination.resolve() not in target.parents and target != destination.resolve():
                        raise WorkspaceError("O ZIP tenta gravar fora da pasta de trabalho.")
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
        except zipfile.BadZipFile as erro:
            raise WorkspaceError("O arquivo ZIP está inválido ou corrompido.") from erro

    def create_generation_dir(self, label: str = "geracao") -> Path:
        """Cria uma pasta exclusiva para os resultados de uma única solicitação."""
        exports = self.base_dir / "data" / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        safe = self._safe_name(label or "geracao")[:32]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = exports / f"{safe}_{stamp}_{uuid.uuid4().hex[:6]}"
        folder.mkdir(parents=True, exist_ok=False)
        return folder.resolve()

    def create_asset_generation_dir(self, label: str = "imagem") -> Path:
        """Cria uma pasta exclusiva em data/generated_images para uma geração visual."""
        root = self.base_dir / "data" / "generated_images"
        root.mkdir(parents=True, exist_ok=True)
        safe = self._safe_name(label or "imagem")[:32]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = root / f"{safe}_{stamp}_{uuid.uuid4().hex[:6]}"
        folder.mkdir(parents=True, exist_ok=False)
        return folder.resolve()

    def output_ref(self, path: Path | str) -> str:
        """Converte um caminho dentro de data/exports em referência segura @output/."""
        root = (self.base_dir / "data" / "exports").resolve()
        candidate = Path(path).resolve()
        if candidate != root and root not in candidate.parents:
            raise WorkspaceError("O caminho de saída está fora da pasta de exportações.")
        return "@output/" + candidate.relative_to(root).as_posix()

    def resolve(self, relative_path: str, must_exist: bool = False) -> Path:
        raw = str(relative_path or "").strip().replace("\\", "/")
        if raw.startswith("@output/"):
            output_root = (self.base_dir / "data" / "exports").resolve()
            suffix = raw[len("@output/"):]
            parts = PurePosixPath(suffix).parts
            if not suffix or not parts or any(part in {"", ".", ".."} for part in parts):
                raise WorkspaceError("Informe um caminho relativo válido dentro da pasta de saída.")
            candidate = (output_root / Path(*parts)).resolve()
            if candidate != output_root and output_root not in candidate.parents:
                raise WorkspaceError("Caminho de saída fora da pasta permitida.")
        else:
            root = self.current_path()
            if root is None:
                raise WorkspaceError("Não há projeto aberto. Anexe um arquivo ou use /create.")
            if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
                raise WorkspaceError("Informe um caminho relativo dentro do projeto.")
            candidate = (root / Path(*PurePosixPath(raw).parts)).resolve()
            if candidate != root.resolve() and root.resolve() not in candidate.parents:
                raise WorkspaceError("Caminho fora da pasta de trabalho não permitido.")
        if must_exist and not candidate.is_file():
            raise WorkspaceError(f"Arquivo não encontrado: {raw}")
        return candidate

    def list_files(self, relative_dir: str = "", limit: int = 300) -> list[dict[str, object]]:
        root = self.current_path()
        if root is None:
            raise WorkspaceError("Não há projeto aberto.")
        directory = root if not relative_dir else self.resolve(relative_dir)
        if not directory.is_dir():
            raise WorkspaceError("A pasta solicitada não existe.")
        results = []
        for item in sorted(directory.rglob("*")):
            try:
                rel = item.relative_to(root)
            except ValueError:
                continue
            if self._is_runtime_data(rel):
                continue
            if item.is_file() and not item.is_symlink():
                results.append({"path": rel.as_posix(), "size": item.stat().st_size})
                if len(results) >= max(1, min(int(limit), 1000)):
                    break
        return results

    def search_files(self, query: str, limit: int = 30) -> list[dict[str, object]]:
        termo = str(query or "").strip().lower()
        if not termo:
            return []
        resultados = []
        for info in self.list_files(limit=1000):
            caminho = str(info["path"])
            path = self.resolve(caminho, must_exist=True)
            if path.suffix.lower() not in TEXT_EXTENSIONS or path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            try:
                conteudo = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            for numero, linha in enumerate(conteudo.splitlines(), 1):
                if termo in linha.lower():
                    resultados.append({"path": caminho, "line": numero, "text": linha[:400]})
                    if len(resultados) >= limit:
                        return resultados
        return resultados

    def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path, must_exist=True)
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise WorkspaceError("Este formato não é texto simples. Use a ferramenta de leitura de documentos.")
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            raise WorkspaceError("O arquivo de texto excede o limite de leitura de 2 MB.")
        return path.read_text(encoding="utf-8-sig", errors="replace")

    def read_text_lines(self, relative_path: str, start_line: int = 1, max_lines: int = 300) -> str:
        texto = self.read_text(relative_path)
        linhas = texto.splitlines()
        inicio = max(1, int(start_line))
        quantidade = max(1, min(int(max_lines), 500))
        trecho = linhas[inicio - 1:inicio - 1 + quantidade]
        if not trecho:
            return f"O arquivo tem {len(linhas)} linhas; a linha inicial solicitada não existe."
        fim = inicio + len(trecho) - 1
        return f"[Linhas {inicio}-{fim} de {len(linhas)}]\n" + "\n".join(trecho)

    def backup_file(self, relative_path: str) -> Path | None:
        """Cria uma cópia versionada antes de substituir um arquivo existente."""
        path = self.resolve(relative_path, must_exist=False)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("Por segurança, só é possível criar backup de arquivos regulares.")
        root = self.current_path()
        if root is None:
            raise WorkspaceError("Não há projeto aberto para criar backup.")
        relative = path.relative_to(root)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root = self.base_dir / "data" / "backups" / str(self.current_id) / stamp
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        return destination

    def write_text(self, relative_path: str, content: str) -> str:
        path = self.resolve(relative_path)
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise WorkspaceError("A edição de formatos binários deve usar a ferramenta específica do documento.")
        texto = str(content or "")
        if len(texto.encode("utf-8")) > MAX_TEXT_FILE_BYTES:
            raise WorkspaceError("O novo conteúdo excede 2 MB.")
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = self.backup_file(relative_path) if path.exists() else None
        temp = path.with_name(path.name + ".gacia.tmp")
        temp.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temp, path)
        detalhe_backup = f" Backup: {backup.relative_to(self.base_dir).as_posix()}." if backup else ""
        return f"Arquivo salvo: {path.name} ({len(texto)} caracteres).{detalhe_backup}"

    def replace_text(self, relative_path: str, replacements: dict[str, str]) -> str:
        path = self.resolve(relative_path, must_exist=True)
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            raise WorkspaceError("A substituição de texto só aceita arquivos textuais.")
        original = self.read_text(relative_path)
        if not isinstance(replacements, dict) or not replacements:
            raise WorkspaceError("Informe um mapa de trechos antigos para novos.")
        updated = original
        total = 0
        for old, new in replacements.items():
            old = str(old)
            if not old:
                raise WorkspaceError("O trecho antigo não pode ser vazio.")
            count = updated.count(old)
            if count != 1:
                raise WorkspaceError(f"O trecho {old[:80]!r} aparece {count} vezes; nenhuma alteração foi feita para evitar substituição ambígua.")
            updated = updated.replace(old, str(new), 1)
            total += 1
        result = self.write_text(relative_path, updated)
        return f"{result} Substituição(ões) exata(s): {total}."

    def export_zip(self) -> Path:
        root = self.current_path()
        if root is None:
            raise WorkspaceError("Não há projeto aberto para exportar.")
        exports = self.base_dir / "data" / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = exports / f"{self._safe_name(root.name)}_GacIA_{stamp}.zip"
        base = root.parent if self.current_root_rel else root
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for item in root.rglob("*"):
                if self._is_runtime_data(item.relative_to(root)):
                    continue
                if item.is_file() and not item.is_symlink():
                    zf.write(item, item.relative_to(base).as_posix())
        return out
