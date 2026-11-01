"""Dublês de teste que simulam a API SGS sem acessar a rede."""

from __future__ import annotations

from datetime import date, datetime, timedelta


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, invalid_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._invalid_json = invalid_json
        self.text = str(payload)

    def json(self):
        if self._invalid_json:
            raise ValueError("JSON inválido")
        return self._payload


def default_value(d: date) -> float:
    return round(5.0 + (d.toordinal() % 100) / 1000, 4)


# Respostas de erro reais do SGS, coletadas do serviço em 01/11/2026.
SGS_ERRO_UM_DIA = {"erro": "DataFinal deve ser maior que dataInicial."}
SGS_ERRO_SEM_DADOS = {
    "erro": {
        "statusCode": 404,
        "detail": "br.gov.bcb.pec.sgs.comum.excecoes.SGSNegocioException: Value(s) not found",
    }
}


class BusinessDaySession:
    """Simula o SGS: devolve os dias úteis do intervalo pedido (dd/MM/aaaa), como texto.

    Reproduz duas recusas do serviço real, verificadas em 01/11/2026. Sem elas o dublê é
    mais permissivo que a fonte e deixa passar erros que só aparecem em produção — foi
    exatamente o que aconteceu com o bloco de um único dia.
    """

    def __init__(self, value_fn=default_value, skip=lambda d: False):
        self.value_fn = value_fn
        self.skip = skip
        self.calls: list[dict] = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        start = datetime.strptime(params["dataInicial"], "%d/%m/%Y").date()
        end = datetime.strptime(params["dataFinal"], "%d/%m/%Y").date()
        if start >= end:  # o SGS exige dataFinal > dataInicial
            return FakeResponse(400, SGS_ERRO_UM_DIA)
        rows, d = [], start
        while d <= end:
            if d.weekday() < 5 and not self.skip(d):
                rows.append({"data": d.strftime("%d/%m/%Y"), "valor": str(self.value_fn(d))})
            d += timedelta(days=1)
        if not rows:  # intervalo válido, porém sem observações
            return FakeResponse(404, SGS_ERRO_SEM_DADOS)
        return FakeResponse(200, rows)


class ScriptedSession:
    """Devolve respostas pré-definidas em ordem; uma exceção na lista é levantada."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params, timeout):
        self.calls += 1
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def no_sleep(_seconds: float) -> None:
    return None
