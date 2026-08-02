# Causal smoke test of discriminant residual directions

## Objective

This experiment asks whether the leave-one-task-out (LOTO) residual directions
derived from base-versus-finetuned representations can causally move DeepSeek
base generations from failure to success.

## Design

- Model: `deepseek-ai/deepseek-coder-6.7b-base`, NF4/eager.
- Generation: the paper-v1 capture contract (`temperature=0.2`, `top_p=0.95`,
  512 new tokens, stored prompt and seed, cached HF generation).
- Layer: 16, last-token intervention at every autoregressive step.
- Direction: unit-norm different-own-text discriminant learned without the
  target task in its LOTO fold and oriented toward improvement.
- Cohort: the ten base-fail/finetuned-pass tasks with the largest positive LOTO
  margins.
- Expected-direction doses: `+2`, `+4`, and `+6` residual-norm units.
- Directionality controls: expected direction at `-4` and `-6`.
- Perturbation controls: seeded unit random directions orthogonal to the
  expected direction at `+4` and `+6`.

The alpha-zero arm reproduced all 10 original raw completions byte-for-byte and
all generated-token counts.

## Aggregate results

| Arm | Evaluated code changed | Passed | Fail to pass |
|---|---:|---:|---:|
| Alpha zero | - | 0/10 | 0 |
| Expected +2 | 2/10 | 0/10 | 0 |
| Expected +4 | 4/10 | 1/10 | HumanEval/68 |
| Expected +6 | 5/10 | 2/10 | HumanEval/68, HumanEval/158 |
| Opposite -4 | 3/10 | 1/10 | HumanEval/96 |
| Opposite -6 | 5/10 | 1/10 | HumanEval/96 |
| Random orthogonal +4 | 3/10 | 2/10 | HumanEval/68, HumanEval/96 |
| Random orthogonal +6 | 5/10 | 2/10 | HumanEval/68, HumanEval/96 |

The expected arm has a dose-response pattern, but it does not outperform the
matched random control in aggregate at norm 6. Consequently, the 2/10 result is
not evidence of an aggregate direction-specific benefit.

HumanEval/68 is corrected by both the expected and random directions. It is
best interpreted as a perturbation-sensitive task. HumanEval/96 is corrected
by the opposite and random directions but not the expected direction, also
arguing against the global causal hypothesis.

## HumanEval/158 candidate

HumanEval/158 is the only direction-specific candidate in this smoke:

- baseline: fail;
- expected +4: fail;
- expected +6: pass;
- opposite -4 and -6: fail;
- initial matched random +4 and +6: fail;
- nine additional orthogonal random directions at +6: 0/9 pass.

Thus the expected +6 direction succeeds while 10/10 norm-matched orthogonal
random directions and both opposite-direction arms fail.

The baseline implements
`max(words, key=lambda x: (len(set(x)), x))`, which chooses the
lexicographically largest word when unique-character counts tie. Expected +6
generates an explicit loop that updates on `word < max_word`, implementing the
required lexicographically smallest tie break. The resulting program passes the
HumanEval evaluator.

This is stronger than a mere syntax repair: the intervention changes the
specific semantic decision that was wrong. The direction for HumanEval/158 was
trained without HumanEval/158 itself.

## Limitations

- The cohort and HumanEval/158 were selected after inspecting LOTO scores and
  causal outcomes; this is exploratory and subject to multiplicity.
- Only one task shows direction-specific success.
- Different-own-text directions mix checkpoint change with code-content
  differences, even though the held-out task is excluded from direction
  training.
- Ten random directions provide a useful specificity check but not a powered
  population-level significance test.
- Each task uses its own LOTO fold direction; this does not yet validate one
  frozen universal steering vector.

The next confirmatory experiment should freeze a direction using HumanEval,
preselect BigCodeBench cases without observing causal outcomes, and compare the
expected direction against multiple orthogonal random controls at norm 6.

## Reproducibility

- Cohort and controls: `tools/prepare_discriminant_steering_smoke.py`.
- Intervention runner: `tools/run_crosscoder_intervention.py` with
  `--per-example-direction-npz`.
- Generated and evaluated artifacts:
  `runs/discriminant_direction_steering_smoke/`.
- Machine-readable summary: [`summary.csv`](summary.csv).
