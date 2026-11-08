"""Linha de comando do Radar — roda no computador do usuário (precisa de internet para as fontes oficiais).

Exemplos:
  python -m radar.coletar ibge                      # cadastro de todos os municípios + malhas das 27 UFs
  python -m radar.coletar pncp --desde 2021-01-01   # licitações e contratos educacionais municipais, Brasil
  python -m radar.coletar pncp --desde 2026-10-01 --ufs SP,MG --so-licitacoes
  python -m radar.coletar ideb                      # Ideb via Base dos Dados; planilhas como reserva
  python -m radar.coletar diarios --desde 2026-01-01
  python -m radar.coletar alertas
  python -m radar.coletar censo                      # matrículas municipais do Censo Escolar (Base dos Dados)
  python -m radar.coletar saeb                       # proficiência e níveis municipais; fora de tudo
  python -m radar.coletar bd-sondar                  # bytes (dry-run) e domínios das próximas tabelas BD
  python -m radar.coletar tudo --desde 2025-01-01
"""

from __future__ import annotations

import argparse
from datetime import date

from radar import alertas, banco, config


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="radar.coletar")
    p.add_argument("etapa", choices=["ibge", "pncp", "ideb", "diarios", "alertas", "censo", "saeb",
                                    "tudo", "bd-descobrir", "bd-sondar"])
    p.add_argument("--desde", type=date.fromisoformat, default=date(date.today().year, 1, 1))
    p.add_argument("--ate", type=date.fromisoformat, default=date.today())
    p.add_argument("--ufs", default="todas", help="todas ou lista separada por vírgula (ex.: SP,MG)")
    p.add_argument("--so-licitacoes", action="store_true")
    p.add_argument("--so-contratos", action="store_true")
    a = p.parse_args(argv)
    ufs = None if a.ufs == "todas" else [u.strip().upper() for u in a.ufs.split(",")]
    con = banco.conectar()

    if a.etapa in ("ibge", "tudo"):
        from radar.coleta import ibge
        print("IBGE: municípios", ibge.carregar_cadastro(con))
        print("IBGE: malhas", len(ibge.baixar_malhas(ufs)))
    if a.etapa in ("pncp", "tudo"):
        from radar.coleta import pncp
        if not a.so_contratos:
            print("PNCP licitações:", pncp.coletar_licitacoes(con, a.desde, a.ate, ufs))
        if not a.so_licitacoes:
            print("PNCP contratos:", pncp.coletar_contratos(con, a.desde, a.ate))
    if a.etapa in ("ideb", "tudo"):
        from radar.coleta import ideb
        print("Ideb:", ideb.carregar(con))
    if a.etapa in ("diarios", "tudo"):
        from radar.coleta import querido_diario
        print("Querido Diário:", querido_diario.coletar(con, a.desde, a.ate))
    if a.etapa == "censo":
        from radar.coleta import censo_escolar
        print("Censo Escolar:", censo_escolar.carregar(con))
    if a.etapa == "saeb":
        from radar.coleta import saeb
        print("Saeb:", saeb.carregar(con))
    if a.etapa == "bd-sondar":
        from radar.coleta import basedosdados
        print(basedosdados.sonda_markdown(basedosdados.sondar()))
    if a.etapa == "bd-descobrir":
        from radar.coleta import basedosdados
        for ds, tabs in basedosdados.descobrir().items():
            print(f"{ds}: {', '.join(tabs)}")
        return
    if a.etapa in ("alertas", "tudo", "pncp"):
        print("Alertas:", alertas.gerar(con))
    print("Banco:", config.BANCO)


if __name__ == "__main__":
    main()
