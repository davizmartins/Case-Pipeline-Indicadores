"""Formatação no padrão brasileiro (vírgula decimal, ponto de milhar, dd/mm/aaaa)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import TIMEZONE

_SWAP = str.maketrans({",": ".", ".": ","})


def fmt_number(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".translate(_SWAP)


def fmt_pct(value: float, decimals: int = 2) -> str:
    """Percentual com sinal explícito. `value` já é percentual (0,25 significa 0,25%)."""
    return f"{value:+,.{decimals}f}".translate(_SWAP) + "%"


def fmt_date(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%d/%m/%Y")


def fmt_timestamp(iso_utc: str) -> str:
    """ISO-8601 em UTC -> 'dd/mm/aaaa HH:MM' no horário de Brasília."""
    return datetime.fromisoformat(iso_utc).astimezone(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")
