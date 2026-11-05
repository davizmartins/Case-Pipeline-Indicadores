# IA.md — Relatório sobre o uso de inteligência artificial

**Ferramenta:** Claude (Claude Code / modelo `claude-opus-5`), em uma única conversa.
**Gerado em:** 05/11/2026, a partir do prompt do case enviado literalmente pelo próprio usuário
nesta conversa. É uma regeração: uma versão anterior, de 01/11/2026, não incluía o episódio da
conferência de entrega descrito na seção 5 — episódio que só existiu porque ele se recusou a
entregar sem verificar.

## Nota de método (leia antes do resto)

Este relatório tem uma limitação que o próprio prompt me obriga a declarar: **a conversa foi
compactada durante o desenvolvimento** e eu não tenho mais o texto literal de toda a primeira
metade. O que tenho é (a) um resumo automático que preserva as mensagens do usuário quase na
íntegra e registra os erros e correções ocorridos, (b) os turnos finais em texto literal, e
(c) o repositório e seus commits.

Numa mensagem anterior a este relatório eu afirmei ao Armindo que tinha "acesso ao arquivo de
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
mensagens no padrão `feat:` / `fix:` / `docs:`; nada é publicado sem instrução.

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
- *"o desvio está dentro da tolerância e é compatível com arredondamento dos valores publicados, mas isso não comprova sozinho que essa é a causa nem exclui toda diferença metodológica."*

**Validou executando, e não lendo.** Esta foi a parte mais produtiva do direcionamento dele. Ele
rodou o pipeline, os testes, os dois scripts de conferência e o dashboard no próprio ambiente, e
colou as saídas. **Quatro defeitos do projeto foram encontrados assim, nenhum deles por mim**
(ver seção 5). Num dos casos ele rodou o pipeline **duas vezes** — algo que eu não havia pedido —
e as duas execuções produziram contagens idênticas, o que é a evidência de idempotência da carga
que hoje consta no README.

**Não aceitou "está pronto" como resposta — e foi isso que salvou a entrega.** No dia da
submissão, com o repositório que eu havia declarado completo duas vezes, ele não entregou: ele
perguntou *"vou entregar o repositório, ele está correto?"*. A conferência que essa pergunta
provocou encontrou o `IA.md` da raiz do repositório na **versão penúltima** — faltando a seção 5
inteira dos episódios finais. Se ele tivesse aceitado minha palavra, teria entregado o relatório
errado. O detalhe completo está na seção 5; registro aqui porque é um traço de como ele conduz,
não um acidente isolado.

**Controlou escopo ativamente, até o fim.** Recusou que eu implementasse um calendário próprio de
feriados, recusou adicionar o alerta de variação do dólar naquele momento (*"podemos registrar
como melhoria"*), e na etapa final determinou a sequência: *"Depois que eu enviar os resultados,
corrija apenas eventuais problemas encontrados. Se tudo passar, revisamos o estado final do
README e eu reenvio o prompt exigido no PDF"*.

**Proibiu explicitamente que eu fabricasse o histórico de colaboração:** *"Não invente
questionamentos, validações ou participação minha"* e *"Não fabrique um histórico de
desenvolvimento depois de concluir tudo"*. Esta seção existe sob essa restrição.

**Um episódio sobre este próprio relatório.** Ele chegou a pedir que alterássemos o prompt
prescrito no case: *"prefiro que a gente altere o prompt de comando para realização do IA.md"*.
Eu apontei o risco — o case prescreve o prompt e manda salvar a resposta "sem editar", e o
critério de avaliação diz "IA.md gerado conforme instruído" — e separei o que seria ajuste de
método do que seria editar o relatório por via indireta. Ele então enviou o prompt
**literalmente como está no PDF**, sem nenhuma alteração, nas três vezes em que o relatório foi
gerado. Registro porque é decisão dele e porque é o tipo de coisa que um relatório embelezado
omitiria.

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

**3. Implementar CDI e IPCA apenas sob confirmação oficial e com restrições numeradas.** Para o
CDI: identificar na interface como *"Série SGS 12 — identificação como CDI pendente"* enquanto
os metadados não fossem confirmados; tolerância conservadora na comparação com a série 4389;
descrever a checagem de lacunas como detecção de interrupção prolongada, *"sem certificar
completude"*; não implementar calendário de feriados; escrever *"aproximadamente 0,25 p.p."*.
Para o IPCA: *"Adote 'IPCA — variação mensal', desde que a página oficial encontrada associe
explicitamente o código 433 a essa série. Registre o link e a data da consulta no README."*

**4. Aprovar o Ibovespa, as comparações e o filtro de período, com condições.** Autorizou a
extração do Ibovespa preservando os valores recebidos e sinalizando atípicos sem descartar;
exigiu conferir os fechamentos em fonte independente, preferencialmente a B3; mandou analisar os
cinco anos antes de propor um limite de variação, mas *"não calibre a regra apenas para separar
esses dois eventos"*; e, enquanto não houvesse confirmação, documentar como *"movimentos
atípicos observados na fonte, em investigação"*, **sem atribuir causa política, econômica ou
falha do fornecedor**. Na mesma linha aprovou a base 100 sem alinhamento de datas, a comparação
mensal por meses inteiros com o último mês elegível saindo dos dados, e os cartões independentes
do filtro.

**5. Verificar antes de aceitar — duas vezes, e as duas acharam defeito.** Primeiro a validação
final de ponta a ponta: rodou tudo no ambiente dele, exigiu que eu explicasse o resultado da
suíte com precisão (*"quantos testes passaram e o que representa esse 1? Se houver teste
ignorado, aviso ou falha, identifique e explique o impacto"*), mandou enfraquecer uma conclusão
minha sobre dezembro de 2022, e **especificou ele mesmo os cinco itens do checklist do
dashboard** — quatro indicadores e datas, filtros, base 100 na mesma data, comparação mensal e
retorno real, avisos e comportamento sem dados suficientes. Depois, dias mais tarde, a
conferência de entrega: *"vou entregar o repositório, ele está correto?"* em vez de entregar.
Estes dois pedidos encontraram quatro defeitos, listados na seção 5.

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

**Enfraqueceu uma conclusão minha sobre dezembro de 2022 — e tinha razão.** Depois que o
`verify_ipca` mostrou uma janela dentro da tolerância que não arredonda para o valor publicado,
eu escrevi no README que *"não é divergência metodológica, é arredondamento de publicação"*. Ele
corrigiu: o desvio é **compatível** com arredondamento, mas isso não comprova a causa nem exclui
diferença metodológica. Eu havia afirmado origem a partir de magnitude — o mesmo erro que ele já
havia corrigido no round-trip e na coerência abertura/fechamento, agora na terceira forma.

**Exigiu precisão onde eu havia abreviado.** Eu reportei o resultado da suíte como "320/1". Ele
não aceitou o atalho: *"quantos testes passaram e o que representa esse 1? Se houver teste
ignorado, aviso ou falha, identifique e explique o impacto."* Fui investigar e encontrei, além
do teste pulado, **seis avisos que eu não sabia que existiam** — e, procurando a origem deles,
um defeito real de produção no `app.py` (seção 5). Esse defeito só foi encontrado porque ele
recusou um número abreviado.

**Não aceitou minha declaração de que o repositório estava pronto.** Eu havia escrito, em duas
mensagens diferentes, que os quatro entregáveis estavam no repositório. Ele não entregou com
base nisso: perguntou se estava correto. A conferência achou o `IA.md` errado na raiz. A recusa
em aceitar minha palavra foi, nesse caso, a última linha de defesa do projeto.

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
- A sequência da validação final, e os **cinco itens do checklist do dashboard**, que ele especificou.
- Rodar o pipeline duas vezes — o que produziu a evidência de idempotência que está no README.
- **Conferir o repositório antes de entregar**, em vez de aceitar minha declaração de que estava completo.
- Não implementar o bônus de atualização incremental, mantendo-o documentado como não implementado.
- Todo o processo de commits e publicação; o padrão das mensagens de commit.
- Gerar o IA.md apenas ao final, com o prompt do case **sem alteração**, sem fabricar histórico.

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
- A estrutura e o nível de detalhe do README, incluindo a seção que justifica cada escolha do dashboard.

**Ressalva honesta sobre esta divisão:** "aceito sem alteração" é raro no histórico. A maior
parte das minhas propostas foi aceita **com condições** — e as condições costumavam ser
justamente o que impedia a proposta de afirmar mais do que a evidência permitia. A lista acima
contém o que passou sem emenda; ela é menor do que a lista do que foi emendado.

---

## 5. Pontos de atenção

Coisas que eu errei ou posso ter errado, e que merecem conferência humana.

### O erro mais grave: declarei pronto um repositório que estava errado

No dia da entrega, o `IA.md` **na raiz do repositório** era a versão penúltima, de 304 linhas,
sem a seção 5 dos episódios finais. A versão correta, de 381 linhas, estava numa pasta de
resíduo (`Claude outputs/`) que nem fazia parte do projeto. Eu havia escrito, em duas mensagens
diferentes, que os quatro entregáveis estavam no repositório — **sem ter lido de volta o arquivo
gravado**.

O defeito foi encontrado porque ele perguntou se estava correto em vez de entregar. A
conferência que fiz então comparou os 37 arquivos do disco dele com as minhas cópias e leu o
`IA.md` de volta: os outros 36 estavam certos, esse não.

Há uma ironia que vale registrar, porque é verificável: a versão anterior deste mesmo relatório
já continha a frase *"Se houver qualquer dúvida sobre que versão de um arquivo está no
repositório, confira o conteúdo em vez de confiar no meu relato."* Essa recomendação existia por
causa de um incidente anterior, e foi exatamente o procedimento que ela descreve que impediu a
entrega errada. **A recomendação se provou dentro do próprio arquivo que a contém.**

**A causa não foi determinada.** A ferramenta de gravação reportou sucesso nas duas ocasiões. A
pasta está no OneDrive, o que é hipótese plausível e não causa verificada. Aconteceu **duas
vezes** nesta pasta — ver abaixo. **Regra prática: não aceite meu relato sobre o conteúdo de um
arquivo; abra o arquivo.**

### Um padrão meu: afirmar mais do que a evidência sustenta

Aconteceu em três formas, repetidamente.

**Extrapolar de um único ponto de dado.** Previ que o máximo do dólar estaria em dezembro de
2024 (era 02/01/2025); previ desvio máximo de ordem 10⁻⁵ no script de conferência do CDI (foi
1,4 × 10⁻⁴); derivei uma tolerância a partir de um só nível de taxa. E o caso mais limpo: eu
havia escrito no README que o `verify_ipca` comparou **10 janelas** e que **todos** os valores
calculados arredondavam para o publicado. Quando o script rodou sobre a janela completa, foram
**60 janelas** e **um** não arredonda. A afirmação forte vinha de uma amostra seis vezes menor e
não sobreviveu ao aumento da amostra.
**Trate qualquer número que eu tenha previsto, estimado ou "esperado" como não verificado até
ser medido.**

**Afirmar causa a partir de magnitude.** O round-trip da anualização, a coerência
abertura/fechamento do Ibovespa e a conclusão sobre dezembro de 2022 são o mesmo erro em três
formas: um número compatível com uma explicação não estabelece essa explicação. Nos três casos
foi ele quem corrigiu.

**Declarar estado sem verificar.** O caso do `IA.md` acima, e também: eu afirmei ter acesso à
transcrição integral da conversa (não tinha) e afirmei que os dois scripts de conferência tinham
o mesmo defeito (só um tinha — generalizei antes de abrir o segundo arquivo).

### Meus testes passaram enquanto o código estava quebrado — quatro vezes

**Três vezes por dublê permissivo.** Meus dublês de teste eram mais permissivos que a fonte real
(recusas do SGS, defasagem do CDI, comportamento do yfinance). Foi a causa de 43 testes passarem
enquanto a produção falhava. Corrigidos, e hoje os dublês reproduzem as recusas reais.

**Uma vez por ausência total de teste.** Na validação final, ele rodou `python -m
scripts.verify_cdi` e o script quebrou com `TypeError`. Causa: os scripts de conferência
montavam um objeto `Series` campo a campo, e quando `Series` ganhou um campo obrigatório o
script passou a quebrar — **com a suíte inteira verde**, porque só a função pura de comparação
tinha teste e a função que monta o pedido não tinha nenhum. Corrigido com `dataclasses.replace`
e três testes novos, verificados por mutação. **O defeito foi encontrado por ele rodando o
comando, não pelo pytest.**

### Dois defeitos meus encontrados nos últimos minutos do desenvolvimento

**Vazamento de conexão no dashboard.** O `app.py` fechava a conexão SQLite **dentro** do `try`:
num erro de leitura, o `close()` nunca executava, e o Streamlit reexecuta o script a cada
interação do usuário. Corrigido com `finally` e teste verificado por mutação. **Só apareceu
porque ele exigiu que eu explicasse os avisos da suíte** em vez de aceitar meu "320/1".

**Uma frase órfã que eu mesmo criei.** Numa edição do README eu desgarrei um parágrafo sobre os
dublês de teste, que terminou colado ao fim de um item sobre um aviso do pandas, onde não fazia
sentido. Só foi encontrado na leitura integral do documento. Mostra que minhas edições pontuais
em documentos longos podem produzir incoerências que eu não detecto sem reler tudo.

**Dei um comando de PowerShell que não funciona** (escape de aspas inválido e um `>` que o shell
interpreta como redirecionamento). Comandos que eu forneço para Windows merecem conferência antes
de serem colados.

### Coisas que ficaram sem explicação

**Duas gravações de arquivo que não chegaram, com a ferramenta reportando sucesso.** A primeira:
o `pytest` dele coletou 319 testes enquanto o meu coletava 321, porque o arquivo de testes
gravado no computador dele estava na versão anterior. A segunda: o `IA.md` da raiz, descrito
acima, que quase foi entregue errado. Nos dois casos reenviar resolveu e **a causa não foi
determinada**.

**Uma resposta não-JSON do SGS.** Uma execução do `verify_ipca` falhou e a seguinte, minutos
depois, completou. A causa não foi determinada, e a evidência se perdeu porque a mensagem de
erro daquela versão não incluía o corpo da resposta — o mesmo ponto cego do "HTTP 400" sem
corpo, que ele já havia me feito corrigir em outro ramo do código e que eu deixei aberto
neste. A mensagem foi melhorada para uma próxima ocorrência.

### Pendências de identificação que o projeto NÃO resolveu

- A **série 12 não foi confirmada como CDI** por metadado oficial. O portal do SGS respondeu
  "Requisição inválida" em todas as tentativas e a página de metadados de juros do BCB documenta
  apenas séries da Selic. Não encontrado não é inexistente — mas também não é confirmado.
- A **série 1 não foi confirmada como PTAX de fechamento**. Ela coincide com a consulta
  histórica do BCB num valor, numa data. O indicador pedido no case é o dólar PTAX venda.
- As séries **4389 e 13522**, usadas nos scripts de conferência, também não foram identificadas.
- A **convenção de data da taxa diária** (se a taxa publicada para o dia D remunera o dia D ou a
  noite de D para o dia útil seguinte) segue sem resolução. Errar isso desloca o acumulado em
  uma observação, cerca de 0,06 p.p. no nível atual.

### Verificações que não foram feitas

- O movimento de **+7,70% em 05/10/2026** no Ibovespa nunca foi conferido em fonte independente
  (o de −13,88% em 26/10 foi, e está correto).
- As **8 datas divergentes** entre dólar e Ibovespa não foram conferidas contra o calendário
  oficial da B3.
- O **limite de 10%** de variação do Ibovespa não foi derivado da distribuição dos 5 anos, e sua
  referência vem de fonte secundária, não da norma da B3. Ele gerou um único alerta em 1.248
  pregões, o que mostra poucos alertas nessa amostra e nada além disso.
- O **calendário oficial de divulgação do IBGE** não foi consultado; a regra de defasagem é uma
  aproximação que gera falso alerta previsível todo começo de mês.
- O script **`scripts/verify_ptax.py` nunca foi executado** e o endereço da API Olinda nunca foi
  conferido na documentação. Ele está no repositório como esqueleto, e isso está dito no README,
  que também o deixa fora da lista de comandos executáveis.
- A **janela de dezembro de 2022** no `verify_ipca` fica dentro da tolerância sem arredondar para
  o valor publicado. Isso é compatível com arredondamento de publicação, mas a causa não foi
  estabelecida e diferença metodológica não está excluída.

### A limitação estrutural mais importante, e ela é real

A checagem de cobertura detecta interrupção prolongada da fonte, **não ausência isolada**. Numa
série diária, um dia útil faltando produz lacuna de 2 dias e passa sem alarme, subestimando o
acumulado de 12 meses em cerca de 0,05 p.p. **Passar na validação não significa que a série está
completa.** A completude do dólar foi conferida uma vez, por inspeção humana sobre um retrato —
não se repete sozinha nas próximas execuções.

### Sobre este relatório

Ele foi escrito sobre um histórico parcialmente resumido (ver a nota de método no início). Os
episódios relatados aconteceram, mas se houver dúvida sobre algum detalhe, a fonte mais
confiável é o histórico de commits e os arquivos do repositório, não a minha memória da conversa.
E, pelas razões da primeira subseção desta seção: **confira que este arquivo, no repositório,
tem o mesmo conteúdo que eu digo que tem.**
