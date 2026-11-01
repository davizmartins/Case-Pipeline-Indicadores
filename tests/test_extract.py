from datetime import date, timedelta

import pytest
import requests

from src.config import MAX_ATTEMPTS, SERIES
from src.extract import ExtractionError, date_chunks, extract_series, fetch_chunk
from tests.helpers import BusinessDaySession, FakeResponse, ScriptedSession, no_sleep


def _days(start, end):
    return {start + timedelta(days=i) for i in range((end - start).days + 1)}


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2021, 10, 30), date(2026, 10, 30)),
        (date(2024, 2, 29), date(2026, 10, 30)),  # início em 29/02
        (date(2026, 1, 1), date(2026, 1, 1)),  # janela de um único dia
        (date(2026, 1, 1), date(2026, 3, 15)),  # menor que um bloco
    ],
)
def test_chunks_cobrem_a_janela_sem_sobreposicao_nem_lacuna(start, end):
    chunks = date_chunks(start, end)
    covered = set()
    for cs, ce in chunks:
        assert cs <= ce
        days = _days(cs, ce)
        assert covered.isdisjoint(days)
        covered |= days
    assert covered == _days(start, end)
    assert chunks[0][0] == start and chunks[-1][1] == end


def test_chunks_rejeita_intervalo_invertido():
    with pytest.raises(ValueError):
        date_chunks(date(2026, 2, 1), date(2026, 1, 1))


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
    assert len(session.calls) == 6  # 5 anos cheios + 1 dia de sobra no fim


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
