"""Matrículas da rede municipal no Censo Escolar, via Base dos Dados.

A tabela ``basedosdados.br_inep_censo_escolar.matricula`` tem uma linha por
matrícula. O schema publicado (basedosdados/sdk, ``matricula/schema-prod.json``)
traz ``ano``, ``sigla_uf``, ``id_municipio``, ``rede`` (texto, por exemplo
``municipal``) e ``etapa_ensino`` (inteiro do ``TP_ETAPA_ENSINO`` do Inep).

A conta é feita no BigQuery, para não baixar o microdado. ``rede`` entra no
filtro e no agrupamento. ``ano >= CENSO_ANO_MIN`` restringe a leitura no
BigQuery: padrão 2015, configurável por ``RADAR_CENSO_ANO_MIN`` no ambiente
antes de iniciar o processo (``radar.config``). Os recortes são creche, pré,
EI unificada, anos iniciais e anos finais. EJA, médio, profissional e
multietapa ficam de fora.

SQL enviado a ``radar.coleta.basedosdados.consultar``::

    SELECT ano, id_municipio, sigla_uf, LOWER(rede) AS rede, etapa_ensino,
           COUNT(*) AS matriculas
    FROM `basedosdados.br_inep_censo_escolar.matricula`
    WHERE LOWER(rede) = 'municipal' AND id_municipio IS NOT NULL AND etapa_ensino IS NOT NULL
      AND ano >= 2015  -- padrão; substituído pelo valor inteiro da configuração
    GROUP BY ano, id_municipio, sigla_uf, LOWER(rede), etapa_ensino

Códigos de ``etapa_ensino`` (dicionário do Censo Escolar, Inep, preservados
pela Base dos Dados): 1 creche; 2 pré-escola; 3 EI unificada; 4–7 e 14–18
anos iniciais; 8–11, 19–21 e 41 anos finais. O código 3 recebe o recorte
``ei_unificada``: não há informação para repartição por idade no agregado
consultado, portanto suas matrículas não são somadas a creche nem a pré,
evitando dupla contagem.

Fontes consultadas em 2026-11-08:
- Dicionário do Censo Escolar 2015 e tabela auxiliar de etapas, publicados
  pela Secretaria de Educação/Recife (levantamento coordenado pelo Inep):
  https://dados.recife.pe.gov.br/dataset/censo-escolar-2015/resource/26830361-9311-40e0-bda6-5c8741405009
  https://dados.recife.pe.gov.br/dataset/censo-escolar-2015/resource/1d6eb8e6-7fcb-40bc-95f2-54e8be101581
  Código 3 = EI unificada (0 a 5 anos); JSON e CSV conferidos via HTTP 200.
- Inep, Caderno de Instruções 2015, p. 51: creche e pré na mesma classe:
  https://download.inep.gov.br/educacao_basica/educacenso/matricula_inicial/2015/documentos/caderno_instrucoes.pdf
- Catálogo nacional dos microdados/dicionários do Inep (download do ZIP
  2015 indisponível nesta consulta; não foi usado como evidência lida):
  https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar
"""

from __future__ import annotations

from radar import banco, config
from radar.coleta import basedosdados

_SQL_MATRICULAS = """
SELECT ano, id_municipio, sigla_uf, LOWER(rede) AS rede, etapa_ensino, COUNT(*) AS matriculas
FROM `basedosdados.br_inep_censo_escolar.matricula`
WHERE LOWER(rede) = 'municipal' AND id_municipio IS NOT NULL AND etapa_ensino IS NOT NULL
  AND ano >= {ano_min}
GROUP BY ano, id_municipio, sigla_uf, LOWER(rede), etapa_ensino
""".strip()


def sql_matriculas(ano_min: int | None = None) -> str:
    """SQL com o recorte de anos lido na hora da consulta (``int`` impede injeção)."""
    return _SQL_MATRICULAS.format(ano_min=int(config.CENSO_ANO_MIN if ano_min is None else ano_min))


SQL_MATRICULAS = sql_matriculas()  # valor padrão, para documentação e testes

# TP_ETAPA_ENSINO do Inep. Fundamental de 8 anos (4–11) entra para os anos antigos.
_ETAPA = {
    1: "creche",
    2: "pre",
    3: "ei_unificada",
    4: "ef_anos_iniciais",
    5: "ef_anos_iniciais",
    6: "ef_anos_iniciais",
    7: "ef_anos_iniciais",
    14: "ef_anos_iniciais",
    15: "ef_anos_iniciais",
    16: "ef_anos_iniciais",
    17: "ef_anos_iniciais",
    18: "ef_anos_iniciais",
    8: "ef_anos_finais",
    9: "ef_anos_finais",
    10: "ef_anos_finais",
    11: "ef_anos_finais",
    19: "ef_anos_finais",
    20: "ef_anos_finais",
    21: "ef_anos_finais",
    41: "ef_anos_finais",
}


def etapa_de(codigo) -> str | None:
    """Recorte estável, ou None quando o código não é uma das cinco etapas."""
    try:
        return _ETAPA.get(int(codigo))
    except (TypeError, ValueError):
        return None


def agregar(linhas: list[dict]) -> list[dict]:
    """Soma matrículas no grão município, ano, rede municipal e etapa."""
    totais: dict[tuple, dict] = {}
    for linha in linhas:
        rede = str(linha.get("rede") or "").strip().lower()
        if rede != "municipal":
            continue
        etapa = etapa_de(linha.get("etapa_ensino"))
        if etapa is None:
            continue
        cod = str(linha.get("id_municipio") or "").strip().zfill(7)
        if not cod.strip("0"):
            continue
        ano = int(linha["ano"])
        chave = (cod, ano, rede, etapa)
        qtd = int(linha["matriculas"])
        atual = totais.get(chave)
        if atual is None:
            totais[chave] = {"cod_ibge7": cod, "ano": ano, "rede": rede, "etapa": etapa,
                             "uf": linha.get("sigla_uf"), "matriculas": qtd}
        else:
            atual["matriculas"] += qtd
    return list(totais.values())


def carregar(con, cli=None, log=print) -> int:
    """Consulta o agregado e grava ``fato_matricula``. ``cli`` falso evita rede nos testes."""
    cid = banco.nova_carga(con, "censo_escolar_matricula")
    try:
        linhas = agregar(basedosdados.consultar(sql_matriculas(), cli))
        for linha in linhas:
            linha["carga_id"] = cid
        n = banco.upsert(con, "fato_matricula", linhas)
        banco.fechar_carga(con, cid, n)
        log(f"Censo Escolar: {n} linhas")
        return n
    except Exception as e:  # noqa: BLE001 - a falha fica na carga e não derruba as outras etapas
        banco.fechar_carga(con, cid, 0, "falha", str(e)[:500])
        log(f"Censo Escolar: FALHA {e}")
        return 0
