"""Configuração central: fontes, séries e parâmetros do pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# API SGS (Banco Central). O limite de 10 anos por consulta e a obrigatoriedade
# de informar dataInicial/dataFinal constam na página de dados abertos do BCB.
SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

# (timeout de conexão, timeout de leitura) em segundos.
HTTP_TIMEOUT = (5, 30)
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0

# Janela móvel: [hoje - WINDOW_YEARS anos, hoje], inclusive nas duas pontas.
WINDOW_YEARS = 5
# Consultas em blocos anuais (bem abaixo do limite de 10 anos; janelas menores
# respondem mais rápido e uma falha afeta só um bloco).
CHUNK_YEARS = 1

# Maior intervalo (em dias corridos) entre observações consecutivas de uma série
# diária antes de considerarmos que há lacuna de coleta. Fim de semana + feriado
# prolongado ficam bem abaixo disso.
MAX_GAP_DAYS = 10
# Dias corridos sem observação nova a partir dos quais o dashboard avisa.
STALE_AFTER_DAYS = 7

TIMEZONE = "America/Sao_Paulo"


def get_db_path() -> Path:
    """Caminho do SQLite. Lido a cada chamada para permitir VENETO_DB nos testes."""
    override = os.environ.get("VENETO_DB")
    return Path(override) if override else ROOT / "data" / "indicadores.db"


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    source: str
    sgs_code: int
    unit: str
    frequency: str
    positive_only: bool  # valores <= 0 são inválidos para esta série?


SERIES: dict[str, Series] = {
    "ptax": Series(
        key="ptax",
        name="Dólar PTAX (venda)",
        source="SGS/BCB série 1",
        sgs_code=1,
        unit="R$/US$",
        frequency="diária (dias úteis)",
        positive_only=True,
    ),
}
