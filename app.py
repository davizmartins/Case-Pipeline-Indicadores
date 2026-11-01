"""Dashboard (Etapa 1): tela mínima da PTAX para validar o fluxo de ponta a ponta.

Lê SOMENTE a base já carregada; nunca chama as fontes. Para atualizar os dados,
rode `python -m src.pipeline`. Execução: `streamlit run app.py`.
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from src import clock, db
from src.config import SERIES, STALE_AFTER_DAYS, get_db_path
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp

KEY = "ptax"
series = SERIES[KEY]

st.set_page_config(page_title="Indicadores de Mercado", page_icon="📈", layout="wide")
st.title("Indicadores de Mercado")
st.caption("Versão em construção: apenas o dólar PTAX está disponível nesta etapa.")

path = get_db_path()
if not path.exists():
    st.error("A base de dados ainda não existe. Execute `python -m src.pipeline` e recarregue a página.")
    st.stop()

try:
    conn = db.connect_readonly(path)
    data = db.read_series(conn, KEY)
    last_run = db.latest_run(conn, KEY)
    last_success = db.latest_run(conn, KEY, status="success")
    conn.close()
except sqlite3.Error as exc:
    st.error(f"Não foi possível ler a base de dados: {exc}")
    st.stop()

if data.empty:
    st.error("A base existe, mas não há observações da PTAX. Execute `python -m src.pipeline`.")
    st.stop()

# --- Avisos de transparência -------------------------------------------------
if last_run and last_run["status"] == "failed":
    st.warning(
        f"A última execução do pipeline ({fmt_timestamp(last_run['finished_at'])}) falhou: "
        f"{last_run['message']}. Os dados abaixo vêm da última carga bem-sucedida."
    )

last_obs = data.iloc[-1]
days_old = (clock.today_br() - last_obs["ref_date"].date()).days
if days_old > STALE_AFTER_DAYS:
    st.warning(
        f"Dados possivelmente desatualizados: a última observação é de "
        f"{fmt_date(last_obs['ref_date'].date())} ({days_old} dias atrás)."
    )

# --- Cartão ------------------------------------------------------------------
delta = None
if len(data) > 1:
    prev = data.iloc[-2]["value"]
    delta = fmt_pct((last_obs["value"] / prev - 1) * 100)

st.metric(
    label=f"{series.name} — {series.unit}",
    value=f"R$ {fmt_number(last_obs['value'], 4)}",
    delta=delta,
    help="Variação em relação à observação anterior. A PTAX é uma taxa de câmbio de "
    "referência, não o retorno de um investimento em dólar.",
)
st.caption(f"Data de referência: {fmt_date(last_obs['ref_date'].date())} · Fonte: {series.source}")

# --- Evolução ----------------------------------------------------------------
st.subheader("Evolução do dólar PTAX (venda)")
st.line_chart(data.set_index("ref_date")["value"], y_label="R$/US$", x_label="Data")

# --- Rodapé de transparência -------------------------------------------------
with st.expander("Fonte e última atualização"):
    st.write(f"**Fonte:** {series.source} · **Unidade:** {series.unit} · **Frequência:** {series.frequency}")
    st.write(f"**Observações armazenadas:** {len(data)} "
             f"({fmt_date(data.iloc[0]['ref_date'].date())} a {fmt_date(last_obs['ref_date'].date())})")
    if last_success:
        st.write(f"**Última carga bem-sucedida:** {fmt_timestamp(last_success['finished_at'])}")
