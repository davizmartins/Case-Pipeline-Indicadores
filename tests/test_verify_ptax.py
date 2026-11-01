import pandas as pd

from scripts.verify_ptax import compare_series


def df(pairs):
    return pd.DataFrame(pairs, columns=["ref_date", "value"])


def test_series_identicas_passam():
    a = df([("2026-01-02", 5.1234), ("2026-01-05", 5.2)])
    res = compare_series(a, a.copy())
    assert res["passed"] and res["n_common"] == 2 and res["max_abs_diff"] == 0


def test_coincidir_em_alguns_dias_nao_basta_data_faltante_reprova():
    a = df([("2026-01-02", 5.1), ("2026-01-05", 5.2), ("2026-01-06", 5.3)])
    b = df([("2026-01-02", 5.1), ("2026-01-05", 5.2)])  # os dias em comum coincidem
    res = compare_series(a, b)
    assert not res["passed"] and res["only_in_sgs"] == ["2026-01-06"]


def test_divergencia_de_valor_na_quarta_casa_reprova_mas_ruido_alem_dela_nao():
    a = df([("2026-01-02", 5.12341), ("2026-01-05", 5.2000)])
    b = df([("2026-01-02", 5.12344), ("2026-01-05", 5.2001)])
    res = compare_series(a, b)
    assert res["n_value_mismatch"] == 1 and res["mismatches"][0]["ref_date"] == "2026-01-05"
    assert not res["passed"]
