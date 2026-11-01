"""Tratamento: padroniza datas e valores e valida a qualidade dos dados recebidos.

Regras (cada uma é contada no relatório, nada é descartado em silêncio):
- datas dd/MM/aaaa viram data real; as inválidas são descartadas;
- valores não numéricos ou não finitos são descartados, NUNCA convertidos em zero;
- séries "positive_only" (ex.: PTAX) descartam valores <= 0;
- duplicidade por data: fica a última ocorrência; datas com valores diferentes são contadas;
- a saída é ordenada cronologicamente, com ref_date em ISO (AAAA-MM-DD).

Dias sem observação (fim de semana, feriado) NÃO são tratados como erro e NÃO são preenchidos.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


class DataQualityError(RuntimeError):
    """Os dados recebidos não são confiáveis o bastante para serem carregados."""


def clean_sgs(raw: pd.DataFrame, *, positive_only: bool) -> tuple[pd.DataFrame, dict]:
    """Recebe colunas 'data' (dd/MM/aaaa) e 'valor' (texto) e devolve (dados limpos, relatório)."""
    report: dict[str, int] = {"rows_in": len(raw)}
    df = raw.loc[:, ["data", "valor"]].copy()

    df["ref_date"] = pd.to_datetime(
        df["data"].astype("string").str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    df["value"] = pd.to_numeric(df["valor"], errors="coerce").astype("float64")

    bad_date = df["ref_date"].isna()
    report["discarded_invalid_date"] = int(bad_date.sum())
    df = df[~bad_date]

    bad_value = ~np.isfinite(df["value"])
    report["discarded_invalid_value"] = int(bad_value.sum())
    df = df[~bad_value]

    if positive_only:
        non_positive = df["value"] <= 0
        report["discarded_non_positive"] = int(non_positive.sum())
        df = df[~non_positive]
    else:
        report["discarded_non_positive"] = 0

    duplicated = df[df.duplicated("ref_date", keep=False)]
    conflicts = duplicated.groupby("ref_date")["value"].nunique()
    report["conflicting_dates"] = int((conflicts > 1).sum())
    before = len(df)
    df = df.drop_duplicates("ref_date", keep="last")
    report["duplicates_removed"] = before - len(df)

    df = df.sort_values("ref_date")
    clean = pd.DataFrame(
        {
            "ref_date": df["ref_date"].dt.strftime("%Y-%m-%d").to_numpy(),
            "value": df["value"].to_numpy(dtype=float),
        }
    )
    report["rows_out"] = len(clean)
    report["rows_discarded"] = (
        report["discarded_invalid_date"]
        + report["discarded_invalid_value"]
        + report["discarded_non_positive"]
    )
    return clean, report


def validate_coverage(clean: pd.DataFrame, start: date, end: date, max_gap_days: int) -> dict:
    """Garante que a série cobre a janela sem lacunas grandes. Levanta DataQualityError se não.

    Não exige dado no último dia da janela: a defasagem natural (hoje pode ser fim de
    semana ou feriado) é tratada no dashboard como "dado desatualizado", não como erro.
    """
    if clean.empty:
        raise DataQualityError("nenhuma observação válida na janela solicitada")

    dates = pd.to_datetime(clean["ref_date"])
    first, last = dates.min().date(), dates.max().date()

    if first - start > timedelta(days=max_gap_days):
        raise DataQualityError(
            f"série começa em {first}, mais de {max_gap_days} dias após o início da janela ({start})"
        )
    if last > end:
        raise DataQualityError(f"observação em {last} é posterior ao fim da janela ({end})")

    gaps = dates.diff().dt.days.dropna()
    max_gap = int(gaps.max()) if not gaps.empty else 0
    if max_gap > max_gap_days:
        pos = int(gaps.idxmax())
        gap_end = dates.iloc[pos].date()
        raise DataQualityError(
            f"lacuna de {max_gap} dias antes de {gap_end} (limite: {max_gap_days})"
        )
    return {"first_date": first.isoformat(), "last_date": last.isoformat(), "max_gap_days": max_gap}
