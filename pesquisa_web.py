"""Pesquisa web sob demanda, com orçamento ajustado ao perfil da Gac.IA.

O pacote ddgs é importado apenas durante uma pesquisa; portanto, a inicialização
normal e o perfil Leve não carregam módulos de busca desnecessariamente.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urlsplit

LOGGER = logging.getLogger("GacIA.Web")

LIMITES_PERFIL = {"rapido": 2, "intermediario": 5, "top": 8}


# Pedidos explícitos que devem acionar pesquisa mesmo quando o botão estiver desligado.
# A detecção é deliberadamente conservadora para não transformar perguntas comuns em busca.
_PADROES_PESQUISA_EXPLICITA = (
    r"\bpesquise\b", r"\bpesquisa na internet\b", r"\bpesquise na internet\b",
    r"\bbusque na internet\b", r"\bprocure na internet\b",
    r"\bpesquise na web\b", r"\bbusque na web\b", r"\bprocure na web\b",
    r"\bveja as notícias\b", r"\bnotícias de hoje\b", r"\bfontes atuais\b",
    r"\bconfira na internet\b", r"\bverifique online\b",
    r"\bsearch the web\b", r"\bsearch online\b", r"\blook up online\b",
    # Sinais de informação dinâmica: devem buscar mesmo sem pedido literal de pesquisa.
    r"\b(preços?|cotação|valor atual|quanto custa|notícias|lançamento|lançamentos)\b",
    r"\b(hoje|agora|atualmente|mais recente|última versão|versão atual|compatibilidade atual)\b",
    r"\b(current price|latest version|recent release|today's news|current compatibility)\b",
)

def detectar_intencao_pesquisa(texto: str) -> bool:
    """Detecta pedidos explícitos e sinais comuns de informação dinâmica."""
    import re
    normalizado = str(texto or "").strip().lower()
    if not normalizado:
        return False
    return any(re.search(padrao, normalizado, flags=re.IGNORECASE) for padrao in _PADROES_PESQUISA_EXPLICITA)


def _url_publica(url: str) -> bool:
    """Aceita somente links HTTP(S) públicos e sem credenciais embutidas."""
    try:
        partes = urlsplit(str(url or "").strip())
        if partes.scheme.lower() not in {"http", "https"}:
            return False
        if not partes.hostname or partes.username or partes.password:
            return False
        host = partes.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".localhost", ".local", ".internal", ".test")
        ):
            return False
        try:
            endereco = ipaddress.ip_address(host)
        except ValueError:
            return True
        return endereco.is_global
    except (TypeError, ValueError):
        return False


def limite_do_perfil(perfil: str | None) -> int:
    """Retorna o orçamento de fontes do perfil, limitado ao intervalo suportado."""
    return LIMITES_PERFIL.get(str(perfil or "intermediario").lower(), 5)


def pesquisar_web(
    termo: str,
    max_resultados: int | None = None,
    *,
    perfil: str = "intermediario",
    idioma: str = "pt-BR",
) -> list[dict[str, str]]:
    """Pesquisa fontes públicas e devolve título, URL, resumo e domínio.

    Leve: uma consulta focada e até 2 fontes. Intermediário: uma consulta e
    até 5 fontes. Avançado: duas consultas complementares e até 8 fontes,
    favorecendo diversidade e cruzamento de fontes sem aumentar o custo dos
    perfis menores.
    """
    termo = str(termo or "").strip()
    if not termo:
        return []

    perfil_normalizado = str(perfil or "intermediario").strip().lower()
    if perfil_normalizado not in LIMITES_PERFIL:
        perfil_normalizado = "intermediario"
    limite = LIMITES_PERFIL[perfil_normalizado]
    if max_resultados is not None:
        try:
            limite = min(limite, max(1, int(max_resultados)))
        except (TypeError, ValueError):
            pass

    ingles = str(idioma).lower().startswith("en")
    regiao = "us-en" if ingles else "br-pt"
    timeout = {"rapido": 6, "intermediario": 8, "top": 12}[perfil_normalizado]

    # Só o perfil Avançado paga o custo de uma segunda consulta. A consulta
    # complementar busca fontes primárias/técnicas, sem ultrapassar o orçamento.
    if perfil_normalizado == "top" and limite > 1:
        # Reserve pelo menos uma fonte para cada consulta. A soma das cotas
        # permanece exatamente dentro do orçamento do perfil (sem pedir 8+5).
        primeira_cota = max(1, min(limite - 1, (limite + 1) // 2 + 1))
        segunda_cota = limite - primeira_cota
        consulta_complementar = (
            f"{termo} official sources documentation research technical analysis"
            if ingles else
            f"{termo} fontes oficiais documentação estudos análise técnica"
        )
        consultas = [(termo, primeira_cota), (consulta_complementar, segunda_cota)]
    else:
        consultas = [(termo, limite)]

    try:
        # Importação tardia: não carrega DDGS no boot nem para tarefas sem pesquisa.
        from ddgs import DDGS

        def executar_consulta(consulta: str, quantidade: int) -> list[dict]:
            # Uma sessão independente por consulta permite paralelismo seguro no
            # perfil Top, sem compartilhar instância DDGS entre threads.
            with DDGS(timeout=timeout) as busca:
                return list(busca.text(consulta, region=regiao, max_results=quantidade))

        resultados_brutos: list[dict] = []
        if len(consultas) > 1:
            # Executa em paralelo, mas agrega na ordem das consultas para manter
            # resultados determinísticos e priorizar a busca original.
            por_consulta: dict[int, list[dict]] = {}
            with ThreadPoolExecutor(max_workers=min(2, len(consultas))) as executor:
                futuros = {
                    executor.submit(executar_consulta, consulta, cota): indice
                    for indice, (consulta, cota) in enumerate(consultas)
                }
                for futuro in as_completed(futuros):
                    indice = futuros[futuro]
                    try:
                        por_consulta[indice] = futuro.result()
                    except Exception:
                        por_consulta[indice] = []
                        LOGGER.warning("Uma consulta complementar falhou; resultados da outra serão preservados.", exc_info=True)
            for indice in range(len(consultas)):
                resultados_brutos.extend(por_consulta.get(indice, []))
        else:
            consulta, quantidade = consultas[0]
            resultados_brutos = executar_consulta(consulta, quantidade)

        resultados: list[dict[str, str]] = []
        urls_vistas: set[str] = set()
        dominios_contagem: dict[str, int] = {}
        for item in resultados_brutos:
            if not isinstance(item, dict):
                continue
            href = str(item.get("href") or item.get("url") or "").strip()
            if not _url_publica(href):
                continue
            partes = urlsplit(href)
            dominio = (partes.hostname or "Fonte externa").lower()
            url_canonica = f"{partes.scheme.lower()}://{dominio}{partes.path.rstrip('/')}"
            if url_canonica in urls_vistas or dominios_contagem.get(dominio, 0) >= 3:
                continue
            urls_vistas.add(url_canonica)
            dominios_contagem[dominio] = dominios_contagem.get(dominio, 0) + 1
            resultados.append({
                "titulo": str(item.get("title") or "Resultado")[:250],
                "href": href[:700],
                "corpo": str(item.get("body") or item.get("snippet") or "")[:1800],
                "fonte": dominio[:180],
                "data": str(item.get("date") or item.get("published") or "")[:80],
            })
            if len(resultados) >= limite:
                break
        return resultados
    except Exception:
        LOGGER.exception("Falha na pesquisa web DDGS.")
        return []


def pesquisar_web_com_preferencias(
    termo: str,
    *,
    perfil: str = "intermediario",
    idioma: str = "pt-BR",
    preferencias: dict | None = None,
    max_resultados: int | None = None,
) -> list[dict[str, str]]:
    """Aplica preferências de fontes sem ultrapassar o orçamento do perfil."""
    preferencias = preferencias if isinstance(preferencias, dict) else {}
    limite = limite_do_perfil(perfil)
    if max_resultados is not None:
        try:
            limite = min(limite, max(1, int(max_resultados)))
        except (TypeError, ValueError):
            pass
    consultas = [("geral", str(termo or "").strip())]
    if preferencias.get("oficiais"):
        consultas.append(("oficiais", f"{termo} fontes oficiais órgãos públicos documentação institucional"))
    if preferencias.get("cientificas"):
        consultas.append(("cientificas", f"{termo} artigos científicos estudos revisão sistemática pesquisa acadêmica"))
    if preferencias.get("noticias"):
        consultas.append(("noticias", f"{termo} notícias reportagens cobertura jornalística"))

    resultados: list[dict[str, str]] = []
    vistos: set[str] = set()

    def adicionar(itens: list[dict[str, str]] | None) -> None:
        for item in itens or []:
            if not isinstance(item, dict):
                continue
            href = str(item.get("href") or item.get("url") or "").strip()
            partes = urlsplit(href) if href else None
            identidade = (
                f"{partes.scheme.lower()}://{(partes.hostname or '').lower()}{partes.path.rstrip('/')}"
                if partes and partes.scheme and partes.hostname else
                str(item.get("titulo") or item.get("title") or repr(item))
            )
            if identidade in vistos:
                continue
            vistos.add(identidade)
            resultados.append(item)
            if len(resultados) >= limite:
                break

    for _categoria, consulta in consultas[:limite]:
        if len(resultados) >= limite:
            break
        adicionar(pesquisar_web(consulta, max_resultados=1, perfil=perfil, idioma=idioma))
    if len(resultados) < limite:
        adicionar(pesquisar_web(termo, max_resultados=limite, perfil=perfil, idioma=idioma))
    return resultados[:limite]


class _ExtratorTextoHTML(HTMLParser):
    """Extrai texto legível de HTML sem executar scripts nem carregar recursos."""
    _IGNORAR = {"script", "style", "noscript", "svg", "canvas", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorar = 0
        self.titulo = False
        self.titulo_partes: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._IGNORAR:
            self._ignorar += 1
        if tag == "title":
            self.titulo = True
        if tag in {"p", "div", "article", "section", "h1", "h2", "h3", "li", "br"}:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._IGNORAR and self._ignorar:
            self._ignorar -= 1
        if tag == "title":
            self.titulo = False
        if tag in {"p", "div", "article", "section", "h1", "h2", "h3", "li"}:
            self.partes.append("\n")

    def handle_data(self, data):
        if self._ignorar:
            return
        texto = " ".join(str(data).split())
        if texto:
            self.partes.append(texto)
            if self.titulo:
                self.titulo_partes.append(texto)


def _host_publico_resolve(host: str) -> bool:
    """Bloqueia destinos privados/locais também quando o domínio resolve para IP interno."""
    try:
        respostas = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not respostas:
            return False
        for resposta in respostas:
            endereco = ipaddress.ip_address(resposta[4][0].split("%", 1)[0])
            if not endereco.is_global:
                return False
        return True
    except (OSError, ValueError):
        return False


def _ler_pagina_publica(item: dict[str, str], timeout: float = 5.0) -> dict[str, str]:
    """Lê uma página HTML pública com limites rígidos e sem seguir redirecionamentos."""
    url = str(item.get("href", ""))
    partes = urlsplit(url)
    if not _url_publica(url) or partes.port not in (None, 80, 443):
        return item
    if not _host_publico_resolve(partes.hostname or ""):
        LOGGER.warning("Página de pesquisa ignorada por resolução para host não público: %s", partes.hostname)
        return item
    try:
        import requests
        with requests.get(
            url, timeout=(3.0, timeout), allow_redirects=False, stream=True,
            headers={"User-Agent": "GacIA/1.0 (public web research)", "Accept": "text/html,application/xhtml+xml"},
        ) as response:
            if response.status_code != 200:
                return item
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return item
            limite = 1024 * 1024
            conteudo = bytearray()
            for bloco in response.iter_content(16384):
                if not bloco:
                    continue
                conteudo.extend(bloco)
                if len(conteudo) > limite:
                    break
            parser = _ExtratorTextoHTML()
            parser.feed(bytes(conteudo[:limite]).decode(response.encoding or "utf-8", errors="replace"))
            texto = " ".join(" ".join(parser.partes).split())
            if texto:
                enriquecido = dict(item)
                enriquecido["titulo_pagina"] = " ".join(parser.titulo_partes).strip()[:250]
                enriquecido["conteudo"] = texto[:6000]
                return enriquecido
    except Exception:
        LOGGER.debug("Não foi possível ler a página %s", url, exc_info=True)
    return item


def ler_paginas_publicas(resultados: list[dict[str, str]], max_paginas: int = 2) -> list[dict[str, str]]:
    """Lê até duas páginas em paralelo; falhas mantêm o resultado original do buscador."""
    selecionados = list(resultados or [])[:max(0, min(int(max_paginas), 3))]
    if not selecionados:
        return list(resultados or [])
    saida = list(resultados)
    indices = {indice: item for indice, item in enumerate(selecionados)}
    with ThreadPoolExecutor(max_workers=min(3, len(selecionados))) as executor:
        futuros = {executor.submit(_ler_pagina_publica, item): indice for indice, item in indices.items()}
        for futuro in as_completed(futuros):
            indice = futuros[futuro]
            try:
                saida[indice] = futuro.result()
            except Exception:
                LOGGER.debug("Falha inesperada ao ler página de pesquisa.", exc_info=True)
    return saida


def formatar_resultados(resultados: list[dict[str, str]], idioma: str = "pt-BR") -> str:
    """Formata resultados com rótulos explícitos e links para conferência."""
    ingles = str(idioma).lower().startswith("en")
    if not resultados:
        return "No usable public results were found." if ingles else "Nenhum resultado público foi encontrado."
    rotulo = "Search result (snippet; not independently verified)" if ingles else "Resultado de busca (trecho; ainda não verificado independentemente)"
    origem = "Source" if ingles else "Fonte"
    data = "Date" if ingles else "Data"
    partes = []
    for indice, item in enumerate(resultados, 1):
        extra_data = f"\n{data}: {item['data']}" if item.get("data") else ""
        conteudo = item.get("conteudo", "")
        detalhe_pagina = (
            ("\nConteúdo da página (extraído; confira a fonte original): " if not ingles else
             "\nPage content (extracted; verify the original source): ") + conteudo
            if conteudo else ""
        )
        titulo_pagina = item.get("titulo_pagina") or item["titulo"]
        partes.append(
            f"{indice}. {titulo_pagina}\n{rotulo}: {item['corpo']}"
            f"{extra_data}{detalhe_pagina}\n{origem}: {item['href']}"
        )
    return "\n\n".join(partes)


def pesquisar_e_ler(
    termo: str,
    max_resultados: int | None = None,
    *,
    perfil: str = "intermediario",
    idioma: str = "pt-BR",
) -> str:
    """Compatibilidade com integrações antigas: retorna trechos e fontes."""
    resultados = pesquisar_web(
        termo, max_resultados=max_resultados, perfil=perfil, idioma=idioma
    )
    return formatar_resultados(resultados, idioma=idioma)
