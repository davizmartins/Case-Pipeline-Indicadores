"""Ibovespa: extração via yfinance, armadilhas da biblioteca e alerta de variação.

Nenhum teste acessa a rede: o `downloader` é substituído por um dublê que devolve o
mesmo formato que a biblioteca devolve (índice com fuso, colunas Close e Adj Close).

Os valores de outubro de 2026 são REAIS, coletados em 01/11/2026. O fechamento de
26/10/2026 foi conferido contra fonte jornalística independente: 176.608 pontos, queda
de 13,88%, com acionamento de circuit breaker pela B3.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from src import db, metrics, pipeline, transform
from src.config import SERIES
from src.extract import ExtractionError
from src.extract_yf import fetch

OUTUBRO_2026 = [
    ("2026-10-01", 187198.0), ("2026-10-02", 192115.0), ("2026-10-05", 206912.0),
    ("2026-10-06", 205835.0), ("2026-10-07", 204302.0), ("2026-10-08", 206220.0),
    ("2026-10-09", 209067.0), ("2026-10-13", 206888.0), ("2026-10-14", 206506.0),
    ("2026-10-15", 204324.0), ("2026-10-16", 205430.0), ("2026-10-19", 205079.0),
    ("2026-10-20", 208296.0), ("2026-10-21", 206495.0), ("2026-10-22", 204120.0),
    ("2026-10-23", 205083.0), ("2026-10-26", 176608.0), ("2026-10-27", 175710.0),
    ("2026-10-28", 171006.0), ("2026-10-29", 169186.0), ("2026-10-30", 167922.0),
]
IBOV = SERIES["ibovespa"]


def quadro(pares=OUTUBRO_2026, tz="America/Sao_Paulo", com_adj=True, adj_delta=0.0):
    """Imita o retorno do yfinance: índice com fuso e colunas OHLC."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in pares])
    if tz:
        idx = idx.tz_localize(tz)
    valores = [v for _, v in pares]
    cols = {"Open": valores, "High": valores, "Low": valores, "Close": valores}
    if com_adj:
        cols["Adj Close"] = [v + adj_delta for v in valores]
    return pd.DataFrame(cols, index=idx)


def serie_cinco_anos():
    """Cinco anos sintéticos terminando nos valores REAIS de outubro de 2026.

    A parte sintética sobe de forma suave, para que o único movimento atípico da série
    seja o de 26/10 — que é real.
    """
    dias = pd.bdate_range("2021-10-30", "2026-09-30")
    n = len(dias)
    inicio, fim = 110000.0, 186000.0
    pares = [
        (d.strftime("%Y-%m-%d"), round(inicio + (fim - inicio) * i / (n - 1), 2))
        for i, d in enumerate(dias)
    ]
    return pares + OUTUBRO_2026


def baixador(frame=None, registro=None):
    frame = quadro() if frame is None else frame

    def _baixa(ticker, start, end_exclusive):
        if registro is not None:
            registro.append({"ticker": ticker, "start": start, "end": end_exclusive})
        return frame

    return _baixa


# --- armadilhas da biblioteca ------------------------------------------------

def test_end_exclusivo_do_yfinance_recebe_um_dia_a_mais():
    """A janela do projeto é inclusiva; o yfinance corta o último dia."""
    chamadas = []
    fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador(registro=chamadas))
    assert chamadas[0]["end"] == date(2026, 10, 31)
    assert chamadas[0]["end"] - chamadas[0]["start"] == timedelta(days=30)
    assert chamadas[0]["ticker"] == "^BVSP"


def test_indice_com_fuso_vira_data_local_sem_deslocar_o_pregao():
    rows = fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador())
    assert rows[0]["data"] == "01/10/2026"
    assert rows[-1]["data"] == "30/10/2026"


def test_conversao_de_fuso_nao_empurra_o_pregao_para_o_dia_seguinte():
    """Um carimbo às 22h em Brasília é 01h do DIA SEGUINTE em UTC.

    Converter para UTC antes de extrair a data mudaria o pregão de dia. Com os carimbos
    à meia-noite que o yfinance devolve hoje o erro não apareceria, mas a conversão
    precisa estar certa de qualquer forma.
    """
    idx = pd.DatetimeIndex([pd.Timestamp("2026-10-30 22:00:00")]).tz_localize(
        "America/Sao_Paulo"
    )
    frame = pd.DataFrame({"Close": [167922.0]}, index=idx)
    rows = fetch(IBOV, date(2026, 10, 30), date(2026, 10, 30), downloader=baixador(frame))
    assert rows[0]["data"] == "30/10/2026"


def test_indice_sem_fuso_tambem_funciona():
    rows = fetch(
        IBOV, date(2026, 10, 1), date(2026, 10, 30),
        downloader=baixador(quadro(tz=None)),
    )
    assert rows[0]["data"] == "01/10/2026"


def test_usa_close_e_nao_adj_close():
    frame = quadro(adj_delta=999.0)
    rows = fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador(frame))
    assert float(rows[0]["valor"]) == 187198.0


def test_divergencia_entre_close_e_adj_close_e_registrada(caplog):
    frame = quadro(adj_delta=5.0)
    with caplog.at_level("WARNING"):
        fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador(frame))
    assert any("Adj Close" in r.message for r in caplog.records)


# --- falhas ------------------------------------------------------------------

def test_excecao_da_biblioteca_vira_erro_do_projeto():
    def explode(ticker, start, end):
        raise RuntimeError("YFTzMissingError: possibly delisted")

    with pytest.raises(ExtractionError, match="YFTzMissingError"):
        fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=explode)


def test_resposta_vazia_e_falha_e_nao_sucesso():
    vazio = pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([]))
    with pytest.raises(ExtractionError, match="nenhuma observação"):
        fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador(vazio))


def test_none_e_falha():
    with pytest.raises(ExtractionError):
        fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=lambda *a: None)


def test_resposta_sem_a_coluna_close_e_falha():
    frame = quadro().drop(columns=["Close"])
    with pytest.raises(ExtractionError, match="Close"):
        fetch(IBOV, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador(frame))


def test_serie_sem_ticker_e_rejeitada():
    sem = SERIES["ptax"]
    with pytest.raises(ExtractionError, match="ticker"):
        fetch(sem, date(2026, 10, 1), date(2026, 10, 30), downloader=baixador())


# --- alerta por variação -----------------------------------------------------

def dados_limpos(pares=OUTUBRO_2026, limite=IBOV.alert_max_change_pct):
    raw = pd.DataFrame(
        [{"data": pd.Timestamp(d).strftime("%d/%m/%Y"), "valor": repr(v)} for d, v in pares],
        columns=["data", "valor"],
    )
    return transform.clean_sgs(
        raw,
        reject_non_positive=IBOV.reject_non_positive,
        alert_min=IBOV.alert_min,
        alert_max=IBOV.alert_max,
        alert_max_change_pct=limite,
    )


def test_queda_de_13_9_por_cento_e_sinalizada_e_carregada():
    clean, rep = dados_limpos()
    assert len(clean) == 21, "nada é descartado"
    assert rep["atypical_change"] == 1
    assert rep["atypical_level"] == 0, "o valor não é implausível em si; o que destoa é a variação"
    sinalizada = clean[clean["atypical"] == 1]
    assert list(sinalizada["ref_date"]) == ["2026-10-26"]
    assert float(sinalizada["value"].iloc[0]) == 176608.0


def test_alta_de_7_7_por_cento_nao_e_sinalizada_pelo_limite_escolhido():
    """O limite vem do circuit breaker da B3 (10%), não foi calibrado para os eventos."""
    _, rep = dados_limpos()
    assert rep["atypical_change"] == 1  # só o 26/10, não o 05/10


def test_limite_e_configuravel():
    assert dados_limpos(limite=5.0)[1]["atypical_change"] == 2  # pega 05/10 e 26/10
    assert dados_limpos(limite=20.0)[1]["atypical_change"] == 0
    assert dados_limpos(limite=None)[1]["atypical_change"] == 0


def test_primeira_observacao_nunca_e_sinalizada_por_variacao():
    clean, rep = dados_limpos(pares=OUTUBRO_2026[:3])
    assert clean["atypical"].iloc[0] == 0
    assert rep["atypical_change"] == 0  # 02/10 e 05/10 ficam abaixo de 10%


def test_as_duas_regras_sao_independentes():
    """Nível e variação contam separado; a marca gravada é a união."""
    pares = [("2026-10-01", 100.0), ("2026-10-02", 101.0)]
    raw = pd.DataFrame(
        [{"data": pd.Timestamp(d).strftime("%d/%m/%Y"), "valor": repr(v)} for d, v in pares],
        columns=["data", "valor"],
    )
    _, rep = transform.clean_sgs(
        raw, reject_non_positive=False, alert_max=50.0, alert_max_change_pct=0.5
    )
    assert rep["atypical_level"] == 2 and rep["atypical_change"] == 1
    assert rep["atypical"] == 2  # união, não soma


# --- pipeline ----------------------------------------------------------------

def test_ibovespa_carrega_e_sinaliza_sem_descartar(tmp_path):
    pares = serie_cinco_anos()
    res = pipeline.run(
        ["ibovespa"], today=date(2026, 10, 30), db_path=tmp_path / "t.db",
        downloader=baixador(quadro(pares)),
    )
    assert res[0].status == "success", res[0].message
    assert "variação: 1" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == len(pares)
    marcadas = conn.execute(
        "SELECT ref_date, value FROM observations WHERE atypical = 1"
    ).fetchall()
    assert marcadas == [("2026-10-26", 176608.0)]
    conn.close()


def test_janela_curta_demais_e_barrada_em_vez_de_carregar_parcial(tmp_path):
    """Só outubro não cobre a janela de 5 anos: falha, e nada entra na base."""
    res = pipeline.run(
        ["ibovespa"], today=date(2026, 10, 30), db_path=tmp_path / "t.db",
        downloader=baixador(),
    )
    assert res[0].status == "failed" and "começa em" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    conn.close()


def test_falha_do_yfinance_nao_carrega_nada(tmp_path):
    def explode(ticker, start, end):
        raise RuntimeError("sem rede")

    res = pipeline.run(
        ["ibovespa"], today=date(2026, 10, 30), db_path=tmp_path / "t.db", downloader=explode
    )
    assert res[0].status == "failed" and "sem rede" in res[0].message
    conn = db.connect(tmp_path / "t.db")
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    conn.close()


def test_valor_bruto_preserva_o_recebido(tmp_path):
    pipeline.run(
        ["ibovespa"], today=date(2026, 10, 30), db_path=tmp_path / "t.db",
        downloader=baixador(quadro(serie_cinco_anos())),
    )
    conn = db.connect(tmp_path / "t.db")
    bruto = conn.execute(
        "SELECT raw_value FROM raw_observations WHERE raw_date = '26/10/2026'"
    ).fetchone()[0]
    assert float(bruto) == 176608.0
    conn.close()


# --- conferência contra fonte independente -----------------------------------

def test_fechamento_de_26_10_confere_com_a_fonte_independente():
    """176.608 pontos e -13,88%, conforme publicado por fonte jornalística."""
    valores = dict(OUTUBRO_2026)
    assert valores["2026-10-26"] == 176608.0
    variacao = (valores["2026-10-26"] / valores["2026-10-23"] - 1) * 100
    assert round(variacao, 2) == -13.88


def test_variacao_do_periodo_usa_niveis_e_nao_capitalizacao():
    """O Ibovespa é série de NÍVEL: variação é razão entre pontas, não produto."""
    valores = [v for _, v in OUTUBRO_2026]
    direto = (valores[-1] / valores[0] - 1) * 100
    assert direto == pytest.approx(-10.3, abs=0.1)
    assert metrics.rebase_100(valores, valores[0])[-1] == pytest.approx(100 + direto, abs=1e-9)
