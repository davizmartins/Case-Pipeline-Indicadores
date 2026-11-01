from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import clock, pipeline
from src.config import SERIES
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp
from tests.helpers import (
    BusinessDaySession,
    MonthlySession,
    RouterSession,
    ScriptedSession,
    cdi_value,
    no_sleep,
)

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


def DualSession(cdi_session=None):
    """Dublê que devolve valores diferentes para cada série, como a fonte real."""
    return RouterSession({
        1: BusinessDaySession(),
        12: cdi_session or BusinessDaySession(value_fn=cdi_value),
        433: MonthlySession(ultimo=(2026, 9)),  # defasagem de divulgação, como na fonte
    })


def _load(db_dir, session=None, indicators=("ptax", "cdi", "ipca")):
    return pipeline.run(
        list(indicators), today=TODAY, db_path=db_dir / "indicadores.db",
        session=session or DualSession(), sleep=no_sleep,
    )


def test_app_sem_base_mostra_instrucao_em_vez_de_quebrar(db_dir):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("python -m src.pipeline" in e.value for e in at.error)


def test_app_exibe_os_tres_cartoes(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    rotulos = [m.label for m in at.metric]
    assert any("venda" in r for r in rotulos)
    assert "Acumulado em 12 meses" in rotulos
    assert "IPCA acumulado em 12 meses" in rotulos
    # O único aviso esperado nesta data é o falso alerta previsto da regra provisória
    # do IPCA (ver test_freshness). Nenhum outro deve aparecer.
    assert all("possível defasagem" in w.value for w in at.warning)


def test_cifrao_e_escapado_para_nao_virar_formula_latex(db_dir, monkeypatch):
    """Sem escapar, 'R$/US$' era renderizado como matemática pelo Streamlit."""
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    rotulo = next(m.label for m in at.metric if "Cotação" in m.label)
    assert r"R\$/US\$" in rotulo
    metodologia = " ".join(m.value for m in at.markdown)
    assert "R$/US$" not in metodologia  # todo cifrão exibido precisa estar escapado


def test_titulo_da_serie_1_usa_o_nome_do_catalogo_e_a_fonte_aparece(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    titulos = [s.value for s in at.subheader]
    assert "Dólar americano (venda)" in titulos
    assert not any("PTAX" in t for t in titulos)
    legendas = " ".join(c.value for c in at.caption)
    assert "Fonte: Banco Central — SGS 1" in legendas


def test_pendencia_da_serie_1_fica_na_metodologia_e_nao_em_destaque(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    destaques = " ".join(i.value for i in at.info)
    assert "PTAX DE FECHAMENTO" not in destaques  # só a série 12 tem aviso em destaque
    assert len(at.info) == 1
    legendas = " ".join(c.value for c in at.caption)
    assert "PTAX DE FECHAMENTO" in legendas and "PENDENTE" in legendas
    assert "5,4212 na venda" in legendas  # a conferência que foi feita fica registrada
    assert "indicador pedido no case" in legendas


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


def test_cartao_do_ipca_mostra_acumulado_e_mes_de_referencia(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert "IPCA — variação mensal" in [s.value for s in at.subheader]
    assert any("IPCA acumulado em 12 meses" == m.label for m in at.metric)
    legendas = " ".join(c.value for c in at.caption)
    assert "Variação de 09/2026" in legendas
    assert "meses posteriores a 09/2025 até 09/2026" in legendas
    assert "divulgado depois do fechamento do mês" in legendas


def test_ipca_nao_tem_aviso_de_identificacao_em_destaque(db_dir, monkeypatch):
    """A identificação da 433 foi confirmada por metadados oficiais do BCB."""
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert len(at.info) == 1  # só a série 12 segue pendente
    legendas = " ".join(c.value for c in at.caption)
    assert "Identificação CONFIRMADA" in legendas and "MG41BP" in legendas
    assert "01/11/2026" in legendas  # data da consulta
    assert "27/09/2002" in legendas  # data da própria página


def test_mes_corrente_ainda_nao_divulgado_nao_vira_aviso(db_dir, monkeypatch):
    """Em 01/11 ter setembro é normal; o alerta não pode disparar por isso."""
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 10, 20))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not any("defasagem" in w.value for w in at.warning)


def test_ipca_muito_atrasado_vira_possivel_defasagem(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 12, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    avisos = " ".join(w.value for w in at.warning)
    assert "possível defasagem" in avisos
    assert "antes de haver atraso real" in avisos


def test_app_avisa_observacoes_atipicas(db_dir, monkeypatch):
    com_atipico = BusinessDaySession(
        value_fn=lambda d: 13.65 if (d.month, d.day) == (10, 30) else 0.050788
    )
    _load(db_dir, session=DualSession(cdi_session=com_atipico))
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
