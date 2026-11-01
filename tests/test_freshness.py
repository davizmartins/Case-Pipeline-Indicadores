"""Regra de atualidade, por série."""

from datetime import date

from src import freshness
from src.config import SERIES


def test_diferenca_em_meses_de_calendario():
    assert freshness.months_between(date(2026, 9, 1), date(2026, 11, 1)) == 2
    assert freshness.months_between(date(2025, 12, 1), date(2026, 1, 31)) == 1
    assert freshness.months_between(date(2026, 11, 1), date(2026, 11, 30)) == 0


# --- série diária ------------------------------------------------------------

def test_serie_diaria_atual_nao_avisa():
    assert freshness.staleness_warning(SERIES["ptax"], date(2026, 10, 30), date(2026, 11, 1)) is None


def test_serie_diaria_parada_avisa_em_dias():
    aviso = freshness.staleness_warning(SERIES["ptax"], date(2026, 10, 1), date(2026, 11, 1))
    assert aviso and "31 dias atrás" in aviso


# --- série mensal ------------------------------------------------------------

def test_mes_anterior_nao_e_defasagem():
    """Em 01/11, ter outubro é o melhor caso possível."""
    assert freshness.staleness_warning(SERIES["ipca"], date(2026, 10, 1), date(2026, 11, 1)) is None


def test_mes_corrente_ainda_nao_publicado_nao_marca_atraso():
    """Em 01/11 o IPCA de novembro nem existe; isso não pode virar alerta."""
    assert freshness.staleness_warning(SERIES["ipca"], date(2026, 10, 1), date(2026, 11, 20)) is None


def test_dois_meses_atras_vira_possivel_defasagem():
    aviso = freshness.staleness_warning(SERIES["ipca"], date(2026, 9, 1), date(2026, 11, 1))
    assert aviso and "possível defasagem" in aviso
    assert "09/2026" in aviso


def test_regra_provisoria_produz_falso_alerta_todo_inicio_de_mes():
    """Comportamento conhecido da regra de 2 meses, documentado em vez de escondido.

    O mês M é divulgado durante M+1, por volta do dia 10. Entre o dia 1 e a divulgação,
    o último mês disponível é M-1, o que dá diferença de 2 e dispara o alerta — sem que
    haja atraso real. Em 01/11/2026, ter setembro é o estado normal, e mesmo assim avisa.
    """
    aviso = freshness.staleness_warning(SERIES["ipca"], date(2026, 9, 1), date(2026, 11, 1))
    assert aviso is not None
    assert "antes de haver atraso real" in aviso  # o próprio texto admite o falso alerta

    # Já no dia 20, com outubro publicado, o alerta some.
    assert freshness.staleness_warning(SERIES["ipca"], date(2026, 10, 1), date(2026, 11, 20)) is None


def test_o_aviso_mensal_declara_que_e_aproximacao():
    aviso = freshness.staleness_warning(SERIES["ipca"], date(2026, 8, 1), date(2026, 11, 1))
    assert "calendário oficial" in aviso and "antes de haver atraso real" in aviso


def test_serie_mensal_nao_usa_regra_de_dias():
    """40 dias é muito para uma cotação diária e normal para um índice mensal."""
    assert freshness.staleness_warning(SERIES["ipca"], date(2026, 10, 1), date(2026, 11, 10)) is None
    assert freshness.staleness_warning(SERIES["ptax"], date(2026, 10, 1), date(2026, 11, 10))
