# Pipeline de Indicadores de Mercado

ETL em Python que extrai séries públicas de mercado, trata e armazena em SQLite e alimenta um
dashboard em Streamlit. Case técnico — Vêneto Family Office.

> **Estado atual: dólar PTAX e a série SGS 12 funcionam de ponta a ponta.**
> IPCA e Ibovespa ainda não entraram.

## Público e objetivo

O dashboard é para a equipe de Inteligência Comercial e os assessores, que hoje acompanham os
indicadores manualmente e precisam de números claros para embasar conversas com clientes.

## Como executar do zero (Windows 11, Python 3.13)

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1          # se a política de execução bloquear, use .venv\Scripts\python.exe
pip install -r requirements.txt

python -m src.pipeline              # extrai, trata e carrega (cria data/indicadores.db)
streamlit run app.py                # abre o dashboard
python -m pytest                    # testes (não dependem de rede)
```

Conferências independentes, fora do pipeline:

```powershell
python -m scripts.verify_cdi        # anualização da série 12 vs. série 4389 do SGS
python -m scripts.verify_ptax       # PTAX vs. API Olinda (ver "Verificações")
```

Inspeção da base, somente leitura:

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
                      blocos anuais,      limpeza, 3 categorias  UPSERT em       (data/)     lê só a base,
                      timeout, retry      e validação            transação                   nunca a fonte
                                               |
                                          src/metrics.py (cálculos puros)
```

| Arquivo | Papel |
|---|---|
| `src/config.py` | Séries, janelas, margens, faixas de alerta, timeouts |
| `src/extract.py` | Consulta o SGS em blocos anuais, com timeout e retentativas |
| `src/transform.py` | Padronização, três categorias de qualidade, checagem de cobertura |
| `src/metrics.py` | Cálculos financeiros, funções puras (capitalização, 12 meses, anualização, base 100) |
| `src/db.py` / `src/load.py` | Esquema SQLite, migração e carga idempotente |
| `src/pipeline.py` | Orquestra as etapas e registra cada execução |
| `app.py` | Dashboard (lê somente a base) |
| `scripts/verify_ptax.py` · `scripts/verify_cdi.py` | Conferências independentes |
| `scripts/consultar.py` | Inspeção da base, somente leitura |

## Séries

| Indicador | Fonte | Código | Unidade | Frequência | Margem | Situação |
|---|---|---|---|---|---|---|
| Dólar PTAX (venda) | SGS/BCB | 1 | R$/US$ | diária (dias úteis) | — | implementado |
| Série SGS 12 | SGS/BCB | 12 | % ao dia | diária (dias úteis) | 12 meses | implementado, **identificação pendente** |
| IPCA | SGS/BCB | a definir | % ao mês | mensal | 12 meses | pendente |
| Ibovespa | yfinance `^BVSP` | — | pontos | diária (pregões) | — | pendente |

### Série 1 — o que foi e o que não foi confirmado

O catálogo de dados abertos do BCB descreve a série como "Taxa de câmbio – Livre – Dólar
americano (venda) – diário", unidade R$/US$, origem na transação PTAX800, e informa que a partir
de março de 1992 a cotação de fechamento passou a ser denominada PTAX.

Conferência numérica adicional: em 30/10/2026 a página de cotações históricas do BCB mostra
5,4206 na compra e **5,4212 na venda** — o mesmo valor que a série 1 devolveu. Isso confere **um
valor em uma data** por dois caminhos do BCB. **Não** valida a API Olinda nem resolve a
identidade metodológica da série.

### Série 12 — identificação NÃO confirmada

**Os metadados oficiais do SGS para esta série não puderam ser consultados.** O portal do SGS
(`www3.bcb.gov.br/sgspub`) responde "Requisição inválida", e buscas restritas ao portal de dados
abertos do BCB não localizaram entrada para o CDI — o que não prova que ela não exista.
Portanto **nome, unidade e periodicidade seguem não confirmados por fonte oficial**, e a
interface identifica a série como *"Série SGS 12 — identificação como CDI pendente"*.

O que **está** confirmado, e sobre o que: a B3 documenta que a Taxa DI é apurada a cada dia
útil e que "as taxas são expressas sob forma anual", "ao ano de 252 dias úteis". Isso ancora a
base 252 usada na anualização **para o índice DI**. Que a série 12 do SGS carregue esse índice é
exatamente o que falta confirmar.

Observações numéricas registradas, que **não identificam a série**: os valores recebidos (ordem
de 0,05% a.d.) são compatíveis com uma taxa diária convertível em base 252; em 17/09/2026 a taxa
passou de 0,051660 para 0,050788, o que equivale a uma queda de **aproximadamente 0,25 p.p.** em
termos anuais. O movimento é compatível com uma mudança de taxa básica, mas por si só não
comprova que houve decisão de política monetária nem sua causa.

### Restrições da API SGS (verificadas em 01/11/2026)

| Pedido | Resposta | Significado |
|---|---|---|
| `dataInicial == dataFinal` | `400` · `DataFinal deve ser maior que dataInicial.` | intervalo de um dia é recusado **mesmo havendo cotação** |
| intervalo válido, sem dados | `404` · `Value(s) not found` | ausência de dados, não erro de pedido |
| data inexistente | `400` · `dataInicial invalida...` | pedido malformado |

Um único dia é inatingível por esta API: para obter uma data é preciso pedir ao menos dois dias
e filtrar. O fatiamento garante que nenhum bloco tenha um dia só, absorvendo a sobra final no
bloco anterior; uma janela inteira de um dia é rejeitada com erro explícito.

## Decisões de tratamento

### Janelas

- **Exibição:** últimos 5 anos corridos, `[hoje - 5 anos, hoje]`, inclusive nas duas pontas, com
  "hoje" no fuso de Brasília.
- **Extração:** a de exibição recuada pela `margin_months` da série. A série 12 recua 12 meses,
  porque o acumulado de 12 meses na primeira data exibida precisa de dados anteriores a ela. A
  margem fica armazenada e é excluída dos gráficos — por isso a série 12 tem mais observações
  que a PTAX.
- **Blocos anuais**, pelo limite de 10 anos por consulta do SGS.

### Três categorias de qualidade

| Categoria | Ação | Regra |
|---|---|---|
| **Inválido** | rejeita e conta | data malformada, valor não numérico, valor não finito (NaN, ±inf) |
| **Impossível pela definição** | rejeita e conta | só onde a definição impede: PTAX ≤ 0 |
| **Atípico** | **carrega**, conta e sinaliza | fora da faixa de alerta configurada |

- Valor ausente **nunca** vira zero.
- Taxa **zero** é válida na série 12. Taxa **negativa** é carregada e sinalizada, nunca
  rejeitada: juros negativos não são impossíveis por definição, e descartar esconderia o caso.
- Faixa de alerta da série 12: `[0; 0,5]` % a.d., **configurável** em `src/config.py` e
  **provisória**. É **regra operacional** para chamar atenção humana — **não** é garantia de
  detectar troca de unidade da série nem separador decimal deslocado.
- A faixa da PTAX não foi definida nesta etapa.
- Duplicidade: chave `(indicador, data)`; vale a última ocorrência, e datas com valores
  conflitantes são contadas.
- **Data de referência x coleta:** `ref_date` é a data do dado; `fetched_at` (UTC) é quando foi
  coletado.
- **Bruto + tratado:** `raw_observations` guarda o texto recebido (auditoria); custo: duplica o
  armazenamento, desprezível nesta escala.

### Alcance da checagem de cobertura

Esta é a limitação mais importante do projeto, e está declarada no código, nos testes e no
dashboard.

`MAX_GAP_DAYS = 10` detecta **interrupção prolongada** da fonte — um bloco que não veio, uma
indisponibilidade. Ele **não detecta ausência isolada**: um dia útil faltando no meio da semana
produz lacuna de 2 dias, e uma segunda após feriado prolongado chega a 5 ou 6 — todos muito
abaixo do limite.

Consequências:

- **Passar na validação não significa que a série está completa.**
- Uma observação faltando subestima o acumulado de 12 meses em cerca de 0,05 p.p., sem disparar
  alerta.
- O rótulo "12 meses" significa *a janela foi percorrida sem interrupção prolongada*, **não**
  *todo dia útil está presente*.

A completude da PTAX (49 dias úteis sem cotação, todos feriados nacionais) foi verificada por
**inspeção humana sobre um retrato**, uma vez. Não é garantia automática e não se repete sozinha
nas próximas execuções.

Quando houver ausência conhecida e ainda não explicada dentro da janela, ela é registrada em
`Series.unexplained_absences` e a métrica **não** é apresentada como completa.

## Fórmulas e convenções

**Acumulado em 12 meses até D**, em %:

```
acum12m(D) = [ ∏ (1 + taxa_i/100) − 1 ] × 100,   i ∈ (D − 1 ano, D]
```

Limite inferior **aberto**, superior **fechado**, para não contar o dia-âncora duas vezes.

> **Convenção provisória.** Se a taxa publicada para o dia D remunera o próprio dia D ou a noite
> de D para o dia útil seguinte é **pendência não resolvida**. Errar isso desloca o acumulado em
> exatamente uma observação — cerca de 0,06 p.p. no nível de taxa atual. A convenção deve ser
> estabelecida por documentação ou calculadora oficial com limites explícitos, **nunca ajustando
> a fórmula até os números coincidirem**.

**Anualização de uma taxa diária d**, em % a.a.:

```
anual(d) = [ (1 + d/100)^252 − 1 ] × 100
```

Apresentada como **conversão de unidade** da taxa de um dia específico, não como projeção de
rendimento. Nunca soma de taxas; nunca multiplicação da diária por um número de dias.

**Ano bissexto:** 29/02 menos um ano recai em 28/02, o que torna a janela de 366 dias. Convenção
declarada e coberta por teste.

## Verificações

- **Testes automatizados (`pytest`):** 196 testes, com dados controlados, **sem rede**. O dublê
  da fonte reproduz as recusas reais do SGS (400 em intervalo de um dia, 404 em intervalo vazio),
  para não ser mais permissivo que o serviço.
- **Extração real do SGS:** executada em 01/11/2026 para a série 1 — 1.256 observações de
  01/11/2021 a 30/10/2026, com as 49 ausências em dia útil conferidas uma a uma como feriados
  nacionais.
- **`scripts/verify_cdi.py`:** compara a anualização calculada a partir da série 12 com a série
  4389 do SGS, pela mesma API já usada no pipeline. Verifica **compatibilidade numérica**; não
  identifica as séries, não comprova derivação entre elas e não estabelece a causa de uma
  divergência. Usa duas tolerâncias declaradas: **H1 (conservadora, referência)**, somando o
  arredondamento de publicação das duas séries, e **H2 (estrita, informativa)**, só o da série
  diária propagado pela anualização, com a sensibilidade no nível de taxa de cada data. As casas
  decimais são contadas no **texto recebido**, o que descreve o **formato de publicação**, não a
  precisão metodológica da fonte.
- **`scripts/verify_ptax.py`:** a parte de rede **ainda não foi executada e o endereço da Olinda
  não foi conferido** na documentação oficial.

## Limitações conhecidas

- **Série 12: identificação não confirmada** por metadados oficiais (ver acima).
- **Série 4389: identificação não confirmada**, pela mesma razão.
- **Convenção de datas do acumulado:** provisória.
- **A checagem de cobertura não detecta ausência isolada.** Fechar isso exigiria um calendário
  de dias úteis **por série**, com as exceções históricas de cada uma — a série 12 segue o
  calendário da B3 e a série 1 o do BCB, que podem divergir. Ficou fora desta etapa.
- **Ausência de 30/10/2026 na série 12:** a série termina em 29/10 enquanto a PTAX vai até 30/10.
  Defasagem de publicação é **hipótese**, não conclusão: calendários diferentes também
  explicariam, e comparar as datas das duas séries não resolve. A ponta será reconferida em
  execução posterior.
- **Identidade metodológica da série 1** (PTAX de fechamento) e a API Olinda seguem em aberto.
- A carga não remove observações que a fonte deixe de publicar (tratamento de revisões
  históricas fica para o bônus incremental).
