# Traditional steering smoke test: feature 2562

## Result

Negative traditional steering of CrossCoder feature 2562 changed most
generations but did not recover any selected DeepSeek fine-tuned regression.
It also preserved all selected controls.

| Alpha | Regression passes | Alpha-0 passing controls |
|---:|---:|---:|
| 0.0 | 0/5 | 5/5 |
| -1.5 | 0/5 | 5/5 |
| -2.0 | 0/5 | 5/5 |
| -3.0 | 0/5 | 5/5 |
| -4.0 | 0/5 | 5/5 |

There were no verdict transitions in either direction.

## Experimental design

- Model: `JetBrains/deepseek-coder-6.7B-kexer`.
- CrossCoder: DeepSeek base versus fine-tuned, layer 16, 16,384 latents.
- Feature: 2562, fine-tuned-side decoder direction.
- Hypothesis: increased feature-2562 contribution is associated with
  base-pass/fine-tuned-fail regressions, so negative steering may remove a
  harmful fine-tuning behavior.
- Intervention:
  `h_last' = h_last + alpha * decoder_finetuned[:, 2562]`.
- Doses: `0`, `-1.5`, `-2`, `-3`, `-4`.
- Generation: 512 maximum new tokens, temperature 0.2, top-p 0.95, and
  per-task paper-v1 seeds.
- Evaluation: extraction/postprocessing v4 and the official BigCodeBench 0.1.5
  execution harness.

Regression tasks:
`134, 238, 133, 1010, 623`.

Passing controls:
`877, 923, 454, 106, 362`.

Ten historical regressions and twenty historical preserved successes were
first regenerated at `alpha=0`. Four historical regressions passed in the new
control and were excluded from a fail-to-pass experiment. The final regressions
are the five largest-differential candidates that actually failed at the new
control. The final controls all actually passed at the new control.

## Intervention diagnostics

The decoder direction norm is `0.6653689`.

| Alpha | Mean projection shift | Mean intervention/residual norm |
|---:|---:|---:|
| -1.5 | -0.998 | 0.80% |
| -2.0 | -1.331 | 1.07% |
| -3.0 | -1.996 | 1.60% |
| -4.0 | -2.661 | 2.13% |

Mean layer-16 residual norm was approximately 128. The DeepSeek residual scale
is therefore about three times the CodeLlama residual scale observed in the
8994 and 11586 tests. Despite the relatively small norm ratio, 7-8 of the 10
completions changed at every tested dose, including almost every regression.
None of those trajectory changes altered a verdict.

## Validation and limitations

- All 40 nonzero generations and 30 candidate controls completed.
- All 70 postprocessed programs compiled without requiring deterministic
  repair.
- The `alpha=0` arm bypassed the hook.
- Nonzero arms modified only the final hidden token and reset the original RNG
  seed independently per task.
- Historical transition labels were used only to form the candidate pool.
  Final causal groups were conditioned on the newly evaluated `alpha=0`.
- Feature 2562 also increased in some historical preserved successes, so it
  may reflect a general fine-tuning behavior rather than a failure-specific
  cause.

## Interpretation

The tested suppression range provides no evidence that directly subtracting
the feature-2562 decoder direction repairs DeepSeek fine-tuning regressions.
Unlike the CodeLlama experiments, the largest intervention was only 2.13% of
the residual norm and caused no control damage. A limited follow-up at `-6`
and `-8` would match the 3-4% relative range already tested for CodeLlama and
is scientifically defensible. It should be treated as a final scale check, not
as an open-ended alpha search.

If that scale-matched check remains null, the combined traditional-steering
evidence favors changing intervention type to activation-matched clamping
rather than testing more constant decoder-vector doses.

## Artifacts

- `pass_rate_by_alpha.png`
- `task_level_results.csv`
- Full generations, postprocessed code, evaluator outputs, and selection
  evidence are stored under `runs/steering_feature_2562_traditional/` and in
  the paper-v1 bucket.

