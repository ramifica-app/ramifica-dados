"""PNCP: licitações (contratações publicadas) e contratos de todos os municípios do Brasil.

Estratégia de volume: varre janelas de datas × modalidades × UF, grava o bruto de cada página,
e só promove para o banco o que for da esfera municipal E passar no classificador educacional.
Nomes de campos conforme a API de consulta v1 [NV: conferir no 1º run; o código usa .get()].
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

from radar import banco, config
from radar.classificar import classificar
from radar.http import baixar, guardar_bruto


def _d(s: str | None) -> str | None:
    return s[:10] if s else None


def _municipal(item: dict) -> bool:
    esfera = ((item.get("orgaoEntidade") or {}).get("esferaId") or "").upper()
    return esfera in ("M", "MUNICIPAL")


def normalizar_licitacao(it: dict, carga_id: str = "") -> dict | None:
    if not _municipal(it):
        return None
    objeto = it.get("objetoCompra") or ""
    c = classificar(objeto)
    if not c.educacional:
        return None
    org, uni = it.get("orgaoEntidade") or {}, it.get("unidadeOrgao") or {}
    pub = _d(it.get("dataPublicacaoPncp"))
    return {
        "id_pncp": it.get("numeroControlePNCP"), "cod_ibge7": str(uni.get("codigoIbge") or "").zfill(7) or None,
        "uf": uni.get("ufSigla"), "municipio": uni.get("municipioNome"), "orgao_cnpj": org.get("cnpj"),
        "orgao_nome": org.get("razaoSocial"), "esfera": org.get("esferaId"), "modalidade": it.get("modalidadeNome"),
        "amparo": (it.get("amparoLegal") or {}).get("nome"), "objeto": objeto,
        "valor_estimado": it.get("valorTotalEstimado"), "valor_homologado": it.get("valorTotalHomologado"),
        "data_publicacao": pub, "data_abertura": it.get("dataAberturaProposta"),
        "data_encerramento": it.get("dataEncerramentoProposta"), "situacao": it.get("situacaoCompraNome"),
        "categorias": ",".join(c.categorias), "termos": "|".join(c.termos), "confianca": c.confianca,
        "link": it.get("linkSistemaOrigem"), "ano": int(pub[:4]) if pub else None, "carga_id": carga_id,
    }


def normalizar_contrato(it: dict, carga_id: str = "") -> dict | None:
    if not _municipal(it):
        return None
    objeto = it.get("objetoContrato") or ""
    c = classificar(objeto)
    if not c.educacional:
        return None
    org, uni = it.get("orgaoEntidade") or {}, it.get("unidadeOrgao") or {}
    ni = (it.get("niFornecedor") or "").replace(".", "").replace("/", "").replace("-", "")
    ini = _d(it.get("dataVigenciaInicio"))
    return {
        "id_pncp": it.get("numeroControlePNCP"), "cod_ibge7": str(uni.get("codigoIbge") or "").zfill(7) or None,
        "uf": uni.get("ufSigla"), "municipio": uni.get("municipioNome"), "orgao_cnpj": org.get("cnpj"),
        "orgao_nome": org.get("razaoSocial"), "esfera": org.get("esferaId"), "objeto": objeto,
        "fornecedor_ni": ni, "fornecedor_nome": it.get("nomeRazaoSocialFornecedor"),
        "fornecedor_raiz": ni[:8] if len(ni) == 14 else ni,
        "valor_inicial": it.get("valorInicial"), "valor_global": it.get("valorGlobal"),
        "vigencia_inicio": ini, "vigencia_fim": _d(it.get("dataVigenciaFim")),
        "data_assinatura": _d(it.get("dataAssinatura")), "categorias": ",".join(c.categorias),
        "termos": "|".join(c.termos), "confianca": c.confianca, "ano": int(ini[:4]) if ini else None, "carga_id": carga_id,
    }


def janelas(inicio: date, fim: date, dias: int = 7) -> Iterator[tuple[date, date]]:
    d = inicio
    while d <= fim:
        f = min(d + timedelta(days=dias - 1), fim)
        yield d, f
        d = f + timedelta(days=1)


def _paginas(endpoint: str, params: dict) -> Iterator[list[dict]]:
    pagina = 1
    while True:
        r = baixar(f"{config.PNCP_API}/{endpoint}", params={**params, "pagina": pagina,
                                                               "tamanhoPagina": config.PNCP_TAMANHO_PAGINA})
        if r.status_code == 204 or not r.content:
            return
        guardar_bruto(r.content, f"pncp_{endpoint.replace('/', '_')}", f"{params.get('dataInicial')}_{params.get('uf', 'BR')}_"
                      f"{params.get('codigoModalidadeContratacao', '')}_p{pagina}.json", r.url)
        corpo = r.json()
        dados = corpo.get("data") or []
        yield dados
        total = corpo.get("totalPaginas") or 1
        if pagina >= total or not dados:
            return
        pagina += 1


def coletar_licitacoes(con, inicio: date, fim: date, ufs: list[str] | None = None,
                       modalidades: list[int] | None = None, log=print) -> int:
    cid = banco.nova_carga(con, "pncp_licitacoes")
    total = 0
    try:
        for a, b in janelas(inicio, fim):
            for uf in ufs or list(config.UFS):
                for mod in modalidades or config.PNCP_SO_MODALIDADES or list(config.PNCP_MODALIDADES):
                    params = {"dataInicial": a.strftime("%Y%m%d"), "dataFinal": b.strftime("%Y%m%d"),
                              "codigoModalidadeContratacao": mod, "uf": uf}
                    for dados in _paginas("contratacoes/publicacao", params):
                        linhas = [x for x in (normalizar_licitacao(i, cid) for i in dados) if x and x["id_pncp"]]
                        total += banco.upsert(con, "licitacao", linhas)
                log(f"licitações {a}..{b} {uf}: acumulado {total}")
        banco.fechar_carga(con, cid, total)
    except Exception as e:  # registra e propaga: a carga fica marcada como falha
        banco.fechar_carga(con, cid, total, "falha", str(e)[:500])
        raise
    return total


def coletar_contratos(con, inicio: date, fim: date, log=print) -> int:
    cid = banco.nova_carga(con, "pncp_contratos")
    total = 0
    try:
        for a, b in janelas(inicio, fim):
            params = {"dataInicial": a.strftime("%Y%m%d"), "dataFinal": b.strftime("%Y%m%d")}
            for dados in _paginas("contratos", params):
                linhas = [x for x in (normalizar_contrato(i, cid) for i in dados) if x and x["id_pncp"]]
                total += banco.upsert(con, "contrato", linhas)
            log(f"contratos {a}..{b}: acumulado {total}")
        banco.fechar_carga(con, cid, total)
    except Exception as e:
        banco.fechar_carga(con, cid, total, "falha", str(e)[:500])
        raise
    return total
