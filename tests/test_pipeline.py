from datetime import date

import pandas as pd
import requests

from src import db, pipeline
from tests.helpers import BusinessDaySession, FakeResponse, ScriptedSession, no_sleep

TODAY = date(2026, 10, 30)  # sexta-feira


def _run(tmp_path, session, today=TODAY):
    return pipeline.run(["ptax"], today=today, db_path=tmp_path / "t.db", session=session, sleep=no_sleep)


def _one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_janela_de_cinco_anos_inclusiva():
    assert pipeline.window_bounds(date(2026, 10, 30)) == (date(2021, 10, 30), date(2026, 10, 30))
    assert pipeline.window_bounds(date(2024, 2, 29)) == (date(2019, 2, 28), date(2024, 2, 29))


def test_fluxo_completo_e_reexecucao_consistente(tmp_path):
    expected_days = len(pd.bdate_range("2021-10-30", TODAY))

    res = _run(tmp_path, BusinessDaySession())
    assert [r.status for r in res] == ["success"]
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations") == expected_days
    assert _one(conn, "SELECT MAX(ref_date) FROM observations") == "2026-10-30"

    _run(tmp_path, BusinessDaySession())  # segunda execução
    assert _one(conn, "SELECT COUNT(*) FROM observations") == expected_days
    assert _one(conn, "SELECT COUNT(*) FROM raw_observations") == expected_days
    assert _one(conn, "SELECT COUNT(*) FROM pipeline_runs WHERE status='success'") == 2
    conn.close()


def test_janela_terminando_em_sobra_de_um_dia_funciona(tmp_path):
    """Regressão de 01/11/2026: a janela gerava um 6º bloco de um dia e o SGS recusava
    com HTTP 400, derrubando a execução inteira — inclusive os 5 anos já coletados."""
    res = _run(tmp_path, BusinessDaySession(), today=date(2026, 11, 1))
    assert res[0].status == "success", res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT MAX(ref_date) FROM observations") == "2026-10-30"  # sexta
    assert _one(conn, "SELECT MIN(ref_date) FROM observations") == "2021-11-01"
    conn.close()


def test_limites_da_janela_sao_respeitados(tmp_path):
    _run(tmp_path, BusinessDaySession())
    conn = db.connect(tmp_path / "t.db")
    lo, hi = conn.execute("SELECT MIN(ref_date), MAX(ref_date) FROM observations").fetchone()
    assert lo >= "2021-10-30" and hi <= "2026-10-30"
    conn.close()


def test_falha_de_rede_nao_carrega_nada_e_registra_falha(tmp_path):
    res = _run(tmp_path, ScriptedSession([requests.ConnectionError("sem rede")]))
    assert res[0].status == "failed" and "tentativas" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations") == 0
    run = db.latest_run(conn, "ptax")
    assert run["status"] == "failed" and run["rows_loaded"] is None
    conn.close()


def test_falha_posterior_preserva_dados_da_ultima_carga_boa(tmp_path):
    _run(tmp_path, BusinessDaySession())
    conn = db.connect(tmp_path / "t.db")
    before = conn.execute("SELECT ref_date, value FROM observations ORDER BY ref_date").fetchall()

    res = _run(tmp_path, ScriptedSession([FakeResponse(503, [])]), today=date(2026, 11, 2))
    assert res[0].status == "failed"
    after = conn.execute("SELECT ref_date, value FROM observations ORDER BY ref_date").fetchall()
    assert after == before
    assert db.latest_run(conn, "ptax")["status"] == "failed"
    assert db.latest_run(conn, "ptax", status="success") is not None
    conn.close()


def test_resposta_vazia_e_falha_e_nao_sucesso(tmp_path):
    res = _run(tmp_path, ScriptedSession([FakeResponse(200, [])]))
    assert res[0].status == "failed" and "nenhuma observação" in res[0].message


def test_lacuna_de_coleta_impede_a_carga(tmp_path):
    # remove todo o mês de março/2024 da resposta da fonte
    session = BusinessDaySession(skip=lambda d: d.year == 2024 and d.month == 3)
    res = _run(tmp_path, session)
    assert res[0].status == "failed" and "lacuna" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations") == 0
    conn.close()


def test_indicador_desconhecido_e_rejeitado(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        pipeline.run(["xyz"], today=TODAY, db_path=tmp_path / "t.db", session=BusinessDaySession())
