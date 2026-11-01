"""Carga: grava dados brutos e tratados no SQLite de forma idempotente.

A chave primária (indicador, data) + UPSERT faz com que reexecutar o pipeline não
duplique linhas e que valores revisados pela fonte atualizem o que já existe.
Bruto e tratado são gravados na MESMA transação: ou entram os dois, ou nenhum.

Limitação conhecida: o UPSERT não remove observações que a fonte tenha deixado de
publicar. Tratar remoções/revisões históricas é objetivo do bônus incremental.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

_RAW_UPSERT = """
INSERT INTO raw_observations (indicator, raw_date, raw_value, source, fetched_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (indicator, raw_date) DO UPDATE SET
    raw_value = excluded.raw_value,
    source = excluded.source,
    fetched_at = excluded.fetched_at
"""

_OBS_UPSERT = """
INSERT INTO observations (indicator, ref_date, value, fetched_at)
VALUES (?, ?, ?, ?)
ON CONFLICT (indicator, ref_date) DO UPDATE SET
    value = excluded.value,
    fetched_at = excluded.fetched_at
"""


def load_series(
    conn: sqlite3.Connection,
    indicator: str,
    source: str,
    raw_rows: list[dict],
    clean: pd.DataFrame,
    fetched_at: str,
) -> int:
    """Grava bruto + tratado numa transação. Devolve o número de observações tratadas."""
    raw_params = [
        (
            indicator,
            str(r["data"]),
            None if r["valor"] is None else str(r["valor"]),
            source,
            fetched_at,
        )
        for r in raw_rows
    ]
    obs_params = [
        (indicator, d, float(v), fetched_at) for d, v in zip(clean["ref_date"], clean["value"])
    ]
    with conn:  # commit se tudo deu certo, rollback se algo levantar exceção
        conn.executemany(_RAW_UPSERT, raw_params)
        conn.executemany(_OBS_UPSERT, obs_params)
    return len(obs_params)


def record_run(
    conn: sqlite3.Connection,
    *,
    indicator: str,
    started_at: str,
    finished_at: str,
    status: str,
    rows_fetched: int | None,
    rows_loaded: int | None,
    rows_discarded: int | None,
    window_start: str,
    window_end: str,
    last_ref_date: str | None,
    message: str,
) -> None:
    """Registra a execução (sucesso ou falha) em transação própria."""
    with conn:
        conn.execute(
            """
            INSERT INTO pipeline_runs (
                indicator, started_at, finished_at, status, rows_fetched, rows_loaded,
                rows_discarded, window_start, window_end, last_ref_date, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                indicator, started_at, finished_at, status, rows_fetched, rows_loaded,
                rows_discarded, window_start, window_end, last_ref_date, message,
            ),
        )
