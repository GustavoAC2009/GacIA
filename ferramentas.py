
from datetime import datetime
import ast
import operator
import math


# ==========================================
# CALCULADORA SEGURA
# ==========================================

OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def calcular(expressao):
    """Calcula expressões matemáticas sem executar código Python arbitrário."""

    try:
        expressao = expressao.replace("^", "**").strip()

        if not expressao or len(expressao) > 150:
            return "Expressão vazia ou muito longa."

        arvore = ast.parse(expressao, mode="eval")
        if sum(1 for _ in ast.walk(arvore)) > 40:
            raise ValueError("Expressão complexa demais.")

        def validar_numero(valor):
            if type(valor) not in (int, float):
                raise ValueError("Use apenas números.")
            if isinstance(valor, float) and not math.isfinite(valor):
                raise ValueError("Número fora do limite.")
            if abs(valor) > 10**100:
                raise ValueError("Resultado muito grande.")
            return valor

        def avaliar(no):
            if isinstance(no, ast.Expression):
                return avaliar(no.body)

            if isinstance(no, ast.Constant):
                return validar_numero(no.value)

            if isinstance(no, ast.BinOp):
                tipo = type(no.op)

                if tipo not in OPERADORES:
                    raise ValueError("Operador não permitido.")

                esquerda = avaliar(no.left)
                direita = avaliar(no.right)

                if tipo is ast.Pow and abs(direita) > 100:
                    raise ValueError("Expoente muito grande.")

                resultado = OPERADORES[tipo](esquerda, direita)

                if isinstance(resultado, complex):
                    raise ValueError("Resultado complexo não permitido.")

                return validar_numero(resultado)

            if isinstance(no, ast.UnaryOp):
                tipo = type(no.op)

                if tipo not in OPERADORES:
                    raise ValueError("Operador não permitido.")

                return validar_numero(OPERADORES[tipo](avaliar(no.operand)))

            raise ValueError("Expressão não permitida.")

        resultado = validar_numero(avaliar(arvore))

        if isinstance(resultado, float):
            resultado = round(resultado, 10)

        return f"Resultado: {resultado}"

    except ZeroDivisionError:
        return "Erro: divisão por zero."

    except Exception as erro:
        return f"Não consegui calcular: {erro}"


# ==========================================
# DATA E HORA
# ==========================================

def consultar_data_hora():
    agora = datetime.now().astimezone()
    dias = (
        "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo",
    )
    return (
        f"Data: {agora.strftime('%d/%m/%Y')}\n"
        f"Hora local: {agora.strftime('%H:%M:%S')}\n"
        f"Dia da semana: {dias[agora.weekday()]}"
    )


# ==========================================
# PESQUISA NA INTERNET
# ==========================================



def responder_consulta_temporal(pergunta):
    """Responde consultas inequívocas de hora/data pelo relógio local."""
    import re
    texto = str(pergunta or "").strip().lower()
    texto = re.sub(r"[^\w\s:]", " ", texto, flags=re.UNICODE)
    texto = " ".join(texto.split())
    padroes_hora = (
        r"\bque horas (sao|são)\b", r"\bqual (e|é) a hora\b",
        r"\bhora (atual|agora|certa)\b", r"\bme diga a hora\b",
        r"\bme fala a hora\b", r"\bhorario (atual|agora)\b",
        r"\bque horario (e|é)\b",
    )
    padroes_data = (
        r"\bque dia (e|é) hoje\b", r"\bqual a data (de hoje|atual)\b",
        r"\bdata (de hoje|atual)\b",
    )
    agora = datetime.now().astimezone()
    if any(re.search(p, texto) for p in padroes_hora):
        return f"Agora são {agora.strftime('%H:%M:%S')}."
    if any(re.search(p, texto) for p in padroes_data):
        dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                "sexta-feira", "sábado", "domingo")
        meses = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
        return f"Hoje é {dias[agora.weekday()]}, {agora.day} de {meses[agora.month - 1]} de {agora.year}."
    return None

def pesquisar_internet(pergunta, quantidade=5):
    """Pesquisa na web e devolve os resumos fornecidos pelo mecanismo de busca."""
    try:
        from pesquisa_web import pesquisar_e_ler
        return pesquisar_e_ler(pergunta, quantidade)
    except Exception as erro:
        return f"A ferramenta de pesquisa não está disponível: {erro}"


# ==========================================
# CENTRAL DE FERRAMENTAS
# ==========================================

def executar_ferramenta(nome, argumento=""):

    ferramentas = {
        "calculadora": calcular,
        "data_hora": consultar_data_hora,
        "pesquisa": pesquisar_internet,
    }

    funcao = ferramentas.get(nome)

    if funcao is None:
        return "Ferramenta não encontrada."

    if nome == "data_hora":
        return funcao()

    return funcao(argumento)
