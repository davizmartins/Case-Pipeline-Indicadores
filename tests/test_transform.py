from datetime import date

import pandas as pd
import pytest

from src.transform import DataQualityError, clean_sgs, validate_coverage


def raw(*pairs):
    return pd.DataFrame(list(pairs), columns=["data", "valor"])


def test_padroniza_datas_e_valores_e_ordena():
    clean, rep = clean_sgs(
        raw(("03/01/2026", "5.30"), ("01/01/2026", "5.10"), ("02/01/2026", "5.20")),
        positive_only=True,
    )
    assert list(clean["ref_date"]) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert list(clean["value"]) == [5.10, 5.20, 5.30]
    assert clean["value"].dtype == "float64"
    assert rep["rows_in"] == 3 and rep["rows_out"] == 3 and rep["rows_discarded"] == 0


def test_valores_invalidos_sao_descartados_nunca_viram_zero():
    clean, rep = clean_sgs(
        raw(
            ("01/01/2026", "5.10"),
            ("02/01/2026", ""),
            ("03/01/2026", None),
            ("04/01/2026", "abc"),
            ("05/01/2026", "inf"),
            ("06/01/2026", "nan"),
        ),
        positive_only=True,
    )
    assert list(clean["ref_date"]) == ["2026-01-01"]
    assert 0.0 not in set(clean["value"])
    assert rep["discarded_invalid_value"] == 5


def test_datas_invalidas_sao_descartadas():
    clean, rep = clean_sgs(
        raw(("32/01/2026", "5.1"), ("2026-01-02", "5.2"), ("", "5.3"), ("01/01/2026", "5.0")),
        positive_only=True,
    )
    assert list(clean["ref_date"]) == ["2026-01-01"]
    assert rep["discarded_invalid_date"] == 3


def test_ptax_nao_aceita_zero_nem_negativo_mas_serie_livre_aceita():
    data = raw(("01/01/2026", "5.1"), ("02/01/2026", "0"), ("03/01/2026", "-1"))
    clean, rep = clean_sgs(data, positive_only=True)
    assert list(clean["ref_date"]) == ["2026-01-01"] and rep["discarded_non_positive"] == 2
    clean, rep = clean_sgs(data, positive_only=False)
    assert len(clean) == 3 and rep["discarded_non_positive"] == 0


def test_duplicidade_mantem_ultima_ocorrencia_e_conta_conflitos():
    clean, rep = clean_sgs(
        raw(
            ("01/01/2026", "5.10"),
            ("01/01/2026", "5.10"),  # duplicata idêntica
            ("02/01/2026", "5.20"),
            ("02/01/2026", "5.25"),  # conflito: valores diferentes na mesma data
        ),
        positive_only=True,
    )
    assert list(clean["ref_date"]) == ["2026-01-01", "2026-01-02"]
    assert list(clean["value"]) == [5.10, 5.25]
    assert rep["duplicates_removed"] == 2 and rep["conflicting_dates"] == 1


def test_entrada_vazia_nao_quebra():
    clean, rep = clean_sgs(raw(), positive_only=True)
    assert clean.empty and rep["rows_in"] == 0


def _clean(*dates):
    return pd.DataFrame({"ref_date": list(dates), "value": [5.0] * len(dates)})


def test_fim_de_semana_nao_e_lacuna():
    # sex -> seg = 3 dias
    info = validate_coverage(
        _clean("2026-01-02", "2026-01-05", "2026-01-06"), date(2026, 1, 1), date(2026, 1, 10), 10
    )
    assert info["max_gap_days"] == 3 and info["last_date"] == "2026-01-06"


def test_lacuna_grande_e_rejeitada():
    with pytest.raises(DataQualityError, match="lacuna"):
        validate_coverage(
            _clean("2026-01-02", "2026-03-02"), date(2026, 1, 1), date(2026, 3, 10), 10
        )


def test_serie_vazia_ou_que_nao_cobre_o_inicio_e_rejeitada():
    with pytest.raises(DataQualityError):
        validate_coverage(_clean(), date(2026, 1, 1), date(2026, 3, 10), 10)
    with pytest.raises(DataQualityError, match="começa"):
        validate_coverage(_clean("2026-02-20", "2026-02-23"), date(2026, 1, 1), date(2026, 3, 10), 10)


def test_dado_posterior_ao_fim_da_janela_e_rejeitado():
    with pytest.raises(DataQualityError, match="posterior"):
        validate_coverage(_clean("2026-01-02", "2026-04-01"), date(2026, 1, 1), date(2026, 3, 10), 100)
