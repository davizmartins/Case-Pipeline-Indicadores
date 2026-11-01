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


def line_chart(
    frame: pd.DataFrame,
    y_title: str,
    decimals: int,
    margin: float = MARGIN,
    height: int = 280,
) -> alt.Chart:
    """Linha de `value` contra `ref_date`, com o eixo ajustado à faixa dos dados."""
    low, high = axis_domain(float(frame["value"].min()), float(frame["value"].max()), margin)
    return (
        alt.Chart(frame)
        .mark_line()
        .encode(
            x=alt.X("ref_date:T", title="Data"),
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
        )
        .properties(height=height)
    )
