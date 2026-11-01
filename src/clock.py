"""Data de hoje no fuso de Brasília. Isolada em módulo próprio para ser trocada nos testes."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import TIMEZONE


def today_br() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()
