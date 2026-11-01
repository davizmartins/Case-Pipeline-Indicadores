"""Extração do Ibovespa via yfinance, normalizada para o mesmo formato bruto do SGS.

A saída é uma lista de {"data": "dd/MM/aaaa", "valor": "<texto>"}, igual à do SGS, para
que tratamento, carga e auditoria sigam sem conhecer a fonte.

ARMADILHAS DESTA FONTE, verificadas na biblioteca instalada (yfinance 1.7.0) em
01/11/2026 — todas com valor explícito na chamada, para não depender de padrão:

- `yf.config.debug.hide_exceptions` vem **True**: a biblioteca ENGOLE exceções por
  padrão, e uma falha de rede viraria resultado vazio. Ligamos a exceção.
  (O antigo `raise_errors=True` existe, mas está marcado como obsoleto nesta versão.)
- `yf.download` **não tem** como levantar exceção e devolve `Optional[DataFrame]`.
  Por isso usamos `Ticker.history`, que tem.
- `end` é **EXCLUSIVO** no yfinance: pedir até 31/10 devolve até 30/10. A janela do
  projeto é inclusiva nas duas pontas, então somamos um dia.
- `auto_adjust` vem **True**, e nesse modo a coluna `Adj Close` nem existe. Passamos
  False para poder comparar as duas colunas a cada carga.
- O índice vem com FUSO (`datetime64[s, America/Sao_Paulo]`), diferente do SGS, que
  manda texto. Convertemos explicitamente antes de extrair a data.

RESSALVA SOBRE O "BRUTO": o SGS entrega texto, que guardamos exatamente como veio. O
yfinance entrega float já convertido pela biblioteca, então o que guardamos é a
representação desse float — um passo distante do que o servidor enviou.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from src.config import TIMEZONE, Series
from src.extract import ExtractionError

log = logging.getLogger(__name__)

# Diferença máxima tolerada entre Close e Adj Close antes de registrar aviso.
# Para um índice sem desdobramentos nem dividendos a ajustar, esperamos zero.
ADJ_CLOSE_EPSILON = 1e-9


def _default_downloader(ticker: str, start: date, end_exclusive: date) -> pd.DataFrame:
    """Chamada real ao yfinance. Isolada para os testes poderem substituí-la."""
    import yfinance as yf

    yf.config.debug.hide_exceptions = False  # sem isso, falha vira resultado vazio
    return yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=end_exclusive.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
    )


def fetch(series: Series, start: date, end: date, downloader=None) -> list[dict]:
    """Baixa o histórico e devolve registros no formato bruto do projeto.

    `end` é INCLUSIVO aqui; a conversão para o limite exclusivo do yfinance é interna.
    """
    if not series.ticker:
        raise ExtractionError(f"{series.key}: série sem ticker configurado")
    downloader = downloader or _default_downloader

    try:
        frame = downloader(series.ticker, start, end + timedelta(days=1))
    except Exception as exc:  # a biblioteca tem exceções próprias; todas viram a nossa
        raise ExtractionError(
            f"{series.ticker} [{start}..{end}]: {type(exc).__name__}: {exc}"
        ) from exc

    if frame is None or len(frame) == 0:
        raise ExtractionError(f"{series.ticker} [{start}..{end}]: nenhuma observação devolvida")
    if "Close" not in frame.columns:
        raise ExtractionError(
            f"{series.ticker}: resposta sem a coluna 'Close'; veio {list(frame.columns)}"
        )

    # Conferência a cada carga: num índice, Close e Adj Close devem coincidir.
    if "Adj Close" in frame.columns:
        maior = float((frame["Close"] - frame["Adj Close"]).abs().max())
        if maior > ADJ_CLOSE_EPSILON:
            log.warning(
                "%s: Close e Adj Close divergem (máx %.6f). Esperado zero para um índice; "
                "usando Close.", series.ticker, maior
            )

    datas = _to_local_dates(frame.index, series.ticker)
    valores = frame["Close"]
    rows = [
        {"data": d.strftime("%d/%m/%Y"), "valor": repr(float(v))}
        for d, v in zip(datas, valores)
        if pd.notna(v)
    ]
    if not rows:
        raise ExtractionError(f"{series.ticker} [{start}..{end}]: todos os fechamentos vazios")
    log.info("%s %s..%s: %s registros", series.ticker, start, end, len(rows))
    return rows


def _to_local_dates(index, ticker: str) -> list[date]:
    """Converte o índice para datas no fuso de Brasília.

    O yfinance devolve carimbos COM fuso. Converter para UTC antes da data poderia
    empurrar um pregão para o dia seguinte, então a conversão é explícita.
    """
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        log.warning("%s: índice sem fuso; datas usadas como vieram", ticker)
        return [ts.date() for ts in idx]
    return [ts.date() for ts in idx.tz_convert(TIMEZONE)]
