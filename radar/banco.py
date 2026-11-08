"""Banco analítico do Radar (DuckDB local). Mesmo SQL roda depois no warehouse da empresa."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from radar import config

DDL = """
create table if not exists dim_uf (sigla varchar primary key, codigo integer, nome varchar, regiao varchar);
create table if not exists dim_municipio (
  cod_ibge7 varchar primary key, nome varchar, uf varchar, regiao_imediata varchar, regiao_intermediaria varchar);
create table if not exists licitacao (
  id_pncp varchar primary key, cod_ibge7 varchar, uf varchar, municipio varchar, orgao_cnpj varchar, orgao_nome varchar,
  esfera varchar, modalidade varchar, amparo varchar, objeto varchar, valor_estimado double, valor_homologado double,
  data_publicacao date, data_abertura timestamp, data_encerramento timestamp, situacao varchar,
  categorias varchar, termos varchar, confianca double, link varchar, ano integer, carga_id varchar);
create table if not exists contrato (
  id_pncp varchar primary key, cod_ibge7 varchar, uf varchar, municipio varchar, orgao_cnpj varchar, orgao_nome varchar,
  esfera varchar, objeto varchar, fornecedor_ni varchar, fornecedor_nome varchar, fornecedor_raiz varchar,
  valor_inicial double, valor_global double, vigencia_inicio date, vigencia_fim date, data_assinatura date,
  categorias varchar, termos varchar, confianca double, ano integer, carga_id varchar);
create table if not exists fato_ideb (
  cod_ibge7 varchar, rede varchar, etapa varchar, ano integer, ideb double, nota_saeb double, rendimento double,
  carga_id varchar, primary key (cod_ibge7, rede, etapa, ano));
create table if not exists fato_matricula (
  cod_ibge7 varchar, ano integer, rede varchar, etapa varchar, uf varchar, matriculas integer, carga_id varchar,
  primary key (cod_ibge7, ano, rede, etapa));
create table if not exists fato_saeb (
  cod_ibge7 varchar, ano integer, rede varchar, serie integer, disciplina varchar, media double,
  niveis varchar, carga_id varchar, primary key (cod_ibge7, ano, rede, serie, disciplina));
create table if not exists diario_trecho (
  id varchar primary key, cod_ibge7 varchar, data date, termo varchar, trecho varchar, url varchar, carga_id varchar);
create table if not exists alerta (
  id varchar primary key, tipo varchar, cod_ibge7 varchar, referencia varchar, data_evento date, mensagem varchar,
  gerado_em timestamp);
create table if not exists carga (
  carga_id varchar primary key, fonte varchar, inicio timestamp, fim timestamp, linhas integer, status varchar, detalhe varchar);
"""


def conectar(caminho: Path | str | None = None, somente_leitura: bool = False) -> duckdb.DuckDBPyConnection:
    caminho = Path(caminho or config.BANCO)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(caminho), read_only=somente_leitura and caminho.exists())
    if not somente_leitura:
        con.execute(DDL)
    return con


def nova_carga(con, fonte: str) -> str:
    cid = uuid.uuid4().hex[:12]
    con.execute("insert into carga values (?, ?, ?, null, 0, 'rodando', null)",
                [cid, fonte, datetime.now(UTC)])
    return cid


def fechar_carga(con, cid: str, linhas: int, status: str = "ok", detalhe: str = "") -> None:
    con.execute("update carga set fim = ?, linhas = ?, status = ?, detalhe = ? where carga_id = ?",
                [datetime.now(UTC), linhas, status, detalhe, cid])


def upsert(con, tabela: str, linhas: list[dict]) -> int:
    """INSERT OR REPLACE idempotente: a mesma carga duas vezes não duplica nada."""
    if not linhas:
        return 0
    cols = list(linhas[0].keys())
    sql = f"insert or replace into {tabela} ({', '.join(cols)}) values ({', '.join('?' for _ in cols)})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in linhas])
    return len(linhas)
