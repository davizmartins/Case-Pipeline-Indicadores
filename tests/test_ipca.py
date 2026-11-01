"""IPCA: cálculo, validação e carga, com os valores reais conferidos contra o IBGE."""

from datetime import date

import pandas as pd
import pytest

from scripts.verify_ipca import compare_accumulated
from src import db, metrics, pipeline, transform
from src.config import SERIES
from tests.dados_ipca import (
    ACUM12_13522,
    IBGE_2025_ACUMULADO,
    IBGE_DEZ_2025_MENSAL,
    MENSAL_433,
    iso,
)
from tests.helpers import MonthlySession, RouterSession, no_sleep


def mensal_frame():
    return pd.DataFrame(
        [{"ref_date": iso(d), "value": float(v), "raw_value": v} for d, v in MENSAL_433]
    )


def acum_frame():
    return pd.DataFrame(ACUM12_13522, columns=["data", "valor"])


# --- os dados batem com o que o IBGE publica ---------------------------------

def test_valor_mensal_de_dezembro_2025_bate_com_o_ibge():
    valores = dict(MENSAL_433)
    assert float(valores["01/12/2025"]) == IBGE_DEZ_2025_MENSAL


def test_carimbo_e_o_mes_de_referencia_e_nao_o_de_publicacao():
    """Sob a hipótese de carimbo por publicação, o 4,26 do IBGE cairia em 01/01/2026."""
    acum = dict(ACUM12_13522)
    assert float(acum["01/12/2025"]) == IBGE_2025_ACUMULADO
    assert float(acum["01/01/2026"]) != IBGE_2025_ACUMULADO


def test_dezembro_2025_e_janeiro_2026_tem_o_mesmo_valor_e_isso_e_coincidencia():
    valores = dict(MENSAL_433)
    assert valores["01/12/2025"] == valores["01/01/2026"] == "0.33"


# --- composição de 12 meses --------------------------------------------------

def test_janela_mensal_pega_exatamente_doze_observacoes():
    inicio, fim = metrics.window_12m(date(2026, 9, 1))
    janela = metrics.select_window(mensal_frame(), inicio, fim)
    assert len(janela) == 12
    assert janela["ref_date"].iloc[0] == "2025-10-01"  # limite inferior exclusivo
    assert janela["ref_date"].iloc[-1] == "2026-09-01"


def test_composicao_reproduz_o_acumulado_oficial_de_2025():
    r = metrics.accumulated_12m(mensal_frame(), date(2025, 12, 1), 40)
    assert r["value"] == pytest.approx(IBGE_2025_ACUMULADO, abs=0.005)
    assert round(r["value"], 2) == IBGE_2025_ACUMULADO


def test_somar_variacoes_daria_numero_errado():
    """A armadilha do enunciado: somar em vez de capitalizar."""
    doze = [float(v) for _, v in MENSAL_433[:12]]
    assert metrics.accumulate(doze) != pytest.approx(sum(doze), abs=1e-6)
    assert round(metrics.accumulate(doze), 2) == IBGE_2025_ACUMULADO
    assert round(sum(doze), 2) != IBGE_2025_ACUMULADO


@pytest.mark.parametrize("data_fim,publicado", [(iso(d), float(v)) for d, v in ACUM12_13522])
def test_cada_janela_reproduz_o_acumulado_publicado(data_fim, publicado):
    fim = date.fromisoformat(data_fim)
    r = metrics.accumulated_12m(mensal_frame(), fim, 40)
    if r["n_obs"] < 12:
        pytest.skip(
            f"janela que termina em {data_fim} exige meses anteriores ao início do conjunto "
            f"controlado (começa em 01/2025); há {r['n_obs']} dos 12. Esta janela é conferida "
            "contra a fonte real por scripts/verify_ipca.py"
        )
    assert round(r["value"], 2) == publicado


# --- comparação com a série publicada ----------------------------------------

def test_comparacao_com_a_13522_passa_em_todas_as_janelas():
    res = compare_accumulated(mensal_frame(), acum_frame())
    assert res["n_janelas"] == 10
    assert res["passed"]
    assert res["n_acima_da_tolerancia"] == 0
    assert res["n_arredonda_igual"] == res["n_janelas"]
    assert res["max_desvio"] < 0.01


def test_tolerancia_considera_os_dois_arredondamentos():
    res = compare_accumulated(mensal_frame(), acum_frame())
    linha = res["detail"].iloc[0]
    # 12 meses com 2 casas (meia unidade 0,005 cada) + a própria publicada com 2 casas
    assert 0.05 < linha["tolerancia"] < 0.08
    assert linha["desvio"] < linha["tolerancia"] / 10


def test_divergencia_real_reprova():
    adulterado = acum_frame().copy()
    adulterado.loc[adulterado["data"] == "01/12/2025", "valor"] = "5.50"
    res = compare_accumulated(mensal_frame(), adulterado)
    assert not res["passed"] and res["n_acima_da_tolerancia"] == 1


def test_casas_decimais_sao_lidas_do_texto_recebido():
    res = compare_accumulated(mensal_frame(), acum_frame())
    assert res["decimals_mensal"] == [2] and res["decimals_publicado"] == [2]


# --- validação ---------------------------------------------------------------

def test_variacao_negativa_e_aceita_sem_sinalizacao():
    """Deflação é resultado legítimo: agosto de 2025 fechou em -0,11%."""
    s = SERIES["ipca"]
    raw = pd.DataFrame([("01/08/2025", "-0.11")], columns=["data", "valor"])
    clean, rep = transform.clean_sgs(
        raw, reject_non_positive=s.reject_non_positive,
        alert_min=s.alert_min, alert_max=s.alert_max,
    )
    assert len(clean) == 1 and clean["atypical"].iloc[0] == 0
    assert rep["rows_discarded"] == 0


def test_valor_na_faixa_do_acumulado_de_12_meses_e_sinalizado():
    """A confusão realista: pegar a 13522 (4 a 5) achando que é a 433."""
    s = SERIES["ipca"]
    raw = pd.DataFrame([("01/09/2026", "4.58")], columns=["data", "valor"])
    clean, rep = transform.clean_sgs(
        raw, reject_non_positive=s.reject_non_positive,
        alert_min=s.alert_min, alert_max=s.alert_max,
    )
    assert rep["atypical"] == 1 and len(clean) == 1  # sinalizado, não descartado


def test_todos_os_mensais_reais_passam_sem_sinalizacao():
    s = SERIES["ipca"]
    raw = pd.DataFrame(MENSAL_433, columns=["data", "valor"])
    clean, rep = transform.clean_sgs(
        raw, reject_non_positive=s.reject_non_positive,
        alert_min=s.alert_min, alert_max=s.alert_max,
    )
    assert len(clean) == 21 and rep["atypical"] == 0 and rep["rows_discarded"] == 0


def test_limite_de_lacuna_mensal_aceita_meses_e_barra_mes_faltante():
    s = SERIES["ipca"]
    completo = pd.DataFrame({"ref_date": [iso(d) for d, _ in MENSAL_433], "value": [1.0] * 21})
    info = transform.validate_coverage(
        completo, date(2025, 1, 1), date(2026, 9, 1), s.max_gap_days
    )
    assert info["max_gap_days"] <= s.max_gap_days

    sem_um_mes = completo[completo["ref_date"] != "2025-06-01"]
    with pytest.raises(transform.DataQualityError, match="interrupção"):
        transform.validate_coverage(sem_um_mes, date(2025, 1, 1), date(2026, 9, 1), s.max_gap_days)


# --- pipeline ----------------------------------------------------------------

TODAY = date(2026, 10, 30)


def test_ipca_carrega_com_margem_de_doze_meses(tmp_path):
    res = pipeline.run(
        ["ipca"], today=TODAY, db_path=tmp_path / "t.db",
        session=MonthlySession(), sleep=no_sleep,
    )
    assert res[0].status == "success", res[0].message
    conn = db.connect(tmp_path / "t.db")
    primeira = conn.execute("SELECT MIN(ref_date) FROM observations").fetchone()[0]
    assert primeira < "2021-10-30", "a margem de 12 meses precisa estar na base"
    conn.close()


def test_defasagem_de_divulgacao_nao_impede_a_carga(tmp_path):
    """O mês corrente ainda não divulgado não é erro."""
    res = pipeline.run(
        ["ipca"], today=TODAY, db_path=tmp_path / "t.db",
        session=MonthlySession(ultimo=(2026, 9)), sleep=no_sleep,
    )
    assert res[0].status == "success"
    conn = db.connect(tmp_path / "t.db")
    assert conn.execute("SELECT MAX(ref_date) FROM observations").fetchone()[0] == "2026-09-01"
    conn.close()


def test_as_tres_series_convivem(tmp_path):
    from tests.helpers import BusinessDaySession, cdi_value

    sessao = RouterSession({
        1: BusinessDaySession(),
        12: BusinessDaySession(value_fn=cdi_value),
        433: MonthlySession(),
    })
    res = pipeline.run(
        ["ptax", "cdi", "ipca"], today=TODAY, db_path=tmp_path / "t.db",
        session=sessao, sleep=no_sleep,
    )
    assert [r.status for r in res] == ["success"] * 3
    conn = db.connect(tmp_path / "t.db")
    por_serie = dict(conn.execute("SELECT indicator, COUNT(*) FROM observations GROUP BY indicator"))
    assert set(por_serie) == {"ptax", "cdi", "ipca"}
    assert por_serie["ipca"] < 100, "série mensal tem ordem de grandeza muito menor"
    conn.close()
