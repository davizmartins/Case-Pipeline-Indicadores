"""Orquestra extração -> tratamento -> validação -> carga e registra cada execução.

Uso:  python -m src.pipeline            (todas as séries configuradas)
      python -m src.pipeline --indicators ptax

Se qualquer etapa falhar, NADA é carregado para aquele indicador, a falha é gravada em
pipeline_runs e o processo termina com código 1. Dados fictícios nunca são gerados.
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

from src import db, extract, load, transform
from src.clock import today_br
from src.config import MAX_GAP_DAYS, SERIES, WINDOW_YEARS

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
    """Janela móvel [hoje - N anos, hoje], inclusive nas duas pontas."""
    start = (pd.Timestamp(today) - pd.DateOffset(years=years)).date()
    return start, today


def run(
    indicators: list[str] | None = None,
    *,
    today: date | None = None,
    db_path: Path | str | None = None,
    session=None,
    sleep=time.sleep,
    clock=utc_now,
) -> list[RunResult]:
    keys = indicators or list(SERIES)
    unknown = [k for k in keys if k not in SERIES]
    if unknown:
        raise ValueError(f"indicador(es) desconhecido(s): {unknown}; disponíveis: {list(SERIES)}")

    start, end = window_bounds(today or today_br())
    conn = db.connect(db_path)
    results: list[RunResult] = []
    try:
        for key in keys:
            series = SERIES[key]
            started_at = clock()
            rows: list[dict] | None = None
            base = dict(
                indicator=key,
                started_at=started_at,
                window_start=start.isoformat(),
                window_end=end.isoformat(),
            )
            try:
                rows = extract.extract_series(series, start, end, session=session, sleep=sleep)
                raw_df = pd.DataFrame(rows, columns=["data", "valor"])
                clean, report = transform.clean_sgs(raw_df, positive_only=series.positive_only)
                coverage = transform.validate_coverage(clean, start, end, MAX_GAP_DAYS)
                loaded = load.load_series(conn, key, series.source, rows, clean, clock())
                message = (
                    f"{loaded} observações carregadas ({coverage['first_date']} a "
                    f"{coverage['last_date']}); descartadas: {report['rows_discarded']}; "
                    f"duplicadas removidas: {report['duplicates_removed']}; "
                    f"datas com valores conflitantes: {report['conflicting_dates']}"
                )
                load.record_run(
                    conn, **base, finished_at=clock(), status="success",
                    rows_fetched=len(rows), rows_loaded=loaded,
                    rows_discarded=report["rows_discarded"],
                    last_ref_date=coverage["last_date"], message=message,
                )
                results.append(RunResult(key, "success", len(rows), loaded, message))
                log.info("%s: %s", key, message)
            except Exception as exc:  # fronteira do pipeline: registra e segue para o próximo
                message = f"{type(exc).__name__}: {exc}"
                log.error("%s: FALHOU — %s", key, message)
                load.record_run(
                    conn, **base, finished_at=clock(), status="failed",
                    rows_fetched=None if rows is None else len(rows),
                    rows_loaded=None, rows_discarded=None, last_ref_date=None, message=message,
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
