# CodeLlama 4309 — exploratory behavioral hypothesis analysis

## Bottom line

The current evidence supports **specific causal repairs in /183 and /490**, with exact changes matching their functional contracts. It does **not** establish that 4309 is a general detector of incomplete implementations or that its natural activation explains the 50 base-to-merged regressions.

The analyses below deliberately retain negative results and counterexamples. They use existing codes/activations only: no GPU inference, new generations, new steering directions or model training were performed. The manuscript and slides were not changed.

## 1. Hypothesis and operational indicators

The two complete alpha-minus-five successes motivated the hypothesis: suppressing 4309 can replace a short return-only answer with a fuller implementation that carries out required operations.

We operationalize the hypothesis through AST proxies:

- **Return-only:** after removing the docstring, `task_func` has exactly one top-level executable statement, which is `return`.
- **No value return:** no syntactic non-None return in the main body, excluding nested function definitions. This does not imply incorrectness when the task expects side effects or None.
- **Potential fallthrough:** a conservative structural check cannot establish that all paths terminate in return/raise. This is not a complete control-flow proof.
- **Repeated statements:** an identical top-level AST statement occurs at least three times. This does not detect all repetition.
- Parameter usage, main-body statement count and call names are recorded as additional descriptive attributes.

These indicators are **not a validated correctness classifier**. For example, the passing base solution for /738 is legitimately return-only. Passing base solutions /119, /604 and /629 have no explicit value return because their required behavior does not depend on returning a non-None value.

## 2. Natural base-versus-merged behavior

Natural feature summaries use the original frozen same-text activation corpus and the exact corresponding source programs. The unit is a generated program jointly encoded by the CrossCoder, not a separate latent activation belonging to each model on identical input.

| Indicator | Passing base text /50 | Failing merged text /50 | Base /48 excluding discovery | Merged /48 excluding discovery |
|---|---:|---:|---:|---:|
| Return-only | 1 | 7 | 1 | 5 |
| No explicit value return | 3 | 17 | 3 | 17 |
| Potential fallthrough | 4 | 23 | 4 | 23 |
| Repeated top-level statements | 0 | 1 | 0 | 1 |

The merged outputs exhibit more of these structural patterns. This describes their behavior under the fixed generation/extraction protocol; it does not show that these patterns are caused by one feature, nor distinguish every semantic omission from generation-budget limitations.

The discovery tasks /183 and /490 are excluded from the 48-case sensitivity analysis. Those 48 cases nevertheless belong to the same original screening cohort: this is **not an independent held-out validation dataset**.

## 3. Does natural activation identify the structural pattern outside discovery?

Only four of the remaining 48 tasks newly become return-only in merged text. We compare each task's merged-text minus base-text activation summary between these four and the other 44 tasks.

| Summary | E/V, new-return-only versus other tasks |
|---|---:|
| Mean activation delta | +0.015 |
| Maximum activation delta | -0.527 |
| Active-fraction delta | +0.841 |
| Newline-conditioned mean activation delta | -0.094 |

These exploratory contrasts **do not provide strong evidence of an association** between this general structural hypothesis and 4309 activation outside the discovery examples. The small positive group also limits the strength of any negative conclusion. We do not interpret this as proof of no association.

E/V here uses 2,000 label permutations and one pre-existing feature. The data include 40 exploratory contrasts across scopes, indicators and summaries. Nominal p-values are recorded separately and are **not multiplicity corrected**; no significance claim is made.

Across all 50 paired tasks, mean activation averaged over tasks is approximately **0.1997 on base-generated text and 0.1979 on merged-generated text**. Thus the feature is not generally more active in the failing text across this cohort.

There is a possible structural confound: on the 48 merged texts, Spearman correlation is approximately **0.353** between mean activation and newline-token fraction, and **0.392** between active fraction and newline-token fraction. These are moderate descriptive associations, not proof that whitespace fully explains the feature. The feature's already observed concentration of activation mass on newlines (about 81% on merged text) motivates this check.

The discovery examples themselves are compatible with the hypothesis but are insufficient confirmation:

| Task | Mean activation: base text | Mean activation: merged text | Mean activation conditional on newline: base | Conditional on newline: merged |
|---|---:|---:|---:|---:|
| /183 | 0.0887 | 0.2396 | 0.9315 | 4.5525 |
| /490 | 0.1866 | 0.3051 | 1.3710 | 3.3566 |

The maximum activation is not consistently higher in merged: for /490 it falls from 4.385 to 3.357. A broad statement that every activation metric marks the failing variant would therefore be incorrect.

## 4. Does steering change the hypothesized behavior more than controls?

All comparisons in this section use the same re-extraction path for the alpha-zero baseline and each intervention. Frozen capture code is not substituted for the intervention baseline.

At magnitude five:

- **Target 4309, negative:** 27/50 evaluated programs change; 2/50 pass.
- The target expands three return-only functions into more than one executable statement: **/183 and /490 pass; /634 still fails**.
- None of the six shuffle arms or three random-latent arms expands a return-only function by this definition.
- The target additionally turns /931 into an empty executable body after its docstring. This is **not** counted as implementation expansion. One random latent also removes the return-only body on /931.
- In /634, the added statements are repeated `input_list = itertools.chain(input_list)` operations without a useful returned result. Expansion alone is therefore not improvement.
- Statement-count increases are not specific: the target increases statement count in ten tasks, and one shuffle also does so in ten tasks. The useful distinction is the kind of rewrite and its observed contract/test outcome, not code volume alone.

The rewritten functions suggest a local implementation-structure effect, but the third expansion and the empty-body case show why it cannot be labeled universally beneficial.

## 5. Concrete contract-pattern indicators, plus counterexamples

We inspect four task-specific operation checklists, based on their previously saved prompts, official tests and reference code. The first two are the discovery examples. The two additional cases were inspected after formulating the hypothesis and are therefore exploratory follow-up, not a preregistered test set.

| Task | Observed contract-related patterns | Base | Merged baseline | Target -5 |
|---|---|---|---|---|
| /183, discovery | UUID header assignment; no second JSON serialization of the supplied JSON string | present | absent | restored |
| /490, discovery | JSON file persistence | present | absent | restored |
| /206, additional | CSV-to-JSON persistence | present | absent | still absent |
| /630, additional | JSON persistence in records orientation | present | wrong orientation | still wrong; file destination removed |

These are AST pattern indicators, **not semantic proofs** of the entire functional contract. The two discoveries are additionally supported by their actual official fail-to-pass transitions. None of the six shuffles or three random latent controls corrects either discovery task at magnitude five; their official correction is /119 instead.

The additional examples prevent a broader serialization/file-writing interpretation:

- **/206:** the target retains the erroneous CSV writer on a read-only input file; it does not restore JSON conversion.
- **/630:** merged originally calls `df.to_json(filename)`, writing the wrong JSON orientation. The target changes this to `df.to_json(indent=4)` and still returns a filename, removing the actual file destination. This is a concrete deterioration of a required operation, even though the task was already failing.

## 6. Interpretation and next discriminating test

The most defensible current interpretation is:

> Feature-4309's decoder direction can causally change implementation structure. In two tasks this restores omitted or mishandled output operations, but neither the natural-activation analysis nor the wider intervention results establish a general incomplete-implementation feature or a single mechanism explaining CodeLlama regressions.

The natural-activation evidence remains dominated by line boundaries. On the frozen /183 and /490 merged codes, the only active token is the final newline after the short return. Continuous additive steering is already active before that token and changes earlier choices; the outcome does **not** demonstrate natural activation-gated mediation.

A useful next test, not performed here, would freeze the common prompt/prefix and compare next-token/log-likelihood effects of the target and controls on `return` versus an assignment/multi-statement continuation, then limit steering to the initial implementation decision. This would discriminate a structural direction hypothesis from an error-detector hypothesis. Any claims of generalization require new tasks and/or seeds.

## Files and reproduction

- `01_structure_and_newline_confound`: structural prevalence and the newline confound.
- `02_return_only_activation_contrast`: activation differences outside the two discovery tasks.
- `03_intervention_rewrites_and_contracts`: target/control rewrites and contract-pattern indicators.
- `natural_program_features.json`, `paired_behavior_activation.csv`: complete source-level and paired statistics.
- `intervention_behavior_details.json` / `intervention_behavior_summary.csv`: all 500 task-arm observations across the target and nine controls.
- `inspected_contract_patterns.json`: task/version checklists, including every control.
- `exploratory_associations.json`, `structural_correlations.json`, `SUMMARY.json`, `METHOD.json`: calculations, provenance and limitations.

Run from the repository root:

```bash
.venv/bin/python tools/analyze_4309_behavior_hypothesis_v1.py
```

The script reads existing official outcomes; it never executes generated code or produces new generations. Basic AST fixtures were checked for return-only, docstring-only and nested-helper cases. The analysis is exploratory and was not independently human annotated.
