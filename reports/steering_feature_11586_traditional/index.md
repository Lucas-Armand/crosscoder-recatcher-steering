# Traditional steering smoke test: feature 11586

## Result

Positive traditional steering of CrossCoder feature 11586 did not recover any
of the five strongest selected CodeLlama merged regressions.

| Alpha | Regression passes | Alpha-0 passing controls |
|---:|---:|---:|
| 0.0 | 0/5 | 5/5 |
| 1.5 | 0/5 | 4/5 |
| 2.0 | 0/5 | 4/5 |
| 3.0 | 0/5 | 4/5 |
| 4.0 | 0/5 | 4/5 |

Task 861 was the only control damaged at every nonzero dose. At alphas 3 and 4,
regression task 536 changed text but remained incorrect. No selected regression
underwent a `fail -> pass` transition.

## Experimental design

- Model: `DevQuasar-5/coma-7B-v0.1` (CodeLlama merged).
- CrossCoder: CodeLlama base versus merged, layer 16, 16,384 latents.
- Feature: 11586, merged-side decoder direction.
- Intervention:
  `h_last' = h_last + alpha * decoder_merged[:, 11586]`.
- Doses: `0`, `1.5`, `2`, `3`, `4`.
- Generation: 512 maximum new tokens, temperature 0.2, top-p 0.95, and
  per-task paper-v1 seeds.
- Evaluation: extraction/postprocessing v4 and the official BigCodeBench 0.1.5
  execution harness.

Regression tasks:
`135, 536, 983, 504, 841`.

Passing controls:
`861, 1109, 272, 455, 827`.

The regression tasks are the five largest historical negative differentials
for feature 11586. Controls were selected only after passing a newly generated
`alpha=0` arm. Of the first ten historical both-pass candidates, only tasks 861
and 1109 passed the new control. Six remaining historical both-pass tasks were
then generated and all six passed, allowing a valid five-control sample.

## Intervention diagnostics

The decoder direction norm is `0.6226296`.

| Alpha | Mean projection shift | Mean intervention/residual norm |
|---:|---:|---:|
| 1.5 | 0.934 | 2.23% |
| 2.0 | 1.245 | 2.98% |
| 3.0 | 1.868 | 4.48% |
| 4.0 | 2.491 | 5.97% |

Mean layer-16 residual norm was approximately 42.3. The intervention therefore
reached a meaningful scale and changed multiple generation trajectories without
rescuing a regression.

## Validation and limitations

- All 40 nonzero generations and all required control generations completed.
- The `alpha=0` arm bypassed the hook.
- The intervention acted only on the last hidden token in each autoregressive
  forward.
- Each nonzero arm reset the original RNG seed independently per task.
- Postprocessing v4 produced compilable code for all ten strong-smoke tasks at
  every nonzero alpha and flagged no suspicious repair.
- Historical both-pass status was poorly reproducible under the current
  sampling runner. Controls in the final causal comparison were therefore
  restricted to tasks that actually passed the new `alpha=0`.
- The feature was selected using historical encoder-side contribution
  differences. Direct decoder-vector steering is related to, but not equivalent
  to, restoring the historical joint CrossCoder latent.

## Interpretation

This experiment gives no evidence that adding the feature-11586 decoder
direction causally restores CodeLlama merged performance. Increasing alpha
further is not justified by the current data: the intervention already changes
trajectories and consistently damages one control without correcting target
failures.

Together with the feature-8994 result, this weakens the hypothesis that a simple
constant decoder-direction addition is sufficient to reverse the merging
regressions. The next informative intervention is activation-matched clamping,
or a move to the distinct DeepSeek fine-tuning hypothesis represented by
feature 2562.

## Artifacts

- `pass_rate_by_alpha.png`
- `task_level_results.csv`
- Full generations, postprocessed code, evaluator results, control-selection
  evidence, and logs are stored under
  `runs/steering_feature_11586_traditional/` and in the paper-v1 bucket.

