from datetime import date, timedelta

import pandas as pd
import pytest
import requests

from src.config import MAX_ATTEMPTS, SERIES
from src.extract import ExtractionError, date_chunks, extract_series, fetch_chunk
from tests.helpers import (
    SGS_ERRO_SEM_DADOS,
    SGS_ERRO_UM_DIA,
    BusinessDaySession,
    FakeResponse,
    ScriptedSession,
    no_sleep,
)


def _days(start, end):
    return {start + timedelta(days=i) for i in range((end - start).days + 1)}


WINDOWS = [
    (date(2021, 11, 1), date(2026, 11, 1)),  # janela real que falhou em 01/11/2026
    (date(2021, 10, 30), date(2026, 10, 30)),
    (date(2024, 2, 29), date(2026, 10, 30)),  # início em 29/02
    (date(2019, 2, 28), date(2024, 2, 29)),  # fim em 29/02
    (date(2026, 1, 1), date(2026, 3, 15)),  # menor que um bloco
    (date(2026, 1, 1), date(2026, 1, 2)),  # menor janela aceita: dois dias
]


@pytest.mark.parametrize("start,end", WINDOWS)
def test_chunks_cobrem_a_janela_sem_sobreposicao_nem_lacuna(start, end):
    """A correção não pode criar lacuna, sobreposição nem excluir data pedida."""
    chunks = date_chunks(start, end)
    covered = set()
    for cs, ce in chunks:
        assert cs <= ce
        days = _days(cs, ce)
        assert covered.isdisjoint(days), f"blocos sobrepostos em {cs}..{ce}"
        covered |= days
    assert covered == _days(start, end), "cobertura diferente da janela pedida"
    assert chunks[0][0] == start and chunks[-1][1] == end


@pytest.mark.parametrize("start,end", WINDOWS)
def test_nenhum_bloco_tem_um_unico_dia(start, end):
    """Regressão: o SGS recusa dataInicial == dataFinal com HTTP 400."""
    assert all(cs < ce for cs, ce in date_chunks(start, end))


@pytest.mark.parametrize("offset", range(0, 400, 7))
def test_nenhum_bloco_de_um_dia_em_qualquer_data_final(offset):
    """Varre fins de janela ao longo de mais de um ano, não só a data que falhou."""
    end = date(2026, 1, 1) + timedelta(days=offset)
    start = (pd.Timestamp(end) - pd.DateOffset(years=5)).date()
    chunks = date_chunks(start, end)
    assert all(cs < ce for cs, ce in chunks)
    assert chunks[-1][1] == end


def test_sobra_de_um_dia_e_absorvida_pelo_bloco_anterior():
    chunks = date_chunks(date(2021, 11, 1), date(2026, 11, 1))
    assert len(chunks) == 5  # seriam 6, com o último valendo só 01/11/2026
    assert chunks[-1] == (date(2025, 11, 1), date(2026, 11, 1))


def test_chunks_rejeita_intervalo_invertido():
    with pytest.raises(ValueError, match="posterior"):
        date_chunks(date(2026, 2, 1), date(2026, 1, 1))


def test_janela_de_um_unico_dia_e_rejeitada_com_mensagem_clara():
    """Sem bloco anterior para absorver a sobra, o pedido é impossível: falha explícita."""
    with pytest.raises(ValueError, match="um único dia"):
        date_chunks(date(2026, 1, 1), date(2026, 1, 1))


def test_extract_series_usa_formato_de_data_do_sgs_e_timeout():
    session = BusinessDaySession()
    rows = extract_series(SERIES["ptax"], date(2026, 1, 1), date(2026, 1, 31), session=session)
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["params"] == {"formato": "json", "dataInicial": "01/01/2026", "dataFinal": "31/01/2026"}
    assert call["timeout"] is not None
    assert call["url"].endswith("bcdata.sgs.1/dados")
    assert rows and set(rows[0]) == {"data", "valor"}


def test_extract_series_faz_um_pedido_por_bloco_anual():
    session = BusinessDaySession()
    extract_series(SERIES["ptax"], date(2021, 10, 30), date(2026, 10, 30), session=session)
    assert len(session.calls) == 5  # a sobra de 1 dia entra no último bloco


def test_mensagem_de_erro_inclui_o_corpo_da_resposta():
    """Sem o corpo, o log dizia só 'HTTP 400' e não dava para diagnosticar."""
    session = ScriptedSession([FakeResponse(400, SGS_ERRO_UM_DIA)])
    with pytest.raises(ExtractionError, match="DataFinal deve ser maior que dataInicial"):
        fetch_chunk(session, 1, date(2026, 1, 1), date(2026, 1, 2), sleep=no_sleep)


def test_mensagem_de_erro_inclui_o_corpo_tambem_no_404_e_no_5xx():
    s404 = ScriptedSession([FakeResponse(404, SGS_ERRO_SEM_DADOS)])
    with pytest.raises(ExtractionError, match="Value\\(s\\) not found"):
        fetch_chunk(s404, 1, date(2026, 1, 1), date(2026, 1, 2), sleep=no_sleep)

    s503 = ScriptedSession([FakeResponse(503, {"erro": "serviço indisponível"})])
    with pytest.raises(ExtractionError, match="serviço indisponível"):
        fetch_chunk(s503, 1, date(2026, 1, 1), date(2026, 1, 2), sleep=no_sleep)


def test_retenta_em_timeout_e_depois_tem_sucesso():
    ok = FakeResponse(200, [{"data": "02/01/2026", "valor": "5.1"}])
    session = ScriptedSession([requests.Timeout("lento"), requests.ConnectionError("caiu"), ok])
    rows = fetch_chunk(session, 1, date(2026, 1, 1), date(2026, 1, 31), sleep=no_sleep)
    assert rows == [{"data": "02/01/2026", "valor": "5.1"}]
    assert session.calls == 3


def test_falha_apos_esgotar_tentativas():
    session = ScriptedSession([requests.Timeout("lento")])
    with pytest.raises(ExtractionError, match="tentativas"):
        fetch_chunk(session, 1, date(2026, 1, 1), date(2026, 1, 31), sleep=no_sleep)
    assert session.calls == MAX_ATTEMPTS


def test_http_5xx_e_retentado_mas_4xx_falha_direto():
    s5 = ScriptedSession([FakeResponse(503, [])])
    with pytest.raises(ExtractionError):
        fetch_chunk(s5, 1, date(2026, 1, 1), date(2026, 1, 31), sleep=no_sleep)
    assert s5.calls == MAX_ATTEMPTS

    s4 = ScriptedSession([FakeResponse(406, [])])
    with pytest.raises(ExtractionError, match="406"):
        fetch_chunk(s4, 1, date(2026, 1, 1), date(2026, 1, 31), sleep=no_sleep)
    assert s4.calls == 1


@pytest.mark.parametrize(
    "resp",
    [
        FakeResponse(200, invalid_json=True),
        FakeResponse(200, {"error": "algo deu errado"}),
        FakeResponse(200, [{"data": "02/01/2026"}]),  # sem 'valor'
    ],
)
def test_resposta_malformada_vira_erro_explicito(resp):
    with pytest.raises(ExtractionError):
        fetch_chunk(ScriptedSession([resp]), 1, date(2026, 1, 1), date(2026, 1, 31), sleep=no_sleep)
