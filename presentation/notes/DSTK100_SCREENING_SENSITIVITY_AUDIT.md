# DSTK100 — auditoria de sensibilidade dos critérios de screening

## Escopo

Tabela canônica completa: 262.144 linhas = 16.384 features × 4 agregações × 2 benchmarks × 2 direções de transição.

Comparações feitas após deduplicar feature ID pela linha de maior `effect_to_permutation_variability`, reproduzindo o critério de desempate do screening original.

## Resultado principal: regressões BigCodeBench

O Top 10 foi invariável em todas as seguintes especificações:

1. Pipeline canônico: `max/early_max` + efeito positivo + ROC-AUC > 0,55 + suporte mínimo.
2. Todas as agregações, mantendo os demais filtros.
3. Somente efeito/variabilidade em `max/early_max`.
4. Somente efeito/variabilidade em todas as quatro agregações.
5. Efeito positivo + suporte, sem ROC.
6. Efeito positivo + ROC, sem suporte.
7. Apenas efeito positivo, sem ROC nem suporte.

| Rank | Feature | Agregação | E/V | Efeito | ROC-AUC | Suporte |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 8587 | max | 4,723 | 7,154 | 0,580 | 54/79 |
| 2 | 6404 | max | 4,465 | 6,596 | 0,641 | 47/79 |
| 3 | 12956 | max | 3,990 | 5,030 | 0,636 | 74/79 |
| 4 | 8959 | max | 3,859 | 2,805 | 0,605 | 77/79 |
| 5 | 6684 | max | 3,856 | 2,304 | 0,574 | 79/79 |
| 6 | 9716 | max | 3,774 | 3,572 | 0,638 | 72/79 |
| 7 | 14818 | max | 3,713 | 3,824 | 0,602 | 74/79 |
| 8 | 15246 | max | 3,710 | 2,105 | 0,624 | 48/79 |
| 9 | 2449 | max | 3,659 | 3,078 | 0,573 | 63/79 |
| 10 | 10967 | early_max | 3,611 | 0,720 | 0,598 | 66/79 |

Conclusão específica: para regressões BigCodeBench, os filtros adicionais não determinaram a entrada da 6404 nem alteraram o Top 10. A 6404 seria a segunda colocada usando somente efeito/variabilidade.

## Redundância entre métricas

Correlação de Spearman calculada sobre todas as linhas `max/early_max`:

| Caso | Efeito × E/V | ROC × E/V | Efeito × ROC | Suporte × E/V |
|---|---:|---:|---:|---:|
| BigCodeBench regressão | 0,999 | 0,599 | 0,594 | 0,145 |
| BigCodeBench melhoria | 0,998 | 0,820 | 0,818 | −0,605 |
| HumanEval+ regressão | 0,999 | 0,742 | 0,736 | −0,092 |
| HumanEval+ melhoria | 0,998 | 0,739 | 0,733 | 0,397 |

O contraste bruto e efeito/variabilidade são empiricamente quase equivalentes em ranking neste dataset. Isso ocorre porque E/V é o efeito dividido pelo desvio-padrão da distribuição nula de permutação, e esse denominador variou de maneira aproximadamente proporcional à escala dos efeitos.

O filtro `efeito > 0` também é matematicamente redundante quando o ranking procura os maiores valores positivos de E/V: como o desvio-padrão é não negativo, efeito e E/V têm o mesmo sinal. O filtro continua útil para declarar explicitamente a direção da hipótese.

ROC-AUC não é idêntica a E/V. A correlação foi apenas moderada nas regressões BigCodeBench (ρ=0,599), mas o limiar 0,55 não alterou o Top 10 porque todas as dez primeiras por E/V já o superavam.

Suporte é a métrica conceitualmente mais distinta, mas também não alterou o Top 10 de regressões BigCodeBench porque as features líderes tinham suporte muito acima do mínimo de 8/79.

## Inclusão de `mean` e `active_fraction`

Sobreposição do Top 10 canônico com o Top 10 incluindo todas as agregações:

| Caso | Features preservadas | Mudança |
|---|---:|---:|
| BigCodeBench regressão | 10/10 | nenhuma |
| BigCodeBench melhoria | 1/10 | muito grande |
| HumanEval+ regressão | 4/10 | grande |
| HumanEval+ melhoria | 8/10 | pequena |

Nas melhorias BigCodeBench, as primeiras posições com todas as agregações foram dominadas por `mean` e `active_fraction`:

| Rank | Feature | Agregação | E/V | ROC-AUC | Suporte |
|---:|---:|---|---:|---:|---:|
| 1 | 2 | active_fraction | 6,769 | 0,635 | 215/215 |
| 2 | 4383 | active_fraction | 6,427 | 0,627 | 215/215 |
| 3 | 6895 | mean | 6,289 | 0,624 | 202/215 |
| 4 | 13631 | active_fraction | 6,075 | 0,621 | 196/215 |
| 5 | 10532 | mean | 6,070 | 0,627 | 198/215 |
| 6 | 8792 | mean | 5,776 | 0,611 | 211/215 |
| 7 | 9741 | active_fraction | 5,694 | 0,615 | 215/215 |
| 8 | 9600 | active_fraction | 5,634 | 0,617 | 204/215 |
| 9 | 16106 | active_fraction | 5,628 | 0,608 | 212/215 |
| 10 | 1395 | mean | 5,623 | 0,611 | 199/215 |

Isso mostra que `mean/active_fraction` não são versões neutras de `max/early_max`. Elas favorecem features persistentes e amplamente ativas, enquanto `max/early_max` favorecem eventos localizados e potencialmente mais adequados a intervenções mecanísticas.

## Sensibilidade dos filtros por caso

Sobreposição entre Top 10 canônico e Top 10 apenas por E/V em `max/early_max`:

| Caso | Sobreposição |
|---|---:|
| BigCodeBench regressão | 10/10 |
| BigCodeBench melhoria | 2/10 |
| HumanEval+ regressão | 7/10 |
| HumanEval+ melhoria | 10/10 |

Nas melhorias BigCodeBench, a diferença vem principalmente do filtro ROC: remover ROC, mantendo suporte, produz o mesmo Top 10 que usar apenas E/V. Nas regressões HumanEval+, o suporte mínimo é relevante: removê-lo troca três posições, coerente com haver somente sete positivos.

## Interpretação metodológica

Para o caso que levou à 6404, é correto dizer:

> A shortlist foi robusta às escolhas de agregação e aos filtros auxiliares. O ranking por efeito/variabilidade sozinho teria recuperado exatamente o mesmo Top 10, incluindo a 6404 em segundo lugar.

Não é correto generalizar isso para todo o screening:

> Em outros benchmarks e direções de transição, sobretudo melhorias BigCodeBench, agregação, ROC e suporte mudam substancialmente quais features aparecem no topo.

Recomendação para apresentação e relatório:

1. Tratar E/V como o score principal de ranking.
2. Tratar direção do efeito, ROC e suporte como guardrails diagnósticos, não como quatro evidências independentes.
3. Explicar que `max/early_max` incorporam uma preferência mecanística por ativações localizadas/precoces.
4. Mostrar `mean/active_fraction` como análise de sensibilidade e como detectores de features persistentes, não misturá-las silenciosamente no mesmo ranking.
5. Para estudos futuros, definir a família de agregações antes de olhar o resultado ou corrigir estatisticamente a escolha entre agregações.
