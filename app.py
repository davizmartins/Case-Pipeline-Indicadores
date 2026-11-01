"""Dashboard: dólar, série SGS 12 e IPCA.

Lê SOMENTE a base já carregada; nunca chama as fontes. Para atualizar os dados,
rode `python -m src.pipeline`. Execução: `streamlit run app.py`.
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from src import charts, clock, db, freshness, metrics
from src.config import SERIES, get_db_path
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp


def md(texto: str) -> str:
    """Escapa cifrões: no markdown do Streamlit, '$...$' é interpretado como LaTeX.

    Sem isso, a unidade "R$/US$" sai renderizada como fórmula matemática.
    """
    return texto.replace("$", r"\$")


def mes_ano(d) -> str:
    return f"{d.month:02d}/{d.year}"


st.set_page_config(page_title="Indicadores de Mercado", page_icon="📈", layout="wide")
st.title("Indicadores de Mercado")
st.caption("Versão em construção: dólar, série SGS 12 e IPCA. Ibovespa ainda não entrou.")

path = get_db_path()
if not path.exists():
    st.error("A base de dados ainda não existe. Execute `python -m src.pipeline` e recarregue a página.")
    st.stop()

try:
    conn = db.connect_readonly(path)
    data = {k: db.read_series(conn, k) for k in SERIES}
    runs = {k: db.latest_run(conn, k) for k in SERIES}
    last_ok = {k: db.latest_run(conn, k, status="success") for k in SERIES}
    conn.close()
except sqlite3.Error as exc:
    st.error(f"Não foi possível ler a base de dados: {exc}")
    st.stop()

hoje = clock.today_br()

# --- Avisos de transparência -------------------------------------------------
for key, series in SERIES.items():
    run = runs.get(key)
    if run and run["status"] == "failed":
        st.warning(
            f"**{series.name}** — a última execução do pipeline "
            f"({fmt_timestamp(run['finished_at'])}) falhou: {run['message']}. "
            "Os dados exibidos vêm da última carga bem-sucedida."
        )
    df = data.get(key)
    if df is None or df.empty:
        continue
    aviso = freshness.staleness_warning(series, df.iloc[-1]["ref_date"].date(), hoje)
    if aviso:
        st.warning(f"**{series.name}** — {aviso}")
    if int(df["atypical"].sum()):
        st.warning(
            f"**{series.name}** — {int(df['atypical'].sum())} observação(ões) sinalizada(s) "
            "para revisão, por destoarem da faixa de alerta ou do valor anterior. Foram "
            "carregadas sem substituição: a sinalização **pede conferência humana e não "
            "declara erro**.",
            icon="🔎",
        )

col_ptax, col_cdi = st.columns(2)
col_ipca, col_ibov = st.columns(2)


def acumulado_12m(series, df):
    """Acumulado em 12 meses até a última observação, ou None se a janela não cobre."""
    return metrics.accumulated_12m(
        df.assign(ref_date=df["ref_date"].dt.strftime("%Y-%m-%d")),
        df.iloc[-1]["ref_date"].date(),
        series.max_gap_days,
        series.unexplained_absences,
    )


# --- Cartão: dólar americano (venda) ----------------------------------------
with col_ptax:
    s = SERIES["ptax"]
    df = data["ptax"]
    st.subheader(s.name)
    if df.empty:
        st.error("Sem observações. Execute `python -m src.pipeline`.")
    else:
        ultimo = df.iloc[-1]
        delta = fmt_pct((ultimo["value"] / df.iloc[-2]["value"] - 1) * 100) if len(df) > 1 else None
        st.metric(
            label=md(f"Cotação de venda — {s.unit}"),
            value=f"R$ {fmt_number(ultimo['value'], 4)}",
            delta=delta,
            help="Variação em relação à observação anterior. É uma taxa de câmbio de "
            "referência, não o retorno de um investimento em dólar.",
        )
        st.caption(f"Data de referência: {fmt_date(ultimo['ref_date'].date())}")
        st.caption(f"Fonte: {s.source}")
        st.altair_chart(charts.line_chart(df, s.unit, 2), width="stretch")

# --- Cartão: série SGS 12 ----------------------------------------------------
with col_cdi:
    s = SERIES["cdi"]
    df = data["cdi"]
    st.subheader(s.name)
    if s.identification_note and s.identification_alert:
        st.info(s.identification_note, icon="⚠️")
    if df.empty:
        st.error("Sem observações. Execute `python -m src.pipeline`.")
    else:
        ultimo = df.iloc[-1]
        d_ref = ultimo["ref_date"].date()
        acum = acumulado_12m(s, df)
        if acum["value"] is None:
            st.metric(label="Acumulado em 12 meses", value="indisponível")
            st.caption(
                "A métrica não é apresentada porque a janela de 12 meses não está "
                f"suficientemente coberta: {acum['coverage']['reason']}."
            )
        else:
            st.metric(
                label="Acumulado em 12 meses",
                value=f"{fmt_number(acum['value'], 2)}%",
                help="Capitalização composta das taxas diárias da janela. A checagem de "
                "cobertura detecta interrupção prolongada da fonte, não ausência isolada.",
            )
            st.caption(
                f"Período: observações posteriores a {fmt_date(acum['start_exclusive'])} até "
                f"{fmt_date(acum['end'])} · {acum['n_obs']} observações"
            )
        st.caption(
            f"Taxa de {fmt_date(d_ref)}: {fmt_number(ultimo['value'], 6)}% a.d., "
            f"equivalente a {fmt_number(metrics.annualize(ultimo['value']), 2)}% a.a. (base 252). "
            "É conversão de unidade da taxa desse dia, não previsão de rendimento."
        )
        st.caption(f"Fonte: {s.source}")
        st.altair_chart(charts.line_chart(df, s.unit, 3), width="stretch")

# --- Cartão: IPCA ------------------------------------------------------------
with col_ipca:
    s = SERIES["ipca"]
    df = data["ipca"]
    st.subheader(s.name)
    if s.identification_note and s.identification_alert:
        st.info(s.identification_note, icon="⚠️")
    if df.empty:
        st.error("Sem observações. Execute `python -m src.pipeline`.")
    else:
        ultimo = df.iloc[-1]
        d_ref = ultimo["ref_date"].date()
        acum = acumulado_12m(s, df)
        if acum["value"] is None:
            st.metric(label="IPCA acumulado em 12 meses", value="indisponível")
            st.caption(
                "A métrica não é apresentada porque a janela de 12 meses não está "
                f"suficientemente coberta: {acum['coverage']['reason']}."
            )
        else:
            st.metric(
                label="IPCA acumulado em 12 meses",
                value=f"{fmt_number(acum['value'], 2)}%",
                help="Capitalização composta das variações mensais da janela — soma de "
                "variações daria número errado. A checagem de cobertura detecta "
                "interrupção prolongada da fonte, não ausência isolada.",
            )
            st.caption(
                f"Período: meses posteriores a {mes_ano(acum['start_exclusive'])} até "
                f"{mes_ano(acum['end'])} · {acum['n_obs']} meses"
            )
        st.caption(
            f"Variação de {mes_ano(d_ref)}: {fmt_pct(ultimo['value'])}. "
            "O mês de referência é anterior ao mês corrente porque o índice é "
            "divulgado depois do fechamento do mês."
        )
        st.caption(f"Fonte: {s.source}")
        st.altair_chart(charts.line_chart(df, s.unit, 2), width="stretch")

# --- Cartão: Ibovespa --------------------------------------------------------
with col_ibov:
    s = SERIES["ibovespa"]
    df = data["ibovespa"]
    st.subheader(s.name)
    if s.identification_note and s.identification_alert:
        st.info(s.identification_note, icon="⚠️")
    if df.empty:
        st.error("Sem observações. Execute `python -m src.pipeline`.")
    else:
        ultimo = df.iloc[-1]
        delta = fmt_pct((ultimo["value"] / df.iloc[-2]["value"] - 1) * 100) if len(df) > 1 else None
        st.metric(
            label=f"Fechamento — {s.unit}",
            value=fmt_number(ultimo["value"], 0),
            delta=delta,
            help="Variação em relação ao pregão anterior. O Ibovespa é índice de retorno "
            "total: os proventos já estão no nível calculado pela B3.",
        )
        st.caption(f"Data de referência: {fmt_date(ultimo['ref_date'].date())}")
        st.caption(f"Fonte: {s.source}")
        sinalizados = int(df["atypical"].sum())
        if sinalizados:
            datas = ", ".join(
                fmt_date(d.date()) for d in df.loc[df["atypical"] == 1, "ref_date"]
            )
            st.caption(
                f"Pregões sinalizados para revisão ({sinalizados}): {datas}. "
                "Variação acima do limite configurado; os valores não foram alterados."
            )
        st.altair_chart(charts.line_chart(df, s.unit, 0), width="stretch")

# --- Metodologia e transparência ---------------------------------------------
with st.expander("Metodologia, fontes e limitações"):
    st.markdown(
        """
**Escala dos gráficos.** O eixo vertical é ajustado à faixa dos dados do período, com
uma pequena margem, e não começa em zero. São gráficos de linha para acompanhar o
movimento de uma cotação ou de uma taxa, não para comparar magnitudes entre categorias.

**Acumulado em 12 meses.** Capitalização composta das variações do período,
∏(1 + taxa/100) − 1. Somar variações daria um número errado que não quebra nada.

**Alcance da checagem de cobertura.** O pipeline detecta **interrupção prolongada**
da fonte. Ele **não** detecta ausência isolada: numa série diária, um dia útil faltando
produz lacuna de 2 dias e passa sem alarme. Portanto, o rótulo "12 meses" significa
*a janela foi percorrida sem interrupção prolongada*, e **não** *toda observação
esperada está presente*. O projeto não tem calendário de dias úteis; fechar essa
lacuna exigiria um calendário por série, com as exceções históricas de cada uma.

**Defasagem do IPCA.** O índice é divulgado depois do fechamento do mês de referência,
então o cartão sempre mostra um mês anterior ao corrente. Isso não é atraso. O aviso de
"possível defasagem" é uma **aproximação**: o projeto não consulta o calendário oficial
de divulgação do IBGE, então ele pode aparecer antes de haver atraso real.

**Faixa de alerta.** Observações fora da faixa configurada são **carregadas** e
sinalizadas, nunca descartadas. É regra operacional para chamar atenção humana, não
garantia de detectar troca de unidade ou separador decimal deslocado.

**Valores ausentes.** Nunca são substituídos por zero. Fim de semana e feriado não
são tratados como erro e não são preenchidos.

**Datas de referência diferentes entre indicadores são esperadas**: cada série tem
seu próprio calendário e seu próprio prazo de publicação.
        """
    )
    for key, series in SERIES.items():
        df = data[key]
        st.markdown(
            md(f"**{series.name}** — {series.source} · {series.unit} · {series.frequency}")
        )
        if series.identification_note:
            rotulo = "Identificação" if not series.identification_alert else "Pendência"
            st.caption(f"{rotulo}: {series.identification_note}")
        if not df.empty:
            st.caption(
                f"{len(df)} observações de {fmt_date(df.iloc[0]['ref_date'].date())} "
                f"a {fmt_date(df.iloc[-1]['ref_date'].date())}"
            )
        run = last_ok.get(key)
        if run:
            st.caption(f"Última carga bem-sucedida: {fmt_timestamp(run['finished_at'])}")
