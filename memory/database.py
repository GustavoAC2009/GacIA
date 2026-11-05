"""Persistência SQLite local da Gac.IA, com conexões curtas por operação."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "memory.db"


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão isolada e garante commit/rollback e fechamento."""
    caminho = Path(DB_PATH)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(str(caminho), timeout=10)
    try:
        conexao.execute("PRAGMA busy_timeout = 10000")
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def init_db() -> None:
    """Cria apenas a tabela usada pela versão atual; não remove dados antigos."""
    with conectar() as conexao:
        conexao.execute("PRAGMA journal_mode = WAL")
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao_id TEXT NOT NULL,
                papel TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                fixada INTEGER NOT NULL DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_historico_sessao_id_id "
            "ON historico (sessao_id, id)"
        )
        # Migração aditiva: bancos existentes recebem a coluna sem perder mensagens.
        colunas_historico = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(historico)").fetchall()
        }
        if "fixada" not in colunas_historico:
            conexao.execute(
                "ALTER TABLE historico ADD COLUMN fixada INTEGER NOT NULL DEFAULT 0"
            )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS conversas_gacia (
                sessao_id TEXT PRIMARY KEY,
                titulo TEXT NOT NULL DEFAULT 'Nova conversa',
                fixada INTEGER NOT NULL DEFAULT 0,
                criada_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                atualizada_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        colunas_conversas = {
            linha[1] for linha in conexao.execute("PRAGMA table_info(conversas_gacia)").fetchall()
        }
        if "fixada" not in colunas_conversas:
            conexao.execute(
                "ALTER TABLE conversas_gacia ADD COLUMN fixada INTEGER NOT NULL DEFAULT 0"
            )
        # Memórias salvas são independentes do histórico de cada conversa.
        # Mensagens marcadas como importantes também são preservadas ao excluir um chat.
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS memorias_salvas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conteudo TEXT NOT NULL UNIQUE,
                papel TEXT NOT NULL DEFAULT 'user',
                origem_sessao_id TEXT,
                origem_mensagem_id INTEGER,
                criada_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Tombstones impedem uma resposta atrasada de recriar um chat excluído.
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS conversas_excluidas (
                sessao_id TEXT PRIMARY KEY,
                excluida_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migra sessões antigas sem apagar nenhuma mensagem.
        sessoes_antigas = conexao.execute(
            "SELECT sessao_id, MIN(id) FROM historico GROUP BY sessao_id"
        ).fetchall()
        for sessao_id, _primeiro_id in sessoes_antigas:
            primeira = conexao.execute(
                "SELECT conteudo FROM historico WHERE sessao_id = ? AND papel = 'user' "
                "ORDER BY id LIMIT 1", (sessao_id,)
            ).fetchone()
            titulo = (primeira[0] if primeira else "Nova conversa").strip() or "Nova conversa"
            titulo = " ".join(titulo.split())[:48]
            conexao.execute(
                "INSERT OR IGNORE INTO conversas_gacia (sessao_id, titulo) VALUES (?, ?)",
                (sessao_id, titulo),
            )


def salvar_mensagem(sessao_id: str, papel: str, conteudo: str) -> int:
    if papel not in {"user", "assistant", "system"}:
        raise ValueError("Papel de mensagem inválido.")
    sessao_id = str(sessao_id or "").strip()
    if not sessao_id:
        raise ValueError("O identificador da sessão não pode estar vazio.")
    texto = str(conteudo or "")
    with conectar() as conexao:
        excluida = conexao.execute(
            "SELECT 1 FROM conversas_excluidas WHERE sessao_id = ?", (sessao_id,)
        ).fetchone()
        if excluida:
            raise RuntimeError("Esta conversa foi excluída e não aceita novas mensagens.")
        conexao.execute(
            "INSERT OR IGNORE INTO conversas_gacia (sessao_id, titulo) VALUES (?, 'Nova conversa')",
            (sessao_id,),
        )
        conexao.execute(
            "INSERT INTO historico (sessao_id, papel, conteudo) VALUES (?, ?, ?)",
            (sessao_id, papel, texto),
        )
        conexao.execute(
            "UPDATE conversas_gacia SET atualizada_em = CURRENT_TIMESTAMP WHERE sessao_id = ?",
            (sessao_id,),
        )
        mensagem_id = conexao.execute("SELECT last_insert_rowid()").fetchone()[0]
    return int(mensagem_id)


def salvar_memoria(conteudo: str, origem_sessao_id: str | None = None) -> bool:
    """Salva uma informação explicitamente indicada pelo usuário para lembrar."""
    texto = " ".join(str(conteudo or "").split()).strip()
    if not texto:
        return False
    with conectar() as conexao:
        cursor = conexao.execute(
            "INSERT OR IGNORE INTO memorias_salvas (conteudo, papel, origem_sessao_id) "
            "VALUES (?, 'user', ?)",
            (texto[:6000], str(origem_sessao_id) if origem_sessao_id else None),
        )
        return cursor.rowcount > 0


def carregar_memorias_salvas(limite: int = 30) -> list[dict]:
    limite = max(1, min(int(limite), 100))
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT id, conteudo, papel, criada_em FROM memorias_salvas "
            "ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [
        {"id": int(mid), "content": conteudo, "role": papel, "created_at": criada}
        for mid, conteudo, papel, criada in reversed(linhas)
    ]


def apagar_conversa(sessao_id: str, preservar_fixadas: bool = True) -> bool:
    """Apaga um chat e seu histórico, preservando dados salvos fora dele.

    Mensagens individualmente fixadas são copiadas para memorias_salvas antes
    da remoção. Configurações, workspaces e demais memórias não são tocados.
    """
    sid = str(sessao_id or "").strip()
    if not sid:
        return False
    with conectar() as conexao:
        existe = conexao.execute(
            "SELECT 1 FROM conversas_gacia WHERE sessao_id = ?", (sid,)
        ).fetchone()
        if not existe:
            existe = conexao.execute(
                "SELECT 1 FROM historico WHERE sessao_id = ? LIMIT 1", (sid,)
            ).fetchone()
        if not existe:
            return False

        # Registra a exclusão antes de remover o conteúdo, protegendo contra
        # workers de IA que terminem depois do clique em Apagar conversa.
        conexao.execute(
            "INSERT OR REPLACE INTO conversas_excluidas (sessao_id) VALUES (?)", (sid,)
        )
        if preservar_fixadas:
            importantes = conexao.execute(
                "SELECT id, papel, conteudo FROM historico "
                "WHERE sessao_id = ? AND fixada = 1 ORDER BY id", (sid,)
            ).fetchall()
            for mensagem_id, papel, conteudo in importantes:
                conexao.execute(
                    "INSERT OR IGNORE INTO memorias_salvas "
                    "(conteudo, papel, origem_sessao_id, origem_mensagem_id) "
                    "VALUES (?, ?, ?, ?)",
                    (str(conteudo), str(papel), sid, int(mensagem_id)),
                )
        conexao.execute("DELETE FROM historico WHERE sessao_id = ?", (sid,))
        conexao.execute("DELETE FROM conversas_gacia WHERE sessao_id = ?", (sid,))
        return True


def definir_conversa_fixada(sessao_id: str, fixada: bool) -> bool:
    sid = str(sessao_id or "").strip()
    if not sid:
        return False
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE conversas_gacia SET fixada = ?, atualizada_em = CURRENT_TIMESTAMP "
            "WHERE sessao_id = ?",
            (1 if fixada else 0, sid),
        )
        return cursor.rowcount > 0


def atualizar_mensagem(mensagem_id: int, sessao_id: str, conteudo: str) -> bool:
    """Atualiza somente o conteúdo de uma mensagem dentro da sessão informada."""
    texto = str(conteudo or "")
    if not texto.strip():
        return False
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE historico SET conteudo = ? WHERE id = ? AND sessao_id = ? AND papel = 'user'",
            (texto, int(mensagem_id), str(sessao_id)),
        )
        if cursor.rowcount:
            conexao.execute(
                "UPDATE conversas_gacia SET atualizada_em = CURRENT_TIMESTAMP WHERE sessao_id = ?",
                (str(sessao_id),),
            )
        return cursor.rowcount > 0


def apagar_mensagem(mensagem_id: int, sessao_id: str) -> bool:
    """Apaga somente a mensagem indicada dentro da sessão informada."""
    with conectar() as conexao:
        cursor = conexao.execute(
            "DELETE FROM historico WHERE id = ? AND sessao_id = ?",
            (int(mensagem_id), str(sessao_id)),
        )
        if cursor.rowcount:
            conexao.execute(
                "UPDATE conversas_gacia SET atualizada_em = CURRENT_TIMESTAMP WHERE sessao_id = ?",
                (str(sessao_id),),
            )
        return cursor.rowcount > 0


def definir_mensagem_fixada(mensagem_id: int, sessao_id: str, fixada: bool) -> bool:
    """Atualiza o estado de fixação sem permitir alteração fora da sessão."""
    with conectar() as conexao:
        cursor = conexao.execute(
            "UPDATE historico SET fixada = ? WHERE id = ? AND sessao_id = ?",
            (1 if fixada else 0, int(mensagem_id), str(sessao_id)),
        )
        return cursor.rowcount > 0


def carregar_mensagens_detalhadas(sessao_id: str, limite: int = 100) -> list[dict]:
    """Carrega mensagens para a interface, incluindo ID estável e estado fixado."""
    limite = max(1, min(int(limite), 1000))
    with conectar() as conexao:
        linhas = conexao.execute(
            """
            SELECT id, papel, conteudo, fixada
            FROM historico
            WHERE sessao_id = ?
              AND (
                    fixada = 1
                    OR id IN (
                        SELECT id FROM historico
                        WHERE sessao_id = ? ORDER BY id DESC LIMIT ?
                    )
              )
            ORDER BY id ASC
            """,
            (str(sessao_id), str(sessao_id), limite),
        ).fetchall()
    # A consulta já ordena por ID crescente; preserve a ordem cronológica
    # para que a interface desenhe a conversa do início para o fim.
    return [
        {"id": int(mid), "role": papel, "content": conteudo, "pinned": bool(fixada)}
        for mid, papel, conteudo, fixada in linhas
    ]


def carregar_historico_contexto(sessao_id: str, limite: int = 100) -> list[dict]:
    """Carrega o contexto do modelo preservando também o estado das mensagens fixadas."""
    return carregar_mensagens_detalhadas(sessao_id, limite=limite)


def criar_conversa(sessao_id: str, titulo: str = "Nova conversa") -> None:
    sessao_id = str(sessao_id or "").strip()
    if not sessao_id:
        raise ValueError("O identificador da conversa não pode estar vazio.")
    with conectar() as conexao:
        conexao.execute("DELETE FROM conversas_excluidas WHERE sessao_id = ?", (sessao_id,))
        conexao.execute(
            "INSERT OR IGNORE INTO conversas_gacia (sessao_id, titulo) VALUES (?, ?)",
            (sessao_id, str(titulo or "Nova conversa").strip()[:80]),
        )


def atualizar_titulo_conversa(sessao_id: str, titulo: str) -> None:
    sessao_id = str(sessao_id or "").strip()
    titulo = " ".join(str(titulo or "").split()).strip()[:80]
    if not sessao_id or not titulo:
        return
    with conectar() as conexao:
        conexao.execute(
            "UPDATE conversas_gacia SET titulo = ?, atualizada_em = CURRENT_TIMESTAMP "
            "WHERE sessao_id = ?",
            (titulo, sessao_id),
        )


def listar_conversas(limite: int = 100) -> list[dict]:
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT sessao_id, titulo, atualizada_em, fixada FROM conversas_gacia "
            "ORDER BY fixada DESC, atualizada_em DESC, rowid DESC LIMIT ?",
            (max(1, min(int(limite), 500)),),
        ).fetchall()
    return [
        {"sessao_id": linha[0], "titulo": linha[1], "atualizada_em": linha[2], "fixada": bool(linha[3])}
        for linha in linhas
    ]


def carregar_mensagens_usuario(sessao_id: str, limite: int = 2) -> list[str]:
    with conectar() as conexao:
        linhas = conexao.execute(
            "SELECT conteudo FROM historico WHERE sessao_id = ? AND papel = 'user' "
            "ORDER BY id LIMIT ?", (str(sessao_id), max(1, int(limite)))
        ).fetchall()
    return [linha[0] for linha in linhas]


def carregar_historico(sessao_id: str, limite: int = 50) -> list[dict[str, str]]:
    if isinstance(limite, bool) or not isinstance(limite, int) or limite < 1:
        raise ValueError("O limite do histórico precisa ser um inteiro positivo.")
    with conectar() as conexao:
        linhas = conexao.execute(
            """
            SELECT papel, conteudo
            FROM historico
            WHERE sessao_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(sessao_id), limite),
        ).fetchall()
    return [{"role": papel, "content": conteudo} for papel, conteudo in reversed(linhas)]
