"""Ideb municipal do Inep: Base dos Dados primeiro, planilhas oficiais como reserva.

Fonte: ``basedosdados.br_inep_ideb.municipio``; contrato e domínios conferidos
em ``brain/10-fontes/BD_IDEB_MUNICIPIO.md`` (2026-11-08).
Municipal e pública são recortes distintos: nunca somamos suas notas.
"""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from radar import banco, config
from radar.coleta import basedosdados
from radar.http import baixar, guardar_bruto

SQL_IDEB = """
SELECT ano, id_municipio, LOWER(rede) AS rede, anos_escolares,
       ideb, nota_saeb_media_padronizada, indicador_rendimento
FROM `basedosdados.br_inep_ideb.municipio`
WHERE ensino = 'fundamental'
  AND anos_escolares IN ('iniciais (1-5)', 'finais (6-9)')
  AND LOWER(rede) IN ('municipal', 'publica')
""".strip()

_ETAPAS_BD = {"iniciais (1-5)": "anos_iniciais", "finais (6-9)": "anos_finais"}


def carregar_bd(con, cli=None, log=print) -> int | None:
    """Grava o recorte municipal da BD; None sinaliza falha, zero é sucesso vazio.

    ``cli`` aceita cliente falso. A falha fica em ``carga`` e permite à fachada
    tentar as planilhas, sem confundir ausência de notas com indisponibilidade.
    """
    cid = banco.nova_carga(con, "ideb_basedosdados")
    try:
        linhas = []
        for r in basedosdados.consultar(SQL_IDEB, cli):
            if r.get("ideb") is None:
                continue
            etapa = _ETAPAS_BD.get(r.get("anos_escolares"))
            rede = str(r.get("rede") or "").strip().lower()
            cod = str(r.get("id_municipio") or "").strip()
            if etapa is None or rede not in ("municipal", "publica") or not cod.isdigit() or len(cod) > 7:
                continue
            linhas.append({"cod_ibge7": cod.zfill(7), "rede": rede, "etapa": etapa,
                           "ano": int(r["ano"]), "ideb": r["ideb"],
                           "nota_saeb": r.get("nota_saeb_media_padronizada"),
                           "rendimento": r.get("indicador_rendimento"), "carga_id": cid})
        n = banco.upsert(con, "fato_ideb", linhas)
        banco.fechar_carga(con, cid, n)
        log(f"Ideb Base dos Dados: {n} linhas")
        return n
    except Exception as e:  # noqa: BLE001 - falha auditada; a fachada tenta a fonte reserva
        banco.fechar_carga(con, cid, 0, "falha", str(e)[:500])
        log(f"Ideb Base dos Dados: FALHA {e}")
        return None


def carregar(con, planilhas: dict | None = None, log=print, *, cli=None) -> int:
    """Tenta BD primeiro; somente uma falha aciona o leitor original de planilhas."""
    n = carregar_bd(con, cli=cli, log=log)
    if n is not None:
        return n
    return _carregar_planilhas(con, planilhas=planilhas, log=log)


def ler_planilha(conteudo: bytes, etapa: str) -> list[dict]:
    """Aceita .zip (com .xlsx dentro) ou .xlsx. Procura a linha de cabeçalho com 'CO_MUNICIPIO'."""
    if conteudo[:2] == b"PK" and zipfile.is_zipfile(io.BytesIO(conteudo)):
        z = zipfile.ZipFile(io.BytesIO(conteudo))
        nomes = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".xls"))]
        if nomes:
            conteudo = z.read(nomes[0])
    bruto = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=str)
    linha = next(i for i, r in bruto.iterrows() if any(str(v).strip().upper() == "CO_MUNICIPIO" for v in r.values))
    df = bruto.iloc[linha + 1:].copy()
    df.columns = [str(c).strip().upper() for c in bruto.iloc[linha]]
    out = []
    for _, r in df.iterrows():
        cod = str(r.get("CO_MUNICIPIO") or "").strip()
        if not cod.isdigit():
            continue
        rede = str(r.get("REDE") or "").strip().lower()
        for col in df.columns:
            m = re.fullmatch(r"VL_OBSERVADO_(\d{4})", col)
            if not m:
                continue
            v = pd.to_numeric(str(r[col]).replace(",", "."), errors="coerce")
            if pd.isna(v):
                continue
            out.append({"cod_ibge7": cod.zfill(7), "rede": rede, "etapa": etapa, "ano": int(m.group(1)),
                        "ideb": float(v), "nota_saeb": None, "rendimento": None})
    return out


def _carregar_planilhas(con, planilhas: dict | None = None, log=print) -> int:
    total = 0
    for (edicao, etapa), url in (planilhas or config.IDEB_PLANILHAS).items():
        cid = banco.nova_carga(con, f"ideb_{edicao}_{etapa}")
        try:
            r = baixar(url, timeout=180)
            guardar_bruto(r.content, "inep_ideb", url.rsplit("/", 1)[-1], url)
            linhas = ler_planilha(r.content, etapa)
            for x in linhas:
                x["carga_id"] = cid
            n = banco.upsert(con, "fato_ideb", linhas)
            banco.fechar_carga(con, cid, n)
            total += n
            log(f"Ideb {edicao} {etapa}: {n} linhas")
        except Exception as e:  # noqa: BLE001 - uma planilha com falha não interrompe as demais
            banco.fechar_carga(con, cid, 0, "falha", str(e)[:500])
            log(f"Ideb {edicao} {etapa}: FALHA {e}")
    return total
