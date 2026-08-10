# DSTK100 — interpretação das features já testadas

> Conclusão: o DSTK100 contém features semanticamente legíveis, mas as candidatas selecionadas por pass/fail são majoritariamente marcadores lexicais, de domínio ou de estilo. Até agora nenhuma fornece uma explicação robusta e geral de correção de código.

## Critério

A avaliação separa coerência semântica, especificidade entre modelos, precedência temporal e validação causal. Uma feature só explica pass/fail em sentido forte quando as quatro convergem.

| Feature | Hipótese pelos máximos | Coerência | Especificidade | Precedência | Causalidade |
|---:|---|---|---|---|---|
| 16383 | input validation / raise ValueError | alta | baixa | moderada | promissora, ainda frágil |
| 14481 | mixed plotting/dataframe/constraints | baixa–moderada | baixa | moderada | nula |
| 12956 | Expected output / example usage | muito alta | alta na ativação por texto FT | muito baixa | nula |
| 6404 | boilerplate assumptions/caveats | alta | moderada na ativação FT | baixa | inespecífica |
| 8587 | numeric literals, especially zero | alta, mas lexical | moderada | baixa | inconclusiva |
| 8294 | Python-language meta commentary | alta | moderada | baixa–moderada | nula |
| 11785 | model fitting / train-test regression | alta em domínio restrito | baixa | moderada | nula |

## Leitura por feature

### 16383 — input validation / raise ValueError

Feature coerente de validação; não explica diretamente as duas correções funcionais.

- Coerência semântica: alta.
- Especificidade base × finetuned: baixa.
- Precedência em relação à decisão: moderada.
- Evidência causal atual: promissora, ainda frágil.

### 14481 — mixed plotting/dataframe/constraints

Contextos heterogêneos e nenhum braço corrigiu tasks.

- Coerência semântica: baixa–moderada.
- Especificidade base × finetuned: baixa.
- Precedência em relação à decisão: moderada.
- Evidência causal atual: nula.

### 12956 — Expected output / example usage

Excelente explicação de estilo tardio; não parece mecanismo de falha.

- Coerência semântica: muito alta.
- Especificidade base × finetuned: alta na ativação por texto FT.
- Precedência em relação à decisão: muito baixa.
- Evidência causal atual: nula.

### 6404 — boilerplate assumptions/caveats

Boilerplate tardio; steering constante mudou tasks sem especificidade de direção.

- Coerência semântica: alta.
- Especificidade base × finetuned: moderada na ativação FT.
- Precedência em relação à decisão: baixa.
- Evidência causal atual: inespecífica.

### 8587 — numeric literals, especially zero

Detector de números/zero; evidência principal contaminada por flakiness.

- Coerência semântica: alta, mas lexical.
- Especificidade base × finetuned: moderada.
- Precedência em relação à decisão: baixa.
- Evidência causal atual: inconclusiva.

### 8294 — Python-language meta commentary

Meta-comentários sobre Python; suporte regressivo HumanEval+ muito pequeno.

- Coerência semântica: alta.
- Especificidade base × finetuned: moderada.
- Precedência em relação à decisão: baixa–moderada.
- Evidência causal atual: nula.

### 11785 — model fitting / train-test regression

Feature de fitting/regressão, não uma direção geral de correção.

- Coerência semântica: alta em domínio restrito.
- Especificidade base × finetuned: baixa.
- Precedência em relação à decisão: moderada.
- Evidência causal atual: nula.

## Implicação metodológica

Os exemplos confirmam que `feature interpretável` não equivale automaticamente a `mecanismo do erro`. A 12956 é o melhor exemplo positivo de interpretabilidade e negativo de relevância causal: seu conceito é claro, mas ocorre depois da implementação. A 16383 é a única candidata causal promissora, porém sua semântica dominante (validação/exceções) não coincide claramente com as mudanças que corrigiram /138 e /259.

O próximo passo fiel à literatura é formular prompts específicos para cada hipótese semântica e testar steering positivo/negativo fora das tasks usadas no screening. Para pass/fail, também precisamos de features cuja ativação máxima esteja sobre decisões funcionais, não em comentários, números genéricos ou boilerplate.

## Artefatos

- `top_activating_contexts.csv`: 50 máximos por feature.
- `top_active_tokens.csv`: tokens ponderados por ativação.
- `feature_task_statistics.csv`: ativação, primeira posição e contribuição por texto.
- `feature_geometry.csv`: geometria encoder/decoder entre os modelos.
- `feature_dashboard.png`: resumo visual.
