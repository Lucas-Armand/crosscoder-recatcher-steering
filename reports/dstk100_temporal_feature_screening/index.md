# DSTK100 — screening temporal

Máscara: tokens do `candidate_code_repaired` avaliados pela extraction v4; prompt/padding e pares não finitos excluídos. Não é cobertura dinâmica de execução.

Foram usados 1.304 pares de tasks, TopK-100 exato, 500 permutações e maxT dentro de benchmark × transição sobre 16.384 features e oito métricas temporais.

## Leitura principal

- Regressão BigCodeBench: 8587 (`discounted_max`, maxT p=0,0439) e 16383 (`q10_max`, p=0,0459) passam 5%; 14481 fica limítrofe (p=0,0519).
- 8587 tem contraste distribuído/tardio e sua evidência anterior foi contaminada por flakiness do avaliador. 16383 e 14481 concentram o contraste nos primeiros 10%, sendo melhores testes de causalidade precoce.
- 12956 não entra no top temporal (melhor p maxT=0,5968), consistente com a ativação natural tardia e o gated steering nulo.
- 6404 mantém associação global (melhor p maxT=0,0918), mas sem prioridade temporal; combina com o efeito inespecífico do steering constante.
- Regressão HumanEval+: nenhum sinal sobrevive maxT; 8294 é o primeiro nominal, porém p=0,511 e suporte=3.
- Melhoria BigCodeBench: várias features de `future_exposure` passam maxT, mas muitas têm contraste maior na segunda metade; isso sugere marcadores persistentes/estilo, não necessariamente decisões iniciais.
- Melhoria HumanEval+: 4833 é o sinal precoce mais convincente (`q25_max`, p=0,006; pico 15–20%; suporte=41).

## Próximo experimento sugerido

1. Regressão mecanística: suppression/clamp gated das features 16383 e 14481 nas regressões BigCodeBench com ativação natural dentro dos primeiros 10%; usar várias tasks, baseline reproduction gate e shams pareados.
2. Teste de direção útil: steering positivo da 4833 no lado apropriado do modelo em HumanEval+ base-fail → finetuned-pass, começando pelas tasks 69, 128, 61, 153 e 113. Separar estudo mecanístico de qualquer claim de generalização.
3. Não priorizar novo teste da 12956; o resultado gated já explica o sucesso do steering constante como perturbação direcional precoce, não remoção da ativação natural.

## Artefatos

- `all_temporal_feature_statistics.csv`: todas as features/métricas.
- `temporal_feature_candidates.csv`: ranking conservador.
- `candidate_temporal_profiles.csv`: perfis em 20 bins.
- `temporal_profile_*.png`: mapas de contraste temporal.
