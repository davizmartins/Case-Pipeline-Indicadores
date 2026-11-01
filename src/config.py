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

# ATENÇÃO AO ALCANCE DESTA REGRA. O limite de lacuna detecta INTERRUPÇÃO PROLONGADA
# da fonte — um bloco que não veio, uma indisponibilidade. Ele NÃO detecta ausência
# isolada: numa série diária, um dia útil faltando produz lacuna de 2 dias, muito
# abaixo do limite. Passar nesta checagem NÃO certifica que a série está completa.
MAX_GAP_DAYS_DIARIA = 10
# Série mensal: observações consecutivas distam 28 a 31 dias; um mês faltando produz
# lacuna de 59 a 62. O limite fica entre os dois.
MAX_GAP_DAYS_MENSAL = 40

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
    sgs_code: int  # 0 quando a fonte não é o SGS
    unit: str
    frequency: str
    kind: str  # "nivel" (estoque) ou "taxa" (fluxo, exige capitalização)

    # --- validação ---------------------------------------------------------
    # Rejeita valores <= 0 apenas onde a DEFINIÇÃO da série os impede.
    reject_non_positive: bool
    # Faixa de alerta por NÍVEL: fora dela a observação é SINALIZADA, nunca
    # descartada. Regra operacional e configurável; não é garantia de detectar
    # troca de unidade nem separador decimal deslocado.
    alert_min: float | None
    alert_max: float | None
    # Lacuna acima da qual a carga é barrada. Ver comentário no topo do arquivo.
    max_gap_days: int

    # --- janela ------------------------------------------------------------
    # Meses extras coletados ANTES da janela de exibição, necessários para
    # métricas que olham para trás (ex.: acumulado em 12 meses na primeira data).
    margin_months: int

    # --- fonte -------------------------------------------------------------
    source_kind: str = "sgs"  # "sgs" ou "yfinance"
    ticker: str | None = None  # usado quando source_kind == "yfinance"

    # --- apresentação ------------------------------------------------------
    # A cor segue o INDICADOR, não a ordem em que ele aparece num gráfico: assim
    # ele é reconhecível em todo o painel e filtrar séries não repinta as outras.
    # Tons validados para daltonismo e contraste; ver src/charts.py.
    color: str = "#3987e5"

    # --- validação por variação --------------------------------------------
    # Faixa de alerta por VARIAÇÃO entre observações consecutivas, em %.
    # Complementa a faixa por nível: um valor pode ser plausível isoladamente e
    # destoar do anterior. Também apenas SINALIZA, pedindo revisão humana.
    alert_max_change_pct: float | None = None

    # --- atualidade --------------------------------------------------------
    # Exatamente um dos dois: dias (séries diárias) ou meses (séries mensais).
    stale_after_days: int | None = None
    stale_after_months: int | None = None

    # --- pendências --------------------------------------------------------
    # Texto exibido na seção de metodologia sempre que preenchido.
    identification_note: str | None = None
    # Quando True, a pendência também aparece como aviso em destaque no cartão.
    # Reservado para os casos em que a própria identificação da série está em
    # aberto — não para ressalvas metodológicas sobre uma série já identificada.
    identification_alert: bool = False
    # Datas ausentes conhecidas e AINDA NÃO EXPLICADAS dentro da janela.
    # Lista mantida MANUALMENTE: não há calendário de dias úteis no projeto,
    # então o preenchimento depende de inspeção humana.
    unexplained_absences: tuple[str, ...] = field(default_factory=tuple)


SERIES: dict[str, Series] = {
    "ptax": Series(
        key="ptax",
        color="#d95926",
        name="Dólar americano (venda)",
        source="Banco Central — SGS 1",
        sgs_code=1,
        unit="R$/US$",
        frequency="diária (dias úteis)",
        kind="nivel",
        reject_non_positive=True,  # uma taxa de câmbio não pode ser <= 0
        alert_min=None,
        alert_max=None,
        max_gap_days=MAX_GAP_DAYS_DIARIA,
        margin_months=0,
        stale_after_days=STALE_AFTER_DAYS,
        identification_note=(
            "Os valores coletados coincidem com a consulta histórica de cotações do "
            "Banco Central: em 30/10/2026 ela mostra 5,4206 na compra e 5,4212 na venda, "
            "o mesmo valor desta série. Isso confere UM valor em UMA data, por dois "
            "caminhos do BCB. A identificação desta série como a PTAX DE FECHAMENTO "
            "segue PENDENTE: o catálogo do BCB a nomeia 'Dólar americano (venda)' e cita "
            "a PTAX apenas em nota histórica. A confirmação continua necessária, porque o "
            "indicador pedido no case é o dólar PTAX venda."
        ),
        identification_alert=False,
    ),
    "cdi": Series(
        key="cdi",
        color="#3987e5",
        name="Série SGS 12 — identificação como CDI pendente",
        source="Banco Central — SGS 12",
        sgs_code=12,
        unit="% ao dia",
        frequency="diária (dias úteis)",
        kind="taxa",
        reject_non_positive=False,  # taxa zero é válida; negativa é sinalizada
        alert_min=0.0,
        alert_max=0.5,
        max_gap_days=MAX_GAP_DAYS_DIARIA,
        margin_months=12,
        stale_after_days=STALE_AFTER_DAYS,
        identification_note=(
            "Os metadados oficiais do SGS para esta série não puderam ser consultados: "
            "o portal do SGS responde 'Requisição inválida' e a página de metadados de "
            "juros do BCB (mg45p) documenta apenas séries da Selic, sem mencionar o CDI "
            "nem os códigos 12 e 4389. O nome, a unidade e a periodicidade seguem NÃO "
            "CONFIRMADOS por fonte oficial — o que significa não encontrados, não "
            "inexistentes."
        ),
        identification_alert=True,
    ),
    "ipca": Series(
        key="ipca",
        color="#c98500",
        name="IPCA — variação mensal",
        source="Banco Central — SGS 433 (apuração: IBGE)",
        sgs_code=433,
        unit="% ao mês",
        frequency="mensal",
        kind="taxa",
        # Deflação é um resultado legítimo: agosto de 2025 fechou em -0,11%.
        reject_non_positive=False,
        # Faixa de alerta desenhada contra a confusão realista: trocar a série 433
        # (variação mensal) pela 13522 (acumulado em 12 meses), cujos valores ficam
        # na casa de 4 a 5. Nos 21 meses conferidos, a 433 variou de -0,32 a 1,31.
        # Regra OPERACIONAL e provisória; não é garantia de detectar troca de unidade.
        alert_min=-2.0,
        alert_max=3.0,
        max_gap_days=MAX_GAP_DAYS_MENSAL,
        margin_months=12,
        stale_after_months=2,
        identification_note=(
            "Identificação CONFIRMADA por fonte oficial: a página de metadados de séries "
            "temporais do Banco Central lista '0433 — IPCA (índice nacional de preços ao "
            "consumidor-amplo)', fonte IBGE "
            "(www4.bcb.gov.br/PEC/SERIES/PORT/METADADOS/MG41BP.HTM, consultada em "
            "01/11/2026; a própria página informa última atualização em 27/09/2002). "
            "Unidade percentual e periodicidade mensal do índice são confirmadas pelo "
            "IBGE. Ressalva: naquela página a unidade e a periodicidade aparecem uma vez "
            "para o grupo de 33 séries do IPCA, não por série."
        ),
        identification_alert=False,
    ),
    "ibovespa": Series(
        key="ibovespa",
        color="#199e70",
        name="Ibovespa",
        source="yfinance — ticker ^BVSP (apuração: B3)",
        sgs_code=0,  # não vem do SGS
        source_kind="yfinance",
        ticker="^BVSP",
        unit="pontos",
        frequency="diária (pregões)",
        kind="nivel",
        reject_non_positive=True,  # um índice de preços não pode ser <= 0
        alert_min=None,
        alert_max=None,
        # Alerta por VARIAÇÃO, e não por nível: um valor pode ser plausível sozinho
        # e destoar do pregão anterior. O limite usa como âncora o circuit breaker da
        # B3, que suspende as negociações quando o índice cai 10% ante o fechamento
        # anterior — ou seja, o patamar que o próprio mercado trata como excepcional.
        # Aplicado simetricamente a altas, o que a regra do circuit breaker não faz.
        # PROVISÓRIO e configurável; ver limitações no README.
        alert_max_change_pct=10.0,
        max_gap_days=MAX_GAP_DAYS_DIARIA,
        margin_months=0,
        stale_after_days=STALE_AFTER_DAYS,
        identification_note=(
            "Fonte de terceiros, não oficial: o yfinance lê dados do Yahoo Finance, sem "
            "contrato de estabilidade. O Ibovespa é apurado pela B3. Conferido em "
            "01/11/2026: o fechamento de 26/10/2026 na série é 176.608 pontos, o mesmo "
            "valor publicado por fonte jornalística independente, com variação de "
            "-13,88% e acionamento de circuit breaker pela B3. Close e Adj Close "
            "coincidem, como esperado para um índice sem desdobramentos nem dividendos a "
            "ajustar — a conferência é refeita a cada carga."
        ),
        identification_alert=False,
    ),
}
