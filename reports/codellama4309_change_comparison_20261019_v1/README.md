# CodeLlama feature 4309 versus shuffled directions at magnitude five

This CPU-only analysis compares saved official evaluations for the same 50 tasks and alpha-zero baseline. No new generations or evaluations were run. The primary comparison is target alpha -5 against three shuffled directions at alpha -5; positive shuffle arms are an additional sensitivity analysis. See METHOD.json and the script for exact criteria.

| Observable | Target 4309 -5 | Shuffle 1 -5 | Shuffle 2 -5 | Shuffle 3 -5 |
|---|---:|---:|---:|---:|
| Changed evaluated programs | 27 | 21 | 19 | 19 |
| Changed main-function AST | 24 | 17 | 14 | 17 |
| Changed code, unchanged main-function AST | 3 | 4 | 5 | 2 |
| Official corrections | 2 | 1 | 0 | 0 |
| Fewer recorded failures, still not passing | 2 | 2 | 3 | 2 |
| More recorded failures | 4 | 5 | 3 | 3 |
| Return-only bodies expanded to multiple executable statements | 3 | 0 | 0 | 0 |
| Explicit value-return removed | 6 | 0 | 1 | 1 |
| Main body reduced to no executable statements | 2 | 0 | 0 | 0 |

Rows are nonexclusive. AST changes are syntactic, not a semantic correctness classifier. An unchanged main-function AST does not rule out meaningful changes in globals, imports, or helper functions. Counts of test failures are descriptive and not interchangeable with distance to the intended specification. All reported reductions/increases for the target and negative shuffles here compare individually recorded test failures, not globally blocked suites.

## Evidence from code inspection

- **/183, target pass:** replaces a one-line response return with response construction, UUID header assignment, and return; removes double serialization in this implementation. Five recorded failures become zero.
- **/490, target pass:** expands `return xmltodict.parse(s)` into parse, write JSON to the requested file, and return. One recorded failure becomes zero.
- **/634, target fail:** also expands a return-only body, but into repeated `itertools.chain` assignments without a useful return. Structural expansion is therefore not sufficient for repair.
- **/423, target still fails:** moves file/threshold validation before processing; recorded failures decrease from five to three, but the return expression remains invalid. Every negative shuffle also reduces five failures to three on this task. This partial change is not target-specific.
- **/878, target still fails:** recorded failures decrease from seven to five, but malformed exception names and repetitive validation remain. Shuffle 3 -5 and shuffle 2 +5 produce the same main-body rewrite. Fewer failures do not imply coherent implementation.
- **/875, target worsens:** removes missing-value filling and the value return; recorded failures rise from two to seven.
- **/841 and /931:** target leaves the main body with no executable statement beyond the docstring. These are deteriorations, not useful simplifications.
- **/119, shuffle 1 -5 pass:** repairs Matplotlib API calls. The plotted values still describe a straight line rather than the named parabola, illustrating that an official pass is not proof of complete semantic fidelity. Shuffle 2 -5 produces a parabola with corrected APIs but retains one recorded test failure.

## Interpretation

The target's strongest distinctive observation is two concrete, task-specific repairs absent from all six shuffled arms, rather than a general dominance over shuffled directions across all changes. The three return-only expansions occur only under the target among these seven arms, but one is an unsuccessful repetitive rewrite. This is an exploratory, post-hoc structural observation on the discovery cohort, not a validated general feature meaning or a significance test.

The other 25 changed target programs do not support a claim that the feature broadly improves code: two have fewer recorded failures, four have more, and nineteen have the same failure count. Three of the 27 retain the main-function AST. Controls also produce partial improvements and deteriorations. Consult ALL_CHANGED_MAIN_BODIES.md for every changed program and its saved evaluation evidence.
