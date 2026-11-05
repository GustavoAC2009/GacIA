"""Utilitários pequenos de orçamento de contexto para o histórico do chat."""
from __future__ import annotations

LIMITE_CARACTERES_HISTORICO = 12_000


def limitar_historico(historico, limite_caracteres: int = LIMITE_CARACTERES_HISTORICO):
    """Mantém mensagens fixadas e mensagens recentes dentro do orçamento.

    Sem mensagens fixadas, preserva exatamente a política anterior: as mensagens
    mais novas têm prioridade e registros antigos não são fragmentados. Mensagens
    fixadas entram primeiro e permanecem no contexto quando couberem no orçamento.
    """
    restantes = max(1, int(limite_caracteres))
    itens = [
        item for item in (historico or [])
        if item.get("role") in {"user", "assistant", "system"}
        and str(item.get("content", ""))
    ]
    fixadas = [item for item in itens if item.get("pinned")]
    ids_fixadas = {item.get("id") for item in fixadas if item.get("id") is not None}
    recentes = [
        item for item in itens
        if not item.get("pinned") and (item.get("id") is None or item.get("id") not in ids_fixadas)
    ]
    resultado_fixadas = []
    resultado_recentes = []

    for item in fixadas:
        conteudo = str(item.get("content", ""))
        if len(conteudo) > restantes:
            conteudo = conteudo[-restantes:]
        resultado_fixadas.append({"role": item["role"], "content": conteudo})
        restantes -= len(conteudo)
        if restantes <= 0:
            return resultado_fixadas

    for item in reversed(recentes):
        conteudo = str(item.get("content", ""))
        if len(conteudo) > restantes:
            if resultado_recentes or resultado_fixadas:
                break
            conteudo = conteudo[-restantes:]
        resultado_recentes.append({"role": item["role"], "content": conteudo})
        restantes -= len(conteudo)
        if restantes <= 0:
            break

    resultado_recentes.reverse()
    return resultado_fixadas + resultado_recentes
