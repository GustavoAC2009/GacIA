"""Comandos de conversa e roteamento inicial da Gac.IA."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    usage: str


COMMANDS = (
    Command("analise", "Analisar, editar e melhorar arquivos enviados.", "/analise [o que deseja fazer]"),
    Command("projeto", "Trabalhar em um projeto de código enviado ou já aberto.", "/projeto [tarefa no projeto]"),
    Command("create", "Criar um projeto, programa ou conjunto de arquivos do zero.", "/create [descreva o projeto]"),
    Command("codigo", "Programar, depurar, refatorar e explicar código.", "/codigo [tarefa de programação]"),
    Command("executar", "Executar verificações e testes autorizados no projeto atual.", "/executar [o que testar]"),
    Command("imagem", "Gerar uma imagem usando um servidor ComfyUI local.", "/imagem [descreva a imagem]"),
    Command("upscale", "Aplicar super-resolução neural em uma imagem do workspace usando um modelo local.", "/upscale [caminho relativo da imagem]"),
    Command("ajuda", "Mostrar os comandos e como usar os recursos.", "/ajuda"),
)

COMMAND_MAP = {item.name: item for item in COMMANDS}


def parse_command(text: str) -> tuple[str | None, str]:
    """Retorna (comando, argumento); não intercepta comandos desconhecidos."""
    texto = str(text or "").strip()
    if not texto.startswith("/"):
        return None, texto
    match = re.match(r"^/([a-zA-ZÀ-ÿ_-]+)(?:\s+(.*))?$", texto, flags=re.S)
    if not match:
        return None, texto
    nome = match.group(1).lower().replace("-", "_")
    argumento = (match.group(2) or "").strip()
    if nome not in COMMAND_MAP:
        return None, texto
    return nome, argumento


def infer_command(text: str, has_attachments: bool = False, has_workspace: bool = False) -> str | None:
    """Detecção conservadora para pedidos de trabalho com arquivos/código.

    Perguntas comuns não são redirecionadas ao agente automaticamente.
    """
    if has_attachments:
        return "analise"
    t = " ".join(str(text or "").lower().split())
    explicit_file_work = (
        "analise meu projeto", "analisa meu projeto", "analise o projeto",
        "analisa o projeto", "modifique o arquivo", "modifica o arquivo",
        "edite o arquivo", "editar o arquivo", "corrija meu código",
        "corrige meu codigo", "corrija o código", "refatore", "refatorar",
        "implemente no projeto", "implementar no projeto", "abra o projeto",
        "trabalhe nesse projeto", "trabalhe neste projeto", "otimize meu projeto",
        "otimize o projeto", "crie um projeto", "criar um projeto",
        "crie um programa", "criar um programa",
    )
    criacao_arquivos_texto = (
        "crie um arquivo txt", "criar um arquivo txt", "crie arquivo txt", "criar arquivo txt",
        "gere um arquivo txt", "gerar um arquivo txt", "salve em um arquivo txt", "salvar em txt",
        "crie um arquivo de texto", "criar um arquivo de texto", "gere um arquivo de texto",
        "crie um arquivo markdown", "criar um arquivo markdown", "crie um arquivo json", "criar um arquivo json",
        "crie um arquivo csv", "criar um arquivo csv",
    )
    if any(phrase in t for phrase in criacao_arquivos_texto):
        return "create"
    criacao_documentos = (
        "quero criar ou editar um documento word", "criar documento word", "gere um documento word", "gerar documento word",
        "quero criar ou editar uma planilha excel", "quero criar uma apresentação powerpoint",
        "quero criar, analisar ou editar um arquivo pdf", "quero criar ou trabalhar em um e-book em pdf", "quero criar um ebook em pdf",
        "quero criar ou trabalhar em um e-book epub 3, com capítulos e sumário",
        "criar planilha excel", "gere uma planilha excel", "gerar planilha excel",
        "criar apresentação powerpoint", "gere slides", "gerar slides",
        "crie um arquivo pdf", "criar arquivo pdf", "quero criar um ebook", "quero criar um e-book",
        "crie uma apresentação", "criar uma apresentação", "gere uma apresentação", "gerar uma apresentação",
        "crie um powerpoint", "criar um powerpoint", "crie um pptx", "criar um pptx",
        "crie um pdf", "criar um pdf", "gere um pdf", "gerar um pdf",
        "crie uma planilha", "criar uma planilha", "gere uma planilha", "gerar uma planilha",
        "crie um documento word", "criar um documento word", "crie um documento", "criar um documento",
        "crie um ebook", "criar um ebook", "crie um e-book", "criar um e-book",
        "gere um ebook", "gerar um ebook", "gere um e-book", "gerar um e-book",
        "crie um ebook pdf", "criar um ebook pdf", "crie um e-book pdf", "criar um e-book pdf",
        "gere um epub", "gerar um epub", "crie um epub", "criar um epub",
        "gere um relatório", "gerar um relatório", "gere um relatorio", "gerar um relatorio",
    )
    if any(phrase in t for phrase in criacao_documentos):
        return "create"
    if any(phrase in t for phrase in explicit_file_work):
        return "create" if t.startswith(("crie", "criar")) else "analise"
    ocr_terms = (
        "ocr", "reconheça o texto", "reconhecer texto", "extraia o texto do pdf",
        "extrair texto do pdf", "pdf escaneado", "pdf digitalizado",
    )
    if has_workspace and any(term in t for term in ocr_terms):
        return "analise"
    upscale_terms = (
        "upscale", "super-resolução", "super resolução", "aumente a resolução",
        "aumentar a resolução", "melhore a resolução da imagem", "ampliar a imagem com ia",
    )
    if any(term in t for term in upscale_terms) and (has_attachments or has_workspace):
        return "analise"
    context_terms = (
        "no projeto", "nesse projeto", "neste projeto", "no código", "no codigo",
        "nesse arquivo", "neste arquivo", "na planilha", "no documento",
        "no word", "no excel", "no epub", "no ebook", "no e-book", "nos arquivos", "na pasta do projeto",
    )
    action_terms = (
        "altere", "alterar", "modifique", "modificar", "edite", "editar",
        "corrija", "corrigir", "adicione", "adicionar", "implemente", "implementar",
        "remova", "remover", "refatore", "refatorar", "otimize", "otimizar",
        "crie", "criar", "gere", "gerar", "conserte", "consertar",
    )
    if any(term in t for term in context_terms) and any(term in t for term in action_terms):
        return "analise"
    if has_workspace and any(term in t for term in action_terms):
        return "codigo"
    return None


def help_text() -> str:
    linhas = ["**Comandos da Gac.IA**", ""]
    for item in COMMANDS:
        linhas.append(f"- `{item.usage}` — {item.description}")
    linhas.extend([
        "",
        "Você também pode escrever normalmente. Anexar arquivos adiciona documentos/imagens à mensagem; use /analise para tarefas com documentos, /projeto para projetos de código e /upscale para super-resolução neural de uma imagem já anexada ou presente no workspace.",
        "A pesquisa na web continua no botão já existente; não há um comando `/pesquisar` separado.",
    ])
    return "\n".join(linhas)
