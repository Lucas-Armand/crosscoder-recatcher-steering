# CrossCoder para investigar diferenças entre modelos — narrativa revisada

## Mensagem central

> CrossCoders podem transformar diferenças comportamentais entre dois modelos em hipóteses mecanísticas testáveis. Neste estudo, o processo foi da caracterização dos erros à descoberta de uma feature semanticamente legível e, finalmente, à demonstração de controle causal específico sobre um modo de falha.

Esta apresentação é a continuação natural do deck preliminar de maio. O primeiro deck apresentou a motivação ReCatcher, o model diffing com CrossCoder e um smoke test de steering. O novo deck deve responder: **a metodologia amadureceu e produziu um caso causal robusto?**

## O método, formulado corretamente

```text
Avaliar modelos
      ↓
Construir transições base ↔ finetuned
      ↓
Caracterizar os tipos de erro
      ↓
Ranquear features associadas às transições
      ↓
Interpretar tokens e contextos de alta ativação
      ↓
Verificar onde a feature aparece no código
      ↓
Formular um modo de falha mecanístico
      ↓
Construir um cohort em que a feature está naturalmente ativa
      ↓
Reproduzir exatamente o baseline
      ↓
Intervir com steering TopK-gated
      ↓
Comparar com sham e features pareadas
      ↓
Medir efeito, especificidade e limites
```

Nuances importantes:

- PR-AUC e métricas relacionadas servem para **screening associativo**; elas não provam causalidade.
- Tokens dominantes e contextos máximos dão a **hipótese semântica**.
- A posição da primeira ativação e sua distribuição ao longo do código testam **precedência temporal**. Uma feature que aparece depois do erro pode ser interpretável, mas não explicá-lo.
- O steering deve ser condicionado à ativação natural da feature no TopK. Isso testa o mecanismo em seu regime operacional.
- Sham e features pareadas distinguem uma direção específica de uma perturbação residual genérica.

## O trinômio de seleção de features

A decisão de fazer steering deve ser apresentada como a interseção de três evidências, e não como um ranking unidimensional:

```text
SEMÂNTICA                         FALHA                         TEMPO
O que a feature representa?  ↔  A qual erro ela se associa?  ↔  Ela ativa antes da decisão?
tokens + contextos               taxonomia + contraste           posição no código
```

Uma feature só vira boa candidata causal quando as três leituras contam uma história compatível. Exemplos:

- Semanticamente clara, mas tardia: pode ser consequência ou marcador de estilo.
- Estatisticamente associada, mas lexical: pode detectar o domínio sem controlar o erro.
- Precoce, mas semanticamente ampla: pode causar mudanças, porém sem especificidade interpretável.
- Semântica compatível + erro compatível + ativação antes/na fronteira: candidata forte para steering gated.

### Visual em dois níveis

**Nível 1 — um exemplo concreto da 6404**

Mostrar o código tokenizado, destacando em vermelho apenas os tokens em que a 6404 entrou no TopK. Ao lado ou abaixo, uma régua de 0% a 100% do código com marcas verticais nas posições de ativação. Marcar também a fronteira em que começa `# tests`/`from task_func...`.

```text
0%                                                         100%
|------×----×-----------×----------------------×××-----------|
                                           ↑ início da contaminação
```

Cor deve representar intensidade, não apenas presença: rosa claro para ativações fracas e vermelho escuro para as mais fortes.

**Nível 2 — distribuição em todas as tarefas**

Para cada feature, usar um raincloud/violin horizontal da posição da **primeira ativação**, com boxplot interno e pontos das tarefas. Um boxplot sozinho esconde multimodalidade e suporte. Ao lado, acrescentar `n ativo / n total`.

Para a 6404, adicionar um segundo painel mais mecanístico: distribuição da distância entre a primeira ativação e o início da contaminação. Valores negativos significam que a feature precedeu o marcador de testes/imports.

Não misturar no mesmo boxplot todas as posições ativas de todos os tokens: gera pseudorreplicação, pois tarefas longas e com muitas ativações passam a pesar mais. A unidade estatística deve ser a tarefa; alternativamente, mostrar um raster com uma linha por tarefa.

## Como as candidatas foram ranqueadas

O screening DSTK100 não deve ser apresentado como “ordenamos por PR-AUC”. Para cada feature, ele comparou a mudança do agregado latente entre o texto gerado pelo finetuned e pelo base, condicionado à direção da transição.

Foram consideradas quatro maneiras complementares de resumir a ativação ao longo dos tokens:

1. `max`: maior ativação em qualquer token;
2. `early_max`: maior ativação nos primeiros 25% do código;
3. `mean`: intensidade média ao longo do código;
4. `active_fraction`: proporção de tokens em que a feature entrou no TopK.

A implementação original calculou as quatro agregações e priorizou `max/early_max` na shortlist de steering. A auditoria posterior refez o ranking incluindo as quatro e recuperou exatamente o mesmo Top 10 para regressões BigCodeBench. Portanto, para essa análise, podemos apresentar as quatro como consideradas sem alterar a conclusão, registrando que `max/early_max` incorporavam a preferência inicial por eventos localizados.

Foi exigido suporte em pelo menos:

`max(3 tarefas, 10% dos casos positivos)`

Em regressões BigCodeBench, isso correspondia a pelo menos 8 das 79 regressões. A 6404 estava ativa em 47/79, bem acima do mínimo.

O score central de ranking foi **E/V: efeito dividido pela variabilidade sob permutação**.

### Como E/V é calculado

Para cada tarefa e feature, primeiro calculamos:

`Δ = agregado no texto finetuned − agregado no texto base`

Depois calculamos o efeito observado:

`efeito = média(Δ nos casos positivos) − média(Δ nos controles)`

Para saber se esse contraste era estável em relação ao acaso, os rótulos positivo/controle foram embaralhados 200 vezes dentro do mesmo benchmark e direção de transição. Em cada permutação, o efeito foi recalculado, produzindo uma distribuição nula para cada feature.

`E/V = efeito observado / desvio-padrão dos efeitos permutados`

Intuição:

> Quantas unidades da variabilidade esperada sob embaralhamento cabem no contraste observado?

Um E/V alto indica que a diferença entre positivos e controles é grande em relação às flutuações produzidas quando a relação entre tarefas e rótulos é quebrada.

E/V é um score de sinal/ruído de permutação. Não deve ser chamado de z-score: o denominador vem de permutações empíricas, a média nula não é explicitamente subtraída na fórmula e não se assume uma distribuição Gaussiana. Também não é um p-valor.

O screening calculou separadamente um p nominal por permutação:

`p = (1 + número de permutações com |efeito nulo| ≥ |efeito observado|) / 201`

Com 200 permutações, o menor valor possível era `1/201 ≈ 0,00498`. Essa etapa inicial não aplicou correção maxT sobre as 16.384 features; por isso, E/V e o p nominal são evidência de screening, não uma descoberta estatística confirmatória.

Para a feature 6404 no screening de regressões BigCodeBench:

- agregado: máximo;
- ROC-AUC: 0,641;
- PR-AUC: 0,405, contra prevalência 0,295;
- PR-AUC lift: 1,37×;
- efeito/variabilidade de permutação: 4,47;
- suporte: 47/79 regressões;
- p nominal por permutação: ≈0,00498, sem correção maxT nessa etapa.

Logo, na apresentação, prefira:

> “Consideramos quatro resumos da ativação, exigimos cobertura mínima e ranqueamos as features pela magnitude do contraste em relação à variabilidade observada após embaralhar os rótulos.”

ROC-AUC e PR-AUC podem aparecer como diagnósticos secundários, mas não precisam conduzir a narrativa. Na auditoria de sensibilidade, o ranking por E/V sozinho recuperou exatamente o mesmo Top 10 de regressões BigCodeBench, incluindo a 6404 em segundo lugar.

A análise temporal posterior usou oito agregados (`max`, `q10_max`, `q25_max`, `q50_max`, `discounted_max`, `discounted_mean`, `first_horizon`, `future_exposure`) e 500 permutações com correção maxT dentro de benchmark × transição. Nessa análise, a 6404 manteve associação global, mas não prioridade temporal corrigida (`melhor p_maxT ≈ 0,0918`). Isso deve ser mostrado como parte da honestidade do processo, não escondido.

O cohort causal de 80 casos não veio diretamente do ranking PR-AUC. Ele emergiu da combinação posterior de:

- taxonomia de contaminação por testes/imports;
- semântica da 6404;
- ativação natural da feature no modelo base;
- seleção de casos base-fail → finetuned-pass.

Essa sequência é especialmente relevante porque os decoder-side cosines das features inspecionadas eram altos: o DSTK100 produziu principalmente features compartilhadas, não latentes claramente exclusivos de um modelo. Por isso, a metodologia precisou buscar **diferenças de uso da mesma feature** — magnitude, suporte, timing e relação com transições — em vez de depender apenas de “features exclusivas do modelo A ou B”.

---

## Ato 1 — Da avaliação agregada ao model diffing

### Slide 1 — De “qual modelo é melhor?” para “o que mudou por dentro?”

**Na tela:**

> CrossCoders como microscópio de diferenças entre modelos

Subtítulo: “Da taxonomia de regressões a uma intervenção causal semanticamente interpretável.”

**Fala:** “No trabalho anterior, mostramos que era possível usar avaliação externa para localizar transições e CrossCoders para procurar diferenças internas. Agora mostramos o pipeline completo funcionando em um caso mecanístico.”

**Visual:** uma linha temporal pequena: `deck preliminar → pipeline robusto → feature 6404`.

### Slide 2 — A avaliação dá o fenômeno; o CrossCoder propõe mecanismos

**Visual em duas metades:**

**Comportamento**

- base passa / finetuned falha
- base falha / finetuned passa
- tipo de erro observado

**Representação interna**

- residuais pareados da camada 16
- features esparsas compartilhadas
- direção de decoder para intervenção

**Mensagem:** “O rótulo pass/fail localiza a diferença. A feature tenta explicá-la.”

### Slide 3 — DSTK100 representa os dois modelos no mesmo vocabulário esparso

**Números:** 2.608 textos; 617.959 tokens; 16.384 features; TopK=100; camada 16; 10.000 steps.

**Visual:** mesmos tokens entrando no base e finetuned; os residuais concatenados entram no CrossCoder; 100 features acendem.

**Nota:** destacar same-text e mesmos token IDs, evitando que diferenças de tokenização/texto sejam confundidas com diferenças de modelo.

---

## Ato 2 — O funil de descoberta

### Slide 4 — O método começa separando transições, não misturando todos os erros

**Dados:** 343 transições unilaterais: 257 melhorias e 86 regressões.

**Visual:** matriz 2×2 com `both pass`, `both fail`, `regression`, `improvement`; iluminar as duas transições unilaterais.

**Fala:** “Uma feature associada a todos os fails pode representar dificuldade geral. Queríamos features associadas à mudança entre modelos.”

### Slide 5 — “Regressão” é um resultado; o mecanismo aparece na taxonomia

**Visual:** barras das 79 regressões BigCodeBench:

- 19 truncation/token limit/extraction
- 18 lógica/output
- 11 file/path
- 11 missing name/import
- 20 outros

**Mensagem:** “Não existe uma única causa de regressão. A taxonomia define quais mecanismos procurar.”

### Slide 6 — Permutações reduzem 16.384 features a hipóteses investigáveis

**Visual:** 16.384 pontos → shortlist de features.

**Visual:** pipeline do score:

`tokens → 4 agregações → Δ FT−base → contraste observado → 200 embaralhamentos → E/V`

**As quatro agregações:** `max`, `early_max`, `mean` e `active_fraction`.

**Filtro de cobertura:** feature ativa em pelo menos `max(3 tarefas, 10% dos positivos)`.

**Score:**

`E/V = contraste observado / desvio-padrão dos contrastes após permutar os rótulos`

**Visual secundário:** uma distribuição nula em cinza produzida pelos embaralhamentos, uma linha vertical azul para o efeito observado e uma seta mostrando a distância em unidades de variabilidade.

**Mensagem de rigor:** “E/V é um score de screening, não um z-score, um p-valor ou uma prova causal. Para regressões BigCodeBench, incluir todas as quatro agregações e remover os diagnósticos auxiliares preservou exatamente o mesmo Top 10.”

### Slide 7 — Interpretabilidade exige responder “o quê?” e “quando?”

**Visual:** duas lentes sobre uma sequência de código.

**O quê?**

- tokens dominantes ponderados pela ativação
- contextos de máxima ativação
- coerência semântica entre tarefas

**Quando?**

- primeira ativação como % do código
- concentração nos primeiros 10%, 25% ou 50%
- ativação antes, durante ou depois da decisão de interesse

**Exemplo contrastivo:** feature 12956 é semanticamente clara (`expected output`, examples), mas geralmente tardia; interpretável não significa causal.

### Slide 8 — As primeiras candidatas ensinaram como evitar falsos mecanismos

**Tabela compacta:**

| Feature | Semântica | Leitura causal inicial |
|---:|---|---|
| 16383 | validação, `raise`, `ValueError` | efeito frágil e não monotônico |
| 14481 | plotting/DataFrames/constraints | ampla; steering nulo |
| 12956 | expected output/examples | legível, porém tardia |
| 8587 | literais, especialmente `0` | lexical; evidência fraca |
| 11785 | fitting/train-test | coerente em domínio restrito |

**Mensagem:** “O pipeline não foi desenhado para produzir uma história bonita; ele também eliminou histórias plausíveis.”

---

## Ato 3 — A pérola que emergiu dos dados

### Slide 9 — O maior modo de melhoria não era um algoritmo novo: era saber parar

**Número central:** `119/215 = 55%` das melhorias BigCodeBench.

**Explicação:** o base produzia uma função plausível e depois continuava com testes/imports; o finetuned frequentemente parava limpo.

**Visual:** diff real ou ilustrativo:

```diff
 def task_func(...):
     ... solução plausível ...
-
-# tests
-from task_func import task_func
```

**Fala:** “A diferença comportamental relevante não era somente capacidade algorítmica. Era controle da continuação.”

### Slide 10 — A feature 6404 conectou semântica, timing e modo de falha

**Na tela:** `expected`, `should`, assumptions, comentários, boilerplate.

**Dados:** ativa em 67% das contaminações versus 31% das outras melhorias; OR exploratório ≈ 4,44.

**Visual:** recorte da linha 6404 no dashboard: ativação por grupo, distribuição da primeira posição e tokens dominantes.

**Mensagem:** “A feature não é simplesmente ‘testes’. Ela representa uma família semântica ligada a expectativa, explicação e continuação pós-solução.”

### Slide 11 — Uma única feature forneceu um cohort mecanístico de 80 casos

**Critérios do cohort:**

1. base falhou;
2. finetuned passou;
3. a falha base continha testes/imports pós-solução;
4. a feature 6404 estava naturalmente ativa.

**Número central:** `80 casos do mesmo mecanismo observável`.

**Cuidado de linguagem:** “Isso é uma vantagem para o teste mecanístico e uma limitação para generalização. O cohort foi deliberadamente selecionado.”

---

## Ato 4 — De associação a causalidade

### Slide 12 — Intervimos somente quando a feature aparecia no TopK natural

**Visual em passos:** residual atual → CrossCoder → gate 6404 → direção base do decoder → próximo token.

**Equação:** `h′ₜ = hₜ + α z₆₄₀₄,ₜ RMS(hₜ) d₆₄₀₄,base`.

**Mensagem:** “Não injetamos a direção cegamente. A intervenção acompanha a ocorrência online da representação.”

### Slide 13 — O experimento só começou depois de reproduzir 80/80 baselines

**Visual:** selo `80/80 raw completions exatamente iguais em α=0`.

**Itens:** seed por tarefa; tokenizer base correto; backend pareado; comparação exata; avaliação oficial nos samples extraídos.

**Fala:** “Sem reprodução, qualquer diferença poderia vir do pipeline. O baseline gate transforma debugging em parte do desenho causal.”

### Slide 14 — Suprimir 6404 recuperou 19 passes e removeu 41 contaminações

**Números grandes:**

- 19/80 fail → pass oficial
- 41/80 sem testes/imports contaminantes
- α = −2

**Visual:** um caso real antes/depois, preservando o corpo da função e removendo a continuação.

**Mensagem:** “A associação semântica virou intervenção sobre o resultado efetivamente avaliado.”

### Slide 15 — Controles mostram que o efeito pertence à direção, não ao ruído

**Gráfico de barras:**

| Direção | Passes | Limpezas |
|---|---:|---:|
| 6404 | 19 | 41 |
| 9388 | 2 | 6 |
| 6757 | 3 | 6 |
| 6509 | 0 | 2 |
| sham ortogonal | 0 | 0 |

**Legenda:** controles pareados por suporte, perfil temporal, norma, especificidade e baixo cosseno; sham com mesma norma, gate, scaling, tarefas e seeds.

**Significância:** pass vs sham `p≈3,8×10⁻⁶`; limpeza vs sham `p≈9,1×10⁻¹³`; 6404 também supera cada feature pareada.

**Mensagem:** “O efeito não é explicado por perturbar o residual, usar mais energia ou simplesmente ativar algum vetor CrossCoder.”

---

## Ato 5 — A não monotonicidade é um resultado, não um inconveniente

### Slide 16 — Steering em geração autoregressiva não funciona como um botão de volume

**Visual:** curva densa da 6404. Destacar pico secundário em −0,5, pico principal em −2 e colapso em −3/−4.

**Dados-chave:**

- −0,5: 12 passes, 28 limpezas
- −2: 19 passes, 41 limpezas
- −3: 3 passes, 11 limpezas
- −4: 1 pass, 3 limpezas

**Título alternativo:** “Mais supressão pode destruir o comportamento que tentamos corrigir.”

### Slide 17 — Por que a curva pode ser tão irregular?

**Visual:** cadeia causal autoregressiva.

`Δ residual contínuo → troca discreta do próximo token → novo contexto → novos TopK/gates → trajetória diferente → pass/fail`

**Hipóteses:**

- fronteiras abruptas de top-p e ordenação de tokens;
- um token muda todo o futuro autoregressivo;
- gate da feature muda ao longo da nova trajetória;
- pass/fail é uma métrica descontínua;
- intervenção forte sai do regime natural e afeta código não relacionado;
- uma seed por tarefa torna a curva pass@1 ruidosa.

**Análises necessárias:** múltiplas seeds; probabilidade de EOS; primeiro token alterado; sequência de gates; preservação do corpo; distância até o marcador de testes.

---

## Ato 6 — Conclusão calibrada

### Slide 18 — O pipeline encontrou uma diferença interpretável e causal entre modelos

**Visual:** voltar ao funil e marcar as etapas concluídas.

**Conclusão em três linhas:**

1. A taxonomia revelou um modo de falha recorrente: continuação pós-solução.
2. O CrossCoder revelou uma feature semanticamente relacionada e naturalmente ativa nesse modo.
3. Steering gated e controles mostraram controle causal específico no cohort selecionado.

**Frase final:** “Não encontramos uma feature universal de correção. Encontramos uma representação interna que ajuda a explicar por que dois modelos se comportam de forma diferente — e mostramos que mexer nela muda o comportamento.”

### Slide 19 — O próximo teste é separar mecanismo de generalização

**Roadmap:**

- replicação multi-seed perto de −0,5 e −2;
- cohort negativo sem contaminação;
- split de seleção e avaliação;
- auditoria token-level;
- repetir o método em outro mecanismo, como a feature 11785 em tarefas de ML.

---

## Ordem recomendada dos visuais

1. Diagrama original do deck preliminar adaptado de camada 12/base–merged para camada 16/base–finetuned.
2. Matriz de transições.
3. Taxonomia dos erros.
4. Funil de screening PR-AUC.
5. Dashboard interpretativo recortado.
6. Diff de contaminação.
7. Diagrama de steering TopK-gated.
8. Antes/depois real.
9. Barras de controles.
10. Curva de não monotonicidade.

## O que reaproveitar do deck preliminar

- A oposição “avaliação externa mostra o que mudou / CrossCoder pergunta onde isso está representado”.
- A explicação simples de espaço esparso compartilhado.
- A sequência avaliação → ativação → CrossCoder → steering.

## O que atualizar ou remover

- Trocar modelo merged e camada 12 pelo experimento canônico DeepSeek base–finetuned, camada 16.
- Trocar Feature 962 pela trajetória real de investigação e pela Feature 6404.
- Substituir “correctness gain score” genérico pelo screening com transições, PR-AUC, suporte e análise temporal.
- Não apresentar steering como causal por si só; apresentar reprodução, gate, sham e features pareadas como pacote de evidência.
- Não abrir com números agregados de acurácia do estudo antigo; abrir com a pergunta de model diffing e o modo de falha descoberto.
