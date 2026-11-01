from datetime import date

import pandas as pd
import pytest
import requests

from src import db, pipeline
from src.config import SERIES
from tests.helpers import BusinessDaySession, FakeResponse, ScriptedSession, cdi_value, no_sleep

TODAY = date(2026, 10, 30)  # sexta-feira


def _run(tmp_path, session, today=TODAY, indicators=None):
    return pipeline.run(
        indicators or ["ptax"], today=today, db_path=tmp_path / "t.db",
        session=session, sleep=no_sleep,
    )


def _one(conn, sql):
    return conn.execute(sql).fetchone()[0]


# --- janelas -----------------------------------------------------------------

def test_janela_de_exibicao_de_cinco_anos_inclusiva():
    assert pipeline.window_bounds(date(2026, 10, 30)) == (date(2021, 10, 30), date(2026, 10, 30))
    assert pipeline.window_bounds(date(2024, 2, 29)) == (date(2019, 2, 28), date(2024, 2, 29))


def test_janela_de_extracao_recua_a_margem_da_serie():
    ptax_start, _ = pipeline.fetch_bounds(TODAY, SERIES["ptax"])
    cdi_start, cdi_end = pipeline.fetch_bounds(TODAY, SERIES["cdi"])
    assert ptax_start == date(2021, 10, 30)  # sem margem
    assert cdi_start == date(2020, 10, 30)  # 12 meses antes da janela de exibição
    assert cdi_end == TODAY


# --- fluxo completo ----------------------------------------------------------

def test_fluxo_completo_e_reexecucao_consistente(tmp_path):
    esperado = len(pd.bdate_range("2021-10-30", TODAY))

    res = _run(tmp_path, BusinessDaySession())
    assert [r.status for r in res] == ["success"]
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations") == esperado
    assert _one(conn, "SELECT MAX(ref_date) FROM observations") == "2026-10-30"

    _run(tmp_path, BusinessDaySession())
    assert _one(conn, "SELECT COUNT(*) FROM observations") == esperado
    assert _one(conn, "SELECT COUNT(*) FROM pipeline_runs WHERE status='success'") == 2
    conn.close()


def test_cdi_carrega_a_margem_alem_da_janela_de_exibicao(tmp_path):
    _run(tmp_path, BusinessDaySession(value_fn=cdi_value), indicators=["cdi"])
    conn = db.connect(tmp_path / "t.db")
    primeira = _one(conn, "SELECT MIN(ref_date) FROM observations WHERE indicator='cdi'")
    assert primeira < "2021-10-30", "a margem de 12 meses precisa estar na base"
    assert primeira >= "2020-10-30"
    conn.close()


def test_as_duas_series_convivem_na_mesma_base(tmp_path):
    res = pipeline.run(
        ["ptax", "cdi"], today=TODAY, db_path=tmp_path / "t.db",
        session=BusinessDaySession(), sleep=no_sleep,
    )
    assert [r.status for r in res] == ["success", "success"]
    conn = db.connect(tmp_path / "t.db")
    por_serie = dict(conn.execute("SELECT indicator, COUNT(*) FROM observations GROUP BY indicator"))
    assert set(por_serie) == {"ptax", "cdi"}
    assert por_serie["cdi"] > por_serie["ptax"], "o CDI tem um ano a mais, por causa da margem"
    conn.close()


def test_janela_terminando_em_sobra_de_um_dia_funciona(tmp_path):
    """Regressão de 01/11/2026: a janela gerava um bloco de um dia, recusado com HTTP 400."""
    res = _run(tmp_path, BusinessDaySession(), today=date(2026, 11, 1))
    assert res[0].status == "success", res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT MAX(ref_date) FROM observations") == "2026-10-30"
    assert _one(conn, "SELECT MIN(ref_date) FROM observations") == "2021-11-01"
    conn.close()


def test_limites_da_janela_sao_respeitados(tmp_path):
    _run(tmp_path, BusinessDaySession())
    conn = db.connect(tmp_path / "t.db")
    lo, hi = conn.execute("SELECT MIN(ref_date), MAX(ref_date) FROM observations").fetchone()
    assert lo >= "2021-10-30" and hi <= "2026-10-30"
    conn.close()


# --- atípicos ----------------------------------------------------------------

def test_atipico_e_carregado_sinalizado_e_contado(tmp_path):
    def taxa(d):
        return 13.65 if (d.year, d.month, d.day) == (2026, 10, 30) else 0.050788

    res = _run(tmp_path, BusinessDaySession(value_fn=taxa), indicators=["cdi"])
    assert res[0].status == "success"
    assert "atípicas sinalizadas: 1" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations WHERE indicator='cdi' AND atypical=1") == 1
    assert _one(conn, "SELECT value FROM observations WHERE indicator='cdi' AND atypical=1") == 13.65
    assert db.latest_run(conn, "cdi")["rows_atypical"] == 1
    conn.close()


def test_taxa_zero_nao_e_atipica_nem_descartada(tmp_path):
    _run(tmp_path, BusinessDaySession(value_fn=lambda d: 0.0), indicators=["cdi"])
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations WHERE indicator='cdi'") > 1000
    assert _one(conn, "SELECT COUNT(*) FROM observations WHERE indicator='cdi' AND atypical=1") == 0
    conn.close()


# --- falhas ------------------------------------------------------------------

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
    antes = conn.execute("SELECT ref_date, value FROM observations ORDER BY ref_date").fetchall()

    res = _run(tmp_path, ScriptedSession([FakeResponse(503, [])]), today=date(2026, 11, 2))
    assert res[0].status == "failed"
    depois = conn.execute("SELECT ref_date, value FROM observations ORDER BY ref_date").fetchall()
    assert depois == antes
    assert db.latest_run(conn, "ptax", status="success") is not None
    conn.close()


def test_falha_de_um_indicador_nao_impede_o_outro(tmp_path):
    class SoPtax:
        def get(self, url, params, timeout):
            if "sgs.1/" in url:
                return BusinessDaySession().get(url, params, timeout)
            return FakeResponse(503, {"erro": "indisponível"})

    res = pipeline.run(
        ["ptax", "cdi"], today=TODAY, db_path=tmp_path / "t.db", session=SoPtax(), sleep=no_sleep
    )
    assert {r.indicator: r.status for r in res} == {"ptax": "success", "cdi": "failed"}
    conn = db.connect(tmp_path / "t.db")
    por_serie = dict(conn.execute("SELECT indicator, COUNT(*) FROM observations GROUP BY indicator"))
    assert set(por_serie) == {"ptax"}
    conn.close()


def test_resposta_vazia_e_falha_e_nao_sucesso(tmp_path):
    res = _run(tmp_path, ScriptedSession([FakeResponse(200, [])]))
    assert res[0].status == "failed" and "nenhuma observação" in res[0].message


def test_interrupcao_prolongada_impede_a_carga(tmp_path):
    session = BusinessDaySession(skip=lambda d: d.year == 2024 and d.month == 3)
    res = _run(tmp_path, session)
    assert res[0].status == "failed" and "interrupção" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert _one(conn, "SELECT COUNT(*) FROM observations") == 0
    conn.close()


def test_indicador_desconhecido_e_rejeitado(tmp_path):
    with pytest.raises(ValueError):
        pipeline.run(["xyz"], today=TODAY, db_path=tmp_path / "t.db", session=BusinessDaySession())
