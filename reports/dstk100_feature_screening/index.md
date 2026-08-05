# DSTK100 feature screening for steering

This screen uses the canonical 10,000-step DSTK100 checkpoint and all 1,304
paired tasks (164 HumanEval+ and 1,140 BigCodeBench). For every task, both the
base-generated and finetuned-generated code were forwarded through both models
with identical tokens. Layer-16 residuals were RMS-normalized and encoded with
the checkpoint's exact ReLU + TopK-100 rule.

The primary score is the change in a latent aggregate between the
finetuned-generated text and the base-generated text. Regression analysis is
conditioned on the base solution passing; improvement analysis is conditioned
on the base solution failing. This avoids conflating transition directions.

## Recommended first steering targets

| Use | Feature | Benchmark | Aggregate | ROC-AUC | PR-AUC lift | Effect / permutation variability | Support |
|---|---:|---|---|---:|---:|---:|---:|
| Remove a failure-associated feature | 8587 | BigCodeBench | max | 0.580 | 1.50x | 4.72 | 54/79 regressions |
| Remove a failure-associated feature | 6404 | BigCodeBench | max | 0.641 | 1.37x | 4.47 | 47/79 regressions |
| HumanEval+ fast smoke test | 11785 | HumanEval+ | max | 0.770 | 5.23x | 4.04 | 4/7 regressions |
| Remove a broadly supported feature | 12956 | BigCodeBench | max | 0.636 | 1.49x | 3.99 | 74/79 regressions |
| Early-token intervention | 8294 | HumanEval+ | early max | 0.707 | 4.28x | 3.92 | 3/7 regressions |
| Add an improvement-associated feature | 4833 | HumanEval+ | early max | 0.764 | 1.66x | 4.23 | 41/42 improvements |

For the first causal smoke test, use **11785 with negative steering** on
HumanEval/49, HumanEval/39, HumanEval/127, and HumanEval/18. It offers a short,
cheap test, but its sample is small. The stronger coverage test is **8587 with
negative steering** on its highest-delta BigCodeBench regressions, including
BigCodeBench/140, /1032, /689, /133, and /134. Feature **4833 with positive
steering** is the best opposite-direction control/hypothesis.

## Statistical interpretation

- Effect/variability is the observed mean transition contrast divided by its
  standard deviation under 200 within-case label permutations (seed 42).
- The reported permutation p-values are nominal, not max-statistic corrected.
  With 16,384 searched features they are screening evidence, not discoveries.
- HumanEval+ has only seven regressions. Its high AUC/lift values are useful for
  selecting a smoke test but are intrinsically unstable.
- Decoder norm specificity for the leading features is approximately 0.50.
  They are shared CrossCoder directions, not cleanly finetuned-only directions.
  Steering should use the decoder vector for the model side being generated.
- Since TopK=100 of 16,384, P50-P99 tokenwise feature percentiles are usually
  zero. Max, active fraction, and early max are the appropriate aggregates.

## Causal-test requirements

Use the original generation configuration, reproduce each unsteered baseline,
apply negative alpha to regression candidates and positive alpha to improvement
candidates, and include random same-norm/sham controls. Report code-change rate,
pass/fail transitions, and qualitative code diffs. Correlation in this screen
does not determine whether a feature is a cause, consequence, or detector of
the generated behavior.

Artifacts:

- `top_feature_candidates.csv`: compact ranked candidates.
- `candidate_task_evidence.csv`: strongest concrete transition tasks.
- `all_feature_statistics.csv`: full 50 MB table (keep outside Git or use a
  versioned artifact store).
- `run_summary.json`: exact checkpoint, coverage, score definition, seed, and
  permutation count.
