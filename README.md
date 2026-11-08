# ramifica-dados

Pipeline público de coleta de **dados públicos** educacionais e de compras municipais (IBGE/Base dos Dados, PNCP, Inep, diários oficiais) usado pelo Ramifica Radar.

- Código sincronizado a partir do repositório principal (privado); não edite aqui.
- A base consolidada (DuckDB) é publicada na Release `base-radar`.
- Execução: GitHub Actions (`.github/workflows/coleta.yml`), incremental diário e sob demanda.
- Só dados públicos. Nenhuma credencial no código (Secrets do GitHub).
