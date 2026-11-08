"""Querido Diário: trechos de diários oficiais municipais (cobertura parcial de cidades)."""

from __future__ import annotations

import hashlib
from datetime import date

from radar import banco, config
from radar.http import baixar, guardar_bruto

TERMOS_PADRAO = ['"sistema de ensino"', '"material didático"', '"plataforma educacional"',
                 '"secretário municipal de educação"', '"secretária municipal de educação"']


def coletar(con, desde: date, ate: date, termos: list[str] | None = None, log=print) -> int:
    cid = banco.nova_carga(con, "querido_diario")
    total = 0
    for termo in termos or TERMOS_PADRAO:
        offset = 0
        while True:
            r = baixar(f"{config.QD_API}/gazettes", params={
                "querystring": termo, "published_since": desde.isoformat(), "published_until": ate.isoformat(),
                "excerpt_size": 400, "number_of_excerpts": 3, "size": 100, "offset": offset})
            guardar_bruto(r.content, "querido_diario", f"{desde}_{hashlib.sha1(termo.encode()).hexdigest()[:8]}_{offset}.json", r.url)
            corpo = r.json()
            gaz = corpo.get("gazettes") or []
            linhas = []
            for g in gaz:
                for trecho in g.get("excerpts") or []:
                    uid = hashlib.sha1(f"{g.get('url')}|{trecho[:80]}".encode()).hexdigest()[:16]
                    linhas.append({"id": uid, "cod_ibge7": str(g.get("territory_id") or "").zfill(7), "data": g.get("date"),
                                   "termo": termo, "trecho": trecho, "url": g.get("url"), "carga_id": cid})
            total += banco.upsert(con, "diario_trecho", linhas)
            offset += len(gaz)
            if not gaz or offset >= (corpo.get("total_gazettes") or 0):
                break
        log(f"Querido Diário {termo}: acumulado {total}")
    banco.fechar_carga(con, cid, total)
    return total
