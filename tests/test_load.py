import sqlite3

import pandas as pd

from src import db, load


def _clean(triples):
    return pd.DataFrame(triples, columns=["ref_date", "value", "atypical"])


def _raw(pairs):
    return [{"data": d, "valor": v} for d, v in pairs]


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_reexecucao_nao_duplica(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    raw = _raw([("01/01/2026", "5.1"), ("02/01/2026", "5.2")])
    clean = _clean([("2026-01-01", 5.1, 0), ("2026-01-02", 5.2, 0)])
    for _ in range(3):
        load.load_series(conn, "ptax", "SGS 1", raw, clean, "2026-11-01T10:00:00+00:00")
    assert _count(conn, "observations") == 2
    assert _count(conn, "raw_observations") == 2


def test_valor_revisado_pela_fonte_atualiza_a_linha_existente(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    load.load_series(conn, "ptax", "SGS 1", _raw([("01/01/2026", "5.1")]),
                     _clean([("2026-01-01", 5.1, 0)]), "2026-11-01T10:00:00+00:00")
    load.load_series(conn, "ptax", "SGS 1", _raw([("01/01/2026", "5.2")]),
                     _clean([("2026-01-01", 5.2, 0)]), "2026-11-02T10:00:00+00:00")
    assert _count(conn, "observations") == 1
    value, fetched = conn.execute("SELECT value, fetched_at FROM observations").fetchone()
    assert value == 5.2 and fetched.startswith("2026-11-02")


def test_marca_de_atipico_e_persistida_e_atualizada(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    load.load_series(conn, "cdi", "SGS 12", _raw([("01/01/2026", "-0.01")]),
                     _clean([("2026-01-01", -0.01, 1)]), "2026-11-01T10:00:00+00:00")
    assert conn.execute("SELECT atypical FROM observations").fetchone()[0] == 1
    load.load_series(conn, "cdi", "SGS 12", _raw([("01/01/2026", "0.05")]),
                     _clean([("2026-01-01", 0.05, 0)]), "2026-11-02T10:00:00+00:00")
    assert conn.execute("SELECT atypical FROM observations").fetchone()[0] == 0


def test_indicadores_diferentes_coexistem_na_mesma_data(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for key in ("ptax", "cdi"):
        load.load_series(conn, key, "SGS", _raw([("01/01/2026", "1")]),
                         _clean([("2026-01-01", 1.0, 0)]), "2026-11-01T10:00:00+00:00")
    assert _count(conn, "observations") == 2


def test_bruto_preserva_o_texto_recebido_e_distingue_referencia_de_coleta(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    load.load_series(conn, "ptax", "SGS 1", _raw([("01/01/2026", "5.1000"), ("02/01/2026", None)]),
                     _clean([("2026-01-01", 5.1, 0)]), "2026-11-01T10:00:00+00:00")
    rows = dict(conn.execute("SELECT raw_date, raw_value FROM raw_observations").fetchall())
    assert rows == {"01/01/2026": "5.1000", "02/01/2026": None}
    ref, fetched = conn.execute("SELECT ref_date, fetched_at FROM observations").fetchone()
    assert ref == "2026-01-01" and fetched == "2026-11-01T10:00:00+00:00"


def test_falha_no_meio_da_carga_nao_grava_nada(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    raw = _raw([("01/01/2026", "5.1")])
    bad = _clean([("2026-01-01", 5.1, 0), (None, 5.2, 0)])  # ref_date NULL viola NOT NULL
    try:
        load.load_series(conn, "ptax", "SGS 1", raw, bad, "2026-11-01T10:00:00+00:00")
    except Exception:
        pass
    assert _count(conn, "observations") == 0
    assert _count(conn, "raw_observations") == 0


def test_migracao_adiciona_colunas_em_base_antiga(tmp_path):
    """Uma base criada antes das colunas novas continua utilizável."""
    caminho = tmp_path / "antiga.db"
    antiga = sqlite3.connect(caminho)
    antiga.executescript(
        """
        CREATE TABLE observations (
            indicator TEXT NOT NULL, ref_date TEXT NOT NULL, value REAL NOT NULL,
            fetched_at TEXT NOT NULL, PRIMARY KEY (indicator, ref_date));
        CREATE TABLE pipeline_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT, indicator TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('success','failed')));
        """
    )
    antiga.execute(
        "INSERT INTO observations VALUES ('ptax','2026-01-01',5.1,'2026-01-01T00:00:00+00:00')"
    )
    antiga.commit()
    antiga.close()

    conn = db.connect(caminho)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
    assert "atypical" in cols
    assert conn.execute("SELECT atypical FROM observations").fetchone()[0] == 0
    assert "rows_atypical" in {r[1] for r in conn.execute("PRAGMA table_info(pipeline_runs)")}
    conn.close()
