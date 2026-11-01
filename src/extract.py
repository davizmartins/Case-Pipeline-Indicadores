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
    """Divide [start, end] em blocos consecutivos, sem sobreposição, inclusive nas pontas.

    O SGS exige dataFinal ESTRITAMENTE maior que dataInicial: um bloco de um único dia é
    recusado com HTTP 400 ("DataFinal deve ser maior que dataInicial."), tenha ele dado ou
    não (verificado em 01/11/2026). Por isso, quando a sobra final é de um dia, ela é
    absorvida pelo bloco anterior, que fica com um dia a mais. Nenhuma data pedida deixa de
    ser coberta e os blocos continuam sem sobreposição.
    """
    if start > end:
        raise ValueError(f"início {start} posterior ao fim {end}")
    if start == end:
        raise ValueError(
            f"intervalo de um único dia ({start}): o SGS exige dataFinal maior que "
            "dataInicial; peça ao menos dois dias"
        )
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_start = (pd.Timestamp(cursor) + pd.DateOffset(years=years)).date()
        chunk_end = min(next_start - timedelta(days=1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    if len(chunks) > 1 and chunks[-1][0] == chunks[-1][1]:
        chunks[-2] = (chunks[-2][0], chunks[-1][1])
        chunks.pop()
    return chunks


def _describe(resp) -> str:
    """Status + corpo da resposta, para que a causa apareça no log em vez de só 'HTTP 400'.

    O SGS explica o motivo no corpo (ex.: "DataFinal deve ser maior que dataInicial.",
    "Value(s) not found", "dataInicial invalida..."). Sem isso o erro é indiagnosticável.
    """
    try:
        body = " ".join((resp.text or "").split())[:300]
    except Exception:  # um dublê de teste pode não ter .text
        body = ""
    return f"HTTP {resp.status_code}" + (f" — {body}" if body else "")


def _content_type(resp) -> str:
    try:
        return (resp.headers or {}).get("Content-Type", "") or ""
    except Exception:  # um dublê de teste pode não ter .headers
        return ""


def _parse(resp, code: int, start: date, end: date) -> list[dict]:
    where = f"SGS {code} [{_fmt(start)}..{_fmt(end)}]"
    try:
        payload = resp.json()
    except ValueError as exc:
        # O corpo tem de aparecer aqui, como já aparece nos erros HTTP: uma resposta com
        # status 200 e corpo não-JSON (uma página de erro em HTML, por exemplo) é
        # indiagnosticável sem ver o que veio. Foi a lição do "HTTP 400" sem corpo,
        # repetida neste outro ramo do código.
        tipo = _content_type(resp)
        detalhe = _describe(resp)
        if tipo:
            detalhe += f" — Content-Type: {tipo}"
        raise ExtractionError(
            f"{where}: resposta não é JSON válido ({exc}) · {detalhe}"
        ) from exc
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
                last_error = _describe(resp)
            elif resp.status_code != 200:
                raise ExtractionError(
                    f"SGS {code} [{_fmt(start)}..{_fmt(end)}]: {_describe(resp)}"
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
