"""Avaliação de atualidade dos dados, por série.

Séries diárias e mensais pedem réguas diferentes. Sete dias é razoável para uma
cotação diária e sem sentido para um índice mensal, que naturalmente fica mais de
um mês atrás.

APROXIMAÇÃO DECLARADA para séries mensais: o ideal seria comparar o último mês
disponível com o último mês cuja divulgação JÁ OCORREU segundo o calendário oficial
do IBGE. Consultar esse calendário automaticamente ampliaria o escopo desta etapa,
então usamos a diferença em meses entre o mês corrente e o mês de referência. Por
isso o alerta se chama "possível defasagem": ele pode disparar sem haver atraso
real, quando o mês já fechou mas a divulgação ainda não aconteceu.
"""

from __future__ import annotations

from datetime import date

from src.config import Series


def months_between(earlier: date, later: date) -> int:
    """Diferença em meses de calendário, ignorando o dia."""
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def staleness_warning(series: Series, last_ref: date, today: date) -> str | None:
    """Texto do aviso, ou None se a série está dentro do esperado."""
    if series.stale_after_months is not None:
        meses = months_between(last_ref, today)
        if meses >= series.stale_after_months:
            return (
                f"possível defasagem: o último mês de referência é "
                f"{last_ref.month:02d}/{last_ref.year}, {meses} meses atrás do mês "
                "corrente. Aproximação: o projeto não consulta o calendário oficial de "
                "divulgação, então este aviso pode aparecer antes de haver atraso real."
            )
        return None
    if series.stale_after_days is not None:
        dias = (today - last_ref).days
        if dias > series.stale_after_days:
            return (
                f"dados possivelmente desatualizados: a última observação é de "
                f"{last_ref.strftime('%d/%m/%Y')} ({dias} dias atrás)."
            )
    return None
