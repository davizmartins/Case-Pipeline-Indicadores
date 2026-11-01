"""Gráficos do dashboard. Separado de app.py para que a escala seja testável.

Decisão de escala: o eixo vertical é ajustado à faixa dos dados do período, com uma
pequena margem, e NÃO começa em zero. São gráficos de linha para acompanhar o
MOVIMENTO de uma cotação ou de uma taxa, não para comparar magnitudes entre
categorias — num gráfico de barras a base zero seria obrigatória, aqui não é.

Os gráficos não levam título: o eixo diz a unidade e o período, e um título
interpretativo sugeriria leitura que os dados sozinhos não sustentam.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

MARGIN = 0.05  # 5% da amplitude, para a linha não encostar nas bordas

# Paleta categórica. A cor segue o INDICADOR, não a ordem em que ele aparece: está
# definida em Series.color, para que o mesmo indicador tenha a mesma cor em todo o
# painel e para que filtrar séries não repinte as que sobraram.
#
# Os quatro tons foram validados (separação para daltonismo e contraste contra fundo
# claro e escuro). Os pares que realmente convivem num mesmo gráfico são:
#   base 100  -> azul, laranja, verde-água
#   barras    -> azul, amarelo
# Ambos passam em todas as checagens. O amarelo fica a 2,99:1 de contraste em fundo
# claro, logo abaixo de 3:1; por isso o gráfico de barras traz legenda e os valores
# acumulados aparecem em números grandes acima dele.


def _eixo_data(titulo: str = "Data") -> alt.X:
    """Eixo temporal com granularidade de DIA e rótulo em formato brasileiro.

    Sem o timeUnit, um período curto faz o Vega-Lite rotular o eixo em HORAS
    ("09 PM", "03 AM") sobre dados que são diários — sugerindo observações
    intradiárias que não existem.
    """
    return alt.X(
        "yearmonthdate(ref_date):T", title=titulo, axis=alt.Axis(format="%d/%m/%Y")
    )


def axis_domain(low: float, high: float, margin: float = MARGIN) -> tuple[float, float]:
    """Faixa do eixo vertical: [mínimo, máximo] dos dados mais uma folga proporcional.

    Série constante não tem amplitude; nesse caso a folga vem do próprio nível, para
    que a linha não vire uma borda do gráfico.
    """
    if high < low:
        raise ValueError(f"máximo {high} menor que o mínimo {low}")
    span = high - low
    slack = span * margin if span > 0 else max(abs(high) * 0.01, 1e-9)
    return low - slack, high + slack


def multi_line_chart(
    frame: pd.DataFrame,
    y_title: str,
    decimals: int,
    color_map: dict[str, str],
    value_col: str = "index",
    series_col: str = "serie",
    margin: float = MARGIN,
    height: int = 360,
) -> alt.Chart:
    """Várias séries no mesmo gráfico, cada uma nas SUAS próprias datas.

    Nada é alinhado, preenchido ou excluído: o formato longo permite que cada série
    tenha o seu calendário. `frame` traz ref_date, `series_col` e `value_col`.
    """
    low, high = axis_domain(
        float(frame[value_col].min()), float(frame[value_col].max()), margin
    )
    return (
        alt.Chart(frame)
        .mark_line()
        .encode(
            x=_eixo_data(),
            y=alt.Y(
                f"{value_col}:Q",
                title=y_title,
                scale=alt.Scale(domain=[low, high], nice=False),
                axis=alt.Axis(labels=True, format=f".{decimals}f"),
            ),
            color=alt.Color(
                f"{series_col}:N",
                title="Indicador",
                scale=alt.Scale(domain=list(color_map), range=list(color_map.values())),
            ),
            tooltip=[
                alt.Tooltip("ref_date:T", title="Data", format="%d/%m/%Y"),
                alt.Tooltip(f"{series_col}:N", title="Indicador"),
                alt.Tooltip(f"{value_col}:Q", title=y_title, format=f".{decimals}f"),
            ],
        )
        .properties(height=height)
    )


def bar_chart(
    frame: pd.DataFrame,
    y_title: str,
    decimals: int,
    color_map: dict[str, str],
    value_col: str = "valor",
    series_col: str = "serie",
    x_col: str = "mes",
    height: int = 320,
) -> alt.Chart:
    """Barras agrupadas por período — usado na comparação mensal.

    Aqui a base zero é obrigatória: barras comparam magnitudes, e cortar o eixo
    distorceria a leitura. É o oposto da decisão tomada para os gráficos de linha.
    """
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X(f"{x_col}:N", title="Mês"),
            y=alt.Y(f"{value_col}:Q", title=y_title, axis=alt.Axis(format=f".{decimals}f")),
            color=alt.Color(
                f"{series_col}:N",
                title="Indicador",
                scale=alt.Scale(domain=list(color_map), range=list(color_map.values())),
            ),
            xOffset=f"{series_col}:N",
            tooltip=[
                alt.Tooltip(f"{x_col}:N", title="Mês"),
                alt.Tooltip(f"{series_col}:N", title="Indicador"),
                alt.Tooltip(f"{value_col}:Q", title=y_title, format=f".{decimals}f"),
            ],
        )
        .properties(height=height)
    )


def line_chart(
    frame: pd.DataFrame,
    y_title: str,
    decimals: int,
    color: str | None = None,
    margin: float = MARGIN,
    height: int = 280,
) -> alt.Chart:
    """Linha de `value` contra `ref_date`, com o eixo ajustado à faixa dos dados.

    Série única não leva legenda: o título do cartão já a nomeia. A cor vem do
    indicador, para que ele seja reconhecível em todos os gráficos do painel.
    """
    low, high = axis_domain(float(frame["value"].min()), float(frame["value"].max()), margin)
    marca = alt.Chart(frame).mark_line(color=color) if color else alt.Chart(frame).mark_line()
    return marca.encode(
        x=_eixo_data(),
        y=alt.Y(
            "value:Q",
            title=y_title,
            scale=alt.Scale(domain=[low, high], nice=False),
            axis=alt.Axis(labels=True, format=f".{decimals}f"),
        ),
        tooltip=[
            alt.Tooltip("ref_date:T", title="Data", format="%d/%m/%Y"),
            alt.Tooltip("value:Q", title=y_title, format=f".{decimals}f"),
        ],
    ).properties(height=height)
