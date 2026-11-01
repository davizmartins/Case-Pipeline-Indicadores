from datetime import date

import pandas as pd
import pytest

from src.transform import DataQualityError, clean_sgs, validate_coverage


def raw(*pairs):
    return pd.DataFrame(list(pairs), columns=["data", "valor"])


def ptax(data):
    return clean_sgs(data, reject_non_positive=True)


def cdi(data, alert_min=0.0, alert_max=0.5):
    return clean_sgs(data, reject_non_positive=False, alert_min=alert_min, alert_max=alert_max)


# --- padronização ------------------------------------------------------------

def test_padroniza_datas_e_valores_e_ordena():
    clean, rep = ptax(raw(("03/01/2026", "5.30"), ("01/01/2026", "5.10"), ("02/01/2026", "5.20")))
    assert list(clean["ref_date"]) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert list(clean["value"]) == [5.10, 5.20, 5.30]
    assert list(clean["atypical"]) == [0, 0, 0]
    assert rep["rows_in"] == 3 and rep["rows_out"] == 3 and rep["rows_discarded"] == 0


# --- categoria 1: inválido ---------------------------------------------------

def test_valores_invalidos_sao_descartados_nunca_viram_zero():
    clean, rep = ptax(
        raw(
            ("01/01/2026", "5.10"), ("02/01/2026", ""), ("03/01/2026", None),
            ("04/01/2026", "abc"), ("05/01/2026", "inf"), ("06/01/2026", "nan"),
        )
    )
    assert list(clean["ref_date"]) == ["2026-01-01"]
    assert 0.0 not in set(clean["value"])
    assert rep["discarded_invalid_value"] == 5


def test_nao_finitos_sao_rejeitados_tambem_em_serie_de_taxa():
    clean, rep = cdi(raw(("01/01/2026", "0.05"), ("02/01/2026", "inf"), ("03/01/2026", "-inf")))
    assert list(clean["ref_date"]) == ["2026-01-01"]
    assert rep["discarded_invalid_value"] == 2


def test_datas_invalidas_sao_descartadas():
    clean, rep = ptax(
        raw(("32/01/2026", "5.1"), ("2026-01-02", "5.2"), ("", "5.3"), ("01/01/2026", "5.0"))
    )
    assert list(clean["ref_date"]) == ["2026-01-01"]
    assert rep["discarded_invalid_date"] == 3


# --- categoria 2: impossível pela definição ----------------------------------

def test_ptax_rejeita_zero_e_negativo_por_definicao():
    clean, rep = ptax(raw(("01/01/2026", "5.1"), ("02/01/2026", "0"), ("03/01/2026", "-1")))
    assert list(clean["ref_date"]) == ["2026-01-01"] and rep["discarded_non_positive"] == 2


# --- categoria 3: atípico (carrega e sinaliza) -------------------------------

def test_taxa_zero_e_valida_e_nao_e_atipica():
    clean, rep = cdi(raw(("01/01/2026", "0"), ("02/01/2026", "0.05")))
    assert len(clean) == 2
    assert list(clean["atypical"]) == [0, 0]
    assert rep["discarded_non_positive"] == 0 and rep["atypical"] == 0


def test_taxa_negativa_e_carregada_e_sinalizada_nunca_rejeitada():
    clean, rep = cdi(raw(("01/01/2026", "-0.01"), ("02/01/2026", "0.05")))
    assert list(clean["ref_date"]) == ["2026-01-01", "2026-01-02"]
    assert list(clean["atypical"]) == [1, 0]
    assert rep["atypical"] == 1 and rep["rows_discarded"] == 0


def test_valor_acima_do_teto_e_carregado_e_sinalizado():
    clean, rep = cdi(raw(("01/01/2026", "0.05"), ("02/01/2026", "13.65")))
    assert len(clean) == 2 and list(clean["atypical"]) == [0, 1]
    assert rep["atypical"] == 1 and rep["atypical_sample"][0]["ref_date"] == "2026-01-02"


def test_faixa_e_configuravel():
    dados = raw(("01/01/2026", "0.9"))
    assert cdi(dados, alert_max=0.5)[1]["atypical"] == 1
    assert cdi(dados, alert_max=1.0)[1]["atypical"] == 0
    assert clean_sgs(dados, reject_non_positive=False)[1]["atypical"] == 0  # sem faixa


# --- duplicidade -------------------------------------------------------------

def test_duplicidade_mantem_ultima_ocorrencia_e_conta_conflitos():
    clean, rep = ptax(
        raw(
            ("01/01/2026", "5.10"), ("01/01/2026", "5.10"),
            ("02/01/2026", "5.20"), ("02/01/2026", "5.25"),
        )
    )
    assert list(clean["ref_date"]) == ["2026-01-01", "2026-01-02"]
    assert list(clean["value"]) == [5.10, 5.25]
    assert rep["duplicates_removed"] == 2 and rep["conflicting_dates"] == 1


def test_entrada_vazia_nao_quebra():
    clean, rep = ptax(raw())
    assert clean.empty and rep["rows_in"] == 0


# --- cobertura (alcance declarado) -------------------------------------------

def _clean(*dates):
    return pd.DataFrame({"ref_date": list(dates), "value": [5.0] * len(dates)})


def test_fim_de_semana_nao_e_interrupcao():
    info = validate_coverage(
        _clean("2026-01-02", "2026-01-05", "2026-01-06"), date(2026, 1, 1), date(2026, 1, 10), 10
    )
    assert info["max_gap_days"] == 3 and info["last_date"] == "2026-01-06"


def test_interrupcao_prolongada_e_rejeitada():
    with pytest.raises(DataQualityError, match="interrupção"):
        validate_coverage(_clean("2026-01-02", "2026-03-02"), date(2026, 1, 1), date(2026, 3, 10), 10)


def test_ausencia_isolada_passa_pela_validacao():
    """Limitação declarada: a validação não enxerga um dia útil faltando."""
    info = validate_coverage(
        _clean("2026-01-05", "2026-01-06", "2026-01-08"),  # falta quarta, 07/01
        date(2026, 1, 1), date(2026, 1, 10), 10,
    )
    assert info["max_gap_days"] == 2


def test_serie_vazia_ou_que_nao_cobre_o_inicio_e_rejeitada():
    with pytest.raises(DataQualityError):
        validate_coverage(_clean(), date(2026, 1, 1), date(2026, 3, 10), 10)
    with pytest.raises(DataQualityError, match="começa"):
        validate_coverage(_clean("2026-02-20", "2026-02-23"), date(2026, 1, 1), date(2026, 3, 10), 10)


def test_dado_posterior_ao_fim_da_janela_e_rejeitado():
    with pytest.raises(DataQualityError, match="posterior"):
        validate_coverage(_clean("2026-01-02", "2026-04-01"), date(2026, 1, 1), date(2026, 3, 10), 100)
