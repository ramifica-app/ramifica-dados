"""Regras de alerta do monitoramento. Idempotente: o mesmo evento gera o mesmo id."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from radar import config


def _id(*partes) -> str:
    return hashlib.sha1("|".join(map(str, partes)).encode()).hexdigest()[:16]


def gerar(con, hoje: date | None = None) -> int:
    h = (hoje or date.today()).isoformat()
    agora = datetime.now(UTC)
    linhas = []
    for dias in config.JANELAS_VENCIMENTO:
        for cod, ref, fim, forn, mun in con.execute(f"""
                select cod_ibge7, id_pncp, vigencia_fim, fornecedor_nome, municipio from contrato
                where vigencia_fim between date '{h}' and date '{h}' + interval {dias} day""").fetchall():
            linhas.append([_id("venc", ref, dias), f"contrato_vence_{dias}d", cod, ref, fim,
                           f"{mun}: contrato com {forn} vence em {fim} (janela {dias} dias). Conferir aditivos e preparar diagnóstico.", agora])
    for cod, ref, pub, obj, mun in con.execute(f"""
            select cod_ibge7, id_pncp, data_publicacao, objeto, municipio from licitacao
            where data_publicacao >= date '{h}' - interval {config.DIAS_LICITACAO_NOVA} day""").fetchall():
        linhas.append([_id("lic", ref), "licitacao_nova", cod, ref, pub, f"{mun}: nova licitação educacional — {obj[:160]}", agora])
    for cod, ref, ab, mun in con.execute(f"""
            select cod_ibge7, id_pncp, cast(data_encerramento as date), municipio from licitacao
            where cast(data_encerramento as date) between date '{h}' and date '{h}' + interval 10 day""").fetchall():
        linhas.append([_id("prazo", ref), "prazo_proposta", cod, ref, ab, f"{mun}: prazo de proposta termina em {ab}.", agora])
    if linhas:
        con.executemany("insert or replace into alerta values (?, ?, ?, ?, ?, ?, ?)", linhas)
    return len(linhas)
