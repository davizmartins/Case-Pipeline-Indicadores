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


# --- eixo temporal e cores ---------------------------------------------------

def _frame_longo():
    dias = pd.bdate_range("2021-11-01", "2026-10-30")
    return pd.DataFrame({"ref_date": dias, "value": [100.0 + i * 0.01 for i in range(len(dias))]})


def _frame_curto():
    dias = pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-28"])
    return pd.DataFrame({"ref_date": dias, "value": [100.0, 99.0, 98.0]})


@pytest.mark.parametrize("frame", [_frame_curto(), _frame_longo()])
def test_eixo_usa_granularidade_de_dia_e_nunca_horas(frame):
    """Sem timeUnit, um período curto era rotulado em horas sobre dados diários."""
    spec = charts.line_chart(frame, "pontos", 0).to_dict()
    x = spec["encoding"]["x"]
    assert x.get("timeUnit") == "yearmonthdate"
    assert x["axis"]["format"] == "%d/%m/%Y"


def test_cor_da_serie_e_aplicada_na_linha_unica():
    spec = charts.line_chart(_frame_curto(), "pontos", 0, color="#199e70").to_dict()
    assert spec["mark"]["color"] == "#199e70"


def test_sem_cor_a_linha_nao_fixa_nenhuma():
    assert "color" not in charts.line_chart(_frame_curto(), "pontos", 0).to_dict()["mark"]


def _longo_multi():
    return pd.DataFrame(
        {
            "ref_date": pd.to_datetime(["2026-10-26", "2026-10-27"] * 2),
            "index": [100.0, 101.0, 100.0, 99.0],
            "serie": ["A", "A", "B", "B"],
        }
    )


def test_cores_das_multiplas_series_seguem_o_mapa_e_nao_a_ordem():
    cores = {"A": "#3987e5", "B": "#d95926"}
    escala = charts.multi_line_chart(_longo_multi(), "Base 100", 1, cores).to_dict()["encoding"]["color"]["scale"]
    assert escala["domain"] == ["A", "B"]
    assert escala["range"] == ["#3987e5", "#d95926"]
    # inverter a ordem do mapa inverte as cores: a cor acompanha a entidade
    invertido = charts.multi_line_chart(_longo_multi(), "Base 100", 1, {"B": "#d95926", "A": "#3987e5"})
    esc2 = invertido.to_dict()["encoding"]["color"]["scale"]
    assert dict(zip(esc2["domain"], esc2["range"])) == {"A": "#3987e5", "B": "#d95926"}


def test_grafico_de_multiplas_series_tambem_usa_eixo_de_dia():
    spec = charts.multi_line_chart(_longo_multi(), "Base 100", 1, {"A": "#1", "B": "#2"}).to_dict()
    assert spec["encoding"]["x"].get("timeUnit") == "yearmonthdate"


def test_barras_recebem_o_mapa_de_cores():
    frame = pd.DataFrame({"mes": ["11/2025", "11/2025"], "valor": [1.0, 0.3], "serie": ["A", "B"]})
    escala = charts.bar_chart(frame, "% no mês", 2, {"A": "#3987e5", "B": "#c98500"}).to_dict()["encoding"]["color"]["scale"]
    assert escala["range"] == ["#3987e5", "#c98500"]


def test_cada_indicador_tem_cor_propria_e_distinta():
    from src.config import SERIES

    cores = [s.color for s in SERIES.values()]
    assert len(set(cores)) == len(cores), "dois indicadores com a mesma cor"
    assert all(c.startswith("#") and len(c) == 7 for c in cores)


def test_barras_respeitam_a_ordem_cronologica_informada():
    """Rótulos como '11/2025' são texto: sem ordem explícita saem em ordem alfabética,
    agrupando todos os janeiros, depois todos os fevereiros."""
    ordem = ["11/2025", "12/2025", "01/2026", "02/2026"]
    frame = pd.DataFrame({"mes": ordem, "valor": [1.0] * 4, "serie": ["A"] * 4})
    spec = charts.bar_chart(frame, "% no mês", 2, {"A": "#3987e5"}, x_order=ordem).to_dict()
    assert spec["encoding"]["x"]["sort"] == ordem


def test_sem_ordem_informada_a_biblioteca_decide():
    frame = pd.DataFrame({"mes": ["11/2025"], "valor": [1.0], "serie": ["A"]})
    spec = charts.bar_chart(frame, "% no mês", 2, {"A": "#3987e5"}).to_dict()
    assert spec["encoding"]["x"].get("sort") is None
