"""Configuração central: fontes, séries e parâmetros do pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# API SGS (Banco Central). O limite de 10 anos por consulta e a obrigatoriedade
# de informar dataInicial/dataFinal constam na página de dados abertos do BCB.
SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

# (timeout de conexão, timeout de leitura) em segundos.
HTTP_TIMEOUT = (5, 30)
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0

# Janela de EXIBIÇÃO: [hoje - WINDOW_YEARS anos, hoje], inclusive nas duas pontas.
# A janela de EXTRAÇÃO pode ser maior, por causa da margem de cada série.
WINDOW_YEARS = 5
CHUNK_YEARS = 1

# ATENÇÃO AO ALCANCE DESTA REGRA. MAX_GAP_DAYS detecta INTERRUPÇÃO PROLONGADA da
# fonte — um bloco que não veio, uma indisponibilidade. Ele NÃO detecta ausência
# isolada: um dia útil faltando no meio da semana produz lacuna de 2 dias, e até
# uma segunda-feira após feriado prolongado fica em 5 ou 6 — todos muito abaixo
# do limite. Passar nesta checagem NÃO certifica que a série está completa.
MAX_GAP_DAYS = 10

STALE_AFTER_DAYS = 7
TIMEZONE = "America/Sao_Paulo"

# Base de dias úteis usada na anualização de taxas diárias.
# Para a Taxa DI, a B3 documenta que as taxas são "expressas ao ano de 252 dias
# úteis". Isso vale para o ÍNDICE; que a série 12 do SGS carregue esse índice é
# pendência aberta (ver identification_note abaixo).
ANNUALIZATION_BASE = 252


def get_db_path() -> Path:
    """Caminho do SQLite. Lido a cada chamada para permitir VENETO_DB nos testes."""
    override = os.environ.get("VENETO_DB")
    return Path(override) if override else ROOT / "data" / "indicadores.db"


@dataclass(frozen=True)
class Series:
    key: str
    name: str  # rótulo exibido na interface
    source: str
    sgs_code: int
    unit: str
    frequency: str
    kind: str  # "nivel" (estoque) ou "taxa" (fluxo, exige capitalização)

    # --- validação ---------------------------------------------------------
    # Rejeita valores <= 0 apenas onde a DEFINIÇÃO da série os impede.
    reject_non_positive: bool
    # Faixa de alerta: fora dela a observação é SINALIZADA, nunca descartada.
    # Regra operacional e configurável; não é garantia de detectar troca de
    # unidade nem separador decimal deslocado.
    alert_min: float | None
    alert_max: float | None

    # --- janela ------------------------------------------------------------
    # Meses extras coletados ANTES da janela de exibição, necessários para
    # métricas que olham para trás (ex.: acumulado em 12 meses na primeira data).
    margin_months: int

    # --- pendências --------------------------------------------------------
    # Quando preenchido, a identificação da série NÃO está confirmada por
    # metadados oficiais e o texto é exibido na interface.
    identification_note: str | None = None
    # Datas ausentes conhecidas e AINDA NÃO EXPLICADAS dentro da janela.
    # Lista mantida MANUALMENTE: não há calendário de dias úteis no projeto,
    # então o preenchimento depende de inspeção humana.
    unexplained_absences: tuple[str, ...] = field(default_factory=tuple)


SERIES: dict[str, Series] = {
    "ptax": Series(
        key="ptax",
        name="Dólar PTAX (venda)",
        source="SGS/BCB série 1",
        sgs_code=1,
        unit="R$/US$",
        frequency="diária (dias úteis)",
        kind="nivel",
        reject_non_positive=True,  # uma taxa de câmbio não pode ser <= 0
        alert_min=None,
        alert_max=None,
        margin_months=0,
    ),
    "cdi": Series(
        key="cdi",
        name="Série SGS 12 — identificação como CDI pendente",
        source="SGS/BCB série 12",
        sgs_code=12,
        unit="% ao dia",
        frequency="diária (dias úteis)",
        kind="taxa",
        reject_non_positive=False,  # taxa zero é válida; negativa é sinalizada
        alert_min=0.0,
        alert_max=0.5,
        margin_months=12,
        identification_note=(
            "Os metadados oficiais do SGS para esta série não puderam ser consultados: "
            "o portal do SGS responde 'Requisição inválida' e o portal de dados abertos "
            "do BCB não traz entrada localizável para o CDI. O nome, a unidade e a "
            "periodicidade seguem NÃO CONFIRMADOS por fonte oficial."
        ),
    ),
}
