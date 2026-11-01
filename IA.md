# IA.md — Relatório sobre o uso de inteligência artificial

**Ferramenta:** Claude (Claude Code / modelo `claude-opus-5`), em uma única conversa.
**Gerado em:** 01/11/2026, ao final do desenvolvimento, a partir do prompt do case enviado
literalmente pelo próprio usuário nesta conversa.

## Nota de método (leia antes do resto)

Este relatório tem uma limitação que o próprio prompt me obriga a declarar: **a conversa foi
compactada durante o desenvolvimento** e eu não tenho mais o texto literal de toda a primeira
metade. O que tenho é (a) um resumo automático que preserva as mensagens do usuário quase na
íntegra e registra os erros e correções ocorridos, e (b) os turnos finais em texto literal.

Na mensagem anterior a este relatório eu afirmei ao Armindo que tinha "acesso ao arquivo de
transcrição integral desta sessão". **Isso estava errado** — fui conferir o arquivo e ele começa
no ponto da compactação. Ele foi informado antes de eu escrever. Registro aqui porque é
exatamente o tipo de afirmação confiante e não verificada que este relatório deve expor, e
porque ela aconteceu na última hora do projeto, não no começo.

Consequência prática: as citações diretas de falas dele são fiéis, e os episódios abaixo
aconteceram todos. O que pode faltar é algum episódio menor da primeira metade que não
sobreviveu ao resumo.

---

## 1. Como fui direcionada

O direcionamento foi **restritivo e orientado a prova**, não a entrega. A característica
dominante não foi o nível de detalhe técnico das instruções — foi o padrão de evidência imposto
a mim.

**Exigiu plano antes de código, de forma consistente.** Em praticamente toda etapa nova a
sequência foi: eu apresento o desenho, ele aprova com ajustes numerados, só então eu implemento.
Houve etapas em que ele bloqueou explicitamente a implementação até o plano estar discutido —
*"Por enquanto, não implemente novas funcionalidades"*, *"Me apresente o resultado antes de
implementar os cálculos"*. As aprovações quase nunca vinham limpas: vinham como *"Aprovo o
desenho, com estes ajustes: 1… 2… 3… 4… 5…"*.

**Deu contexto e restrições de ambiente desde o início:** Windows 11, Python 3.13.6, interface
em português com formatos brasileiros de data e número, e a definição de quem usaria o
dashboard. Também impôs restrições de processo: os commits e o push são dele, eu só sugiro
mensagens no padrão `feat:` / `fix:`; nada é publicado sem instrução.

**O traço mais incomum foi exigir que eu separasse o que foi verificado do que foi suposto.** Em
vários pontos ele recusou uma conclusão não porque estivesse errada, mas porque a evidência não
a sustentava ainda. Exemplos textuais dele:

- *"Coincidir em alguns dias é suficiente para comprovar que duas séries representam a mesma coisa?"*
- *"Não conclua que os metadados não existem apenas porque o portal está inacessível."*
- *"Não afirme que validou algo que não conseguiu executar."*
- *"Registre como explicadas apenas as que forem verificadas."*
- *"Não ajuste a fórmula apenas para fazer os números coincidirem."*
- *"Oito observações de diferença não comprovam, sozinhas, uma diferença de calendário."*
- *"Um único alerta do Ibovespa também não comprova que o limite detecta todos os problemas; apenas mostra que gerou poucos alertas nessa amostra."*

**Controlou escopo ativamente.** Recusou que eu implementasse um calendário próprio de feriados,
recusou adicionar o alerta de variação do dólar naquele momento (*"podemos registrar como
melhoria"*) e mandou manter pendências documentadas em vez de resolvê-las ampliando o projeto.

**Proibiu explicitamente que eu fabricasse o histórico de colaboração:** *"Não invente
questionamentos, validações ou participação minha"* e *"Não fabrique um histórico de
desenvolvimento depois de concluir tudo"*. Esta seção existe sob essa restrição.

**Um episódio sobre este próprio relatório, no último minuto do projeto.** Ele chegou a pedir
que alterássemos o prompt prescrito no case: *"prefiro que a gente altere o prompt de comando
para realização do IA.md"*. Eu apontei o risco — o case prescreve o prompt e manda salvar a
resposta "sem editar", e o critério de avaliação diz "IA.md gerado conforme instruído" — e
separei o que seria ajuste de método do que seria editar o relatório por via indireta. Ele então
enviou o prompt **literalmente como está no PDF**, sem nenhuma alteração. Registro porque é
decisão dele e porque é o tipo de coisa que um relatório embelezado omitiria.

**Onde o direcionamento foi mais fraco:** ele delegou a mim quase toda a arquitetura de código
(divisão de módulos, esquema do banco, estrutura dos testes) sem pedir alternativas. Em geral
ele reagia ao que eu propunha em vez de especificar antes — o que funcionou porque ele revisava
com rigor, mas significa que a forma do código é mais minha do que dele.

---

## 2. Pedidos principais

**1. Enquadrar o case e fixar o padrão de prova.** Pediu que eu validasse o conceito de cada
indicador antes de codar, questionou minha afirmação de que o Ibovespa é "índice de preço, sem
dividendos", questionou a interseção de datas entre séries, e exigiu confirmar código, unidade
e periodicidade de cada série do SGS em fonte oficial antes de decidir. Determinou também manter
o SGS como fonte do dólar (como o case pede), *"salvo se você demonstrar uma incompatibilidade
com o requisito"*.

**2. Conduzir a validação local passo a passo, sem corrigir antes de entender.** *"Vou executar
o projeto no meu ambiente e fazer algumas verificações manuais… Se aparecer algum erro, vamos
entender a causa antes de alterar o código."* Foi assim que apareceu a falha de HTTP 400 na
extração do dólar, e foi um teste feito por ele — não por mim — que refutou minha hipótese
principal.

**3. Implementar o CDI sob restrições explícitas.** Autorizou extração, cálculos e testes com
dados controlados, mas com seis condições numeradas, entre elas: identificar na interface como
*"Série SGS 12 — identificação como CDI pendente"* enquanto os metadados não fossem confirmados;
usar tolerância conservadora na comparação com a série 4389; descrever a checagem de lacunas
como detecção de interrupção prolongada, "sem certificar completude"; não implementar calendário
de feriados; e escrever *"aproximadamente 0,25 p.p."* na mudança de taxa.

**4. Confirmar o IPCA em fonte oficial antes de qualquer código.** *"Adote 'IPCA — variação
mensal', desde que a página oficial encontrada associe explicitamente o código 433 a essa série.
Registre o link e a data da consulta no README."* Também definiu como tratar desatualização:
preferia o calendário oficial do IBGE, mas aceitou provisoriamente a regra de dois meses se
consultá-lo ampliasse demais o escopo — identificando o alerta como *"possível defasagem"*.

**5. Aprovar o Ibovespa, as comparações e o filtro de período, com condições.** Autorizou a
extração do Ibovespa preservando os valores recebidos e sinalizando atípicos sem descartar;
exigiu conferir os fechamentos em fonte independente, preferencialmente a B3; mandou analisar os
cinco anos antes de propor um limite de variação, mas *"não calibre a regra apenas para separar
esses dois eventos"*; e, enquanto não houvesse confirmação, documentar como *"movimentos
atípicos observados na fonte, em investigação"*, **sem atribuir causa política, econômica ou
falha do fornecedor**. Na mesma linha aprovou a base 100 sem alinhamento de datas, a comparação
mensal por meses inteiros com o último mês elegível saindo dos dados, e os cartões independentes
do filtro.

---

## 3. Correções e questionamentos

Esta é a seção mais longa porque foi o que mais aconteceu.

**Conceito do Ibovespa — eu estava errado.** Afirmei que era um índice de preço, sem dividendos.
Ele não aceitou e pediu validação. É um índice de **retorno total**: os proventos entram no
nível calculado pela B3. A correção mudou o texto do README e a interpretação de `Close` vs.
`Adj Close`.

**Interseção de datas — ele viu um erro que eu não tinha visto.** Eu propus intersectar as datas
das séries antes de calcular. Ele perguntou: *"Se houver uma observação de CDI em um dia sem
negociação do Ibovespa, eliminar essa data antes de acumular as taxas não faria perder um dia de
rendimento?"* Faria. Cada série passou a ser acumulada no seu próprio calendário, e o
alinhamento ficou só para a exibição. Essa é hoje uma decisão central do projeto e é dele.

**Minha hipótese do HTTP 400 foi refutada por um teste dele.** Eu atribuí a falha a um intervalo
vazio. Ele rodou os testes que eu pedi e o resultado mostrou outra causa: o SGS recusa
`dataInicial == dataFinal` **mesmo havendo cotação na data**.

**Minha correção era maior que o problema.** Propus absorver sobras de até 30 dias no bloco
anterior. Ele respondeu: *"por que usar 30 dias se o problema identificado foi um intervalo de
um único dia? Prefiro corrigir com a regra mínima necessária"*. Eu não tinha base nenhuma para
os 30 dias — admiti e reduzi à regra de um dia.

**Rejeitou meu "round-trip" como prova.** Eu disse que a anualização de 0,050788 dando ~13,65%
confirmava unidade, base e taxa vigente. Ele respondeu que é uma **verificação de consistência,
não prova**. Está certo: a Selic faria o mesmo round-trip. Na mesma conversa percebi que outro
teste que eu havia proposto (comparar as séries 11 e 12) também não identificaria nenhuma das
duas.

**Rejeitou minha tolerância numérica.** Eu derivei uma tolerância de 0,001 p.p. a partir de um
único nível de taxa, ignorando o arredondamento da própria série de referência. Ele exigiu
derivá-la do arredondamento das **duas** séries e da sensibilidade da anualização em níveis
diferentes de taxa. O script foi refeito com duas hipóteses declaradas (H1 conservadora, H2
estrita).

**Corrigiu minha conclusão de que os metadados "não existem".** *"Não conclua que os metadados
não existem apenas porque o portal está inacessível."* Depois dessa correção eu procurei de
novo e **encontrei** a página oficial de metadados do IPCA (`MG41BP.HTM`), que associa
explicitamente o código 0433 ao índice. Se ele tivesse aceitado minha conclusão, o projeto teria
entregado o IPCA como "não confirmado" sem motivo.

**Corrigiu um raciocínio meu sobre o Ibovespa.** Eu argumentei que a coerência entre a abertura
de um dia e o fechamento do anterior sugeria um movimento real de mercado. Ele respondeu: *"A
coerência entre abertura e fechamento não comprova que o movimento ocorreu no mercado."* Está
certo — dados errados podem ser internamente coerentes. Foi a conferência externa que resolveu.

**Impediu que eu misturasse duas referências de câmbio.** Eu dei a entender que uma variação de
+8,2% citada na imprensa para o "dólar de fechamento" corroborava nossa série. Ele apontou que
são referências distintas. Nossa série mostrou +9,19%. Os dois números estão hoje no README,
lado a lado, com a ressalva.

**Recusou que eu tratasse observações como explicadas sem verificação.** Sobre as 8 datas em que
o dólar tem cotação e o Ibovespa não tem pregão, ele determinou: listar as datas e *"registrar
como explicadas apenas as que forem verificadas"*. Elas seguem registradas como padrão
observado, não explicado.

**Recusou que eu superestimasse a regra de alerta.** Sobre o alerta de variação do Ibovespa ter
disparado uma única vez em 1.248 pregões, ele determinou que isso mostra que a regra gerou
poucos alertas **naquela amostra**, e não que ela detecta todos os problemas. O README diz isso.

**Recusou o uso de contagem fixa de dias úteis** para investigar uma ausência, sem conferir o
calendário correspondente — e recusou que eu implementasse esse calendário naquela etapa.

**Recusou atribuição de causa.** Mandou documentar os movimentos atípicos *"sem atribuir causa
política, econômica ou falha do fornecedor"* enquanto não houvesse confirmação. A lembrança dele
de um evento ajudou a investigação, mas ele próprio disse que *"não encerra a validação"*.

**Me corrigiu sobre fabricar histórico.** Deixou claro que o IA.md seria gerado só ao final, com
o prompt do case, e que eu não deveria inventar acontecimentos para preenchê-lo nem inventar
participação dele. Este relatório obedece a isso: tudo aqui aconteceu.

---

## 4. Divisão das decisões

**Decidido por ele (e, em vários casos, contra o que eu propus):**

- Acumular cada série no seu próprio calendário, sem interseção de datas.
- Manter o SGS como fonte do dólar, por ser o que o case pede.
- Corrigir bugs com a **regra mínima necessária**, não com margem folgada.
- Separar valores **inválidos** de valores **atípicos** — atípico é carregado e sinalizado, nunca descartado.
- Aceitar taxa zero como válida; não escolher teto arbitrário com base em dois valores.
- Cartão do CDI com o acumulado em 12 meses como valor principal e a anualizada abaixo, **como equivalência de unidade, sem sugerir previsão de rendimento**.
- Identificar na interface a série 12 como pendente enquanto não houver metadado oficial.
- Regra provisória de dois meses para "possível defasagem" do IPCA, com esse nome.
- Base 100 ancorada na primeira data com observação nas três séries, exibida na tela; mostrar a última data de cada série e avisar quando diferirem.
- Comparação mensal só com meses inteiros; último mês elegível determinado pelos dados, não fixado no código.
- Filtro de 12 meses / 24 meses / 5 anos / personalizado, com os cartões **independentes do filtro**.
- Não adicionar o alerta de variação do dólar nesta etapa; registrar como melhoria.
- Eixo vertical ajustado à faixa do período; título "Dólar americano (venda)" com a fonte abaixo.
- Preservar os valores recebidos do yfinance sem substituir nem descartar.
- Analisar os 5 anos antes de propor o limite de variação, sem calibrar para os eventos conhecidos.
- Todo o processo de commits e publicação; o padrão das mensagens de commit.
- Gerar o IA.md apenas ao final, com o prompt do case, sem fabricar histórico.

**Sugerido por mim e aceito sem alteração:**

- A arquitetura de módulos (`extract` / `transform` / `load` / `metrics` / `pipeline`), e depois `charts.py` e `freshness.py` como módulos separados para serem testáveis fora do Streamlit.
- O esquema do banco com tabela **bruta** e tabela **tratada**, mais um registro de execuções; carga idempotente por UPSERT em transação única; mecanismo de migração de coluna.
- Fatiamento da consulta ao SGS em blocos anuais, com timeout e retentativas.
- Incluir o **corpo da resposta** nas mensagens de erro de HTTP (sugerido por mim depois que ele precisou abrir o navegador para descobrir a causa de um erro meu).
- Capitalização composta para acumular taxas; base 252 na anualização; janela de 12 meses como `(D − 1 ano, D]`; convenção para 29/02.
- Retorno real pela razão entre os fatores, nunca por subtração.
- O mecanismo de margem de extração (`margin_months`) para que o acumulado de 12 meses exista já na primeira data exibida.
- Limite de lacuna **por série** (10 dias nas diárias, 40 na mensal), com o alcance da regra declarado.
- O script de inspeção da base e a sugestão do DB Browser for SQLite.
- Cores fixas por indicador, validadas para daltonismo e contraste; eixo de datas com granularidade de dia.
- A estrutura e o nível de detalhe do README.

**Ressalva honesta sobre esta divisão:** "aceito sem alteração" é raro no histórico. A maior
parte das minhas propostas foi aceita **com condições** — e as condições costumavam ser
justamente o que impedia a proposta de afirmar mais do que a evidência permitia. A lista acima
contém o que passou sem emenda; ela é menor do que a lista do que foi emendado.

---

## 5. Pontos de atenção

Coisas que eu posso ter errado, ou que já errei e merecem conferência humana.

**Um padrão meu que se repetiu três vezes: extrapolar de um único ponto de dado.** Previ que o
máximo do dólar estaria em dezembro de 2024 (era 02/01/2025); previ desvio máximo de ordem
10⁻⁵ no script de conferência do CDI (foi 1,4 × 10⁻⁴); e derivei uma tolerância a partir de um
só nível de taxa. **Trate qualquer número que eu tenha previsto, estimado ou "esperado" como não
verificado até ser medido.**

**Outro padrão: meus dublês de teste foram mais permissivos que a fonte real — três vezes.** Foi
a causa de 43 testes passarem enquanto a produção falhava. Corrigido nos três casos (recusas do
SGS, defasagem do CDI, yfinance), mas é um ponto cego meu: **o teste passar não prova que a
fonte se comporta como o teste supõe.**

**Eu introduzi pelo menos um bug no final do projeto.** Ao traduzir os rótulos de mês de
`2025-11` para `11/2025`, quebrei a ordenação do gráfico de barras — a biblioteca passou a
ordenar alfabeticamente, agrupando todos os janeiros. Só foi detectado porque ele olhou as
capturas de tela. Antes disso, uma mutação que eu mesmo introduzi para testar (UTC em vez do
fuso de São Paulo) **não foi detectada** pelos meus testes, porque eu os havia escrito só com
horários de meia-noite.

**Dei um comando de PowerShell que não funciona.** Usei escape de aspas inválido no PowerShell e
um `>` que o shell interpreta como redirecionamento. Comandos que eu forneço para Windows
merecem conferência antes de serem colados.

**O README estava factualmente errado até a revisão final.** O bloco de estado, a primeira coisa
que um avaliador lê, dizia que o IPCA e o Ibovespa "ainda não entraram" muito depois de os dois
estarem funcionando; a contagem de testes dizia 196 quando eram 315; a tabela de arquivos
omitia seis módulos. Isso não foi um erro de raciocínio, foi documentação que envelheceu sem
que eu a revisasse — e só foi corrigido porque houve uma revisão final dedicada.

**Pendências de identificação que o projeto NÃO resolveu, e que importam para a avaliação:**

- A **série 12 não foi confirmada como CDI** por metadado oficial. O portal do SGS respondeu
  "Requisição inválida" em todas as tentativas e a página de metadados de juros do BCB documenta
  apenas séries da Selic. Não encontrado não é inexistente — mas também não é confirmado.
- A **série 1 não foi confirmada como PTAX de fechamento**. Ela coincide com a consulta
  histórica do BCB num valor, numa data. O indicador pedido no case é o dólar PTAX venda.
- As séries **4389 e 13522**, usadas nos scripts de conferência, também não foram identificadas.
- A **convenção de data da taxa diária** (se a taxa publicada para o dia D remunera o dia D ou a
  noite de D para o dia útil seguinte) segue sem resolução. Errar isso desloca o acumulado em
  uma observação, cerca de 0,06 p.p. no nível atual.

**Verificações que não foram feitas:**

- O movimento de **+7,70% em 05/10/2026** no Ibovespa nunca foi conferido em fonte independente
  (o de −13,88% em 26/10 foi, e está correto).
- As **8 datas divergentes** entre dólar e Ibovespa não foram conferidas contra o calendário
  oficial da B3.
- O **limite de 10%** de variação do Ibovespa não foi derivado da distribuição dos 5 anos, e sua
  referência vem de fonte secundária, não da norma da B3.
- O **calendário oficial de divulgação do IBGE** não foi consultado; a regra de defasagem é uma
  aproximação que gera falso alerta previsível todo começo de mês.
- O script **`scripts/verify_ptax.py` nunca foi executado** e o endereço da API Olinda nunca foi
  conferido na documentação. Ele está no repositório como esqueleto, e isso está dito no README.

**A limitação estrutural mais importante, e ela é real:** a checagem de cobertura detecta
interrupção prolongada da fonte, **não ausência isolada**. Numa série diária, um dia útil
faltando produz lacuna de 2 dias e passa sem alarme, subestimando o acumulado de 12 meses em
cerca de 0,05 p.p. Passar na validação **não** significa que a série está completa. A
completude do dólar foi conferida uma vez, por inspeção humana sobre um retrato — não se repete
sozinha nas próximas execuções.

**Por último, sobre este relatório:** ele foi escrito sobre um histórico parcialmente resumido
(ver a nota de método no início). Os episódios relatados aconteceram, mas se houver dúvida sobre
algum detalhe, a fonte mais confiável é o histórico de commits e os arquivos do repositório, não
a minha memória da conversa.
