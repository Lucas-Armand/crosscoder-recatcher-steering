# Focused BBASV reanalysis (2026-09-01)

This report recomputes all currently complete and comparable arms after extraction v4 and official BigCodeBench evaluation. It separates the predicted/direct intervention from the inverse intervention and does not pool incomplete controls.

## Scope and baseline gates

| Family | Direct baseline | Reverse baseline | Target arms | Comparable control arms |
|---|---:|---:|---:|---:|
| DeepSeek | 0/80 pass | 60/80 pass | 50 | 0 |
| CodeLlama | 0/50 pass | 50/50 pass | 50 | 25 random-feature arms |

The DeepSeek inverse result is not a clean 80-task success-to-failure experiment: only 60/80 reverse-baseline generations reproduce a pass. Reverse DeepSeek failure counts therefore use only the baseline-pass tasks on an arm-by-arm paired basis. The same arms also contain 60 aggregate fail-to-pass transitions among the 20 non-reproduced baseline tasks. This must be reported rather than treating the reverse baseline as 80/80.

No complete, protocol-matched sham arms exist in this stopped run. Historical sham results are not pooled because they differ in target selection and/or generation protocol. CodeLlama random-feature comparisons are reported only in cells for which complete arms exist.

## 1. Direct and inverse causal outcomes

Across five features and five magnitudes per direction:

| Family | Direct fail-to-pass | Unique direct tasks | Reverse pass-to-fail | Unique reverse tasks |
|---|---:|---:|---:|---:|
| DeepSeek | 119 feature-task transitions | 16/80 | 97 feature-task transitions | 17/80 |
| CodeLlama | 19 feature-task transitions | 5/50 | 40 feature-task transitions | 9/50 |

DeepSeek direct curves (fail-to-pass at magnitudes 1, 2, 3, 4, 5):

| Feature | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|
| 1078 | 2 | 5 | 5 | 7 | 6 |
| 2468 | 3 | 4 | 7 | 7 | 7 |
| 2621 | 3 | 4 | 6 | 5 | 8 |
| 14175 | 1 | 2 | 6 | 6 | 5 |
| 15235 | 2 | 3 | 6 | 5 | 4 |

DeepSeek inverse curves (pass-to-fail, paired against the 60/80 reproduced reverse baseline):

| Feature | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|
| 1078 | 0 | 2 | 2 | 2 | 6 |
| 2468 | 3 | 6 | 6 | 8 | 8 |
| 2621 | 2 | 3 | 4 | 4 | 7 |
| 14175 | 1 | 3 | 3 | 7 | 8 |
| 15235 | 2 | 3 | 3 | 2 | 2 |

CodeLlama direct curves:

| Feature | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|
| 4309 | 0 | 0 | 1 | 2 | 2 |
| 5642 | 0 | 0 | 1 | 1 | 1 |
| 7692 | 0 | 1 | 1 | 1 | 1 |
| 10818 | 0 | 0 | 1 | 1 | 1 |
| 11596 | 0 | 1 | 1 | 1 | 1 |

CodeLlama inverse curves:

| Feature | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|
| 4309 | 0 | 0 | 0 | 2 | 2 |
| 5642 | 0 | 1 | 1 | 2 | 3 |
| 7692 | 1 | 1 | 1 | 1 | 2 |
| 10818 | 0 | 1 | 3 | 4 | 4 |
| 11596 | 1 | 1 | 2 | 3 | 4 |

For CodeLlama, target arms exceed the available random controls most clearly in the inverse high-dose cells. At magnitude 5, targets have a median 3 pass-to-fail transitions (range 2--4; five arms), versus median 1 (range 1--1; two random arms). Direct magnitude 3 has median 1 for targets versus 0 for two random arms. At magnitude 4, however, direct targets and random controls are similar (medians 1 and 1). These small, incomplete control groups are descriptive, not a specificity test.

## 2. Changes to generated code

The comparison is exact and paired to the corresponding alpha-zero baseline. For changed outputs, the report records normalized edit distance, first differing position, length delta, and a rule-based primary category. Categories are descriptive heuristics, not human semantic annotations.

| Family/direction | Changed outputs | Directional transitions | Median edit fraction in transitions | Median first divergence |
|---|---:|---:|---:|---:|
| DeepSeek direct | 642/2000 (32.1%) | 119 | 0.147 | 86.8% |
| DeepSeek inverse | 513/2000 (25.7%) | 97 | 0.053 | 69.5% |
| CodeLlama direct | 455/1250 (36.4%) | 19 | 0.219 | 86.7% |
| CodeLlama inverse | 437/1250 (35.0%) | 40 | 0.290 | 62.2% |

All official transitions changed the exact evaluated code. DeepSeek direct transitions are especially coherent with the selected failure mode: all 119 are categorized as `test_marker` (76) or `imports` (43), and 89/119 satisfy the stricter contamination-cleanup heuristic. Across all changed DeepSeek-direct outputs, the leading categories are other logic/text (186), test markers (176), imports (137), function structure (69), comments (55), and returns (19).

CodeLlama changes are broader. Direct transitions split across function structure (8), other logic/text (6), and returns (5). Inverse transitions span function structure (16), comments (7), imports (7), test markers (6), and returns (4). This supports a more diffuse intervention phenotype, though the rule-based taxonomy should be manually audited before semantic claims.

## 3. Task concentration and susceptibility

The effects are strongly task-concentrated rather than uniformly distributed.

| Family/direction | Unique susceptible tasks | Share from top task | Share from top 3 | Share from top 5 |
|---|---:|---:|---:|---:|
| DeepSeek direct | 16 | 20.2% | 40.3% | 55.5% |
| DeepSeek inverse | 17 | 23.7% | 52.6% | 67.0% |
| CodeLlama direct | 5 | 52.6% | 84.2% | 100% |
| CodeLlama inverse | 9 | 42.5% | 62.5% | 80.0% |

DeepSeek direct task `/435` accounts for 24/119 transitions and responds to all five target features; `/316` accounts for 13 and also responds to all five. CodeLlama direct task `/119` accounts for 10/19 transitions and responds to three features. CodeLlama inverse task `/604` accounts for 17/40 and responds to four features.

Thus the curves establish that steering changes trajectories and can move official outcomes in both directions, but they also reveal a susceptibility component shared across features. Feature specificity cannot be concluded until the missing matched shams and random controls are completed under the same protocol.

## Files

- `summary.json`: experiment-level counts.
- `*_target_curves.csv`: per-feature dose curves.
- `*_arm_outcomes_and_changes.csv`: official outcomes and code-change summaries per arm.
- `*_task_details.csv`: paired task-level outcomes and code-change measurements.
- `*_available_control_comparison.csv`: only complete control cells.
- `*_task_susceptibility.csv`: task response counts across target arms.
- `*_dose_retention.csv`: consecutive-dose retention by feature.

