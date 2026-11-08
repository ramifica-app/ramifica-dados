"""Configuração do Ramifica Radar: caminhos, UFs, fontes e taxonomia.

Tudo que muda de ano para ano (URLs de planilhas, limites legais) fica aqui ou em YAML,
nunca espalhado pelo código. Endereços marcados [NV] precisam de teste no primeiro run.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = Path(os.environ.get("RADAR_DADOS", RAIZ / "dados"))
BRONZE = DADOS / "bronze"        # arquivos brutos imutáveis + manifesto
GEO = DADOS / "geo"              # malhas GeoJSON do IBGE
BANCO = Path(os.environ.get("RADAR_BANCO", DADOS / "radar.duckdb"))
MANIFESTO = BRONZE / "manifesto.jsonl"

USER_AGENT = "RamificaRadar/0.1 (pesquisa academica; dados publicos)"

# Intervalo mínimo (s) entre pedidos por host — o PNCP devolve 429 com rajadas.
INTERVALO_MIN = {"pncp.gov.br": 1.2, "api.queridodiario.ok.org.br": 0.5}

UFS = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23, "DF": 53, "ES": 32, "GO": 52,
    "MA": 21, "MT": 51, "MS": 50, "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42, "SP": 35, "SE": 28, "TO": 17,
}
REGIAO = {"N": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"], "NE": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
          "CO": ["DF", "GO", "MT", "MS"], "SE": ["ES", "MG", "RJ", "SP"], "S": ["PR", "RS", "SC"]}

# --- Fontes -------------------------------------------------------------------------------
IBGE_API = "https://servicodados.ibge.gov.br/api"
PNCP_API = "https://pncp.gov.br/api/consulta/v1"
QD_API = "https://api.queridodiario.ok.org.br"

# Modalidades da Lei 14.133 no PNCP (códigos da API de consulta) [NV: conferir tabela de domínio]
PNCP_MODALIDADES = {
    1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 4: "Concorrência eletrônica",
    5: "Concorrência presencial", 6: "Pregão eletrônico", 7: "Pregão presencial", 8: "Dispensa",
    9: "Inexigibilidade", 10: "Manifestação de interesse", 11: "Pré-qualificação", 12: "Credenciamento",
    13: "Leilão presencial",
}
PNCP_TAMANHO_PAGINA = 50
# Restringe modalidades (ex.: "6,8") para validações rápidas; vazio = todas.
PNCP_SO_MODALIDADES = [int(x) for x in os.environ.get("RADAR_PNCP_MODALIDADES", "").split(",") if x.strip()]

# Ideb por município: uma entrada por (edição, etapa). As URLs mudam a cada edição. [NV]
IDEB_PLANILHAS = {
    ("2023", "anos_iniciais"): "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2023.zip",
    ("2023", "anos_finais"): "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_finais_municipios_2023.zip",
}

# --- Ciclo de estratégia ----------------------------------------------------------------
JANELAS_VENCIMENTO = (30, 90, 180)       # dias para alertas de contrato
DIAS_LICITACAO_NOVA = 7
