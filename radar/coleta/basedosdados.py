"""Base dos Dados (BigQuery): dados públicos já tratados (diretórios, Censo Escolar, Ideb, SAEB, TSE...).

Credencial: GOOGLE_APPLICATION_CREDENTIALS (conta de serviço só com "BigQuery Job User") e o projeto de
faturamento em BASEDOSDADOS_BILLING_PROJECT (sandbox grátis). Usado principalmente no GitHub Actions.
"""

from __future__ import annotations

import os

DATASETS_INTERESSE = ("br_bd_diretorios_brasil", "br_inep_censo_escolar", "br_inep_ideb", "br_inep_saeb",
                      "br_tse_eleicoes", "br_geobr_mapas", "br_fnde_pnae", "br_me_siconfi")


def cliente():
    from google.cloud import bigquery  # import tardio: só quem coleta precisa da biblioteca

    return bigquery.Client(project=os.environ["BASEDOSDADOS_BILLING_PROJECT"])


def consultar(sql: str, cli=None) -> list[dict]:
    cli = cli or cliente()
    return [dict(r.items()) for r in cli.query(sql, timeout=60).result(timeout=180)]


def mapear_municipio(linha: dict) -> dict:
    """Converte uma linha do diretório de municípios para o formato de dim_municipio."""
    def g(*nomes):
        for n in nomes:
            if linha.get(n) not in (None, ""):
                return linha[n]
        return None

    return {"cod_ibge7": str(g("id_municipio") or "").zfill(7), "nome": g("nome", "nome_municipio"),
            "uf": g("sigla_uf"), "regiao_imediata": g("nome_regiao_imediata", "regiao_imediata"),
            "regiao_intermediaria": g("nome_regiao_intermediaria", "regiao_intermediaria")}


def municipios(cli=None) -> list[dict]:
    linhas = consultar("SELECT * FROM `basedosdados.br_bd_diretorios_brasil.municipio`", cli)
    return [m for m in (mapear_municipio(x) for x in linhas) if m["cod_ibge7"].strip("0") and m["uf"]]


def descobrir(cli=None) -> dict[str, list[str]]:
    """Lista as tabelas de cada dataset de interesse (para planejar os conectores)."""
    out = {}
    for ds in DATASETS_INTERESSE:
        try:
            out[ds] = [r["table_name"] for r in consultar(
                f"SELECT table_name FROM `basedosdados.{ds}.INFORMATION_SCHEMA.TABLES` ORDER BY 1", cli)]
        except Exception as e:  # noqa: BLE001 - dataset inexistente ou sem permissão
            out[ds] = [f"(indisponível: {type(e).__name__})"]
    return out
