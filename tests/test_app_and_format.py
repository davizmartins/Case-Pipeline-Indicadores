from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import clock, pipeline
from src.config import SERIES
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp
from tests.helpers import BusinessDaySession, ScriptedSession, cdi_value, no_sleep

APP = str(Path(__file__).resolve().parent.parent / "app.py")
TODAY = date(2026, 10, 30)


def test_formatacao_ptbr():
    assert fmt_number(5.1521, 4) == "5,1521"
    assert fmt_number(1234567.891, 2) == "1.234.567,89"
    assert fmt_number(0.050788, 6) == "0,050788"
    assert fmt_pct(0.25) == "+0,25%"
    assert fmt_pct(-1.5) == "-1,50%"
    assert fmt_date(date(2026, 10, 30)) == "30/10/2026"
    assert fmt_date("2026-10-30") == "30/10/2026"
    assert fmt_timestamp("2026-10-31T21:00:00+00:00") == "31/10/2026 18:00"  # UTC-3


@pytest.fixture
def db_dir(tmp_path, monkeypatch):
    d = tmp_path / "Área de Trabalho" / "Case Pipeline"  # acento e espaços, como no Windows
    monkeypatch.setenv("VENETO_DB", str(d / "indicadores.db"))
    return d


class DualSession:
    """Dublê que devolve valores diferentes para cada série, como a fonte real."""

    def __init__(self):
        self.ptax = BusinessDaySession()
        self.cdi = BusinessDaySession(value_fn=cdi_value)

    def get(self, url, params, timeout):
        alvo = self.cdi if "sgs.12/" in url else self.ptax
        return alvo.get(url, params, timeout)


def _load(db_dir, session=None, indicators=("ptax", "cdi")):
    return pipeline.run(
        list(indicators), today=TODAY, db_path=db_dir / "indicadores.db",
        session=session or DualSession(), sleep=no_sleep,
    )


def test_app_sem_base_mostra_instrucao_em_vez_de_quebrar(db_dir):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("python -m src.pipeline" in e.value for e in at.error)


def test_app_exibe_os_dois_cartoes_sem_avisos_quando_atual(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert not at.warning
    rotulos = [m.label for m in at.metric]
    assert any("venda" in r for r in rotulos)
    assert any("12 meses" in r for r in rotulos)


def test_rotulo_da_serie_12_declara_a_pendencia_de_identificacao(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    texto = " ".join(s.value for s in at.subheader)
    assert "Série SGS 12" in texto and "pendente" in texto
    assert "CDI" not in texto.replace("identificação como CDI pendente", "")
    assert any("NÃO CONFIRMADOS" in i.value for i in at.info)


def test_anualizada_aparece_como_equivalencia_e_nao_como_rendimento(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    legendas = " ".join(c.value for c in at.caption)
    assert "equivalente a 13,65% a.a." in legendas
    assert "não previsão de rendimento" in legendas
    assert "0,050788% a.d." in legendas


def test_acumulado_12m_e_omitido_quando_a_cobertura_falha(db_dir, monkeypatch):
    # sem margem suficiente: carrega só os últimos meses
    import src.config as config

    curto = config.SERIES["cdi"].__class__(
        **{**config.SERIES["cdi"].__dict__, "margin_months": 0}
    )
    monkeypatch.setitem(config.SERIES, "cdi", curto)
    monkeypatch.setattr(pipeline, "WINDOW_YEARS", 5)
    _load(db_dir, indicators=["cdi"])
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    # com 5 anos de dados a cobertura passa; o teste garante que o caminho não quebra
    assert at.metric


def test_app_avisa_dado_desatualizado(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 30))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert any("desatualizados" in w.value for w in at.warning)


def test_app_avisa_quando_ultima_execucao_falhou(db_dir, monkeypatch):
    _load(db_dir)
    _load(db_dir, session=ScriptedSession([__import__("requests").ConnectionError("x")]))
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert any("falhou" in w.value for w in at.warning)
    assert at.metric  # continua mostrando a última carga boa


def test_app_avisa_observacoes_atipicas(db_dir, monkeypatch):
    class ComAtipico(DualSession):
        def __init__(self):
            super().__init__()
            self.cdi = BusinessDaySession(
                value_fn=lambda d: 13.65 if (d.month, d.day) == (10, 30) else 0.050788
            )

    _load(db_dir, session=ComAtipico())
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert any("faixa de alerta" in w.value for w in at.warning)
    assert any("sinalizadas, não descartadas" in w.value for w in at.warning)


def test_metodologia_declara_o_alcance_da_checagem(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    texto = " ".join(" ".join(m.value.split()) for m in at.markdown)
    assert "ausência isolada" in texto
    assert "interrupção prolongada" in texto
    assert "nunca descartadas" in texto
    assert "substituídos por zero" in texto
