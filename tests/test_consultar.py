"""Garante que cada consulta do script roda sem erro de SQL contra uma base real."""

from datetime import date

import pytest

from scripts import consultar
from src import pipeline
from tests.helpers import BusinessDaySession, no_sleep

TODAY = date(2026, 11, 1)


@pytest.fixture
def base(tmp_path):
    caminho = tmp_path / "indicadores.db"
    res = pipeline.run(
        ["ptax"], today=TODAY, db_path=caminho, session=BusinessDaySession(), sleep=no_sleep
    )
    assert res[0].status == "success"
    return str(caminho)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["resumo"],
        ["ultimos"],
        ["lacunas"],
        ["duplicadas"],
        ["execucoes"],
        ["data", "2026-10-30"],
        ["sql", "SELECT COUNT(*) AS total FROM observations"],
    ],
)
def test_todos_os_comandos_rodam(base, argv, capsys):
    assert consultar.main(argv + ["--db", base]) == 0
    assert "Erro" not in capsys.readouterr().out


def test_resumo_traz_a_contagem_e_o_periodo(base, capsys):
    consultar.main(["resumo", "--db", base])
    saida = capsys.readouterr().out
    assert "ptax" in saida and "2026-10-30" in saida and "2021-11-01" in saida


def test_lacunas_mostra_fim_de_semana_e_nao_erro(base, capsys):
    consultar.main(["lacunas", "--db", base])
    saida = capsys.readouterr().out
    assert "dias_sem_dado" in saida and "3" in saida  # sexta -> segunda


def test_duplicadas_vem_vazio(base, capsys):
    consultar.main(["duplicadas", "--db", base])
    assert "nenhum resultado" in capsys.readouterr().out


def test_data_mostra_as_duas_tabelas(base, capsys):
    consultar.main(["data", "2026-10-30", "--db", base])
    saida = capsys.readouterr().out
    assert "2026-10-30" in saida and "30/10/2026" in saida


def test_data_invalida_avisa_sem_quebrar(base, capsys):
    assert consultar.main(["data", "30/10/2026", "--db", base]) == 2
    assert "AAAA-MM-DD" in capsys.readouterr().out


def test_sql_recusa_escrita(base, capsys):
    assert consultar.main(["sql", "DELETE FROM observations", "--db", base]) == 2
    assert "leitura" in capsys.readouterr().out


def test_sql_invalido_avisa_em_vez_de_quebrar(base, capsys):
    assert consultar.main(["sql", "SELECT * FROM tabela_que_nao_existe", "--db", base]) == 1
    assert "Erro na consulta" in capsys.readouterr().out


def test_banco_inexistente_orienta_o_usuario(tmp_path, capsys):
    assert consultar.main(["resumo", "--db", str(tmp_path / "nao_existe.db")]) == 2
    assert "src.pipeline" in capsys.readouterr().out
