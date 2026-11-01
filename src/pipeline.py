"""Orquestra extração -> tratamento -> validação -> carga e registra cada execução.

Uso:  python -m src.pipeline                       (todas as séries configuradas)
      python -m src.pipeline --indicators cdi      (só uma)

Se qualquer etapa falhar, NADA é carregado para aquele indicador, a falha é gravada em
pipeline_runs e o processo termina com código 1. Dados fictícios nunca são gerados.

Janelas: a de EXIBIÇÃO tem WINDOW_YEARS anos; a de EXTRAÇÃO recua margin_months a mais,
porque métricas que olham para trás (acumulado em 12 meses) precisam de dados anteriores
ao início da janela exibida. A margem fica armazenada e é excluída dos gráficos.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src import db, extract, extract_yf, load, transform
from src.clock import today_br
from src.config import SERIES, WINDOW_YEARS, Series

log = logging.getLogger("pipeline")


@dataclass
class RunResult:
    indicator: str
    status: str  # "success" | "failed"
    rows_fetched: int | None
    rows_loaded: int | None
    message: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def window_bounds(today: date, years: int = WINDOW_YEARS) -> tuple[date, date]:
    """Janela de EXIBIÇÃO: [hoje - N anos, hoje], inclusive nas duas pontas."""
    start = (pd.Timestamp(today) - pd.DateOffset(years=years)).date()
    return start, today


def fetch_bounds(today: date, series: Series, years: int = WINDOW_YEARS) -> tuple[date, date]:
    """Janela de EXTRAÇÃO: a de exibição recuada em margin_months."""
    start, end = window_bounds(today, years)
    if series.margin_months:
        start = (pd.Timestamp(start) - pd.DateOffset(months=series.margin_months)).date()
    return start, end


def run(
    indicators: list[str] | None = None,
    *,
    today: date | None = None,
    db_path: Path | str | None = None,
    session=None,
    sleep=time.sleep,
    clock=utc_now,
    downloader=None,
) -> list[RunResult]:
    keys = indicators or list(SERIES)
    unknown = [k for k in keys if k not in SERIES]
    if unknown:
        raise ValueError(f"indicador(es) desconhecido(s): {unknown}; disponíveis: {list(SERIES)}")

    reference_day = today or today_br()
    conn = db.connect(db_path)
    results: list[RunResult] = []
    try:
        for key in keys:
            series = SERIES[key]
            start, end = fetch_bounds(reference_day, series)
            started_at = clock()
            rows: list[dict] | None = None
            base = dict(
                indicator=key,
                started_at=started_at,
                window_start=start.isoformat(),
                window_end=end.isoformat(),
            )
            try:
                if series.source_kind == "yfinance":
                    rows = extract_yf.fetch(series, start, end, downloader=downloader)
                else:
                    rows = extract.extract_series(series, start, end, session=session, sleep=sleep)
                raw_df = pd.DataFrame(rows, columns=["data", "valor"])
                clean, report = transform.clean_sgs(
                    raw_df,
                    reject_non_positive=series.reject_non_positive,
                    alert_min=series.alert_min,
                    alert_max=series.alert_max,
                    alert_max_change_pct=series.alert_max_change_pct,
                )
                cov = transform.validate_coverage(clean, start, end, series.max_gap_days)
                loaded = load.load_series(conn, key, series.source, rows, clean, clock())
                message = (
                    f"{loaded} observações carregadas ({cov['first_date']} a "
                    f"{cov['last_date']}); descartadas: {report['rows_discarded']}; "
                    f"atípicas sinalizadas: {report['atypical']} "
                    f"(nível: {report['atypical_level']}, variação: {report['atypical_change']}); "
                    f"duplicadas removidas: {report['duplicates_removed']}; "
                    f"datas com valores conflitantes: {report['conflicting_dates']}"
                )
                load.record_run(
                    conn, **base, finished_at=clock(), status="success",
                    rows_fetched=len(rows), rows_loaded=loaded,
                    rows_discarded=report["rows_discarded"],
                    rows_atypical=report["atypical"],
                    last_ref_date=cov["last_date"], message=message,
                )
                results.append(RunResult(key, "success", len(rows), loaded, message))
                log.info("%s: %s", key, message)
                if report["atypical"]:
                    log.warning(
                        "%s: %s observação(ões) fora da faixa de alerta, carregadas e "
                        "sinalizadas: %s", key, report["atypical"], report["atypical_sample"]
                    )
            except Exception as exc:  # fronteira do pipeline: registra e segue adiante
                message = f"{type(exc).__name__}: {exc}"
                log.error("%s: FALHOU — %s", key, message)
                load.record_run(
                    conn, **base, finished_at=clock(), status="failed",
                    rows_fetched=None if rows is None else len(rows),
                    rows_loaded=None, rows_discarded=None, rows_atypical=None,
                    last_ref_date=None, message=message,
                )
                results.append(
                    RunResult(key, "failed", None if rows is None else len(rows), None, message)
                )
    finally:
        conn.close()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atualiza a base de indicadores de mercado.")
    parser.add_argument("--indicators", nargs="+", choices=list(SERIES), help="padrão: todos")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    results = run(args.indicators)
    failed = [r for r in results if r.status == "failed"]
    for r in results:
        print(f"[{'OK' if r.status == 'success' else 'FALHA'}] {r.indicator}: {r.message}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
