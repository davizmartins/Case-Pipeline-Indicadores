"""Comparação entre a anualização calculada e a série anual publicada.

Dados controlados, sem rede: a função comparada é pura.
"""

import pandas as pd
import pytest

from scripts.verify_cdi import compare_annualized
from src import metrics


def daily(pairs):
    """pairs: (ref_date ISO, texto da taxa diária)."""
    return pd.DataFrame(
        [{"ref_date": d, "value": float(v), "raw_value": v} for d, v in pairs]
    )


def annual(pairs):
    """pairs: (data dd/MM/aaaa, texto da taxa anual)."""
    return pd.DataFrame(pairs, columns=["data", "valor"])


DIAS = [("2026-10-28", "0.050788"), ("2026-10-29", "0.050788")]
ANUAL = [("28/10/2026", "13.65"), ("29/10/2026", "13.65")]


def test_valores_reais_observados_sao_compativeis():
    res = compare_annualized(daily(DIAS), annual(ANUAL))
    assert res["passed"]
    assert res["n_common"] == 2
    assert res["max_deviation"] < 1e-4
    assert res["decimals_daily"] == [6] and res["decimals_annual"] == [2]


def test_tolerancia_conservadora_soma_os_dois_arredondamentos():
    res = compare_annualized(daily(DIAS), annual(ANUAL))
    linha = res["detail"].iloc[0]
    propagado = metrics.annualization_sensitivity(0.050788) * metrics.rounding_half(6)
    assert linha["tol_h2_strict"] == pytest.approx(propagado)
    assert linha["tol_h1_conservative"] == pytest.approx(propagado + metrics.rounding_half(2))
    assert linha["tol_h1_conservative"] > linha["tol_h2_strict"]


def test_tolerancia_varia_com_o_nivel_da_taxa():
    baixa = compare_annualized(daily([("2026-01-02", "0.010000")]), annual([("02/01/2026", "2.55")]))
    alta = compare_annualized(daily([("2026-01-02", "0.150000")]), annual([("02/01/2026", "45.89")]))
    assert alta["detail"].iloc[0]["tol_h2_strict"] > baixa["detail"].iloc[0]["tol_h2_strict"]


def test_divergencia_real_reprova_em_h1():
    res = compare_annualized(daily(DIAS), annual([("28/10/2026", "13.65"), ("29/10/2026", "14.20")]))
    assert not res["passed"] and res["n_above_h1"] == 1
    assert res["max_deviation"] > 0.5


def test_desvio_entre_h2_e_h1_nao_reprova_e_e_apenas_contado():
    """A faixa em que o desvio cai é observação, não diagnóstico da causa."""
    # 13.653 fica acima do estrito e abaixo do conservador (meia unidade de 2 casas = 0,005)
    res = compare_annualized(daily([("2026-10-29", "0.050788")]), annual([("29/10/2026", "13.653")]))
    assert res["n_above_h2"] == 1
    assert res["n_above_h1"] == 1  # 3 casas publicadas -> tolerância conservadora menor
    res2 = compare_annualized(daily([("2026-10-29", "0.050788")]), annual([("29/10/2026", "13.65")]))
    assert res2["n_above_h2"] == 0 and res2["n_above_h1"] == 0


def test_datas_exclusivas_de_cada_serie_sao_listadas():
    res = compare_annualized(
        daily(DIAS + [("2026-10-30", "0.050788")]),
        annual(ANUAL + [("27/10/2026", "13.65")]),
    )
    assert res["only_in_daily"] == ["2026-10-30"]
    assert res["only_in_annual"] == ["2026-10-27"]
    assert res["n_common"] == 2


def test_casas_decimais_sao_lidas_do_texto_recebido():
    res = compare_annualized(
        daily([("2026-10-29", "0.0508")]), annual([("29/10/2026", "13.650000")])
    )
    assert res["decimals_daily"] == [4] and res["decimals_annual"] == [6]
    # menos casas na diária -> tolerância propagada maior
    assert res["detail"].iloc[0]["tol_h2_strict"] > 1e-3
