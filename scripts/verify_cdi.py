"""Confere a anualização: série 12 anualizada por nós vs. série 4389 do SGS.

O QUE ESTA CONFERÊNCIA FAZ: verifica COMPATIBILIDADE NUMÉRICA entre o valor que
calculamos a partir da série 12 e o valor publicado na série 4389, nas datas comuns.

O QUE ELA NÃO FAZ:
- não identifica nenhuma das duas séries: a identificação depende de metadados
  oficiais, pendentes (ver Series.identification_note em src/config.py);
- não comprova derivação direta entre as séries. Desvios pequenos mostram que os
  números são compatíveis, nada além disso;
- não estabelece a CAUSA de uma divergência. A faixa em que um desvio cai é uma
  observação, não um diagnóstico;
- não valida o acumulado em 12 meses, que é outro cálculo.

HIPÓTESES DE ARREDONDAMENTO (declaradas, não comprovadas):

  H1 (conservadora, usada como referência) — as duas séries são arredondamentos
     INDEPENDENTES de um mesmo valor subjacente. A tolerância soma:
       (a) a meia unidade da última casa publicada da 4389; e
       (b) a meia unidade da última casa publicada da série 12, propagada pela
           anualização com a sensibilidade no nível de taxa de cada data.

  H2 (estrita, apenas informativa) — uma série é derivada da outra, e só (b) entra.

A referência de aprovação é H1. H2 aparece no relatório como contagem auxiliar, sem
que se conclua nada sobre a cadeia de origem a partir dela.

As casas decimais são contadas no TEXTO recebido: isso descreve o FORMATO de
publicação, não a precisão metodológica com que a fonte apura o número.

Uso:  python -m scripts.verify_cdi
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date

import pandas as pd
import requests

from src import db, extract, metrics
from src.config import ANNUALIZATION_BASE, SERIES

ANNUAL_SERIES_CODE = 4389


class VerificationError(RuntimeError):
    pass


def fetch_annual(start: date, end: date, session=None, sleep=None) -> pd.DataFrame:
    """Baixa a série 4389 pela MESMA API já usada no pipeline (endpoint verificado)."""
    kwargs = {"session": session}
    if sleep is not None:
        kwargs["sleep"] = sleep
    # Derivado da série real com `replace`, e não construído campo a campo: `extract_series`
    # usa apenas `sgs_code`, e montar o dataclass inteiro à mão fazia o script quebrar a cada
    # campo novo em Series — foi exatamente o que aconteceu (TypeError por `max_gap_days`).
    stub = replace(
        SERIES["cdi"],
        key="sgs4389",
        name="Série SGS 4389",
        source=f"SGS/BCB série {ANNUAL_SERIES_CODE}",
        sgs_code=ANNUAL_SERIES_CODE,
        unit="(não confirmado)",
        alert_min=None,
        alert_max=None,
        margin_months=0,
        identification_note=None,
        identification_alert=False,
    )
    rows = extract.extract_series(stub, start, end, **kwargs)
    if not rows:
        raise VerificationError("a série 4389 não devolveu observações no período")
    return pd.DataFrame(rows, columns=["data", "valor"])


def compare_annualized(
    daily: pd.DataFrame,
    annual_raw: pd.DataFrame,
    base: int = ANNUALIZATION_BASE,
) -> dict:
    """Compara nossa anualização da série diária com a série anual publicada.

    `daily`: colunas ref_date (ISO) e value (float, % a.d.), mais raw_value (texto) quando
    disponível, para medir as casas publicadas.
    `annual_raw`: colunas data (dd/MM/aaaa) e valor (texto).

    Função pura: sem rede, sem banco. Testada com dados controlados.
    """
    ann = annual_raw.copy()
    ann["ref_date"] = pd.to_datetime(ann["data"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    ann["published"] = pd.to_numeric(ann["valor"], errors="coerce").astype(float)
    ann["decimals"] = ann["valor"].map(metrics.decimals_in)

    dly = daily.copy()
    if "raw_value" in dly.columns:
        dly["decimals"] = dly["raw_value"].map(metrics.decimals_in)
    else:
        dly["decimals"] = dly["value"].map(lambda v: metrics.decimals_in(repr(float(v))))

    merged = dly.merge(ann, on="ref_date", how="inner", suffixes=("_daily", "_annual"))
    only_daily = sorted(set(dly["ref_date"]) - set(ann["ref_date"]))
    only_annual = sorted(set(ann["ref_date"]) - set(dly["ref_date"]))

    rows = []
    for _, r in merged.iterrows():
        computed = metrics.annualize(r["value"], base)
        deviation = abs(computed - r["published"])
        # (b) erro da diária propagado pela anualização, no nível de taxa desta data
        propagated = metrics.annualization_sensitivity(r["value"], base) * metrics.rounding_half(
            int(r["decimals_daily"])
        )
        # (a) erro de publicação da própria série anual
        published_half = metrics.rounding_half(int(r["decimals_annual"]))
        rows.append(
            {
                "ref_date": r["ref_date"],
                "daily": float(r["value"]),
                "computed_annual": computed,
                "published_annual": float(r["published"]),
                "deviation": deviation,
                "tol_h1_conservative": propagated + published_half,
                "tol_h2_strict": propagated,
            }
        )

    detail = pd.DataFrame(rows)
    above_h1 = detail[detail["deviation"] > detail["tol_h1_conservative"]] if not detail.empty else detail
    above_h2 = detail[detail["deviation"] > detail["tol_h2_strict"]] if not detail.empty else detail
    return {
        "n_common": len(detail),
        "only_in_daily": only_daily,
        "only_in_annual": only_annual,
        "max_deviation": float(detail["deviation"].max()) if not detail.empty else 0.0,
        "n_above_h1": int(len(above_h1)),
        "n_above_h2": int(len(above_h2)),
        "decimals_daily": sorted(set(int(d) for d in dly["decimals"])),
        "decimals_annual": sorted(set(int(d) for d in ann["decimals"])),
        "detail": detail,
        "passed": bool(detail.shape[0] > 0 and len(above_h1) == 0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", help="caminho do SQLite (padrão: data/indicadores.db)")
    args = parser.parse_args(argv)

    conn = db.connect_readonly(args.db)
    stored = pd.read_sql_query(
        "SELECT o.ref_date, o.value, r.raw_value "
        "FROM observations o LEFT JOIN raw_observations r "
        "  ON r.indicator = o.indicator "
        " AND r.raw_date = substr(o.ref_date,9,2)||'/'||substr(o.ref_date,6,2)||'/'||substr(o.ref_date,1,4) "
        "WHERE o.indicator = 'cdi' ORDER BY o.ref_date",
        conn,
    )
    conn.close()
    if stored.empty:
        print("Base sem a série 12 ('cdi'); rode 'python -m src.pipeline --indicators cdi' antes.")
        return 2

    start = date.fromisoformat(stored["ref_date"].iloc[0])
    end = date.fromisoformat(stored["ref_date"].iloc[-1])
    try:
        annual = fetch_annual(start, end)
    except (VerificationError, extract.ExtractionError, requests.RequestException) as exc:
        print(f"NÃO FOI POSSÍVEL VERIFICAR: {type(exc).__name__}: {exc}")
        return 2

    res = compare_annualized(stored, annual)

    print(f"\nPeríodo comparado: {start} a {end}  (base de anualização: {ANNUALIZATION_BASE})")
    print(f"Datas em comum: {res['n_common']}")
    print(f"  só na série 12:   {len(res['only_in_daily'])} {res['only_in_daily'][:5]}")
    print(f"  só na série 4389: {len(res['only_in_annual'])} {res['only_in_annual'][:5]}")
    print(f"\nCasas decimais observadas no TEXTO recebido (formato de publicação,")
    print(f"NÃO precisão metodológica da fonte):")
    print(f"  série 12:   {res['decimals_daily']}")
    print(f"  série 4389: {res['decimals_annual']}")
    print(f"\nDesvio máximo observado: {res['max_deviation']:.8f} p.p.")
    print(f"  datas acima da tolerância H1 (conservadora, referência): {res['n_above_h1']}")
    print(f"  datas acima da tolerância H2 (estrita, informativa):     {res['n_above_h2']}")
    if res["n_above_h1"]:
        print("\nDatas acima de H1 (investigar; a faixa NÃO indica a causa):")
        for _, r in res["detail"][res["detail"]["deviation"] > res["detail"]["tol_h1_conservative"]].head(20).iterrows():
            print(f"  {r['ref_date']}: calculado={r['computed_annual']:.6f} "
                  f"publicado={r['published_annual']:.6f} desvio={r['deviation']:.8f}")

    print("\nRESULTADO:", "COMPATÍVEL dentro de H1" if res["passed"] else "DIVERGÊNCIAS ACIMA DE H1")
    print("Compatibilidade numérica não identifica as séries nem comprova derivação")
    print("entre elas. A identificação depende de metadados oficiais, ainda pendentes.")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
