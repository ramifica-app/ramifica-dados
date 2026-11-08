"""Ideb por município (Inep). Lê as planilhas oficiais, detecta o cabeçalho e derrete os anos."""

from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from radar import banco, config
from radar.http import baixar, guardar_bruto


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


def carregar(con, planilhas: dict | None = None, log=print) -> int:
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
