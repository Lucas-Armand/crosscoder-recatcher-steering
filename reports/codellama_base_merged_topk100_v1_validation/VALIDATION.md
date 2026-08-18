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
