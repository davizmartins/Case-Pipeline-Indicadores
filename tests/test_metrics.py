"""Cálculos financeiros, com dados controlados e resultados conferíveis à mão."""

from datetime import date

import pandas as pd
import pytest

from src import metrics


def frame(pairs):
    return pd.DataFrame(pairs, columns=["ref_date", "value"])


# --- capitalização -----------------------------------------------------------

def test_capitalizacao_difere_de_soma():
    taxas = [0.05] * 252
    composto = metrics.accumulate(taxas)
    soma = sum(taxas)
    assert composto > soma
    assert composto == pytest.approx(((1.0005**252) - 1) * 100, abs=1e-12)
    assert soma == pytest.approx(12.6)
    assert composto - soma > 0.8  # a diferença não é desprezível em 12 meses


def test_acumulado_de_exemplo_pequeno_conferivel_a_mao():
    # (1,01 × 1,02 × 0,99) − 1 = 0,019898 -> 1,9898%
    assert metrics.accumulate([1.0, 2.0, -1.0]) == pytest.approx(1.9898, abs=1e-9)


def test_taxa_zero_nao_altera_o_acumulado():
    assert metrics.accumulate([0.05, 0.0, 0.05]) == pytest.approx(metrics.accumulate([0.05, 0.05]))


def test_sequencia_vazia_acumula_zero():
    assert metrics.accumulate([]) == 0.0


# --- anualização -------------------------------------------------------------

def test_anualizacao_do_valor_observado():
    assert metrics.annualize(0.050788) == pytest.approx(13.65, abs=1e-4)


@pytest.mark.parametrize("diaria", [0.001, 0.01, 0.030, 0.050788, 0.08, 0.12, 0.15])
def test_ida_e_volta_em_varios_niveis_de_taxa(diaria):
    assert metrics.deannualize(metrics.annualize(diaria)) == pytest.approx(diaria, abs=1e-12)


def test_anualizar_nao_e_multiplicar_pela_quantidade_de_dias():
    d = 0.050788
    assert metrics.annualize(d) != pytest.approx(d * 252, abs=0.1)


def test_sensibilidade_cresce_com_o_nivel_da_taxa():
    baixa = metrics.annualization_sensitivity(0.01)
    alta = metrics.annualization_sensitivity(0.15)
    assert alta > baixa
    # é por isso que a tolerância não pode sair de um único exemplo
    assert alta / baixa > 1.2


# --- janela de 12 meses ------------------------------------------------------

def test_limite_inferior_e_exclusivo_e_o_superior_inclusivo():
    dados = frame([("2025-10-30", 99.0), ("2025-10-31", 0.05), ("2026-10-30", 0.05)])
    janela = metrics.select_window(dados, date(2025, 10, 30), date(2026, 10, 30))
    assert list(janela["ref_date"]) == ["2025-10-31", "2026-10-30"]  # 99.0 ficou de fora


def test_convencao_de_datas_erra_por_uma_observacao_se_mudar():
    """Se o limite inferior virasse fechado, a taxa de borda entraria e distorceria tudo."""
    dados = frame([("2025-10-30", 50.0)] + [("2026-01-%02d" % d, 0.05) for d in range(1, 11)])
    acum = metrics.accumulate(metrics.select_window(dados, date(2025, 10, 30), date(2026, 10, 30))["value"])
    assert acum == pytest.approx(metrics.accumulate([0.05] * 10), abs=1e-12)


@pytest.mark.parametrize(
    "fim,inicio_esperado",
    [
        (date(2024, 2, 29), date(2023, 2, 28)),  # 29/02 menos um ano cai em 28/02
        (date(2025, 2, 28), date(2024, 2, 28)),  # janela contém 29/02/2024
        (date(2024, 3, 1), date(2023, 3, 1)),
        (date(2026, 10, 30), date(2025, 10, 30)),
    ],
)
def test_janela_12m_em_datas_proximas_de_29_de_fevereiro(fim, inicio_esperado):
    assert metrics.window_12m(fim) == (inicio_esperado, fim)


def test_janela_que_termina_em_29_de_fevereiro_tem_366_dias():
    inicio, fim = metrics.window_12m(date(2024, 2, 29))
    assert (fim - inicio).days == 366  # convenção declarada, não acidente


def test_29_de_fevereiro_entra_na_janela_do_ano_seguinte():
    dados = frame([("2024-02-28", 0.05), ("2024-02-29", 0.05), ("2025-02-28", 0.05)])
    janela = metrics.select_window(dados, *metrics.window_12m(date(2025, 2, 28)))
    assert "2024-02-29" in list(janela["ref_date"])
    assert "2024-02-28" not in list(janela["ref_date"])  # limite inferior exclusivo


# --- cobertura ---------------------------------------------------------------

def serie_diaria(inicio: str, fim: str, valor: float = 0.05, pular=()):
    datas = pd.bdate_range(inicio, fim)
    return frame([(d.strftime("%Y-%m-%d"), valor) for d in datas if d.strftime("%Y-%m-%d") not in pular])


def test_cobertura_completa_aprova():
    dados = serie_diaria("2025-10-01", "2026-10-30")
    cov = metrics.coverage(dados, date(2025, 10, 30), date(2026, 10, 30), 10)
    assert cov["ok"] and cov["reason"] is None


def test_cobertura_falha_quando_a_serie_comeca_tarde():
    dados = serie_diaria("2026-06-01", "2026-10-30")
    cov = metrics.coverage(dados, date(2025, 10, 30), date(2026, 10, 30), 10)
    assert not cov["ok"] and "começa" in cov["reason"]


def test_cobertura_falha_quando_a_serie_termina_cedo():
    dados = serie_diaria("2025-10-01", "2026-06-30")
    cov = metrics.coverage(dados, date(2025, 10, 30), date(2026, 10, 30), 10)
    assert not cov["ok"] and "termina" in cov["reason"]


def test_cobertura_falha_com_interrupcao_prolongada():
    pular = {d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-03-01", "2026-03-31")}
    dados = serie_diaria("2025-10-01", "2026-10-30", pular=pular)
    cov = metrics.coverage(dados, date(2025, 10, 30), date(2026, 10, 30), 10)
    assert not cov["ok"] and "interrupção" in cov["reason"]


def test_ausencia_isolada_NAO_e_detectada_pela_cobertura():
    """Limitação declarada: a checagem vê interrupção prolongada, não falta isolada."""
    dados = serie_diaria("2025-10-01", "2026-10-30", pular={"2026-05-13"})  # uma quarta-feira
    cov = metrics.coverage(dados, date(2025, 10, 30), date(2026, 10, 30), 10)
    assert cov["ok"], "a função não detecta ausência isolada — e isso está documentado"
    assert cov["max_gap_days"] <= 10


def test_ausencia_conhecida_e_nao_explicada_bloqueia_o_rotulo():
    dados = serie_diaria("2025-10-01", "2026-10-30", pular={"2026-05-13"})
    cov = metrics.coverage(
        dados, date(2025, 10, 30), date(2026, 10, 30), 10, unexplained_absences=("2026-05-13",)
    )
    assert not cov["ok"] and "não explicada" in cov["reason"]


def test_ausencia_conhecida_fora_da_janela_nao_bloqueia():
    dados = serie_diaria("2025-10-01", "2026-10-30")
    cov = metrics.coverage(
        dados, date(2025, 10, 30), date(2026, 10, 30), 10, unexplained_absences=("2026-10-31",)
    )
    assert cov["ok"]


# --- acumulado em 12 meses ---------------------------------------------------

def test_acumulado_12m_usa_dados_anteriores_a_janela_de_exibicao():
    """A margem é o que permite calcular o acumulado já na primeira data exibida."""
    dados = serie_diaria("2024-10-01", "2026-10-30")
    r = metrics.accumulated_12m(dados, date(2025, 11, 3), 10)
    assert r["value"] is not None
    assert r["start_exclusive"] == date(2024, 11, 3)
    assert r["n_obs"] > 240


def test_acumulado_12m_sem_cobertura_devolve_none():
    dados = serie_diaria("2026-06-01", "2026-10-30")
    r = metrics.accumulated_12m(dados, date(2026, 10, 30), 10)
    assert r["value"] is None and not r["coverage"]["ok"]


def test_acumulado_12m_bate_com_a_capitalizacao_direta():
    dados = serie_diaria("2024-10-01", "2026-10-30", valor=0.05)
    r = metrics.accumulated_12m(dados, date(2026, 10, 30), 10)
    esperado = metrics.accumulate([0.05] * r["n_obs"])
    assert r["value"] == pytest.approx(esperado, abs=1e-12)


# --- utilitários de precisão e base 100 --------------------------------------

@pytest.mark.parametrize(
    "texto,casas", [("13.65", 2), ("0.050788", 6), ("5", 0), ("5.0", 1), (" 0.0500 ", 4)]
)
def test_contagem_de_casas_decimais_do_texto(texto, casas):
    assert metrics.decimals_in(texto) == casas


def test_meia_unidade_da_ultima_casa():
    assert metrics.rounding_half(2) == pytest.approx(0.005)
    assert metrics.rounding_half(6) == pytest.approx(5e-7)


def test_rebase_100():
    assert metrics.rebase_100([50, 75, 100], 50) == [100.0, 150.0, 200.0]
    with pytest.raises(ValueError):
        metrics.rebase_100([1, 2], 0)
