"""Conferência independente: PTAX do SGS (série 1) armazenada vs. API Olinda/PTAX do BCB.

Objetivo: reunir evidência de que a série 1 do SGS representa a PTAX de fechamento. Coincidir
em poucos dias NÃO basta; por isso a comparação cobre toda a base armazenada.

Critério de aprovação (definido ANTES de rodar):
  PASSA somente se (1) os conjuntos de datas forem idênticos e (2) os valores forem iguais
  após arredondar para 4 casas decimais em todas as datas. Qualquer divergência é listada e
  deve ser explicada antes de se decidir qualquer troca de fonte.

ATENÇÃO — não verificado: o endereço, o nome da função e o formato das datas da Olinda
(abaixo) vêm de memória e NÃO foram conferidos contra a documentação oficial, que não pôde
ser acessada ao escrever este script. A lógica de comparação (`compare_series`) é testada
com dados controlados; a chamada de rede (`fetch_olinda`) nunca foi executada. Se a Olinda
rejeitar a requisição, o script falha com mensagem explícita (não reporta "passou").

Uso:  python -m scripts.verify_ptax
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd
import requests

from src import db
from src.config import HTTP_TIMEOUT

OLINDA_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
TOP = 10000
DECIMALS = 4


class VerificationError(RuntimeError):
    pass


def fetch_olinda(start: date, end: date, session=None) -> pd.DataFrame:
    """Baixa cotações da Olinda e devolve (ref_date ISO, value = cotacaoVenda). NÃO VERIFICADO."""
    session = session or requests.Session()
    params = {
        "@dataInicial": f"'{start:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
        "$format": "json",
        "$top": TOP,
    }
    resp = session.get(OLINDA_URL, params=params, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise VerificationError(f"Olinda respondeu HTTP {resp.status_code}: {resp.text[:200]}")
    rows = resp.json().get("value")
    if rows is None:
        raise VerificationError("resposta da Olinda sem o campo 'value'")
    if len(rows) >= TOP:
        raise VerificationError(f"resposta truncada em {TOP} registros; reduza o período")
    df = pd.DataFrame(rows)
    if df.empty:
        raise VerificationError("Olinda não devolveu cotações")
    if "tipoBoletim" in df.columns:  # se houver vários boletins por dia, fica só o fechamento
        df = df[df["tipoBoletim"].astype(str).str.lower().str.contains("fechamento")]
    out = pd.DataFrame(
        {"ref_date": df["dataHoraCotacao"].astype(str).str[:10], "value": df["cotacaoVenda"].astype(float)}
    )
    if out["ref_date"].duplicated().any():
        raise VerificationError("mais de uma cotação por dia na Olinda; critério de boletim indefinido")
    return out.sort_values("ref_date").reset_index(drop=True)


def compare_series(sgs: pd.DataFrame, ref: pd.DataFrame, decimals: int = DECIMALS) -> dict:
    """Compara duas séries (colunas ref_date ISO e value). Função pura, testada com dados controlados."""
    a = sgs.set_index("ref_date")["value"]
    b = ref.set_index("ref_date")["value"]
    only_a = sorted(set(a.index) - set(b.index))
    only_b = sorted(set(b.index) - set(a.index))
    common = sorted(set(a.index) & set(b.index))
    mismatches = []
    max_abs = 0.0
    for d in common:
        diff = abs(a[d] - b[d])
        max_abs = max(max_abs, diff)
        if round(a[d], decimals) != round(b[d], decimals):
            mismatches.append({"ref_date": d, "sgs": float(a[d]), "ref": float(b[d])})
    return {
        "n_sgs": len(a),
        "n_ref": len(b),
        "n_common": len(common),
        "only_in_sgs": only_a,
        "only_in_ref": only_b,
        "n_value_mismatch": len(mismatches),
        "mismatches": mismatches,
        "max_abs_diff": float(max_abs),
        "passed": not only_a and not only_b and not mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", help="caminho do SQLite (padrão: data/indicadores.db)")
    args = parser.parse_args(argv)

    conn = db.connect_readonly(args.db)
    sgs = db.read_series(conn, "ptax")
    conn.close()
    if sgs.empty:
        print("Base sem PTAX; rode o pipeline antes.")
        return 2
    sgs["ref_date"] = sgs["ref_date"].dt.strftime("%Y-%m-%d")
    start, end = date.fromisoformat(sgs["ref_date"].iloc[0]), date.fromisoformat(sgs["ref_date"].iloc[-1])

    try:
        ref = fetch_olinda(start, end)
    except (VerificationError, requests.RequestException, KeyError, ValueError) as exc:
        print(f"NÃO FOI POSSÍVEL VERIFICAR: {type(exc).__name__}: {exc}")
        return 2

    res = compare_series(sgs, ref)
    print(f"Período comparado: {start} a {end}")
    print(f"SGS: {res['n_sgs']} datas | Olinda: {res['n_ref']} datas | em comum: {res['n_common']}")
    print(f"Só no SGS: {len(res['only_in_sgs'])} {res['only_in_sgs'][:10]}")
    print(f"Só na Olinda: {len(res['only_in_ref'])} {res['only_in_ref'][:10]}")
    print(f"Divergências de valor ({DECIMALS} casas): {res['n_value_mismatch']}; "
          f"maior diferença absoluta: {res['max_abs_diff']:.6f}")
    for m in res["mismatches"][:20]:
        print(f"  {m['ref_date']}: SGS={m['sgs']} Olinda={m['ref']}")
    print("RESULTADO:", "PASSOU" if res["passed"] else "DIVERGÊNCIAS ENCONTRADAS")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
