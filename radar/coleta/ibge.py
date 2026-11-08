"""IBGE: UFs, todos os municípios e malhas GeoJSON (Brasil por UF e cada UF por município)."""

from __future__ import annotations

import json

from radar import banco, config
from radar.http import FonteIndisponivel, baixar, guardar_bruto

NOME_REGIAO = {"N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste", "SE": "Sudeste", "S": "Sul"}


def _uf_do_municipio(m: dict) -> tuple[str | None, str | None, str | None]:
    """Municípios novos podem vir sem microrregião; a região imediata é o caminho seguro."""
    ri = m.get("regiao-imediata") or {}
    rint = ri.get("regiao-intermediaria") or {}
    uf = (rint.get("UF") or {}).get("sigla")
    if not uf:
        uf = (((m.get("microrregiao") or {}).get("mesorregiao") or {}).get("UF") or {}).get("sigla")
    return uf, ri.get("nome"), rint.get("nome")


def normalizar_municipios(dados: list[dict]) -> list[dict]:
    out = []
    for m in dados:
        uf, ri, rint = _uf_do_municipio(m)
        out.append({"cod_ibge7": str(m["id"]).zfill(7), "nome": m["nome"], "uf": uf,
                    "regiao_imediata": ri, "regiao_intermediaria": rint})
    return out


NOMES_UF = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
            "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
            "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
            "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
            "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
            "SE": "Sergipe", "TO": "Tocantins"}


def carregar_cadastro(con, log=print) -> int:
    """Cadastro de municípios: API do IBGE; se ela não responder (bloqueio de IP fora do Brasil, comum
    nos runners do GitHub), usa o diretório da Base dos Dados (mesmos códigos IBGE)."""
    cid = banco.nova_carga(con, "ibge_cadastro")
    try:
        try:
            r = baixar(f"{config.IBGE_API}/v1/localidades/municipios", tentativas=2, timeout=30)
            guardar_bruto(r.content, "ibge", "municipios.json", r.url)
            muns, origem = normalizar_municipios(r.json()), "api_ibge"
        except FonteIndisponivel as e:
            log(f"IBGE indisponível ({str(e)[:80]}); usando Base dos Dados")
            from radar.coleta import basedosdados

            muns, origem = basedosdados.municipios(), "basedosdados"
        reg_por_uf = {uf: reg for reg, ufs in config.REGIAO.items() for uf in ufs}
        ufs = [{"sigla": s, "codigo": c, "nome": NOMES_UF[s], "regiao": NOME_REGIAO[reg_por_uf[s]]}
               for s, c in config.UFS.items()]
        n = banco.upsert(con, "dim_uf", ufs) + banco.upsert(con, "dim_municipio", muns)
        sem_uf = sum(1 for m in muns if not m["uf"])
        banco.fechar_carga(con, cid, n, "ok" if not sem_uf else "aviso",
                           f"{len(muns)} municípios via {origem}; {sem_uf} sem UF")
        return len(muns)
    except Exception as e:
        banco.fechar_carga(con, cid, 0, "falha", str(e)[:500])
        raise


def baixar_malhas(ufs: list[str] | None = None) -> list[str]:
    """Salva data/geo/brasil_ufs.json e data/geo/<UF>_municipios.json (qualidade mínima, leve)."""
    config.GEO.mkdir(parents=True, exist_ok=True)
    feitos = []
    fmt = {"formato": "application/vnd.geo+json", "qualidade": "minima"}
    try:
        r = baixar(f"{config.IBGE_API}/v3/malhas/paises/BR", params={**fmt, "intrarregiao": "UF"}, tentativas=2, timeout=30)
    except FonteIndisponivel:
        return feitos  # malhas ficam para a fonte alternativa (geobr/Base dos Dados) ou para o PC do usuário
    (config.GEO / "brasil_ufs.json").write_bytes(r.content)
    feitos.append("brasil_ufs.json")
    for uf in ufs or list(config.UFS):
        r = baixar(f"{config.IBGE_API}/v3/malhas/estados/{config.UFS[uf]}", params={**fmt, "intrarregiao": "municipio"})
        json.loads(r.content)  # valida
        (config.GEO / f"{uf}_municipios.json").write_bytes(r.content)
        feitos.append(f"{uf}_municipios.json")
    return feitos
