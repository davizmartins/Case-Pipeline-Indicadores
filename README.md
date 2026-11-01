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
python -m scripts.verify_ipca       # composição de 12 meses da 433 vs. série 13522
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
| Dólar americano (venda) | Banco Central — SGS | 1 | R$/US$ | diária (dias úteis) | — | implementado, **identificação como PTAX de fechamento pendente** |
| Série SGS 12 | Banco Central — SGS | 12 | % ao dia | diária (dias úteis) | 12 meses | implementado, **identificação pendente** |
| IPCA — variação mensal | Banco Central — SGS (apuração: IBGE) | 433 | % ao mês | mensal | 12 meses | implementado, **identificação confirmada** |
| Ibovespa | yfinance `^BVSP` (apuração: B3) | — | pontos | diária (pregões) | — | implementado |

### Série 1 — o que foi e o que não foi confirmado

O catálogo de dados abertos do BCB descreve a série como "Taxa de câmbio – Livre – Dólar
americano (venda) – diário", unidade R$/US$, origem na transação PTAX800, e informa que a partir
de março de 1992 a cotação de fechamento passou a ser denominada PTAX.

Conferência numérica adicional: em 30/10/2026 a página de cotações históricas do BCB mostra
5,4206 na compra e **5,4212 na venda** — o mesmo valor que a série 1 devolveu. Isso confere **um
valor em uma data** por dois caminhos do BCB. **Não** valida a API Olinda nem resolve a
identidade metodológica da série.

Por isso o dashboard a identifica como **"Dólar americano (venda)"**, o nome do catálogo, e não
como PTAX. **A confirmação continua necessária**, porque o indicador pedido no case é o dólar
PTAX venda: enquanto ela não vier, o projeto entrega uma série que coincide numericamente no
ponto conferido, sem ter estabelecido que é a série pedida.

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

### Série 433 — identificação CONFIRMADA

A página de metadados de séries temporais do Banco Central lista explicitamente
**"0433 — IPCA (índice nacional de preços ao consumidor-amplo)"**, com fonte **IBGE**:

- <https://www4.bcb.gov.br/PEC/SERIES/PORT/METADADOS/MG41BP.HTM>
- **Consultada em 01/11/2026.** A própria página informa última atualização em **27/09/2002**.

Ressalva: nessa página a unidade e a periodicidade aparecem **uma única vez para o grupo
de 33 séries do IPCA**, não por série. Unidade percentual e periodicidade mensal do índice
vêm confirmadas separadamente pelo IBGE, que é quem o apura: o fascículo IPCA/INPC traz
"Mensal" na ficha técnica e divulga a variação em percentual.

Conferências numéricas feitas na coleta, contra o fascículo do IBGE de dezembro de 2025:

| Verificação | Resultado |
|---|---|
| 433 em 01/12/2025 | 0,33 — igual ao IPCA de dezembro publicado pelo IBGE |
| 13522 em 01/12/2025 | 4,26 — igual ao fechamento de 2025 publicado pelo IBGE |
| Carimbo de data | **mês de referência**, não de publicação: sob a outra hipótese, o 4,26 teria de aparecer em 01/01/2026, onde há 4,44 |

### Ibovespa — fonte de terceiros, com armadilhas próprias

O yfinance lê dados do Yahoo Finance. **Não é fonte oficial e não tem contrato de
estabilidade**; o índice é apurado pela B3. Verificações feitas na biblioteca instalada
(yfinance 1.7.0) em 01/11/2026, todas com valor explícito na chamada para não depender
de padrão:

| Armadilha | Consequência |
|---|---|
| `yf.config.debug.hide_exceptions` vem **True** | a biblioteca **engole exceções**; uma falha viraria resultado vazio. Ligamos a exceção |
| `yf.download` não tem como levantar exceção e devolve `Optional[DataFrame]` | usamos `Ticker.history`, que tem |
| `raise_errors=True` está **obsoleto** nesta versão | usamos `yf.config.debug.hide_exceptions = False` |
| `end` é **exclusivo** | pedir até 31/10 devolve até 30/10; a janela do projeto é inclusiva, então somamos um dia |
| `auto_adjust` vem **True**, e aí `Adj Close` nem existe | passamos `False`, para comparar as duas colunas a cada carga |
| índice vem **com fuso** (`datetime64[s, America/Sao_Paulo]`) | conversão explícita antes de extrair a data |
| `multi_level_index`, `progress`, `threads` | irrelevantes em `Ticker.history`, que não os tem |

**`Close` e `Adj Close` coincidem**, como esperado para um índice sem desdobramentos nem
dividendos a ajustar — o Ibovespa já é índice de retorno total, com os proventos dentro
do nível calculado pela B3. Diferença máxima medida: **0,0**. A conferência é refeita a
cada carga e registra aviso se divergir.

**Ressalva sobre o "bruto":** o SGS entrega texto, guardado exatamente como veio. O
yfinance entrega float já convertido pela biblioteca, então o que a tabela bruta guarda é
a representação desse float — um passo distante do que o servidor enviou.

#### Movimentos atípicos de outubro de 2026

A série apresenta dois movimentos muito acima do normal: **+7,70% em 05/10/2026** e
**−13,88% em 26/10/2026**. Nos outros 19 pregões do mês a variação ficou entre −2,68% e
+2,63%.

**O de 26/10 foi conferido contra fonte independente e está correto:** o fechamento de
176.608 pontos e a queda de 13,88% conferem com o publicado pela imprensa financeira, que
também registra acionamento de circuit breaker pela B3. O dado é real e **não deve ser
corrigido nem removido**.

O de 05/10 **não foi conferido individualmente** e permanece como movimento atípico
observado na fonte.

Correção de um raciocínio que usamos no caminho: a coerência entre a abertura de um dia e
o fechamento do anterior **não comprova** que o movimento ocorreu no mercado — mostra
apenas consistência interna dos dados recebidos, que poderiam estar errados de forma
coerente. Foi a conferência externa que resolveu, não a coerência interna.

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
| **Atípico** | **carrega**, conta e sinaliza | fora da faixa de alerta, por nível **ou** por variação |

Há **duas regras de alerta independentes**, ambas apenas sinalizando:

- **por nível:** o valor é implausível em si (ex.: uma variação mensal do IPCA na casa de 4%, que seria o acumulado em 12 meses);
- **por variação:** o valor é plausível sozinho mas destoa do anterior (ex.: a queda de 13,88% do Ibovespa, em que 176.608 pontos não têm nada de absurdo isoladamente).

A marca gravada é a união das duas; o relatório da execução conta cada uma. **Sinalizar
pede conferência humana e não declara erro** — o próprio caso do Ibovespa mostra por quê:
o pregão sinalizado estava correto.

**Limite de variação do Ibovespa: 10%**, provisório e configurável. A âncora é o circuit
breaker da B3, que suspende as negociações quando o índice cai 10% ante o fechamento
anterior — o patamar que o próprio mercado trata como excepcional. Limitações conhecidas:

- é aplicado **simetricamente** a altas, o que a regra do circuit breaker não faz;
- **não** foi derivado da distribuição dos 5 anos, e **não** foi calibrado para os dois
  eventos de outubro: ele sinaliza o de 26/10 (−13,88%) e **não** sinaliza o de 05/10
  (+7,70%);
- a referência de 10% vem de fonte secundária, não da norma da B3.

Derivar o limite da distribuição real dos 5 anos é melhoria prevista.

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

O limite é **por série**, derivado do calendário de cada uma:

| Série | Limite | Por quê |
|---|---|---|
| diárias | 10 dias | fim de semana dá 3; o maior feriado emendado observado em 5 anos deu 5 |
| mensal | 40 dias | observações consecutivas distam 28 a 31 dias; **um mês faltando produz 59 a 62** |

No caso mensal o limite é bem apertado: ele **detecta um mês faltante**, ao contrário do caso
diário, onde uma ausência isolada passa.

### Atualidade dos dados

Regra por série. Diárias contam em dias; a mensal conta em **meses de calendário**, porque
sete dias não significa nada para um índice que sai depois do fechamento do mês.

**O IPCA é divulgado após o mês de referência**, então o cartão sempre mostra um mês anterior
ao corrente — isso não é atraso.

**Aproximação declarada.** O ideal seria comparar o último mês disponível com o último mês cuja
divulgação já ocorreu segundo o calendário oficial do IBGE. Consultá-lo automaticamente
ampliaria o escopo desta etapa, então o projeto usa a diferença em meses, com alerta a partir
de 2. **Isso produz um falso alerta previsível todo começo de mês:** o mês M é divulgado
durante M+1, por volta do dia 10; antes disso o último disponível é M−1, diferença de 2. Por
isso o alerta se chama "possível defasagem" e o próprio texto avisa que pode aparecer sem haver
atraso real.

Quando houver ausência conhecida e ainda não explicada dentro da janela, ela é registrada em
`Series.unexplained_absences` e a métrica **não** é apresentada como completa.

### Escala dos gráficos

O eixo vertical é ajustado à faixa dos dados do período, com margem de 5% da amplitude, e **não
começa em zero**. São gráficos de linha para acompanhar o **movimento** de uma cotação ou de uma
taxa, não para comparar magnitudes entre categorias — num gráfico de barras a base zero seria
obrigatória, aqui não é. Começando em zero, a variação da PTAX de 4,62 a 6,21 vira uma linha
quase reta. Os gráficos não levam título: o eixo informa unidade e período, e um título
interpretativo sugeriria leitura que os dados sozinhos não sustentam.

### Calendários das séries diárias

As séries diárias **não** compartilham calendário. Medido na base, PTAX e Ibovespa
divergem em **8 datas** na janela de 5 anos, todas com cotação de câmbio e sem pregão:

| Data | Dia |
|---|---|
| 24/12/2021, 31/12/2021 | sexta |
| 30/12/2022, 29/12/2023 | sexta |
| 24/12/2024, 31/12/2024 | terça |
| 24/12/2025, 31/12/2025 | quarta |

**Todas em dezembro, em datas de fim de ano.** Isso é compatível com a B3 encerrar o
calendário de negociação antes do Banco Central, mas **não foi verificado** contra o
calendário oficial da B3 e portanto **não está registrado como explicado**. Fica como
padrão observado, a confirmar.

A série 12 também termina um dia antes das outras duas (29/10 contra 30/10 em
01/11/2026) — ver limitações.

Consequência de projeto: a comparação entre séries diárias **não alinha datas**. Cada
série é desenhada nas suas próprias, sem preenchimento e sem exclusão de observação; o
único ponto compartilhado é a data-base do rebase.

## Comparações do dashboard

### Evolução diária em base 100

Compara a série 12 (taxa), o dólar e o Ibovespa (níveis).

- **Data-base:** a primeira data, dentro do período filtrado, com observação nas
  **três** séries. É exibida na tela. Sem data comum, a comparação não é apresentada.
- **Séries de nível:** índice = valor(d) ÷ valor(base) × 100.
- **Série de taxa:** capitaliza as taxas das datas **posteriores** à data-base, no
  calendário da própria série — mesma convenção do acumulado em 12 meses. A taxa
  publicada *na* data-base não entra: ali o índice vale 100 por definição.
- A tela mostra a **última data de cada série**. Quando diferem, um aviso diz que os
  valores finais **não** são variações de períodos exatamente iguais.
- Nota permanente: são **naturezas diferentes** — uma taxa de juros acumulada, uma taxa
  de câmbio e um índice de ações. Não é comparação de investimentos equivalentes, e
  nenhuma das três considera custos, impostos ou viabilidade de replicação.

### Comparação mensal: série 12 e IPCA

Entram apenas **meses inteiros** contidos no filtro, com o índice mensal publicado e com
cobertura suficiente na série diária. **O último mês elegível sai dos dados**, não está
fixado no código: se a fonte publicar mais um mês, a comparação avança sozinha. O período
efetivamente usado é exibido.

Retorno real **pela razão entre os fatores**:

```
real = (1 + taxa/100) ÷ (1 + inflação/100) − 1
```

Subtrair uma taxa da outra dá resultado parecido e errado.

**Limitação:** a checagem de cobertura de cada mês detecta interrupção prolongada, não
ausência isolada — um dia útil faltando dentro de um mês passaria sem alarme e
subestimaria o acumulado daquele mês.

### Filtro de período

12 meses, 24 meses, 5 anos e personalizado. Afeta os gráficos de evolução e as duas
comparações, e define a data-base do rebase.

**Os cartões não mudam com o filtro.** Ficam numa seção própria, "Últimos indicadores
disponíveis", com semântica fixa — última observação e acumulado nos 12 meses até ela —
e período e data de referência explícitos em cada um.

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
- **`scripts/verify_ipca.py`:** compõe os 12 mensais da série 433 e compara com o acumulado
  publicado na série 13522, em todas as janelas comparáveis. Com os dados de novembro de 2026,
  as **10 janelas disponíveis bateram**: o desvio máximo foi de 0,0049 p.p., e os dez valores
  calculados **arredondam para exatamente o publicado**. A tolerância soma o arredondamento dos
  doze mensais (±0,005 p.p. cada, propagados) com o da própria série publicada, chegando a
  ±0,067 p.p. no pior caso. Isso valida a composição e a convenção da janela mensal; **não**
  identifica a série 13522, cujos metadados não foram localizados, e **não** vale para a
  convenção de séries diárias.
- **`scripts/verify_ptax.py`:** a parte de rede **ainda não foi executada e o endereço da Olinda
  não foi conferido** na documentação oficial.

## Limitações conhecidas

- **Série 12: identificação não confirmada** por metadados oficiais. A página de metadados de
  juros do BCB (`mg45p`) documenta apenas séries da Selic. **Não encontrado não é inexistente**:
  o portal do SGS responde "Requisição inválida" e o caminho certo pode existir.
- **Séries 4389 e 13522: identificação não confirmada**, pela mesma razão. Ambas são usadas
  apenas em scripts de conferência, fora da entrega.
- **Calendário oficial de divulgação do IBGE não consultado** — ver "Atualidade dos dados".
- **Ibovespa vem de fonte de terceiros** (yfinance/Yahoo), sem contrato de estabilidade,
  e os padrões dessa biblioteca já mudaram entre versões. Todos os parâmetros relevantes
  são passados explicitamente, mas uma mudança de comportamento da fonte continua sendo
  risco.
- **Movimento de 05/10/2026 no Ibovespa (+7,70%) não conferido** contra fonte
  independente.
- **Limite de variação do Ibovespa não derivado dos 5 anos.** Na carga de 01/11/2026 ele
  gerou **um único alerta** em 1.248 pregões (26/10/2026, conferido e correto). Isso
  mostra que a regra gerou poucos alertas **nesta amostra**; não comprova que detecta
  todos os problemas possíveis.
- **A PTAX não tem alerta de variação.** O mesmo evento de 26/10/2026 aparece nela
  (+9,19%, de 5,0377 para 5,5007) e não é sinalizado, porque nenhuma regra foi
  configurada para essa série. Melhoria prevista; exigiria um limite próprio, já que
  câmbio e índice de ações têm volatilidades diferentes. Note também que esses +9,19%
  **não** são os +8,2% citados na imprensa para o "dólar de fechamento": são
  referências distintas e não devem ser tratadas como o mesmo número.
- **As 8 datas divergentes entre PTAX e Ibovespa não foram verificadas** contra o
  calendário oficial da B3 — ver "Calendários das séries diárias".
- **A série 12 termina um dia antes** da PTAX e do Ibovespa (29/10 contra 30/10 em
  01/11/2026). Defasagem de publicação é hipótese, não conclusão.
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
