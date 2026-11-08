"""Executa uma etapa de coleta do Radar no GitHub Actions e escreve um resumo em Markdown.

Uso: python tools/coleta_ci.py <etapa> [--desde AAAA-MM-DD] [--ate AAAA-MM-DD] [--ufs SP,MG] [--saida resumo.md]
O resumo traz contagens por tabela, cargas e as últimas linhas do log (sem segredos).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ETAPAS = ("ibge", "pncp", "ideb", "diarios", "alertas", "tudo", "bd-descobrir")
TABELAS = ("dim_municipio", "licitacao", "contrato", "fato_ideb", "diario_trecho", "alerta", "carga")


def contagens(con) -> dict[str, int]:
    out = {}
    for t in TABELAS:
        try:
            out[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
        except Exception:  # noqa: BLE001 - tabela ainda não criada
            out[t] = -1
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("etapa")
    p.add_argument("--desde")
    p.add_argument("--ate")
    p.add_argument("--ufs", default="todas")
    p.add_argument("--saida", default="resumo.md")
    a = p.parse_args(argv)
    import re
    from datetime import date

    if a.etapa not in ETAPAS:
        p.error(f"etapa inválida: {a.etapa}")
    for campo in ("desde", "ate"):
        v = getattr(a, campo) or None
        if v:
            date.fromisoformat(v)  # levanta erro em data inválida
        setattr(a, campo, v)
    if a.ufs != "todas" and not re.fullmatch(r"[A-Z]{2}(,[A-Z]{2})*", a.ufs.upper()):
        p.error("ufs deve ser 'todas' ou siglas separadas por vírgula")
    from radar import banco, coletar

    args = [a.etapa, "--ufs", a.ufs] + (["--desde", a.desde] if a.desde else []) + (["--ate", a.ate] if a.ate else [])
    antes = contagens(banco.conectar())
    buf, ok, t0 = io.StringIO(), True, time.monotonic()
    with contextlib.redirect_stdout(buf):
        try:
            coletar.main(args)
        except Exception:  # noqa: BLE001 - o resumo precisa registrar a falha
            ok = False
            traceback.print_exc(file=buf)
    con = banco.conectar()
    depois = contagens(con)
    amostra = ""
    try:
        rows = con.execute("select uf, municipio, modalidade, left(objeto, 90), valor_estimado, data_publicacao "
                           "from licitacao order by data_publicacao desc limit 5").fetchall()
        amostra = "\n".join(f"| {' | '.join(str(c) for c in r)} |" for r in rows)
    except Exception:  # noqa: BLE001
        pass
    cargas = con.execute("select fonte, status, linhas, left(coalesce(detalhe,''), 120) from carga "
                         "order by inicio desc limit 6").fetchall() if depois["carga"] > 0 else []
    linhas = [f"## Coleta `{a.etapa}` · {'✅ ok' if ok else '❌ falha'} · {time.monotonic() - t0:.0f}s",
              f"Parâmetros: `{' '.join(args)}`", "", "| Tabela | Antes | Depois |", "|---|---|---|"]
    linhas += [f"| {t} | {antes[t]} | {depois[t]} |" for t in TABELAS]
    if cargas:
        linhas += ["", "| Carga | Status | Linhas | Detalhe |", "|---|---|---|---|"]
        linhas += [f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} |" for c in cargas]
    if amostra:
        linhas += ["", "**Amostra (licitações mais recentes)**", "", "| UF | Município | Modalidade | Objeto | Estimado | Publicação |",
                   "|---|---|---|---|---|---|", amostra]
    log = buf.getvalue().strip().splitlines()[-40:]
    linhas += ["", "<details><summary>Log (últimas linhas)</summary>", "", "```", *log, "```", "</details>"]
    Path(a.saida).write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
