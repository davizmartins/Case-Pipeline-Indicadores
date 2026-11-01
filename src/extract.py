"""Extração: consulta a API SGS do Banco Central em blocos, com timeout e retentativas."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Callable

import pandas as pd
import requests

from src.config import (
    CHUNK_YEARS,
    HTTP_TIMEOUT,
    MAX_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    SGS_URL,
    Series,
)

log = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Falha ao obter dados da fonte. Nunca deve ser tratada como sucesso."""


def _fmt(d: date) -> str:
    """Formato dd/MM/aaaa exigido pelo SGS."""
    return d.strftime("%d/%m/%Y")


def date_chunks(start: date, end: date, years: int = CHUNK_YEARS) -> list[tuple[date, date]]:
    """Divide [start, end] em blocos consecutivos, sem sobreposição, inclusive nas pontas."""
    if start > end:
        raise ValueError(f"início {start} posterior ao fim {end}")
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_start = (pd.Timestamp(cursor) + pd.DateOffset(years=years)).date()
        chunk_end = min(next_start - timedelta(days=1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _parse(resp, code: int, start: date, end: date) -> list[dict]:
    where = f"SGS {code} [{_fmt(start)}..{_fmt(end)}]"
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ExtractionError(f"{where}: resposta não é JSON válido ({exc})") from exc
    if not isinstance(payload, list):
        raise ExtractionError(f"{where}: formato inesperado de resposta: {str(payload)[:200]}")
    for item in payload:
        if not isinstance(item, dict) or "data" not in item or "valor" not in item:
            raise ExtractionError(f"{where}: registro sem campos 'data'/'valor': {str(item)[:200]}")
    return payload


def fetch_chunk(
    session,
    code: int,
    start: date,
    end: date,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Busca um bloco. Repete em timeout/erro de conexão/HTTP 5xx; falha direto em 4xx."""
    url = SGS_URL.format(code=code)
    params = {"formato": "json", "dataInicial": _fmt(start), "dataFinal": _fmt(end)}
    last_error = "desconhecido"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.get(url, params=params, timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
            elif resp.status_code != 200:
                raise ExtractionError(
                    f"SGS {code} [{_fmt(start)}..{_fmt(end)}]: HTTP {resp.status_code}"
                )
            else:
                return _parse(resp, code, start, end)
        log.warning("SGS %s bloco %s..%s, tentativa %s/%s falhou: %s",
                    code, _fmt(start), _fmt(end), attempt, MAX_ATTEMPTS, last_error)
        if attempt < MAX_ATTEMPTS:
            sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise ExtractionError(
        f"SGS {code} [{_fmt(start)}..{_fmt(end)}]: falhou após {MAX_ATTEMPTS} tentativas ({last_error})"
    )


def extract_series(
    series: Series,
    start: date,
    end: date,
    *,
    session=None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Extrai a série no intervalo [start, end], bloco a bloco. Devolve os registros como recebidos."""
    owns_session = session is None
    session = session or requests.Session()
    try:
        rows: list[dict] = []
        for chunk_start, chunk_end in date_chunks(start, end):
            chunk = fetch_chunk(session, series.sgs_code, chunk_start, chunk_end, sleep=sleep)
            log.info("SGS %s %s..%s: %s registros", series.sgs_code,
                     _fmt(chunk_start), _fmt(chunk_end), len(chunk))
            rows.extend(chunk)
        return rows
    finally:
        if owns_session:
            session.close()
