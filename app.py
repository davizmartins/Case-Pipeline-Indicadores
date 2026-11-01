"""Dashboard (Etapa 2): PTAX e a série SGS 12, lado a lado.

Lê SOMENTE a base já carregada; nunca chama as fontes. Para atualizar os dados,
rode `python -m src.pipeline`. Execução: `streamlit run app.py`.
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from src import charts, clock, db, metrics
from src.config import MAX_GAP_DAYS, SERIES, STALE_AFTER_DAYS, get_db_path
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp


def md(texto: str) -> str:
    """Escapa cifrões: no markdown do Streamlit, '$...$' é interpretado como LaTeX.

    Sem isso, a unidade "R$/US$" sai renderizada como fórmula matemática.
    """
    return texto.replace("$", r"\$")


st.set_page_config(page_title="Indicadores de Mercado", page_icon="📈", layout="wide")
st.title("Indicadores de Mercado")
st.caption("Versão em construção: dólar e a série SGS 12. IPCA e Ibovespa ainda não entraram.")

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
    if df is not None and not df.empty:
        idade = (hoje - df.iloc[-1]["ref_date"].date()).days
        if idade > STALE_AFTER_DAYS:
            st.warning(
                f"**{series.name}** — dados possivelmente desatualizados: a última "
                f"observação é de {fmt_date(df.iloc[-1]['ref_date'].date())} ({idade} dias atrás)."
            )
    if df is not None and not df.empty and int(df["atypical"].sum()):
        st.warning(
            f"**{series.name}** — {int(df['atypical'].sum())} observação(ões) fora da faixa "
            "de alerta. Elas foram carregadas e estão sinalizadas, não descartadas."
        )

col_ptax, col_cdi = st.columns(2)

# --- Cartão: dólar americano (venda) ----------------------------------------
with col_ptax:
    s = SERIES["ptax"]
    df = data["ptax"]
    st.subheader(s.name)
    if s.identification_note and s.identification_alert:
        st.info(s.identification_note, icon="⚠️")
    if df.empty:
        st.error("Sem observações. Execute `python -m src.pipeline`.")
    else:
        ultimo = df.iloc[-1]
        delta = None
        if len(df) > 1:
            delta = fmt_pct((ultimo["value"] / df.iloc[-2]["value"] - 1) * 100)
        st.metric(
            label=md(f"Cotação de venda — {s.unit}"),
            value=f"R$ {fmt_number(ultimo['value'], 4)}",
            delta=delta,
            help="Variação em relação à observação anterior. É uma taxa de câmbio de "
            "referência, não o retorno de um investimento em dólar.",
        )
        st.caption(f"Data de referência: {fmt_date(ultimo['ref_date'].date())}")
        st.caption(f"Fonte: {s.source}")
        st.altair_chart(charts.line_chart(df, s.unit, 2), use_container_width=True)

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
        acum = metrics.accumulated_12m(
            df.assign(ref_date=df["ref_date"].dt.strftime("%Y-%m-%d")),
            d_ref,
            MAX_GAP_DAYS,
            s.unexplained_absences,
        )
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
        anual = metrics.annualize(ultimo["value"])
        st.caption(
            f"Taxa de {fmt_date(d_ref)}: {fmt_number(ultimo['value'], 6)}% a.d., "
            f"equivalente a {fmt_number(anual, 2)}% a.a. (base 252). "
            "É conversão de unidade da taxa desse dia, não previsão de rendimento."
        )
        st.caption(f"Fonte: {s.source}")
        st.altair_chart(charts.line_chart(df, s.unit, 3), use_container_width=True)

# --- Metodologia e transparência ---------------------------------------------
with st.expander("Metodologia, fontes e limitações"):
    st.markdown(
        """
**Escala dos gráficos.** O eixo vertical é ajustado à faixa dos dados do período, com
uma pequena margem, e não começa em zero. São gráficos de linha para acompanhar o
movimento de uma cotação ou de uma taxa, não para comparar magnitudes entre categorias.

**Alcance da checagem de cobertura.** O pipeline detecta **interrupção prolongada**
da fonte (mais de 10 dias corridos sem observação). Ele **não** detecta ausência
isolada: um dia útil faltando no meio da semana produz lacuna de 2 dias e passa sem
alarme. Portanto, o rótulo "12 meses" significa *a janela foi percorrida sem
interrupção prolongada*, e **não** *todo dia útil está presente*. O projeto não tem
calendário de dias úteis; fechar essa lacuna exigiria um calendário por série, com
as exceções históricas de cada uma, e ficou fora desta etapa.

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
            st.caption(f"Pendência: {series.identification_note}")
        if not df.empty:
            st.caption(
                f"{len(df)} observações de {fmt_date(df.iloc[0]['ref_date'].date())} "
                f"a {fmt_date(df.iloc[-1]['ref_date'].date())}"
            )
        run = last_ok.get(key)
        if run:
            st.caption(f"Última carga bem-sucedida: {fmt_timestamp(run['finished_at'])}")
