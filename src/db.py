"""SQLite: esquema, conexões e consultas usadas pelo pipeline e pelo dashboard.

Tabelas:
- raw_observations: dado recebido da fonte, sem tratamento (auditoria).
- observations: dado tratado, o que alimenta o dashboard. A coluna `atypical`
  marca observações fora da faixa de alerta — elas SÃO carregadas, só ficam
  sinalizadas.
- pipeline_runs: uma linha por indicador a cada execução (sucesso ou falha).

Distinção importante: ref_date é a data a que o dado se REFERE; fetched_at é o
momento (UTC) em que o pipeline o COLETOU.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.config import get_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_observations (
    indicator   TEXT NOT NULL,
    raw_date    TEXT NOT NULL,
    raw_value   TEXT,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (indicator, raw_date)
);

CREATE TABLE IF NOT EXISTS observations (
    indicator   TEXT NOT NULL,
    ref_date    TEXT NOT NULL,
    value       REAL NOT NULL,
    atypical    INTEGER NOT NULL DEFAULT 0,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (indicator, ref_date)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator       TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    rows_fetched    INTEGER,
    rows_loaded     INTEGER,
    rows_discarded  INTEGER,
    rows_atypical   INTEGER,
    window_start    TEXT,
    window_end      TEXT,
    last_ref_date   TEXT,
    message         TEXT
);
"""

# Colunas acrescentadas depois da primeira versão do esquema. CREATE TABLE IF NOT
# EXISTS não as adiciona a uma base já existente, então aplicamos na conexão.
_MIGRATIONS = {
    "observations": {"atypical": "INTEGER NOT NULL DEFAULT 0"},
    "pipeline_runs": {"rows_atypical": "INTEGER"},
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Abre (criando, se preciso) a base de escrita do pipeline."""
    path = Path(path) if path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def connect_readonly(path: Path | str | None = None) -> sqlite3.Connection:
    """Abre a base somente para leitura (dashboard). Falha se o arquivo não existir."""
    path = Path(path) if path else get_db_path()
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def read_series(conn: sqlite3.Connection, indicator: str) -> pd.DataFrame:
    """Observações tratadas do indicador, em ordem cronológica (ref_date como datetime)."""
    df = pd.read_sql_query(
        "SELECT ref_date, value, atypical FROM observations WHERE indicator = ? ORDER BY ref_date",
        conn,
        params=(indicator,),
    )
    df["ref_date"] = pd.to_datetime(df["ref_date"])
    return df


def latest_run(conn: sqlite3.Connection, indicator: str, status: str | None = None) -> dict | None:
    """Última execução registrada do indicador (opcionalmente filtrando por status)."""
    sql = "SELECT * FROM pipeline_runs WHERE indicator = ?"
    params: list = [indicator]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY run_id DESC LIMIT 1"
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([c[0] for c in cur.description], row))
