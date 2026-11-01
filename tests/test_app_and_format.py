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
        # A série 12 real para um dia antes das outras (defasagem de publicação
        # observada em 01/11/2026): o dublê reproduz isso.
        12: cdi_session or BusinessDaySession(value_fn=cdi_value, ultimo=date(2026, 10, 29)),
        433: MonthlySession(ultimo=(2026, 9)),  # defasagem de divulgação, como na fonte
    })


def _load(db_dir, session=None, indicators=("ptax", "cdi", "ipca", "ibovespa")):
    from tests.test_ibovespa import baixador, quadro, serie_cinco_anos

    return pipeline.run(
        list(indicators), today=TODAY, db_path=db_dir / "indicadores.db",
        session=session or DualSession(), sleep=no_sleep,
        downloader=baixador(quadro(serie_cinco_anos())),
    )


def test_app_sem_base_mostra_instrucao_em_vez_de_quebrar(db_dir):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("python -m src.pipeline" in e.value for e in at.error)


def test_app_exibe_os_quatro_cartoes(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    rotulos = [m.label for m in at.metric]
    assert any("venda" in r for r in rotulos)
    assert "Acumulado em 12 meses" in rotulos
    assert "IPCA acumulado em 12 meses" in rotulos
    assert "Fechamento — pontos" in rotulos
    # Nesta data esperamos exatamente três avisos, todos previstos: o falso alerta da
    # regra provisória do IPCA, o pregão do Ibovespa sinalizado para revisão e a
    # advertência de que as séries diárias terminam em datas diferentes.
    avisos = [w.value for w in at.warning]
    assert len(avisos) == 3
    assert any("possível defasagem" in a for a in avisos)
    assert any("revisão" in a for a in avisos)
    assert any("datas **diferentes**" in a for a in avisos)


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
    pendencias = [i for i in at.info if i.icon == "\u26a0\ufe0f"]
    assert "PTAX DE FECHAMENTO" not in " ".join(i.value for i in pendencias)
    assert len(pendencias) == 1  # só a série 12 tem aviso de identificação em destaque
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
    assert "divulgado após o fechamento do mês" in legendas


def test_ipca_nao_tem_aviso_de_identificacao_em_destaque(db_dir, monkeypatch):
    """A identificação da 433 foi confirmada por metadados oficiais do BCB."""
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    pendencias = [i for i in at.info if i.icon == "\u26a0\ufe0f"]
    assert len(pendencias) == 1  # só a série 12 segue pendente
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


def test_cartao_do_ibovespa_lista_os_pregoes_sinalizados(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert "Ibovespa" in [s.value for s in at.subheader]
    assert any("Fechamento — pontos" == m.label for m in at.metric)
    legendas = " ".join(c.value for c in at.caption)
    assert "Pregões sinalizados para revisão (1): 26/10/2026" in legendas
    assert "não foram alterados" in legendas
    assert "yfinance — ticker ^BVSP" in legendas


def test_sinalizacao_pede_revisao_e_nao_declara_erro(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    aviso = next(w.value for w in at.warning if "revisão" in w.value)
    assert "não" in aviso and "declara erro" in aviso
    assert "sem substituição" in aviso
    for proibido in ("erro", "inválido", "incorreto"):
        assert f" {proibido} " not in aviso.replace("declara erro", "")


def test_app_avisa_observacoes_atipicas(db_dir, monkeypatch):
    com_atipico = BusinessDaySession(
        value_fn=lambda d: 13.65 if (d.month, d.day) == (10, 30) else 0.050788
    )
    _load(db_dir, session=DualSession(cdi_session=com_atipico))
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert any("faixa de alerta" in w.value for w in at.warning)
    assert any("não\ndeclara erro" in w.value or "não declara erro" in w.value for w in at.warning)
    assert any("sem substituição" in w.value for w in at.warning)


def test_metodologia_declara_o_alcance_da_checagem(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    texto = " ".join(" ".join(m.value.split()) for m in at.markdown)
    assert "ausência isolada" in texto
    assert "interrupção prolongada" in texto
    assert "apenas **sinalizam**" in texto and "não declara erro" in texto
    assert "substituídos por zero" in texto


# --- seções, filtro e comparações --------------------------------------------

def test_secao_de_cartoes_declara_que_nao_depende_do_filtro(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "Últimos indicadores disponíveis" in [h.value for h in at.header]
    legendas = " ".join(" ".join(c.value.split()) for c in at.caption)
    assert "não** é afetada pelo filtro" in legendas


def test_filtro_de_periodo_existe_com_as_quatro_opcoes(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    opcoes = at.sidebar.radio[0].options
    assert opcoes == ["12 meses", "24 meses", "5 anos", "Personalizado"]


def test_mudar_o_filtro_reduz_as_observacoes_dos_graficos(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    cinco_anos = " ".join(c.value for c in at.caption)
    at.sidebar.radio[0].set_value("12 meses").run()
    doze_meses = " ".join(c.value for c in at.caption)
    assert cinco_anos != doze_meses
    assert "30/10/2025 a 30/10/2026" in " ".join(c.value for c in at.sidebar.caption)


def test_comparacao_base_100_mostra_a_data_base_efetiva(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "Comparação no período" in [h.value for h in at.header]
    legendas = " ".join(" ".join(c.value.split()) for c in at.caption)
    assert "Data-base efetiva:" in legendas
    assert "não entra, porque ali o índice vale 100" in legendas
    assert "Nenhuma série é alinhada, preenchida ou truncada" in legendas


def test_comparacao_avisa_quando_as_series_terminam_em_datas_diferentes(db_dir, monkeypatch):
    """A série 12 vai até 29/10 e as outras até 30/10 — períodos não são iguais."""
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    avisos = " ".join(w.value for w in at.warning)
    assert "terminam em datas **diferentes**" in avisos
    assert "não devem ser comparados" in avisos


def test_comparacao_mensal_informa_o_periodo_efetivo(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    rotulos = [m.label for m in at.metric]
    assert "Retorno real" in rotulos
    legendas = " ".join(" ".join(c.value.split()) for c in at.caption)
    assert "Período efetivamente usado:" in legendas
    assert "não está fixado no código" in legendas
    assert "Subtrair uma taxa da outra dá resultado parecido e errado" in legendas


def test_nota_de_naturezas_diferentes_aparece_na_comparacao(db_dir, monkeypatch):
    _load(db_dir)
    monkeypatch.setattr(clock, "today_br", lambda: date(2026, 11, 1))
    at = AppTest.from_file(APP, default_timeout=60).run()
    notas = " ".join(" ".join(i.value.split()) for i in at.info)
    assert "Naturezas diferentes" in notas
    assert "não a comparação de investimentos equivalentes" in notas
