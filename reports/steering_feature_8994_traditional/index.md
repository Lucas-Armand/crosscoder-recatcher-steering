# Traditional steering smoke test: feature 8994

## Result

Traditional positive steering of CrossCoder feature 8994 did not recover any
of the selected CodeLlama merged regressions in the tested range. The result
does not support a causal rescue effect for `alpha = 0..1` under this
intervention protocol.

| Alpha | Regression passes | Preserved-success passes | All passes |
|---:|---:|---:|---:|
| 0.00 | 0/10 | 5/10 | 5/20 |
| 0.25 | 0/10 | 5/10 | 5/20 |
| 0.50 | 0/10 | 4/10 | 4/20 |
| 0.75 | 0/10 | 5/10 | 5/20 |
| 1.00 | 0/10 | 4/10 | 4/20 |

Only three tasks changed text at any nonzero alpha:

- `BigCodeBench/607` (regression): changed at `0.5`, `0.75`, and `1.0`,
  but failed at every dose.
- `BigCodeBench/861` (preserved-success control): passed at `0`, `0.25`,
  and `0.75`, but failed at `0.5` and `1.0`.
- `BigCodeBench/1000` (preserved-success control): changed at `0.25` and
  `1.0`, but passed at every dose.

The harmful transition on task 861 is non-monotonic and is not evidence for a
stable dose-response effect.

## Stronger-dose follow-up

A preregistered follow-up tested `alpha = 1.5, 2, 3, 4` on the five strongest
regressions and the five controls that passed in the new `alpha=0` arm.

| Alpha | Regression passes | Passing-control passes |
|---:|---:|---:|
| 0.00 | 0/5 | 5/5 |
| 1.50 | 0/5 | 4/5 |
| 2.00 | 0/5 | 5/5 |
| 3.00 | 0/5 | 4/5 |
| 4.00 | 0/5 | 4/5 |

The intervention was not merely too weak to affect the model. Mean projection
shifts were approximately `0.95`, `1.27`, `1.91`, and `2.54`; the corresponding
mean intervention-to-residual norm ratios were `2.3%`, `3.1%`, `4.6%`, and
`6.1%`. At alpha 3 and 4, six of ten completions changed, including regressions
756 and 536, but neither regression passed. Task 861 was again damaged at
alphas 1.5, 3, and 4.

This stronger-dose follow-up therefore also provides no evidence of causal
rescue. Increasing the same intervention further is not currently justified:
the direction is already changing generation trajectories and causing control
damage without correcting the target failures.

## Experimental design

- Model: `DevQuasar-5/coma-7B-v0.1` (CodeLlama merged).
- CrossCoder: CodeLlama base versus merged, layer 16, 16,384 latents.
- Feature: 8994, merged-side decoder direction.
- Intervention:
  `h_last' = h_last + alpha * decoder_merged[:, 8994]`.
- Token scope: only the final hidden token in every autoregressive forward.
- Doses: `0`, `0.25`, `0.5`, `0.75`, `1`.
- Generation: 512 maximum new tokens, temperature 0.2, top-p 0.95, seeds
  retained from the paper-v1 rows.
- Evaluation: extraction/postprocessing v4 followed by the official
  BigCodeBench 0.1.5 execution harness.
- Sample: the ten aligned base-pass/merged-fail tasks with the largest negative
  feature-contribution differential, plus ten aligned both-pass controls with
  high merged-side contribution.

Regression tasks:
`415, 1083, 974, 756, 536, 390, 607, 742, 563, 166`.

Preserved-success controls:
`1133, 713, 783, 336, 1109, 820, 861, 437, 272, 1000`.

## Validation and limitations

- All 100 requested generations completed.
- The `alpha=0` arm bypassed the hook.
- Nonzero traditional-steering arms did not load or use the reference model.
- Per-task RNG seeds were reset independently, so different alpha arms are
  paired even when another task terminates at a different token.
- The checkpoint column norm was `0.6352413`, despite the training manifest
  describing a unit-normalized decoder contract. Therefore the actual
  intervention-vector norms were approximately `0`, `0.159`, `0.318`,
  `0.476`, and `0.635`.
- Postprocessing v4 produced compilable code for 19/20 tasks at every alpha.
  It applied eight deterministic repairs per arm and flagged no suspicious
  repair.
- Only 2/20 `alpha=0` completions were textually identical to their historical
  completions. The new arms remain directly comparable to one another, but the
  historical transition labels should be treated as task-selection strata,
  not as guaranteed replayed generations. All ten historically selected
  regressions did reproduce a failure at the new `alpha=0`.
- BigCodeBench 0.1.5 normally rejects partial datasets. The subset evaluator
  calls its official `check_correctness` function and uses the same problem
  definitions, execution sandbox, time limits, status constant, and tests.

## Interpretation

The association that selected feature 8994 was based on the maximum positive
encoder-side contribution over historical evaluated tokens. Directly adding
the merged-side decoder vector is related but is not mathematically equivalent
to restoring that contribution or the joint CrossCoder latent. This smoke test
therefore rejects only the specific traditional-steering intervention and dose
range tested; it does not show that feature 8994 is non-causal under every
intervention.

The next justified step is not a larger run at the same doses. First measure
the residual-stream scale and feature projection during the new generations.
Then either test a wider normalized dose range, or perform activation-matched
clamping if the objective is specifically to restore the levels observed in
the base model.

## Artifacts

- `task_level_results.csv`: task, group, alpha, verdict, syntax status, token
  count, and whether the generation changed from `alpha=0`.
- `pass_rate_by_alpha.png`: dose-response summary.
- `strong_task_level_results.csv`: stronger-dose verdicts and residual-stream
  diagnostics.
- Full generations, postprocessed samples, evaluator details, and logs are
  stored under `runs/steering_feature_8994_traditional/` and in the paper-v1
  bucket report copy.
