"""Cálculos financeiros. Funções puras, sem banco e sem rede, para serem testáveis.

Convenções declaradas (e testadas):

- Séries de TAXA são capitalizadas, nunca somadas.
- Acumulado em 12 meses até D usa as observações com data em (D − 1 ano, D]:
  limite inferior ABERTO, superior FECHADO. O limite aberto evita contar o dia-âncora
  duas vezes. CONVENÇÃO PROVISÓRIA: se a taxa publicada para o dia D remunera o próprio
  dia D ou a noite de D para o dia útil seguinte é pendência não resolvida; errar isso
  desloca o acumulado em exatamente uma observação.
- Ano bissexto: 29/02 menos um ano recai em 28/02, o que torna a janela de 366 dias.
  É a convenção adotada, declarada aqui e coberta por teste.
- Anualização em base 252 (ver ANNUALIZATION_BASE).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.config import ANNUALIZATION_BASE


def compound_factor(rates_pct) -> float:
    """∏ (1 + taxa/100). Capitalização composta — NUNCA soma de taxas."""
    factor = 1.0
    for rate in rates_pct:
        factor *= 1.0 + float(rate) / 100.0
    return factor


def accumulate(rates_pct) -> float:
    """Variação acumulada, em %, de uma sequência de taxas em %."""
    return (compound_factor(rates_pct) - 1.0) * 100.0


def annualize(daily_pct: float, base: int = ANNUALIZATION_BASE) -> float:
    """Equivalente anual de uma taxa diária, em % a.a.

    É CONVERSÃO DE UNIDADE da taxa de um dia, não projeção de rendimento.
    """
    return ((1.0 + float(daily_pct) / 100.0) ** base - 1.0) * 100.0


def deannualize(annual_pct: float, base: int = ANNUALIZATION_BASE) -> float:
    """Caminho inverso de annualize(), em % a.d. Usado em testes de ida e volta."""
    return ((1.0 + float(annual_pct) / 100.0) ** (1.0 / base) - 1.0) * 100.0


def rebase_100(values, base_value: float) -> list[float]:
    """Série normalizada em base 100 a partir de um valor de referência."""
    if base_value == 0:
        raise ValueError("valor-base zero: não é possível rebasear")
    return [100.0 * float(v) / float(base_value) for v in values]


def window_12m(end: date) -> tuple[date, date]:
    """Janela de 12 meses até `end`: (limite inferior EXCLUSIVO, superior INCLUSIVO)."""
    start = (pd.Timestamp(end) - pd.DateOffset(years=1)).date()
    return start, end


def select_window(frame: pd.DataFrame, start_exclusive: date, end_inclusive: date) -> pd.DataFrame:
    """Observações com start_exclusive < ref_date <= end_inclusive, em ordem de data."""
    dates = pd.to_datetime(frame["ref_date"]).dt.date
    mask = (dates > start_exclusive) & (dates <= end_inclusive)
    return frame.loc[mask].sort_values("ref_date")


def coverage(
    frame: pd.DataFrame,
    start_exclusive: date,
    end_inclusive: date,
    max_gap_days: int,
    unexplained_absences: tuple[str, ...] = (),
) -> dict:
    """Avalia se a janela está coberta o bastante para rotular a métrica.

    ALCANCE: verifica que a janela foi percorrida de ponta a ponta SEM INTERRUPÇÃO
    PROLONGADA. NÃO verifica que todo dia útil esperado está presente — o projeto não
    tem calendário de dias úteis, então uma ausência isolada passa despercebida por
    esta função. Uma observação faltando subestima o acumulado sem disparar alerta.

    Devolve {'ok': bool, 'reason': str | None, ...}. Quando ok é False, a métrica não
    deve ser apresentada como completa.
    """
    window = select_window(frame, start_exclusive, end_inclusive)
    info: dict = {
        "ok": False,
        "reason": None,
        "n_obs": len(window),
        "first_date": None,
        "last_date": None,
        "max_gap_days": None,
    }
    if window.empty:
        info["reason"] = "nenhuma observação na janela"
        return info

    dates = pd.to_datetime(window["ref_date"])
    first, last = dates.min().date(), dates.max().date()
    info["first_date"], info["last_date"] = first, last

    gaps = dates.diff().dt.days.dropna()
    max_gap = int(gaps.max()) if not gaps.empty else 0
    info["max_gap_days"] = max_gap

    pendentes = [
        d for d in unexplained_absences
        if start_exclusive < date.fromisoformat(d) <= end_inclusive
    ]
    if pendentes:
        info["reason"] = (
            f"ausência conhecida e não explicada dentro da janela: {', '.join(pendentes)}"
        )
        return info
    if (first - start_exclusive).days > max_gap_days:
        info["reason"] = f"série só começa em {first}, {(first - start_exclusive).days} dias após o início da janela"
        return info
    if (end_inclusive - last).days > max_gap_days:
        info["reason"] = f"série termina em {last}, {(end_inclusive - last).days} dias antes do fim da janela"
        return info
    if max_gap > max_gap_days:
        info["reason"] = f"interrupção de {max_gap} dias dentro da janela (limite {max_gap_days})"
        return info

    info["ok"] = True
    return info


def accumulated_12m(
    frame: pd.DataFrame,
    end: date,
    max_gap_days: int,
    unexplained_absences: tuple[str, ...] = (),
) -> dict:
    """Acumulado em 12 meses até `end`, com o resultado da checagem de cobertura.

    Devolve {'value': float | None, 'coverage': dict, 'start_exclusive', 'end'}.
    `value` é None quando a cobertura falha: a métrica NÃO deve ser rotulada como
    de 12 meses nesse caso.
    """
    start_exclusive, end_inclusive = window_12m(end)
    cov = coverage(frame, start_exclusive, end_inclusive, max_gap_days, unexplained_absences)
    window = select_window(frame, start_exclusive, end_inclusive)
    value = accumulate(window["value"]) if cov["ok"] and not window.empty else None
    return {
        "value": value,
        "coverage": cov,
        "start_exclusive": start_exclusive,
        "end": end_inclusive,
        "n_obs": len(window),
    }


# --- comparação entre séries -------------------------------------------------
#
# As séries diárias têm calendários próprios e COMPROVADAMENTE diferentes (PTAX e
# Ibovespa divergem em 8 datas na janela de 5 anos). A comparação NÃO alinha as datas:
# cada série é desenhada nos seus próprios pontos, sem preenchimento e sem exclusão de
# observação. O único ponto compartilhado é a data-base do rebase.


def common_base_date(frames: list[pd.DataFrame], start: date, end: date) -> str | None:
    """Primeira data dentro de [start, end] com observação em TODAS as séries.

    Devolve None quando não existe data comum no período — nesse caso não há base
    honesta para o rebase e a comparação não deve ser apresentada.
    """
    if not frames or any(f.empty for f in frames):
        return None
    comuns = set.intersection(*(set(f["ref_date"]) for f in frames))
    lo, hi = start.isoformat(), end.isoformat()
    dentro = sorted(d for d in comuns if lo <= d <= hi)
    return dentro[0] if dentro else None


def index_level(frame: pd.DataFrame, base_date: str) -> pd.DataFrame:
    """Série de NÍVEL em base 100: valor(d) / valor(base) × 100, de base_date em diante."""
    sel = frame[frame["ref_date"] >= base_date].sort_values("ref_date")
    if sel.empty or sel.iloc[0]["ref_date"] != base_date:
        raise ValueError(f"série sem observação na data-base {base_date}")
    base = float(sel.iloc[0]["value"])
    if base == 0:
        raise ValueError(f"valor-base zero em {base_date}")
    return pd.DataFrame(
        {
            "ref_date": sel["ref_date"].to_numpy(),
            "index": [100.0 * float(v) / base for v in sel["value"]],
        }
    )


def index_rate(frame: pd.DataFrame, base_date: str) -> pd.DataFrame:
    """Série de TAXA em base 100, capitalizada no calendário DELA MESMA.

    Entram as taxas das datas em (base_date, d] — limite inferior ABERTO, a mesma
    convenção do acumulado em 12 meses. A taxa publicada NA data-base não entra: na
    data-base o índice vale 100 por definição.
    """
    if frame.empty or base_date not in set(frame["ref_date"]):
        raise ValueError(f"série sem observação na data-base {base_date}")
    posteriores = frame[frame["ref_date"] > base_date].sort_values("ref_date")
    fatores = (1.0 + posteriores["value"].astype(float) / 100.0).cumprod()
    return pd.DataFrame(
        {
            "ref_date": [base_date] + list(posteriores["ref_date"]),
            "index": [100.0] + [100.0 * float(f) for f in fatores],
        }
    )


# --- comparação mensal -------------------------------------------------------


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Limites de um mês no formato (EXCLUSIVO inferior, INCLUSIVO superior)."""
    primeiro = date(year, month, 1)
    proximo = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return primeiro - timedelta(days=1), proximo - timedelta(days=1)


def monthly_rate_accumulation(
    frame: pd.DataFrame, year: int, month: int, max_gap_days: int
) -> dict:
    """Acumula uma série de taxa dentro de um mês, com a checagem de cobertura.

    ALCANCE: a checagem detecta interrupção prolongada, não ausência isolada.
    """
    inicio_excl, fim = month_bounds(year, month)
    cov = coverage(frame, inicio_excl, fim, max_gap_days)
    janela = select_window(frame, inicio_excl, fim)
    return {
        "value": accumulate(janela["value"]) if cov["ok"] else None,
        "coverage": cov,
        "n_obs": len(janela),
    }


def real_return(nominal_pct: float, inflation_pct: float) -> float:
    """Retorno real pela RAZÃO entre os fatores, nunca pela diferença entre as taxas."""
    return ((1.0 + nominal_pct / 100.0) / (1.0 + inflation_pct / 100.0) - 1.0) * 100.0


def eligible_months(
    rate_frame: pd.DataFrame,
    monthly_frame: pd.DataFrame,
    start: date,
    end: date,
    max_gap_days: int,
) -> list[dict]:
    """Meses INTEIROS dentro de [start, end] comparáveis entre as duas séries.

    Um mês entra quando: cabe inteiro no período filtrado, a série mensal tem
    observação para ele, e a série de taxa tem cobertura suficiente no mês. O último
    mês elegível sai DOS DADOS — nada é fixado no código.
    """
    if rate_frame.empty or monthly_frame.empty:
        return []
    mensais = {d[:7]: float(v) for d, v in zip(monthly_frame["ref_date"], monthly_frame["value"])}
    out: list[dict] = []
    ano, mes = start.year, start.month
    while date(ano, mes, 1) <= end:
        primeiro = date(ano, mes, 1)
        _, ultimo = month_bounds(ano, mes)
        chave = f"{ano:04d}-{mes:02d}"
        if primeiro >= start and ultimo <= end and chave in mensais:
            acum = monthly_rate_accumulation(rate_frame, ano, mes, max_gap_days)
            if acum["value"] is not None:
                out.append(
                    {
                        "mes": chave,
                        "taxa": acum["value"],
                        "mensal": mensais[chave],
                        "real": real_return(acum["value"], mensais[chave]),
                        "n_obs": acum["n_obs"],
                    }
                )
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return out


def decimals_in(text: str) -> int:
    """Casas decimais no TEXTO recebido da fonte.

    ATENÇÃO: isto descreve o FORMATO em que o valor chegou, não a precisão
    metodológica com que a fonte apura o número. Uma fonte pode publicar seis casas
    e apurar com menos; pode publicar duas e apurar com mais. Serve só para estimar
    o arredondamento de publicação.
    """
    s = str(text).strip()
    if "." not in s:
        return 0
    return len(s.split(".", 1)[1].rstrip())


def rounding_half(decimals: int) -> float:
    """Meia unidade da última casa publicada: maior erro possível do arredondamento."""
    return 0.5 * (10.0 ** -decimals)


def annualization_sensitivity(daily_pct: float, base: int = ANNUALIZATION_BASE) -> float:
    """d(anualizada)/d(diária): quanto um erro na taxa diária desloca a anualizada.

    Cresce com o nível da taxa, por isso a tolerância não pode sair de um único exemplo.
    """
    return base * (1.0 + float(daily_pct) / 100.0) ** (base - 1)
