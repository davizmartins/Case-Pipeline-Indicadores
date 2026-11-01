"""Comparações: base 100 diária, comparação mensal e retorno real.

Dados controlados. As séries de teste têm calendários DIFERENTES de propósito — é a
situação real, medida na base: PTAX e Ibovespa divergem em 8 datas na janela de 5 anos.
"""

from datetime import date

import pandas as pd
import pytest

from src import metrics


def quadro(pares):
    return pd.DataFrame(pares, columns=["ref_date", "value"])


NIVEL_A = quadro([("2026-01-05", 100.0), ("2026-01-06", 110.0), ("2026-01-07", 99.0)])
NIVEL_B = quadro([("2026-01-05", 50.0), ("2026-01-07", 55.0), ("2026-01-08", 60.0)])
TAXA = quadro([("2026-01-05", 1.0), ("2026-01-06", 2.0), ("2026-01-07", 3.0)])


# --- data-base comum ---------------------------------------------------------

def test_data_base_e_a_primeira_com_observacao_em_todas():
    base = metrics.common_base_date([NIVEL_A, NIVEL_B, TAXA], date(2026, 1, 1), date(2026, 1, 31))
    assert base == "2026-01-05"


def test_data_base_ignora_datas_fora_do_periodo():
    base = metrics.common_base_date([NIVEL_A, NIVEL_B, TAXA], date(2026, 1, 6), date(2026, 1, 31))
    assert base == "2026-01-07", "05/01 está fora do período; a próxima comum é 07/01"


def test_sem_data_comum_devolve_none():
    a = quadro([("2026-01-05", 1.0)])
    b = quadro([("2026-01-06", 1.0)])
    assert metrics.common_base_date([a, b], date(2026, 1, 1), date(2026, 1, 31)) is None


def test_serie_vazia_impede_a_base():
    assert metrics.common_base_date([NIVEL_A, quadro([])], date(2026, 1, 1), date(2026, 1, 31)) is None


# --- base 100 ----------------------------------------------------------------

def test_todas_as_series_comecam_em_100():
    base = "2026-01-05"
    for idx in (metrics.index_level(NIVEL_A, base), metrics.index_level(NIVEL_B, base),
                metrics.index_rate(TAXA, base)):
        assert idx["index"].iloc[0] == pytest.approx(100.0)
        assert idx["ref_date"].iloc[0] == base


def test_nivel_e_razao_entre_pontas():
    idx = metrics.index_level(NIVEL_A, "2026-01-05")
    assert list(idx["index"]) == pytest.approx([100.0, 110.0, 99.0])


def test_cada_serie_mantem_as_proprias_datas():
    """Nada é alinhado, preenchido ou truncado."""
    a = metrics.index_level(NIVEL_A, "2026-01-05")
    b = metrics.index_level(NIVEL_B, "2026-01-05")
    assert list(a["ref_date"]) == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert list(b["ref_date"]) == ["2026-01-05", "2026-01-07", "2026-01-08"]
    assert len(a) == 3 and len(b) == 3


def test_taxa_na_data_base_nao_entra_no_acumulado():
    """Convenção documentada: entram as taxas das datas POSTERIORES à base."""
    idx = metrics.index_rate(TAXA, "2026-01-05")
    assert idx["index"].iloc[1] == pytest.approx(102.0)  # só 2%, não 1%×2%
    assert idx["index"].iloc[2] == pytest.approx(102.0 * 1.03)


def test_taxa_capitaliza_e_nao_soma():
    idx = metrics.index_rate(TAXA, "2026-01-05")
    assert idx["index"].iloc[-1] == pytest.approx(100 * 1.02 * 1.03)
    assert idx["index"].iloc[-1] != pytest.approx(100 + 2 + 3)


def test_data_base_ausente_na_serie_e_erro():
    with pytest.raises(ValueError, match="data-base"):
        metrics.index_level(NIVEL_B, "2026-01-06")
    with pytest.raises(ValueError, match="data-base"):
        metrics.index_rate(TAXA, "2026-01-08")


def test_valor_base_zero_e_erro():
    with pytest.raises(ValueError, match="zero"):
        metrics.index_level(quadro([("2026-01-05", 0.0), ("2026-01-06", 1.0)]), "2026-01-05")


# --- limites do mês ----------------------------------------------------------

@pytest.mark.parametrize(
    "ano,mes,esperado",
    [
        (2026, 1, (date(2025, 12, 31), date(2026, 1, 31))),
        (2026, 2, (date(2026, 1, 31), date(2026, 2, 28))),
        (2024, 2, (date(2024, 1, 31), date(2024, 2, 29))),  # bissexto
        (2026, 12, (date(2026, 11, 30), date(2026, 12, 31))),
    ],
)
def test_limites_do_mes(ano, mes, esperado):
    assert metrics.month_bounds(ano, mes) == esperado


# --- retorno real ------------------------------------------------------------

def test_retorno_real_e_razao_e_nao_diferenca():
    real = metrics.real_return(14.0, 4.5)
    assert real == pytest.approx((1.14 / 1.045 - 1) * 100)
    assert real != pytest.approx(14.0 - 4.5), "subtrair dá resultado parecido e errado"
    assert real < 14.0 - 4.5


def test_retorno_real_negativo_quando_a_inflacao_supera():
    assert metrics.real_return(3.0, 5.0) < 0


def test_retorno_real_com_deflacao():
    assert metrics.real_return(1.0, -0.5) > 1.0


# --- meses elegíveis ---------------------------------------------------------

def serie_diaria_mensal(meses):
    """Uma taxa diária constante e um índice mensal, cobrindo os meses pedidos."""
    dias, mensal = [], []
    for ano, mes in meses:
        _, ultimo = metrics.month_bounds(ano, mes)
        for d in pd.bdate_range(date(ano, mes, 1), ultimo):
            dias.append((d.strftime("%Y-%m-%d"), 0.05))
        mensal.append((f"{ano:04d}-{mes:02d}-01", 0.40))
    return quadro(dias), quadro(mensal)


MESES = [(2026, m) for m in range(1, 7)]


def test_so_entram_meses_inteiros_dentro_do_filtro():
    taxa, mensal = serie_diaria_mensal(MESES)
    # o filtro começa no meio de janeiro: janeiro não cabe inteiro
    elegiveis = metrics.eligible_months(taxa, mensal, date(2026, 1, 15), date(2026, 6, 30), 10)
    assert [m["mes"] for m in elegiveis] == ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def test_mes_sem_indice_mensal_publicado_fica_de_fora():
    taxa, mensal = serie_diaria_mensal(MESES)
    sem_junho = mensal[mensal["ref_date"] != "2026-06-01"]
    elegiveis = metrics.eligible_months(taxa, sem_junho, date(2026, 1, 1), date(2026, 6, 30), 10)
    assert [m["mes"] for m in elegiveis][-1] == "2026-05"


def test_ultimo_mes_elegivel_sai_dos_dados_e_nao_esta_fixado():
    """Tirar o último índice mensal deve mover o fim da comparação, sem tocar no código."""
    taxa, mensal = serie_diaria_mensal(MESES)
    completo = metrics.eligible_months(taxa, mensal, date(2026, 1, 1), date(2026, 6, 30), 10)
    reduzido = metrics.eligible_months(
        taxa, mensal[mensal["ref_date"] <= "2026-03-01"], date(2026, 1, 1), date(2026, 6, 30), 10
    )
    assert completo[-1]["mes"] == "2026-06" and reduzido[-1]["mes"] == "2026-03"


def test_mes_com_interrupcao_na_serie_diaria_fica_de_fora():
    taxa, mensal = serie_diaria_mensal(MESES)
    sem_marco = taxa[~taxa["ref_date"].str.startswith("2026-03")]
    elegiveis = metrics.eligible_months(sem_marco, mensal, date(2026, 1, 1), date(2026, 6, 30), 10)
    assert "2026-03" not in [m["mes"] for m in elegiveis]


def test_acumulado_mensal_capitaliza_as_taxas_do_mes():
    taxa, mensal = serie_diaria_mensal([(2026, 1)])
    r = metrics.monthly_rate_accumulation(taxa, 2026, 1, 10)
    assert r["value"] == pytest.approx(metrics.accumulate([0.05] * r["n_obs"]))
    assert r["coverage"]["ok"]


def test_cada_mes_traz_taxa_inflacao_e_real():
    taxa, mensal = serie_diaria_mensal(MESES)
    m = metrics.eligible_months(taxa, mensal, date(2026, 1, 1), date(2026, 6, 30), 10)[0]
    assert set(m) == {"mes", "taxa", "mensal", "real", "n_obs"}
    assert m["real"] == pytest.approx(metrics.real_return(m["taxa"], m["mensal"]))


def test_series_vazias_nao_quebram():
    assert metrics.eligible_months(quadro([]), quadro([]), date(2026, 1, 1), date(2026, 6, 30), 10) == []
