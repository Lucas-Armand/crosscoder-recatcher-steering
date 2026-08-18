# CodeLlama base × merged TopK-100 screening audit

## Canonical artifact

- Checkpoint: step `10000`; SHA-256 `b8df3b3a8ea3a488cdca426283399f906b9b0e439e3797c6785f30f21e87093d`.
- Same-text captures: `2608` across `1304` tasks; `582135` evaluated tokens.
- Alignment errors: `0`; maximum RMS error: `0.000314355`.
- Validation loss `0.377846`; L0 `99.997`.

## Extraction-v4 behavioral populations

| Benchmark | Regressions | Improvements | Both pass | Both fail |
|---|---:|---:|---:|---:|
| bigcodebench | 291 | 4 | 23 | 822 |
| humanevalplus | 39 | 1 | 16 | 108 |

The primary screen conditions on tasks passed by the base model. Positives are base-pass → merged-fail regressions; controls are both-pass tasks. Improvements are not interpreted because only 4 BigCodeBench and 1 HumanEval+ cases exist.

## BigCodeBench localized ranking (`max` / `early_max`)

| Rank | Feature | Summary | E/V | ROC-AUC | Support |
|---:|---:|---|---:|---:|---:|
| 1 | 4300 | early_max | 4.331 | 0.594 | 90/291 |
| 2 | 3612 | max | 3.881 | 0.769 | 282/291 |
| 3 | 8471 | early_max | 3.754 | 0.628 | 77/291 |
| 4 | 14881 | max | 3.531 | 0.736 | 195/291 |
| 5 | 2910 | early_max | 3.467 | 0.592 | 49/291 |
| 6 | 12671 | early_max | 3.361 | 0.698 | 172/291 |
| 7 | 10890 | early_max | 3.355 | 0.628 | 101/291 |
| 8 | 1058 | max | 3.281 | 0.729 | 243/291 |
| 9 | 6128 | max | 3.185 | 0.679 | 258/291 |
| 10 | 2857 | max | 3.137 | 0.691 | 106/291 |

## HumanEval+ localized ranking (`max` / `early_max`)

| Rank | Feature | Summary | E/V | ROC-AUC | Support |
|---:|---:|---|---:|---:|---:|
| 1 | 2572 | max | 2.551 | 0.729 | 31/39 |
| 2 | 4614 | max | 2.076 | 0.713 | 35/39 |
| 3 | 7097 | early_max | 1.960 | 0.638 | 38/39 |
| 4 | 3612 | max | 1.872 | 0.650 | 29/39 |
| 5 | 2969 | early_max | 1.868 | 0.596 | 11/39 |
| 6 | 1287 | max | 1.837 | 0.587 | 12/39 |
| 7 | 4966 | early_max | 1.825 | 0.603 | 9/39 |
| 8 | 8764 | early_max | 1.791 | 0.579 | 5/39 |
| 9 | 4672 | max | 1.789 | 0.642 | 15/39 |
| 10 | 7123 | max | 1.785 | 0.579 | 4/39 |

## Sensitivity and limitations

- BigCodeBench localized-versus-all-four Top-10 overlap: `4/10`.
- HumanEval+ localized-versus-all-four Top-10 overlap: `4/10`.
- Feature 3612 is the clearest stable candidate: it appears in both benchmark shortlists and in the all-four-summary rankings.
- BigCodeBench prevalence is 291/314 (92.7%); only 23 both-pass controls exist. PR-AUC is therefore high by construction and PR lift is more informative than raw PR-AUC, though still close to 1 for many leaders.
- E/V is effect divided by the permutation-null SD. It is not a z-score or a corrected significance test.
- Nominal permutation p-values use 200 permutations and are not maxT-corrected.
- `max/early_max` are the prespecified mechanistic shortlist; `mean/active_fraction` are sensitivity views favoring persistent features.
- IDs 8994 and 11586 belong to the old dense CrossCoder coordinate system and cannot be expected to retain their IDs in this newly trained dictionary.
