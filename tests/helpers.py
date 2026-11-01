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


def cdi_value(_d: date) -> float:
    """Taxa diária constante, no formato de 6 casas em que a série 12 é publicada."""
    return 0.050788


def fixed(value: float):
    return lambda _d: value


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

    def __init__(self, value_fn=default_value, skip=lambda d: False, ultimo: date | None = None):
        self.value_fn = value_fn
        self.skip = skip
        self.ultimo = ultimo  # simula defasagem de publicação na ponta da série
        self.calls: list[dict] = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        start = datetime.strptime(params["dataInicial"], "%d/%m/%Y").date()
        end = datetime.strptime(params["dataFinal"], "%d/%m/%Y").date()
        if start >= end:  # o SGS exige dataFinal > dataInicial
            return FakeResponse(400, SGS_ERRO_UM_DIA)
        rows, d = [], start
        while d <= end:
            if self.ultimo and d > self.ultimo:
                break
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


class MonthlySession:
    """Simula uma série mensal do SGS: um registro por mês, carimbado no dia 01.

    Reproduz as mesmas recusas do serviço real que o dublê diário reproduz.
    `ultimo` permite simular a defasagem de divulgação (o mês corrente ainda não saiu).
    """

    def __init__(self, value_fn=lambda y, m: 0.50, ultimo: tuple[int, int] | None = None):
        self.value_fn = value_fn
        self.ultimo = ultimo
        self.calls: list[dict] = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        start = datetime.strptime(params["dataInicial"], "%d/%m/%Y").date()
        end = datetime.strptime(params["dataFinal"], "%d/%m/%Y").date()
        if start >= end:
            return FakeResponse(400, SGS_ERRO_UM_DIA)
        y, m = (start.year, start.month) if start.day == 1 else _prox_mes(start.year, start.month)
        rows = []
        while date(y, m, 1) <= end:
            if self.ultimo and (y, m) > self.ultimo:
                break
            rows.append({"data": f"01/{m:02d}/{y}", "valor": f"{self.value_fn(y, m):.2f}"})
            y, m = _prox_mes(y, m)
        if not rows:
            return FakeResponse(404, SGS_ERRO_SEM_DADOS)
        return FakeResponse(200, rows)


def _prox_mes(y: int, m: int) -> tuple[int, int]:
    return (y + 1, 1) if m == 12 else (y, m + 1)


class RouterSession:
    """Encaminha cada código de série do SGS ao dublê correspondente."""

    def __init__(self, por_codigo: dict[int, object]):
        self.por_codigo = por_codigo

    def get(self, url, params, timeout):
        for code, sessao in self.por_codigo.items():
            if f"sgs.{code}/" in url:
                return sessao.get(url, params, timeout)
        raise AssertionError(f"nenhum dublê configurado para {url}")


def no_sleep(_seconds: float) -> None:
    return None
