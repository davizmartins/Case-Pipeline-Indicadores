"""Tratamento e qualidade dos dados. Três categorias, declaradas e contadas:

1. INVÁLIDO — rejeitado: data malformada, valor não numérico, valor não finito.
2. IMPOSSÍVEL PELA DEFINIÇÃO — rejeitado: só onde a definição da série o impede
   (ex.: PTAX <= 0, porque taxa de câmbio é razão entre quantidades positivas).
3. ATÍPICO — CARREGADO, contado e sinalizado: fora da faixa de alerta.

Nenhuma observação é descartada por ser atípica. Valor ausente NUNCA vira zero.
Fim de semana e feriado não são erro e não são preenchidos.

A faixa de alerta é REGRA OPERACIONAL e configurável. Ela sinaliza o que destoa para
olhar humano. NÃO é garantia de detectar troca de unidade da série nem separador
decimal deslocado: pode pegar alguns desses casos, não todos.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


class DataQualityError(RuntimeError):
    """Os dados recebidos não são confiáveis o bastante para serem carregados."""


def clean_sgs(
    raw: pd.DataFrame,
    *,
    reject_non_positive: bool,
    alert_min: float | None = None,
    alert_max: float | None = None,
    alert_max_change_pct: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Recebe 'data' (dd/MM/aaaa) e 'valor' (texto). Devolve (dados limpos, relatório).

    A saída traz ref_date (ISO), value (float) e atypical (0/1).
    """
    report: dict = {"rows_in": len(raw)}
    df = raw.loc[:, ["data", "valor"]].copy()

    df["ref_date"] = pd.to_datetime(
        df["data"].astype("string").str.strip(), format="%d/%m/%Y", errors="coerce"
    )
    df["value"] = pd.to_numeric(df["valor"], errors="coerce").astype("float64")

    # --- 1. inválido: rejeita -------------------------------------------------
    bad_date = df["ref_date"].isna()
    report["discarded_invalid_date"] = int(bad_date.sum())
    df = df[~bad_date]

    bad_value = ~np.isfinite(df["value"])  # pega NaN, +inf e -inf
    report["discarded_invalid_value"] = int(bad_value.sum())
    df = df[~bad_value]

    # --- 2. impossível pela definição: rejeita --------------------------------
    if reject_non_positive:
        non_positive = df["value"] <= 0
        report["discarded_non_positive"] = int(non_positive.sum())
        df = df[~non_positive]
    else:
        report["discarded_non_positive"] = 0

    # --- duplicidade ----------------------------------------------------------
    duplicated = df[df.duplicated("ref_date", keep=False)]
    conflicts = duplicated.groupby("ref_date")["value"].nunique()
    report["conflicting_dates"] = int((conflicts > 1).sum())
    before = len(df)
    df = df.drop_duplicates("ref_date", keep="last")
    report["duplicates_removed"] = before - len(df)

    df = df.sort_values("ref_date")

    # --- 3. atípico: CARREGA, conta e sinaliza --------------------------------
    # Duas regras independentes. A de NÍVEL pega um valor implausível em si; a de
    # VARIAÇÃO pega um valor plausível sozinho que destoa do anterior. Nenhuma das
    # duas descarta nada: ambas pedem revisão humana, não declaram erro.
    by_level = pd.Series(False, index=df.index)
    if alert_min is not None:
        by_level |= df["value"] < alert_min
    if alert_max is not None:
        by_level |= df["value"] > alert_max

    by_change = pd.Series(False, index=df.index)
    if alert_max_change_pct is not None and len(df) > 1:
        variacao = df["value"].pct_change() * 100.0
        by_change = variacao.abs() > alert_max_change_pct
        by_change = by_change.fillna(False)  # a primeira observação não tem anterior

    atypical = by_level | by_change
    report["atypical_level"] = int(by_level.sum())
    report["atypical_change"] = int(by_change.sum())
    report["atypical"] = int(atypical.sum())
    report["atypical_sample"] = [
        {"ref_date": d.strftime("%Y-%m-%d"), "value": float(v)}
        for d, v in zip(df.loc[atypical, "ref_date"], df.loc[atypical, "value"])
    ][:10]

    clean = pd.DataFrame(
        {
            "ref_date": df["ref_date"].dt.strftime("%Y-%m-%d").to_numpy(),
            "value": df["value"].to_numpy(dtype=float),
            "atypical": atypical.to_numpy().astype(int),
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
    """Barra a carga quando a série não cobre a janela ou tem INTERRUPÇÃO PROLONGADA.

    ALCANCE: detecta interrupção da fonte, não ausência isolada. Um dia útil faltando
    no meio da semana gera lacuna de 2 dias e passa por aqui sem alarme. Passar nesta
    validação NÃO significa que a série está completa.

    Não exige dado no último dia da janela: a defasagem natural (hoje pode ser fim de
    semana, feriado, ou a fonte publicar com atraso) é tratada adiante como "dado
    desatualizado", não como erro de carga.
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
            f"interrupção de {max_gap} dias antes de {gap_end} (limite: {max_gap_days})"
        )
    return {"first_date": first.isoformat(), "last_date": last.isoformat(), "max_gap_days": max_gap}
