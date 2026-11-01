"""Valores reais do IPCA, conferidos contra fonte oficial em 01/11/2026.

Não é dado gerado: são as respostas da API SGS para as séries 433 e 13522, usadas como
dados CONTROLADOS nos testes (nenhum teste acessa a rede).

Conferências feitas na coleta:
- 433 em 01/12/2025 = 0,33 — mesmo valor que o fascículo IPCA/INPC do IBGE publica
  para dezembro de 2025;
- 13522 em 01/12/2025 = 4,26 — mesmo valor que o IBGE publica para o fechamento de 2025.
  Isso confirma que o carimbo de data é o MÊS DE REFERÊNCIA, e não o de publicação:
  sob a outra hipótese, esse 4,26 teria de aparecer em 01/01/2026, onde há 4,44.
"""

# Série 433 — variação mensal (%), como texto, no formato recebido da API.
MENSAL_433 = [
    ("01/01/2025", "0.16"), ("01/02/2025", "1.31"), ("01/03/2025", "0.56"),
    ("01/04/2025", "0.43"), ("01/05/2025", "0.26"), ("01/06/2025", "0.24"),
    ("01/07/2025", "0.26"), ("01/08/2025", "-0.11"), ("01/09/2025", "0.48"),
    ("01/10/2025", "0.09"), ("01/11/2025", "0.18"), ("01/12/2025", "0.33"),
    ("01/01/2026", "0.33"), ("01/02/2026", "0.70"), ("01/03/2026", "0.88"),
    ("01/04/2026", "0.67"), ("01/05/2026", "0.58"), ("01/06/2026", "0.16"),
    ("01/07/2026", "0.07"), ("01/08/2026", "-0.32"), ("01/09/2026", "0.82"),
]

# Série 13522 — acumulado em 12 meses (%), como texto.
ACUM12_13522 = [
    ("01/11/2025", "4.46"), ("01/12/2025", "4.26"), ("01/01/2026", "4.44"),
    ("01/02/2026", "3.81"), ("01/03/2026", "4.14"), ("01/04/2026", "4.39"),
    ("01/05/2026", "4.72"), ("01/06/2026", "4.64"), ("01/07/2026", "4.44"),
    ("01/08/2026", "4.22"), ("01/09/2026", "4.58"),
]

# Valores do fascículo IPCA/INPC do IBGE para dezembro de 2025.
IBGE_DEZ_2025_MENSAL = 0.33
IBGE_2025_ACUMULADO = 4.26


def iso(br: str) -> str:
    """dd/MM/aaaa -> AAAA-MM-DD."""
    d, m, a = br.split("/")
    return f"{a}-{m}-{d}"
