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


# --------------------------------------------------------------------------- sonda (T-88)
# Confirma o que a pesquisa T-80 deixou como "não confirmado": bytes de cada consulta proposta
# (dry-run, grátis) e domínios/anos (consultas pequenas, só se o dry-run couber no limite).
LIMITE_SONDA_BYTES = 2 * 1024**3  # 2 GB por consulta pequena; a cota grátis do sandbox é 1 TB/mês

PROPOSTAS = {
    "censo_matricula": None,  # preenchida com censo_escolar.sql_matriculas() na hora
    "ideb_municipio": ("SELECT ano, id_municipio, LOWER(rede) AS rede, anos_escolares, ideb, "
                       "nota_saeb_media_padronizada, indicador_rendimento FROM `basedosdados.br_inep_ideb.municipio` "
                       "WHERE ensino = 'fundamental' AND anos_escolares IN ('iniciais (1-5)', 'finais (6-9)') "
                       "AND LOWER(rede) IN ('municipal', 'publica')"),
    "saeb_municipio": ("SELECT ano, id_municipio, LOWER(rede) AS rede, serie, disciplina, media, nivel_0, nivel_1, "
                       "nivel_2, nivel_3, nivel_4, nivel_5, nivel_6, nivel_7, nivel_8, nivel_9, nivel_10 "
                       "FROM `basedosdados.br_inep_saeb.municipio` WHERE LOWER(rede) = 'municipal' AND localizacao = 'total'"),
    "siconfi_despesas_funcao": ("SELECT ano, id_municipio, estagio_bd, id_conta_bd, conta_bd, SUM(valor) AS valor "
                                "FROM `basedosdados.br_me_siconfi.municipio_despesas_funcao` WHERE ano >= 2015 "
                                "GROUP BY ano, id_municipio, estagio_bd, id_conta_bd, conta_bd"),
    "geobr_municipio_sp": ("SELECT id_municipio, sigla_uf, ST_ASGEOJSON(ST_SIMPLIFY(geometria, 200)) AS geojson "
                           "FROM `basedosdados.br_geobr_mapas.municipio` WHERE sigla_uf = 'SP'"),
}

DOMINIOS = {
    "ideb_anos": "SELECT MIN(ano) AS min_ano, MAX(ano) AS max_ano, COUNT(*) AS linhas "
                 "FROM `basedosdados.br_inep_ideb.municipio` WHERE ensino = 'fundamental'",
    "saeb_ano_serie": "SELECT ano, serie, disciplina, COUNT(*) AS linhas FROM `basedosdados.br_inep_saeb.municipio` "
                      "WHERE LOWER(rede) = 'municipal' AND localizacao = 'total' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3",
    "siconfi_anos": "SELECT MIN(ano) AS min_ano, MAX(ano) AS max_ano FROM `basedosdados.br_me_siconfi.municipio_despesas_funcao`",
    "siconfi_educacao_2023": "SELECT estagio_bd, id_conta_bd, conta_bd, COUNT(*) AS linhas "
                             "FROM `basedosdados.br_me_siconfi.municipio_despesas_funcao` "
                             "WHERE ano = 2023 AND id_conta_bd LIKE '3.12.%' AND estagio_bd = 'Despesas Liquidadas' GROUP BY 1, 2, 3 ORDER BY 2, 1",
    "censo_anos_etapa3": "SELECT MIN(ano) AS min_ano, MAX(ano) AS max_ano, COUNTIF(SAFE_CAST(etapa_ensino AS INT64) = 3) AS etapa3 "
                         "FROM `basedosdados.br_inep_censo_escolar.matricula` WHERE ano >= 2015",
}


def bytes_dry_run(sql: str, cli=None) -> int:
    """Bytes que a consulta processaria (dry-run não cobra nem executa)."""
    from google.cloud import bigquery

    cli = cli or cliente()
    job = cli.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False), timeout=60)
    return int(job.total_bytes_processed or 0)


def sondar(cli=None, dry=bytes_dry_run, consulta=consultar) -> dict:
    """Dry-run de todas as propostas e consultas pequenas de domínio (só se couberem no limite)."""
    from radar.coleta import censo_escolar

    props = dict(PROPOSTAS, censo_matricula=censo_escolar.sql_matriculas())
    out: dict = {"bytes_propostas": {}, "dominios": {}}
    for nome, sql in props.items():
        try:
            out["bytes_propostas"][nome] = dry(sql, cli)
        except Exception as e:  # noqa: BLE001 - tabela/coluna inexistente vira achado, não queda
            out["bytes_propostas"][nome] = f"erro: {type(e).__name__}: {str(e)[:160]}"
    for nome, sql in DOMINIOS.items():
        try:
            b = dry(sql, cli)
            if b > LIMITE_SONDA_BYTES:
                out["dominios"][nome] = f"pulada: {b / 1024**3:.1f} GB > limite"
                continue
            out["dominios"][nome] = {"bytes": b, "linhas": consulta(sql, cli)}
        except Exception as e:  # noqa: BLE001
            out["dominios"][nome] = f"erro: {type(e).__name__}: {str(e)[:160]}"
    return out


def sonda_markdown(res: dict) -> str:
    """Resumo legível para o log do CI."""
    def gb(v):
        return f"{v / 1024**3:.3f} GB" if isinstance(v, int) else str(v)
    linhas = ["### Bytes por consulta proposta (dry-run)", "", "| consulta | bytes |", "|---|---|"]
    linhas += [f"| {k} | {gb(v)} |" for k, v in res["bytes_propostas"].items()]
    linhas += ["", "### Domínios e anos"]
    for k, v in res["dominios"].items():
        linhas.append(f"- **{k}**: " + (gb(v["bytes"]) + " · " + "; ".join(
            ", ".join(f"{c}={x}" for c, x in r.items()) for r in v["linhas"][:60]) if isinstance(v, dict) else v))
    return "\n".join(linhas)
