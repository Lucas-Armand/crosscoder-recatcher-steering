# Steering smoke: DeepSeek base feature 6873

## Scope

This smoke tests feature 6873 from
`deepseek_base_finetuned_layer16` on the DeepSeek base side at layer 16.
The feature was selected by the bidirectional PR-AUC screen as
failure-associated (`PR-AUC=0.8463`, normalized effect `0.6144`,
`E/V=6.35`, `p_maxT=1/201`).

The fixed sample contains 20 HumanEval tasks: 10 historical extraction-v4
passes and 10 historical failures. This stratification is only for detecting
paired transitions; its pass rate is not a population estimate.

Generation used 128 new tokens, greedy decoding (`temperature=0`), seed 1000,
and alpha values `-1`, `0`, and `+1`. The new alpha-zero arm is the causal
control. It is not expected to reproduce the historical paper generation,
which used `temperature=0.2` and task-local sampling seeds.

## Intervention

The runner applies

`h_target' = h_target + alpha * z_j * decoder_target[:, j]`.

For this feature, the target-side decoder-vector L2 norm is `0.8683`.
Alpha `-1` is a subtractive intervention, not an exact mathematical ablation
of the original hidden state.

## Results

| Alpha | Passed | Pass rate | Compiled before repair | Compiled after repair |
|---:|---:|---:|---:|---:|
| -1 | 1/20 | 5% | 2/20 | 2/20 |
| 0 | 7/20 | 35% | 9/20 | 9/20 |
| +1 | 1/20 | 5% | 2/20 | 2/20 |

Relative to alpha zero, both nonzero arms produced:

- 0 fail-to-pass transitions;
- 6 pass-to-fail transitions;
- 1 pass-to-pass transition;
- 13 fail-to-fail transitions;
- net paired improvement `0 - 6 = -6`.

Eighteen of 20 raw completions changed in each nonzero arm. The same two tasks
were unchanged across all three arms. A representative pass-to-fail example
(`HumanEval/3`) changed from valid Python into repetitions dominated by `!`
tokens in both directions. The evaluator failure is therefore attributable to
destructive generation, not aggressive cleanup: repair changed 4/20 rows for
alpha `-1` and 8/20 for alpha `+1`, reported no suspicious repairs, and did not
change compilation totals.

## Interpretation

This smoke demonstrates that the hook is active, but it does not validate the
predicted causal direction. Alpha magnitude 1 is too strong for this feature:
both signs destroy syntax at similar rates. The result should not be interpreted
as evidence that increasing and decreasing the feature have the same semantic
effect; it is evidence that this intervention scale is outside the useful local
regime.

The next calibration should keep the same 20 tasks and control, and test smaller
symmetric magnitudes such as `0.01`, `0.03`, `0.1`, and `0.3`. A useful range
should first preserve compilation and baseline passes, then be evaluated for a
directional fail-to-pass versus pass-to-fail response.

## Runner correction discovered by the smoke

The initial nonzero run exposed corruption of the GPU-resident generated-token
buffer after a hooked forward pass. `tools/run_crosscoder_intervention.py` now
keeps the authoritative token sequence on CPU, creates fresh device copies for
each target/reference forward, and checks both lower and upper vocabulary
bounds. A two-example/eight-token nonzero regression run completed after the
correction. No invalid output from the failed attempt was used.

## Artifact locations

Local server artifacts:

`runs/steering_smoke_pr_auc_feature_6873/`

The directory contains the fixed input, three raw generation JSONLs, normalized
and postprocessed records, repair summaries, and evaluator outputs.
