"""Saeb municipal do Inep via Base dos Dados, com distribuição crua por série.

Fonte: https://basedosdados.org/dataset/br-inep-saeb
Tabela: ``basedosdados.br_inep_saeb.municipio``. Contrato consultado em
``brain/10-fontes/BD_SAEB_MUNICIPIO.md`` em 2026-11-08.

Somente rede municipal e localização total: não somar agregados às redes.
Os níveis 0 a 10 são preservados em JSON, inclusive nulos. As escalas diferem
por série e disciplina: nunca somamos níveis entre séries nem derivamos
"percentual adequado". Comparabilidade entre edições exige verificar a matriz.
Sonda T-88 (2026-11-08): edições 2011–2025; séries 5 e 9 cobrem mais de 3 mil municípios.
As séries 4, 12, 13 e 14 aparecem em poucos municípios e ficam de fora até o dicionário confirmar o significado.
"""

from __future__ import annotations

import json

from radar import banco
from radar.coleta import basedosdados

SQL_SAEB = """
SELECT ano, id_municipio, LOWER(rede) AS rede, serie, disciplina, media,
       nivel_0, nivel_1, nivel_2, nivel_3, nivel_4, nivel_5, nivel_6, nivel_7, nivel_8, nivel_9, nivel_10
FROM `basedosdados.br_inep_saeb.municipio`
WHERE LOWER(rede) = 'municipal' AND localizacao = 'total' AND serie IN (5, 9)
""".strip()


def carregar(con, cli=None, log=print) -> int:
    """Consulta BD e grava fato_saeb; falhas auditadas não interrompem outras etapas."""
    cid = banco.nova_carga(con, "saeb_basedosdados")
    try:
        linhas = []
        for r in basedosdados.consultar(SQL_SAEB, cli):
            cod = str(r.get("id_municipio") or "").strip()
            rede = str(r.get("rede") or "").strip().lower()
            disciplina = str(r.get("disciplina") or "").strip().upper()
            if not cod.isdigit() or len(cod) > 7 or rede != "municipal" or not disciplina:
                continue
            linhas.append({"cod_ibge7": cod.zfill(7), "ano": int(r["ano"]), "rede": rede,
                           "serie": int(r["serie"]), "disciplina": disciplina, "media": r.get("media"),
                           "niveis": json.dumps({f"nivel_{i}": r.get(f"nivel_{i}") for i in range(11)},
                                                allow_nan=False), "carga_id": cid})
        n = banco.upsert(con, "fato_saeb", linhas)
        banco.fechar_carga(con, cid, n)
        log(f"Saeb Base dos Dados: {n} linhas")
        return n
    except Exception as e:  # noqa: BLE001 - falha auditada sem derrubar a coleta
        banco.fechar_carga(con, cid, 0, "falha", str(e)[:500])
        log(f"Saeb Base dos Dados: FALHA {e}")
        return 0
