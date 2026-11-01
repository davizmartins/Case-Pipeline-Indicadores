"""Confere a composição de 12 meses: série 433 composta por nós vs. série 13522 do SGS.

O QUE ESTA CONFERÊNCIA FAZ: verifica que capitalizar os 12 mensais da série 433 reproduz
o acumulado publicado na série 13522, nas janelas em que há dados para as duas.

O QUE ELA NÃO FAZ:
- não identifica a série 13522: os metadados oficiais dela NÃO foram localizados;
- não valida a convenção de datas de séries DIÁRIAS (o CDI é outro cálculo);
- não estabelece a causa de uma eventual divergência.

TOLERÂNCIA (derivada, não arbitrada). Duas fontes de erro:
  (a) cada variação mensal da 433 é publicada arredondada; o erro de meia unidade da
      última casa se propaga ao acumulado com fator ~(1+acumulado)/(1+mensal) por mês,
      e doze meses no mesmo sentido somam;
  (b) a própria 13522 é publicada arredondada.
A referência de aprovação é a soma das duas (pior caso). As casas decimais são contadas
no TEXTO recebido: isso descreve o FORMATO de publicação, não a precisão metodológica.

Uso:  python -m scripts.verify_ipca
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd
import requests

from src import db, extract, metrics
from src.config import SERIES

ACC12_SERIES_CODE = 13522


class VerificationError(RuntimeError):
    pass


def fetch_accumulated(start: date, end: date, session=None, sleep=None) -> pd.DataFrame:
    """Baixa a série 13522 pela MESMA API já usada no pipeline (endpoint verificado)."""
    kwargs = {"session": session}
    if sleep is not None:
        kwargs["sleep"] = sleep
    stub = SERIES["ipca"].__class__(
        key="sgs13522", name="Série SGS 13522", source=f"Banco Central — SGS {ACC12_SERIES_CODE}",
        sgs_code=ACC12_SERIES_CODE, unit="(não confirmado)", frequency="mensal", kind="taxa",
        reject_non_positive=False, alert_min=None, alert_max=None,
        max_gap_days=40, margin_months=0,
    )
    rows = extract.extract_series(stub, start, end, **kwargs)
    if not rows:
        raise VerificationError(f"a série {ACC12_SERIES_CODE} não devolveu observações")
    return pd.DataFrame(rows, columns=["data", "valor"])


def compare_accumulated(monthly: pd.DataFrame, published_raw: pd.DataFrame) -> dict:
    """Compara nossa composição de 12 meses com o acumulado publicado.

    `monthly`: ref_date (ISO), value (float, % ao mês) e, se houver, raw_value (texto).
    `published_raw`: data (dd/MM/aaaa) e valor (texto).

    Função pura: sem rede, sem banco. Testada com dados controlados.
    """
    pub = published_raw.copy()
    pub["ref_date"] = pd.to_datetime(pub["data"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    pub["published"] = pd.to_numeric(pub["valor"], errors="coerce").astype(float)
    pub["decimals_pub"] = pub["valor"].map(metrics.decimals_in)

    mon = monthly.copy().sort_values("ref_date").reset_index(drop=True)
    if "raw_value" in mon.columns:
        mon["decimals_mon"] = mon["raw_value"].map(metrics.decimals_in)
    else:
        mon["decimals_mon"] = mon["value"].map(lambda v: metrics.decimals_in(repr(float(v))))

    rows = []
    for _, p in pub.iterrows():
        fim = date.fromisoformat(p["ref_date"])
        inicio_excl, _ = metrics.window_12m(fim)
        janela = metrics.select_window(mon, inicio_excl, fim)
        if len(janela) != 12:
            continue  # sem os 12 meses não dá para compor esta janela
        calculado = metrics.accumulate(janela["value"])
        desvio = abs(calculado - p["published"])
        # (a) arredondamento dos mensais, propagado: 12 meses no mesmo sentido
        fator = 1.0 + calculado / 100.0
        por_mes = [
            metrics.rounding_half(int(d)) * fator / (1.0 + float(v) / 100.0)
            for d, v in zip(janela_decimais(janela, mon), janela["value"])
        ]
        tol_mensais = sum(por_mes)
        # (b) arredondamento da própria série publicada
        tol_pub = metrics.rounding_half(int(p["decimals_pub"]))
        rows.append(
            {
                "ref_date": p["ref_date"],
                "calculado": calculado,
                "publicado": float(p["published"]),
                "desvio": desvio,
                "tolerancia": tol_mensais + tol_pub,
                "arredonda_igual": round(calculado, int(p["decimals_pub"])) == p["published"],
            }
        )

    detail = pd.DataFrame(rows)
    acima = detail[detail["desvio"] > detail["tolerancia"]] if not detail.empty else detail
    return {
        "n_janelas": len(detail),
        "max_desvio": float(detail["desvio"].max()) if not detail.empty else 0.0,
        "n_acima_da_tolerancia": int(len(acima)),
        "n_arredonda_igual": int(detail["arredonda_igual"].sum()) if not detail.empty else 0,
        "decimals_mensal": sorted(set(int(d) for d in mon["decimals_mon"])),
        "decimals_publicado": sorted(set(int(d) for d in pub["decimals_pub"])),
        "detail": detail,
        "passed": bool(len(detail) > 0 and len(acima) == 0),
    }


def janela_decimais(janela: pd.DataFrame, mon: pd.DataFrame) -> list[int]:
    """Casas decimais publicadas de cada mês da janela."""
    mapa = dict(zip(mon["ref_date"], mon["decimals_mon"]))
    return [int(mapa.get(d, 2)) for d in janela["ref_date"]]


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
        "WHERE o.indicator = 'ipca' ORDER BY o.ref_date",
        conn,
    )
    conn.close()
    if stored.empty:
        print("Base sem a série 433 ('ipca'); rode 'python -m src.pipeline --indicators ipca'.")
        return 2

    start = date.fromisoformat(stored["ref_date"].iloc[0])
    end = date.fromisoformat(stored["ref_date"].iloc[-1])
    try:
        publicado = fetch_accumulated(start, end)
    except (VerificationError, extract.ExtractionError, requests.RequestException) as exc:
        print(f"NÃO FOI POSSÍVEL VERIFICAR: {type(exc).__name__}: {exc}")
        return 2

    res = compare_accumulated(stored, publicado)
    print(f"\nPeríodo: {start} a {end}")
    print(f"Janelas de 12 meses comparáveis: {res['n_janelas']}")
    print("\nCasas decimais no TEXTO recebido (formato de publicação, NÃO precisão")
    print("metodológica da fonte):")
    print(f"  série 433:   {res['decimals_mensal']}")
    print(f"  série 13522: {res['decimals_publicado']}")
    print(f"\nDesvio máximo: {res['max_desvio']:.6f} p.p.")
    print(f"  janelas acima da tolerância: {res['n_acima_da_tolerancia']}")
    print(f"  janelas em que o calculado ARREDONDA para o publicado: "
          f"{res['n_arredonda_igual']} de {res['n_janelas']}")
    if res["n_acima_da_tolerancia"]:
        print("\nJanelas acima da tolerância (investigar; a faixa não indica a causa):")
        for _, r in res["detail"][res["detail"]["desvio"] > res["detail"]["tolerancia"]].head(20).iterrows():
            print(f"  {r['ref_date']}: calculado={r['calculado']:.4f} "
                  f"publicado={r['publicado']:.2f} desvio={r['desvio']:.6f}")
    print("\nRESULTADO:", "COMPATÍVEL" if res["passed"] else "DIVERGÊNCIAS ACIMA DA TOLERÂNCIA")
    print("Compatibilidade numérica não identifica a série 13522, cujos metadados")
    print("oficiais não foram localizados, e não valida a convenção de séries diárias.")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
