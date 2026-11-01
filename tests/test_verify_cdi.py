"""Comparação entre a anualização calculada e a série anual publicada.

Dados controlados, sem rede: a função comparada é pura.
"""

from datetime import date

import pandas as pd
import pytest

from scripts import verify_cdi as verify_cdi_mod
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


# --- construção do pedido ao SGS ---------------------------------------------
#
# Até aqui este arquivo testava só `compare_annualized`, que é pura. `fetch_annual`
# era a ÚNICA função do script que toca em `src.config` e na rede, e estava sem teste:
# quando Series ganhou o campo obrigatório `max_gap_days`, o script passou a quebrar com
# TypeError e a suíte inteira continuou verde. Os testes abaixo fecham essa lacuna.

def test_fetch_annual_pede_a_serie_4389_e_funciona_com_a_series_atual():
    from scripts.verify_cdi import ANNUAL_SERIES_CODE, fetch_annual
    from tests.helpers import BusinessDaySession, fixed, no_sleep

    sessao = BusinessDaySession(value_fn=fixed(13.65))
    frame = fetch_annual(date(2026, 10, 26), date(2026, 10, 30), session=sessao, sleep=no_sleep)

    assert list(frame.columns) == ["data", "valor"]
    assert len(frame) == 5  # cinco dias úteis
    assert all(f"sgs.{ANNUAL_SERIES_CODE}/" in c["url"] for c in sessao.calls), (
        "o pedido tem de ir para a série anual, não para a diária"
    )


def test_fetch_accumulated_pede_a_serie_13522_e_funciona_com_a_series_atual():
    """Mesma lacuna no script do IPCA: o stub é montado a partir de Series."""
    from scripts.verify_ipca import ACC12_SERIES_CODE, fetch_accumulated
    from tests.helpers import MonthlySession, no_sleep

    sessao = MonthlySession(value_fn=lambda y, m: 4.26)
    frame = fetch_accumulated(date(2025, 12, 1), date(2026, 3, 1), session=sessao, sleep=no_sleep)

    assert list(frame.columns) == ["data", "valor"]
    assert not frame.empty


def test_stub_herda_o_limite_de_lacuna_da_serie_de_origem(monkeypatch):
    """O stub deriva da série real: campos novos em Series não quebram mais o script."""
    from dataclasses import fields

    from scripts.verify_cdi import ANNUAL_SERIES_CODE, fetch_annual
    from src.config import SERIES
    from tests.helpers import BusinessDaySession, fixed, no_sleep

    capturado = {}
    sessao = BusinessDaySession(value_fn=fixed(13.65))
    original = verify_cdi_mod.extract.extract_series

    def espiao(series, *a, **kw):
        capturado["series"] = series
        return original(series, *a, **kw)

    # monkeypatch restaura sozinho ao fim do teste, inclusive se ele falhar
    monkeypatch.setattr(verify_cdi_mod.extract, "extract_series", espiao)
    fetch_annual(date(2026, 10, 26), date(2026, 10, 30), session=sessao, sleep=no_sleep)

    stub = capturado["series"]
    assert stub.sgs_code == ANNUAL_SERIES_CODE
    assert stub.max_gap_days == SERIES["cdi"].max_gap_days
    # todos os campos do dataclass estão preenchidos, sem exigir manutenção manual
    assert len(fields(stub)) == len(fields(SERIES["cdi"]))
