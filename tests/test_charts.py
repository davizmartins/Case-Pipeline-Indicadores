"""Escala dos gráficos. Testada fora do app, por isso charts.py é módulo separado."""

import pandas as pd
import pytest

from src import charts


def test_eixo_nao_comeca_em_zero_quando_os_dados_estao_longe_de_zero():
    low, high = charts.axis_domain(4.6175, 6.2086)
    assert low > 4.0, "começar perto de zero achataria a variação da cotação"
    assert low < 4.6175 and high > 6.2086  # a linha não encosta nas bordas


def test_margem_e_proporcional_a_amplitude():
    low, high = charts.axis_domain(10.0, 20.0, margin=0.05)
    assert low == pytest.approx(9.5) and high == pytest.approx(20.5)


def test_margem_configuravel():
    assert charts.axis_domain(10.0, 20.0, margin=0.10) == pytest.approx((9.0, 21.0))


def test_serie_constante_ainda_tem_faixa_valida():
    low, high = charts.axis_domain(0.050788, 0.050788)
    assert low < 0.050788 < high, "sem folga, a linha viraria a borda do gráfico"


def test_serie_constante_em_zero_nao_quebra():
    low, high = charts.axis_domain(0.0, 0.0)
    assert low < high


def test_faixa_invertida_e_rejeitada():
    with pytest.raises(ValueError):
        charts.axis_domain(10.0, 1.0)


def _frame():
    return pd.DataFrame(
        {
            "ref_date": pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30"]),
            "value": [5.342, 5.3744, 5.4212],
        }
    )


def test_grafico_usa_o_dominio_calculado_e_nao_arredonda_para_zero():
    spec = charts.line_chart(_frame(), "R$/US$", 4).to_dict()
    escala = spec["encoding"]["y"]["scale"]
    assert escala["nice"] is False, "nice=True deixaria o Altair esticar o eixo por conta própria"
    low, high = escala["domain"]
    assert low > 5.0 and high < 5.5


def test_grafico_declara_a_unidade_no_eixo_e_nao_tem_titulo():
    spec = charts.line_chart(_frame(), "R$/US$", 4).to_dict()
    assert spec["encoding"]["y"]["title"] == "R$/US$"
    assert spec["encoding"]["x"]["title"] == "Data"
    assert "title" not in spec, "um título interpretativo sugeriria leitura além dos dados"


def test_grafico_mantem_os_valores_do_eixo_visiveis():
    spec = charts.line_chart(_frame(), "R$/US$", 4).to_dict()
    assert spec["encoding"]["y"]["axis"]["labels"] is True


def test_data_no_tooltip_sai_no_formato_brasileiro():
    spec = charts.line_chart(_frame(), "R$/US$", 4).to_dict()
    formatos = [t.get("format") for t in spec["encoding"]["tooltip"]]
    assert "%d/%m/%Y" in formatos
