"""Dashboard: dólar, série SGS 12, IPCA e Ibovespa.

Lê SOMENTE a base já carregada; nunca chama as fontes. Para atualizar os dados,
rode `python -m src.pipeline`. Execução: `streamlit run app.py`.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

from src import charts, clock, db, freshness, metrics
from src.config import SERIES, get_db_path
from src.ptbr import fmt_date, fmt_number, fmt_pct, fmt_timestamp


def md(texto: str) -> str:
    """Escapa cifrões: no markdown do Streamlit, '$...$' é interpretado como LaTeX."""
    return texto.replace("$", r"\$")


def mes_ano(d) -> str:
    return f"{d.month:02d}/{d.year}"


def recua(d: date, anos: int) -> date:
    return (pd.Timestamp(d) - pd.DateOffset(years=anos)).date()


st.set_page_config(page_title="Indicadores de Mercado", page_icon="📈", layout="wide")
st.title("Indicadores de Mercado")

path = get_db_path()
if not path.exists():
    st.error("A base de dados ainda não existe. Execute `python -m src.pipeline` e recarregue a página.")
    st.stop()

# O fechamento vai em `finally`, não dentro do `try`: se a leitura falhar, o Streamlit
# reexecuta este script a cada interação do usuário e uma conexão vazaria por reexecução.
# `src/pipeline.py` já usava try/finally; aqui estava solto.
conn = None
try:
    conn = db.connect_readonly(path)
    bruto = {k: db.read_series(conn, k) for k in SERIES}
    runs = {k: db.latest_run(conn, k) for k in SERIES}
    last_ok = {k: db.latest_run(conn, k, status="success") for k in SERIES}
except sqlite3.Error as exc:
    st.error(f"Não foi possível ler a base de dados: {exc}")
    st.stop()
finally:
    if conn is not None:
        conn.close()

# ref_date como texto ISO: é o formato que os cálculos em src/metrics.py esperam.
data = {
    k: df.assign(ref_date=df["ref_date"].dt.strftime("%Y-%m-%d"))
    for k, df in bruto.items()
    if not df.empty
}
if not data:
    st.error("A base existe, mas está sem observações. Execute `python -m src.pipeline`.")
    st.stop()

hoje = clock.today_br()
ultima_por_serie = {k: date.fromisoformat(df["ref_date"].iloc[-1]) for k, df in data.items()}
fim = max(ultima_por_serie.values())

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
    if df is None:
        continue
    aviso = freshness.staleness_warning(series, ultima_por_serie[key], hoje)
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

# =============================================================================
# Seção 1 — Últimos indicadores disponíveis (NÃO dependem do filtro)
# =============================================================================
st.header("Últimos indicadores disponíveis")
st.caption(
    "Esta seção **não** é afetada pelo filtro de período: mostra sempre a observação mais "
    "recente de cada série e, quando cabível, o acumulado nos 12 meses até ela. Cada "
    "cartão traz a sua própria data de referência — elas diferem, porque cada fonte tem "
    "calendário e prazo de publicação próprios."
)


def acumulado_12m(series, df):
    return metrics.accumulated_12m(
        df, date.fromisoformat(df["ref_date"].iloc[-1]),
        series.max_gap_days, series.unexplained_absences,
    )


c1, c2 = st.columns(2)
c3, c4 = st.columns(2)

with c1:
    s, df = SERIES["ptax"], data.get("ptax")
    st.subheader(s.name)
    if df is None:
        st.error("Sem observações.")
    else:
        ultimo = df.iloc[-1]
        delta = fmt_pct((ultimo["value"] / df.iloc[-2]["value"] - 1) * 100) if len(df) > 1 else None
        st.metric(
            label=md(f"Cotação de venda — {s.unit}"),
            value=f"R$ {fmt_number(ultimo['value'], 4)}",
            delta=delta,
            help="Variação em relação à observação anterior. É taxa de câmbio de "
            "referência, não retorno de um investimento em dólar.",
        )
        st.caption(f"Data de referência: {fmt_date(ultimo['ref_date'])} · Fonte: {s.source}")

with c2:
    s, df = SERIES["cdi"], data.get("cdi")
    st.subheader(s.name)
    if s.identification_note and s.identification_alert:
        st.info(s.identification_note, icon="⚠️")
    if df is None:
        st.error("Sem observações.")
    else:
        ultimo = df.iloc[-1]
        acum = acumulado_12m(s, df)
        if acum["value"] is None:
            st.metric(label="Acumulado em 12 meses", value="indisponível")
            st.caption(f"Janela insuficiente: {acum['coverage']['reason']}.")
        else:
            st.metric(
                label="Acumulado em 12 meses",
                value=f"{fmt_number(acum['value'], 2)}%",
                help="Capitalização composta das taxas diárias. A checagem de cobertura "
                "detecta interrupção prolongada, não ausência isolada.",
            )
            st.caption(
                f"Período: observações posteriores a {fmt_date(acum['start_exclusive'])} "
                f"até {fmt_date(acum['end'])} · {acum['n_obs']} observações"
            )
        st.caption(
            f"Taxa de {fmt_date(ultimo['ref_date'])}: {fmt_number(ultimo['value'], 6)}% a.d., "
            f"equivalente a {fmt_number(metrics.annualize(ultimo['value']), 2)}% a.a. "
            "(base 252). É conversão de unidade, não previsão de rendimento."
        )
        st.caption(f"Fonte: {s.source}")

with c3:
    s, df = SERIES["ipca"], data.get("ipca")
    st.subheader(s.name)
    if df is None:
        st.error("Sem observações.")
    else:
        ultimo = df.iloc[-1]
        d_ref = date.fromisoformat(ultimo["ref_date"])
        acum = acumulado_12m(s, df)
        if acum["value"] is None:
            st.metric(label="IPCA acumulado em 12 meses", value="indisponível")
            st.caption(f"Janela insuficiente: {acum['coverage']['reason']}.")
        else:
            st.metric(
                label="IPCA acumulado em 12 meses",
                value=f"{fmt_number(acum['value'], 2)}%",
                help="Capitalização composta das variações mensais — somar daria número errado.",
            )
            st.caption(
                f"Período: meses posteriores a {mes_ano(acum['start_exclusive'])} até "
                f"{mes_ano(acum['end'])} · {acum['n_obs']} meses"
            )
        st.caption(
            f"Variação de {mes_ano(d_ref)}: {fmt_pct(ultimo['value'])}. O mês de referência "
            "é anterior ao corrente porque o índice é divulgado após o fechamento do mês."
        )
        st.caption(f"Fonte: {s.source}")

with c4:
    s, df = SERIES["ibovespa"], data.get("ibovespa")
    st.subheader(s.name)
    if df is None:
        st.error("Sem observações.")
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
        st.caption(f"Data de referência: {fmt_date(ultimo['ref_date'])} · Fonte: {s.source}")
        marcados = df[df["atypical"] == 1]
        if not marcados.empty:
            st.caption(
                f"Pregões sinalizados para revisão ({len(marcados)}): "
                + ", ".join(fmt_date(d) for d in marcados["ref_date"])
                + ". Variação acima do limite configurado; os valores não foram alterados."
            )

# =============================================================================
# Filtro de período
# =============================================================================
st.sidebar.header("Período")
opcao = st.sidebar.radio(
    "Janela exibida",
    ["12 meses", "24 meses", "5 anos", "Personalizado"],
    index=2,
    help="Afeta os gráficos de evolução e as comparações. Os cartões acima não mudam.",
)
limite_inferior = recua(fim, 5)
if opcao == "12 meses":
    inicio = recua(fim, 1)
elif opcao == "24 meses":
    inicio = recua(fim, 2)
elif opcao == "5 anos":
    inicio = limite_inferior
else:
    inicio = st.sidebar.date_input(
        "Início", value=recua(fim, 1), min_value=limite_inferior, max_value=fim
    )
    fim = st.sidebar.date_input("Fim", value=fim, min_value=inicio, max_value=fim)
st.sidebar.caption(
    f"Período selecionado: {fmt_date(inicio)} a {fmt_date(fim)}. "
    "Os cartões de 'Últimos indicadores disponíveis' são independentes deste filtro."
)


def no_periodo(df):
    if df is None:
        return None
    sel = df[(df["ref_date"] >= inicio.isoformat()) & (df["ref_date"] <= fim.isoformat())]
    return sel if not sel.empty else None


filtrado = {k: no_periodo(df) for k, df in data.items()}

# =============================================================================
# Seção 2 — Evolução no período
# =============================================================================
st.header("Evolução no período")
casas = {"ptax": 2, "cdi": 3, "ipca": 2, "ibovespa": 0}
e1, e2 = st.columns(2)
e3, e4 = st.columns(2)
for coluna, key in zip((e1, e2, e3, e4), ("ptax", "cdi", "ipca", "ibovespa")):
    with coluna:
        s, df = SERIES[key], filtrado.get(key)
        st.subheader(s.name)
        if df is None:
            st.info("Sem observações no período selecionado.")
        else:
            st.altair_chart(charts.line_chart(df, s.unit, casas[key], color=s.color), width="stretch")
            st.caption(
                f"{len(df)} observações · {fmt_date(df['ref_date'].iloc[0])} a "
                f"{fmt_date(df['ref_date'].iloc[-1])}"
            )

# =============================================================================
# Seção 3 — Comparação no período
# =============================================================================
st.header("Comparação no período")

st.subheader("Evolução diária em base 100")
diarias = ["cdi", "ptax", "ibovespa"]
quadros = [filtrado[k] for k in diarias if filtrado.get(k) is not None]
if len(quadros) < len(diarias):
    st.info("Comparação indisponível: alguma das séries diárias não tem dados no período.")
else:
    base = metrics.common_base_date(quadros, inicio, fim)
    if base is None:
        st.warning(
            "Não há nenhuma data com observação nas três séries dentro do período "
            "selecionado, então não existe base comum para o rebase. A comparação não é "
            "apresentada."
        )
    else:
        partes = []
        for key in diarias:
            s, df = SERIES[key], filtrado[key]
            idx = metrics.index_rate(df, base) if s.kind == "taxa" else metrics.index_level(df, base)
            partes.append(idx.assign(serie=s.name))
        longo = pd.concat(partes, ignore_index=True)
        cores = {SERIES[k].name: SERIES[k].color for k in diarias}
        st.altair_chart(charts.multi_line_chart(longo, "Base 100", 1, cores), width="stretch")

        st.caption(f"**Data-base efetiva: {fmt_date(base)}** — a primeira data, dentro do "
                   "período, com observação nas três séries. Todas valem 100 nela.")
        linhas = []
        for key in diarias:
            s = SERIES[key]
            idx = longo[longo["serie"] == s.name]
            linhas.append(
                {
                    "Indicador": s.name,
                    "Última data": fmt_date(idx["ref_date"].iloc[-1]),
                    "Base 100 no fim": fmt_number(float(idx["index"].iloc[-1]), 1),
                    "Observações": len(idx),
                }
            )
        tabela = pd.DataFrame(linhas)
        st.dataframe(tabela, hide_index=True, width="stretch")
        if tabela["Última data"].nunique() > 1:
            st.warning(
                "As séries terminam em datas **diferentes**. Os valores finais acima não "
                "são variações de períodos exatamente iguais e não devem ser comparados "
                "como se fossem.",
                icon="⚠️",
            )
        st.caption(
            "**Como o CDI entra:** a partir da data-base, capitalizam-se as taxas das datas "
            "**posteriores** a ela, no calendário da própria série — a taxa publicada na "
            "data-base não entra, porque ali o índice vale 100 por definição. "
            "**Nenhuma série é alinhada, preenchida ou truncada:** cada uma é desenhada nas "
            "suas próprias datas, que são comprovadamente diferentes entre si."
        )
        st.info(
            "**Naturezas diferentes.** Uma taxa de juros acumulada, uma taxa de câmbio e um "
            "índice de ações. O gráfico mostra a evolução de três referências distintas, "
            "não a comparação de investimentos equivalentes. Nenhuma das três considera "
            "custos, impostos ou a viabilidade de replicar a carteira.",
            icon="📌",
        )

st.subheader("Comparação mensal: série SGS 12 e IPCA")
if filtrado.get("cdi") is None or data.get("ipca") is None:
    st.info("Comparação indisponível: falta uma das séries.")
else:
    meses = metrics.eligible_months(
        data["cdi"], data["ipca"], inicio, fim, SERIES["cdi"].max_gap_days
    )
    if not meses:
        st.info(
            "Nenhum mês inteiro do período selecionado tem as duas séries disponíveis. "
            "O índice mensal é divulgado após o fechamento do mês, então os meses mais "
            "recentes costumam não estar elegíveis."
        )
    else:
        fator_taxa = metrics.compound_factor([m["taxa"] for m in meses])
        fator_infl = metrics.compound_factor([m["mensal"] for m in meses])
        acum_taxa = (fator_taxa - 1) * 100
        acum_infl = (fator_infl - 1) * 100
        m1, m2, m3 = st.columns(3)
        m1.metric("Série SGS 12 acumulada", f"{fmt_number(acum_taxa, 2)}%")
        m2.metric("IPCA acumulado", f"{fmt_number(acum_infl, 2)}%")
        m3.metric(
            "Retorno real",
            f"{fmt_number(metrics.real_return(acum_taxa, acum_infl), 2)}%",
            help="Razão entre os fatores, não diferença entre as taxas.",
        )
        st.caption(
            f"**Período efetivamente usado: {meses[0]['mes']} a {meses[-1]['mes']}** "
            f"({len(meses)} meses inteiros). Entram apenas meses que cabem inteiros no "
            "filtro, têm o índice mensal publicado e passam na checagem de cobertura da "
            "série diária. O último mês elegível sai dos dados, não está fixado no código."
        )
        rotulos = [f"{m['mes'][5:]}/{m['mes'][:4]}" for m in meses]  # AAAA-MM -> MM/AAAA
        nome_taxa, nome_ipca = SERIES["cdi"].name, SERIES["ipca"].name
        barras = pd.concat(
            [
                pd.DataFrame({"mes": rotulos,
                              "valor": [m["taxa"] for m in meses], "serie": nome_taxa}),
                pd.DataFrame({"mes": rotulos,
                              "valor": [m["mensal"] for m in meses], "serie": nome_ipca}),
            ],
            ignore_index=True,
        )
        cores_mensal = {nome_taxa: SERIES["cdi"].color, nome_ipca: SERIES["ipca"].color}
        st.altair_chart(
            charts.bar_chart(barras, "% no mês", 2, cores_mensal, x_order=rotulos),
            width="stretch",
        )
        st.caption(
            "**Retorno real pela razão:** (1 + taxa) ÷ (1 + inflação) − 1. Subtrair uma "
            "taxa da outra dá resultado parecido e errado. "
            "**Limitação:** a checagem de cobertura de cada mês detecta interrupção "
            "prolongada da fonte, **não** ausência isolada — um dia útil faltando dentro de "
            "um mês passaria sem alarme e subestimaria o acumulado daquele mês."
        )

# =============================================================================
# Metodologia
# =============================================================================
with st.expander("Metodologia, fontes e limitações"):
    st.markdown(
        """
**Escala dos gráficos de linha.** O eixo vertical é ajustado à faixa dos dados do
período, com uma pequena margem, e não começa em zero: são gráficos de acompanhamento
de movimento. Nas barras da comparação mensal a base zero é obrigatória, porque ali
comparam-se magnitudes.

**Acumulado por capitalização.** ∏(1 + taxa/100) − 1. Somar variações daria um número
errado que não quebra nada.

**Retorno real pela razão**, nunca pela diferença entre as taxas.

**Calendários próprios.** As séries diárias têm calendários diferentes — PTAX e
Ibovespa divergem em 8 datas na janela de 5 anos. Na comparação, nenhuma série é
alinhada, preenchida ou truncada: cada uma é desenhada nas suas próprias datas, e o
único ponto compartilhado é a data-base do rebase.

**Alcance da checagem de cobertura.** O pipeline detecta **interrupção prolongada** da
fonte. Ele **não** detecta ausência isolada: numa série diária, um dia útil faltando
produz lacuna de 2 dias e passa sem alarme. O rótulo "12 meses" significa *a janela foi
percorrida sem interrupção prolongada*, e **não** *toda observação esperada está
presente*.

**Faixa de alerta.** Duas regras independentes — por nível e por variação entre
observações consecutivas. Ambas apenas **sinalizam**: a observação é carregada sem
substituição, e a sinalização **pede conferência humana, não declara erro**. Um número
baixo de sinalizações mostra que a regra gerou poucos alertas nesta amostra; **não**
comprova que ela detecta todos os problemas possíveis.

**Valores ausentes.** Nunca são substituídos por zero. Fim de semana e feriado não são
tratados como erro e não são preenchidos.
        """
    )
    for key, series in SERIES.items():
        df = data.get(key)
        st.markdown(
            md(f"**{series.name}** — {series.source} · {series.unit} · {series.frequency}")
        )
        if series.identification_note:
            rotulo = "Pendência" if series.identification_alert else "Identificação"
            st.caption(f"{rotulo}: {series.identification_note}")
        if df is not None:
            st.caption(
                f"{len(df)} observações de {fmt_date(df['ref_date'].iloc[0])} "
                f"a {fmt_date(df['ref_date'].iloc[-1])}"
            )
        run = last_ok.get(key)
        if run:
            st.caption(f"Última carga bem-sucedida: {fmt_timestamp(run['finished_at'])}")
