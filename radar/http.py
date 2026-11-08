"""Download robusto com retentativa e arquivo bruto imutável (camada bronze) + manifesto."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from radar import config


class FonteIndisponivel(RuntimeError):
    pass


_ULTIMA: dict[str, float] = {}


def _ritmo(url: str) -> None:
    """Respeita um intervalo mínimo entre pedidos ao mesmo host (evita 429, ex.: PNCP)."""
    host = url.split("/")[2] if "://" in url else url
    intervalo = config.INTERVALO_MIN.get(host, 0.0)
    if intervalo:
        espera = _ULTIMA.get(host, 0.0) + intervalo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        _ULTIMA[host] = time.monotonic()


def baixar(url: str, params: dict | None = None, tentativas: int = 7, timeout: int = 60,
           sessao: requests.Session | None = None) -> requests.Response:
    """GET com backoff exponencial em 429/5xx/rede. 204 é devolvido como está (sem conteúdo)."""
    s = sessao or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    erro: Exception | None = None
    for i in range(tentativas):
        try:
            _ritmo(url)
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                padrao = 2 ** i * (5 if r.status_code == 429 else 2)
                try:
                    espera = float(r.headers.get("Retry-After", padrao))
                except ValueError:
                    espera = padrao
                time.sleep(min(espera, 90))
                erro = FonteIndisponivel(f"{r.status_code} em {r.url}")
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            erro = e
            time.sleep(2 ** i * 2)
    raise FonteIndisponivel(str(erro))


def guardar_bruto(conteudo: bytes, fonte: str, nome: str, url: str = "") -> dict:
    """Grava o bruto em bronze/<fonte>/<sha>_<nome> uma única vez e registra no manifesto."""
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta = config.BRONZE / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sha[:16]}_{nome}"
    novo = not destino.exists()
    if novo:
        destino.write_bytes(conteudo)
    reg = {"fonte": fonte, "arquivo": str(destino.relative_to(config.DADOS)), "sha256": sha, "bytes": len(conteudo),
           "url": url, "coletado_em": datetime.now(UTC).isoformat(timespec="seconds"), "novo": novo}
    config.MANIFESTO.parent.mkdir(parents=True, exist_ok=True)
    with config.MANIFESTO.open("a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg


def ler_json(caminho: Path):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))
