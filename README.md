# Pipeline de Indicadores de Mercado

ETL em Python que extrai séries públicas de mercado, trata e armazena em SQLite e alimenta um
dashboard em Streamlit. Case técnico — Vêneto Family Office.

> **Estado atual: Etapa 1 de 9 — somente o dólar PTAX (venda) funciona de ponta a ponta.**
> CDI, IPCA e Ibovespa serão adicionados nas próximas etapas. Este README cresce junto com o projeto.

## Público e objetivo

O dashboard é para a equipe de Inteligência Comercial e os assessores, que hoje acompanham os
indicadores manualmente e precisam de números claros para embasar conversas com clientes.

## Como executar do zero (Windows 11, Python 3.13)

No PowerShell, na pasta do projeto:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1          # se a política de execução bloquear, use .venv\Scripts\python.exe no lugar de python
pip install -r requirements.txt

python -m src.pipeline              # extrai, trata e carrega (cria data/indicadores.db)
streamlit run app.py                # abre o dashboard
python -m pytest                    # testes (não dependem de rede)
python -m scripts.verify_ptax       # conferência da PTAX contra a API Olinda (ver "Verificações")
```

Para inspecionar a base sem escrever SQL na mão:

```powershell
python -m scripts.consultar                  # resumo e últimas execuções
python -m scripts.consultar ultimos          # últimas observações
python -m scripts.consultar lacunas          # maiores intervalos entre datas
python -m scripts.consultar duplicadas       # datas repetidas (deve vir vazio)
python -m scripts.consultar data 2026-10-30  # uma data, nas tabelas bruta e tratada
python -m scripts.consultar sql "SELECT COUNT(*) FROM observations"
```

## Arquitetura

```
fontes (SGS/BCB)  ->  src/extract.py  ->  src/transform.py  ->  src/load.py  ->  SQLite  ->  app.py
                      blocos anuais,      limpeza e validação   UPSERT em        (data/)     lê só a base,
                      timeout, retry                            transação                    nunca a fonte
```

| Arquivo | Papel |
|---|---|
| `src/config.py` | Séries, janela, timeouts e limites |
| `src/extract.py` | Consulta o SGS em blocos anuais, com timeout e retentativas |
| `src/transform.py` | Padronização, descarte de inválidos, duplicidades e checagem de lacunas |
| `src/db.py` / `src/load.py` | Esquema SQLite e carga idempotente |
| `src/pipeline.py` | Orquestra as etapas e registra cada execução |
| `app.py` | Dashboard (lê somente a base) |
| `scripts/verify_ptax.py` | Conferência independente da PTAX (fora do pipeline) |
| `scripts/consultar.py` | Consultas de inspeção à base, somente leitura (fora do pipeline) |

## Séries

| Indicador | Fonte | Código | Unidade | Frequência | Situação |
|---|---|---|---|---|---|
| Dólar PTAX (venda) | SGS/BCB | 1 | R$/US$ | diária (dias úteis) | implementado |
| CDI | SGS/BCB | a definir | % ao dia | diária | pendente |
| IPCA | SGS/BCB | a definir | % ao mês | mensal | pendente |
| Ibovespa | yfinance `^BVSP` | — | pontos | diária (pregões) | pendente |

**SGS 1.** O catálogo de dados abertos do BCB descreve a série como "Taxa de câmbio – Livre – Dólar
americano (venda) – diário", unidade R$/US$, origem na transação PTAX800, e informa que a partir de
março de 1992 a cotação de fechamento passou a ser denominada PTAX. Não é uma afirmação literal de
"PTAX venda"; por isso existe a conferência com a Olinda (abaixo).

### Restrições da API SGS (verificadas em 01/11/2026)

Consultas feitas direto ao serviço, fora do pipeline, para entender respostas de erro:

| Pedido | Resposta | Significado |
|---|---|---|
| `dataInicial == dataFinal` | `400` · `DataFinal deve ser maior que dataInicial.` | intervalo de um dia é recusado **mesmo havendo cotação** nesse dia |
| intervalo válido, sem cotações | `404` · `Value(s) not found` | ausência de dados, não erro de pedido |
| data inexistente (`99/99/2026`) | `400` · `dataInicial invalida...` | pedido malformado |
| intervalo com dados terminando em fim de semana | `200` + cotações | funciona normalmente |

Duas consequências para o código:

1. **Um único dia é inatingível por esta API.** Para obter só uma data é preciso pedir um
   intervalo de ao menos dois dias e filtrar. O fatiamento garante que nenhum bloco tenha um dia
   só, absorvendo a sobra final no bloco anterior.
2. **"Sem dados" é distinguível de "pedido errado"** (404 com mensagem própria vs. 400). Isso
   permitirá, na atualização incremental, tolerar intervalos vazios sem mascarar erros reais.
   Hoje o 404 ainda é falha explícita, porque com o fatiamento corrigido nenhum bloco da janela
   de 5 anos pode vir vazio.

## Decisões de tratamento (Etapa 1)

- **Janela:** últimos 5 anos corridos, `[hoje - 5 anos, hoje]`, inclusive nas duas pontas, com "hoje" no fuso de Brasília.
- **Consultas em blocos anuais:** o SGS limita consultas diárias a 10 anos e exige datas de início e fim. Se a sobra final da janela for de um único dia, ela entra no bloco anterior — o SGS recusa `dataInicial == dataFinal`. Uma janela inteira de um dia só é rejeitada com erro explícito, pois não há bloco anterior que a absorva.
- **Erros HTTP carregam o corpo da resposta** na mensagem e no log: é lá que o SGS explica a causa.
- **Falha é falha:** sem resposta válida da fonte, nada é carregado, a falha é registrada em `pipeline_runs` e o processo sai com código 1. Nunca há dados fictícios.
- **Valores inválidos** (vazios, não numéricos, infinitos, e `<= 0` na PTAX) são descartados e contados — **nunca viram zero**.
- **Duplicidade:** chave `(indicador, data)`; havendo repetição, vale a última ocorrência e datas com valores conflitantes são contadas.
- **Fim de semana e feriado não são erro** e não são preenchidos. Lacuna só é erro quando passa de 10 dias corridos entre observações.
- **Data de referência x coleta:** `ref_date` é a data do dado; `fetched_at` (UTC) é quando foi coletado.
- **Bruto + tratado:** `raw_observations` guarda o recebido (auditoria); custo: duplica o armazenamento, algo desprezível aqui.
- **Dado desatualizado:** o dashboard avisa quando a última observação tem mais de 7 dias.

## Verificações

- **Testes automatizados (`pytest`):** cobrem blocos de datas, retentativas, resposta malformada, limpeza, duplicidade, lacunas, carga idempotente e atualização por revisão, falha sem corromper a base e o dashboard. Usam dados controlados; **não tocam a rede**. O dublê da fonte reproduz as recusas reais do SGS (400 em intervalo de um dia, 404 em intervalo vazio), para não ser mais permissivo que o serviço.
- **Extração real do SGS:** executada em 01/11/2026. Trouxe **1.256 observações** de 01/11/2021 a 30/10/2026. Nessa execução o fatiamento gerava um bloco final de um único dia e o SGS o recusava com HTTP 400, derrubando a carga inteira; esse defeito está corrigido e **a reexecução após a correção ainda precisa ser confirmada**.
- **`scripts/verify_ptax.py`:** compara a PTAX armazenada com a API Olinda do BCB em todo o período (conjunto de datas idêntico e valores iguais em 4 casas). A parte de rede desse script também **ainda não foi executada e o endereço da Olinda não foi conferido na documentação oficial** — confirme antes de confiar no resultado.

## Limitações atuais

- Só a PTAX está implementada.
- A carga não remove observações que a fonte deixe de publicar (tratamento de revisões históricas fica para o bônus incremental).
- O dashboard é uma tela mínima de validação do fluxo.
