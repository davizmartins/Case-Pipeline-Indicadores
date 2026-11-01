"""Consultas prontas ao banco, para inspeção manual. NÃO faz parte do pipeline.

Abre a base somente para leitura: nenhum comando daqui altera dados.

Uso:
    python -m scripts.consultar                  # resumo de todos os indicadores
    python -m scripts.consultar ultimos          # últimas observações
    python -m scripts.consultar lacunas          # maiores intervalos entre datas
    python -m scripts.consultar duplicadas       # datas repetidas (deve vir vazio)
    python -m scripts.consultar execucoes        # histórico do pipeline
    python -m scripts.consultar data 2026-10-30  # uma data nas duas tabelas
    python -m scripts.consultar sql "SELECT ..." # consulta livre (só leitura)

Opções: --indicador ptax   --limite 10   --db caminho/para/arquivo.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from src import db
from src.config import SERIES, get_db_path

LARGURA_MAX = 60  # corta textos longos (mensagens de execução) para a tabela não estourar

SQL_RESUMO = """
SELECT indicator      AS indicador,
       COUNT(*)       AS observacoes,
       MIN(ref_date)  AS primeira,
       MAX(ref_date)  AS ultima,
       MIN(value)     AS menor_valor,
       MAX(value)     AS maior_valor
FROM observations
GROUP BY indicator
ORDER BY indicator
"""

SQL_ULTIMOS = """
SELECT ref_date AS data, value AS valor, fetched_at AS coletado_em
FROM observations
WHERE indicator = ?
ORDER BY ref_date DESC
LIMIT ?
"""

# julianday() converte 'AAAA-MM-DD' em número de dias, permitindo a subtração.
SQL_LACUNAS = """
SELECT anterior                                  AS de,
       ref_date                                  AS ate,
       CAST(julianday(ref_date) - julianday(anterior) AS INTEGER) AS dias_sem_dado
FROM (
    SELECT ref_date, LAG(ref_date) OVER (ORDER BY ref_date) AS anterior
    FROM observations
    WHERE indicator = ?
)
WHERE anterior IS NOT NULL
ORDER BY dias_sem_dado DESC, ate
LIMIT ?
"""

SQL_DUPLICADAS = """
SELECT ref_date AS data, COUNT(*) AS vezes
FROM observations
WHERE indicator = ?
GROUP BY ref_date
HAVING COUNT(*) > 1
ORDER BY ref_date
"""

SQL_EXECUCOES = """
SELECT run_id AS execucao, indicator AS indicador, status, rows_loaded AS carregadas,
       last_ref_date AS ultima_data, finished_at AS terminou_em, message AS mensagem
FROM pipeline_runs
ORDER BY run_id DESC
LIMIT ?
"""


def _texto(valor) -> str:
    return "-" if valor is None else str(valor)


def imprimir(titulo: str, colunas: list[str], linhas: list[tuple]) -> None:
    """Imprime uma tabela alinhada, só com caracteres ASCII na estrutura."""
    print(f"\n{titulo}")
    if not linhas:
        print("  (nenhum resultado)")
        return
    celulas = [[_texto(v)[:LARGURA_MAX] for v in linha] for linha in linhas]
    larguras = [
        max(len(col), max(len(linha[i]) for linha in celulas))
        for i, col in enumerate(colunas)
    ]
    cabecalho = "  ".join(col.ljust(larguras[i]) for i, col in enumerate(colunas))
    print("  " + cabecalho)
    print("  " + "  ".join("-" * w for w in larguras))
    for linha in celulas:
        print("  " + "  ".join(v.ljust(larguras[i]) for i, v in enumerate(linha)))
    print(f"  ({len(linhas)} linha{'s' if len(linhas) != 1 else ''})")


def executar(conn: sqlite3.Connection, titulo: str, sql: str, params: tuple = ()) -> None:
    cur = conn.execute(sql, params)
    colunas = [d[0] for d in cur.description]
    imprimir(titulo, colunas, cur.fetchall())


def mostrar_data(conn: sqlite3.Connection, indicador: str, iso: str) -> int:
    """Mostra uma data nas duas tabelas, para comparar o recebido com o tratado."""
    try:
        ano, mes, dia = iso.split("-")
        if len(ano) != 4 or len(mes) != 2 or len(dia) != 2:
            raise ValueError
    except ValueError:
        print(f"Data invalida: {iso!r}. Use o formato AAAA-MM-DD, por exemplo 2026-10-30.")
        return 2
    executar(
        conn,
        f"Tratado (observations) em {iso}",
        "SELECT ref_date AS data, value AS valor, fetched_at AS coletado_em "
        "FROM observations WHERE indicator = ? AND ref_date = ?",
        (indicador, iso),
    )
    executar(
        conn,
        f"Recebido da fonte (raw_observations) em {dia}/{mes}/{ano}",
        "SELECT raw_date AS data, raw_value AS valor, source AS fonte "
        "FROM raw_observations WHERE indicator = ? AND raw_date = ?",
        (indicador, f"{dia}/{mes}/{ano}"),
    )
    print("\n  O valor tratado e numero; o recebido e texto, exatamente como veio da fonte.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Consultas de inspecao ao banco (somente leitura).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "comando",
        nargs="?",
        default="resumo",
        choices=["resumo", "ultimos", "lacunas", "duplicadas", "execucoes", "data", "sql"],
    )
    parser.add_argument("argumento", nargs="?", help="a data (AAAA-MM-DD) ou a consulta SQL")
    parser.add_argument("--indicador", default="ptax", choices=list(SERIES))
    parser.add_argument("--limite", type=int, default=10)
    parser.add_argument("--db", help="caminho do arquivo .db (padrao: data/indicadores.db)")
    args = parser.parse_args(argv)

    caminho = args.db or get_db_path()
    try:
        conn = db.connect_readonly(caminho)
    except sqlite3.Error:
        print(f"Nao foi possivel abrir o banco em {caminho}.")
        print("Rode 'python -m src.pipeline' para cria-lo.")
        return 2

    try:
        if args.comando == "resumo":
            executar(conn, "Resumo por indicador", SQL_RESUMO)
            executar(conn, "Ultimas execucoes do pipeline", SQL_EXECUCOES, (5,))
        elif args.comando == "ultimos":
            executar(
                conn,
                f"Ultimas {args.limite} observacoes de {args.indicador}",
                SQL_ULTIMOS,
                (args.indicador, args.limite),
            )
        elif args.comando == "lacunas":
            executar(
                conn,
                f"Maiores intervalos entre datas de {args.indicador}",
                SQL_LACUNAS,
                (args.indicador, args.limite),
            )
            print("\n  Fim de semana da 3 dias; feriado emendado, mais. Nao sao erros.")
        elif args.comando == "duplicadas":
            executar(
                conn,
                f"Datas repetidas em {args.indicador} (esperado: nenhuma)",
                SQL_DUPLICADAS,
                (args.indicador,),
            )
        elif args.comando == "execucoes":
            executar(conn, "Historico de execucoes", SQL_EXECUCOES, (args.limite,))
        elif args.comando == "data":
            if not args.argumento:
                print("Informe a data: python -m scripts.consultar data 2026-10-30")
                return 2
            return mostrar_data(conn, args.indicador, args.argumento)
        elif args.comando == "sql":
            if not args.argumento:
                print('Informe a consulta: python -m scripts.consultar sql "SELECT ..."')
                return 2
            if not args.argumento.lstrip().upper().startswith(("SELECT", "WITH", "PRAGMA")):
                print("Apenas consultas de leitura (SELECT, WITH, PRAGMA) sao aceitas aqui.")
                return 2
            try:
                executar(conn, "Consulta livre", args.argumento)
            except sqlite3.Error as exc:
                print(f"Erro na consulta: {exc}")
                return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
