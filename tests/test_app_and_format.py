from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import clock, pipeline
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp
from tests.helpers import BusinessDaySession, ScriptedSession, no_sleep

APP = str(Path(__file__).resolve().parent.parent / "app.py")
TODAY = date(2026, 10, 30)


def test_formatacao_ptbr():
    assert fmt_number(5.1521, 4) == "5,1521"
    assert fmt_number(1234567.891, 2) == "1.234.567,89"
    assert fmt_pct(0.25) == "+0,25%"
    assert fmt_pct(-1.5) == "-1,50%"
    assert fmt_date(date(2026, 10, 30)) == "30/10/2026"
    assert fmt_date("2026-10-30") == "30/10/2026"
    assert fmt_timestamp("2026-10-31T21:00:00+00:00") == "31/10/2026 18:00"  # UTC-3


@pytest.fixture
def db_dir(tmp_path, monkeypatch):
    d = tmp_path / "Área de Trabalho" / "Case Pipeline"  # acento e espaços, como no Windows do usuário
    monkeypatch.setenv("VENETO_DB", str(d / "indicadores.db"))
    return d


def _load(db_dir, session=None):
    return pipeline.run(["ptax"], today=TODAY, db_path=db_dir / "indicadores.db",
                        session=session or BusinessDaySession(), sleep=no_sleep)


def test_app_sem_base_mostra_instrucao_em_vez_de_quebrar(db_dir):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("python -m src.pipeline" in e.value for e in at.error)


def test_app_exibe_cartao_com_data_e_sem_avisos_quando_atual(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))  # sábado
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.metric[0].value.startswith("R$ ") and "," in at.metric[0].value
    assert any("30/10/2026" in c.value for c in at.caption)
    assert not at.warning


def test_app_avisa_dado_desatualizado(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 30))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("desatualizados" in w.value for w in at.warning)


def test_app_avisa_quando_ultima_execucao_falhou(db_dir, monkeypatch):
    _load(db_dir)
    _load(db_dir, session=ScriptedSession([__import__("requests").ConnectionError("x")]))
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("falhou" in w.value for w in at.warning)
    assert at.metric  # continua mostrando a última carga boa
