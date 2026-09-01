# DSTK100 feature 5422 contamination cohort audit

- Generated: `2026-08-15T05:54:36-04:00`
- Run: `runs/dstk100_f5422_test_contamination_v1`
- Cohort: 119 BigCodeBench base-fail to finetuned-pass tasks preselected as generated test/import contamination
- Checkpoint: canonical DSTK100 step-10000 checkpoint only
- Baseline reproduction: verified `119/119` exact raw completions for `alpha=0`

## Official results

| Arm | Alpha | Official passes | Fail-to-pass vs alpha=0 | Exploratory contamination removed | Exact raw change rate | Exact code change rate | Tasks with active online gate |
|---|---:|---:|---:|---:|---:|---:|---:|
| zero | 0 | 0/119 | 0 | 0 | 0.0% | 0.0% | 0 |
| neg0p5 | -0.5 | 3/119 | 3 | 0 | 24.4% | 0.0% | 111 |
| neg1 | -1 | 1/119 | 1 | 0 | 10.9% | 0.0% | 114 |
| neg2 | -2 | 1/119 | 1 | 0 | 31.1% | 0.0% | 119 |
| neg3 | -3 | 6/119 | 6 | 0 | 35.3% | 0.0% | 107 |
| pos1 | +1 | 3/119 | 3 | 0 | 34.5% | 0.0% | 109 |

## Decision

Feature 5422 is **not promising** under the overnight operational threshold.

- Best negative arm: `alpha=-3`
- Best negative-arm official passes: `6/119`
- Best negative-arm exploratory contamination removals: `0/119`
- Positive control arm: `alpha=+1` still produced `3/119` official passes in the same direction

No negative arm reached either threshold:

- at least `8/119` official passes, or
- at least `20/119` exploratory contamination removals.

## Interpretation limits

- The contamination-removal count above is explicitly exploratory and rule-based.
- The current rule version was taken from `tools/analyze_transition_failures.py`.
- Under that rule set, no arm removed the tagged test/import contamination from the repaired evaluated code relative to `alpha=0`.
- Exact raw completions changed frequently, but those changes did not propagate to code-level diffs after extraction/repair in this run.

## Next action

Proceed to the next untested alternative feature from the overnight queue after confirming live GPU availability and that no in-scope GPU experiment is already active.
