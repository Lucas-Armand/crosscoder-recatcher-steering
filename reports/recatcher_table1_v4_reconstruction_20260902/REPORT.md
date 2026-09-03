# ReCatcher Table 1 General Logic reconstruction and v4 re-evaluation

Date: 2026-09-02

## Scope

This audit focuses on the two BigCodeBench model pairs used by the CrossCoder study:

- DeepSeek-Coder base versus fine-tuned;
- CodeLlama base versus merged.

It answers two separate questions:

1. Can the published Table 1 values be reconstructed from the archived ReCatcher labels?
2. What happens when the exact archived generations are re-extracted with extraction v4 and evaluated with the project's BigCodeBench 0.1.5 evaluator?

No model generation was rerun. Each model has 1,140 tasks and 10 archived generations per task (11,400 samples). The source artifacts are the `code_generation_results.zip` and `testing_results.zip` files from Zenodo record 14997627.

## Main results

| Pair and evaluation | Base passes | Variant passes | Delta |
|---|---:|---:|---:|
| DeepSeek, published Table 1 | -- | -- | +9.32 p.p. |
| DeepSeek, archived Zenodo labels | 4,654/11,400 | 5,176/11,400 | **+4.58 p.p.** |
| DeepSeek, same generations under v4 | 4,707/11,400 | 4,834/11,400 | **+1.11 p.p.** |
| CodeLlama, published Table 1 | -- | -- | +6.71 p.p. |
| CodeLlama, archived Zenodo labels | 3,169/11,400 | 3,934/11,400 | **+6.71 p.p.** |
| CodeLlama, same generations under v4 | 3,039/11,400 | 271/11,400 | **-24.28 p.p.** |

The CodeLlama Table 1 number is reconstructed exactly from the archived labels. The published DeepSeek base-to-fine-tuned value is not: the archived labels imply +4.58 p.p., not +9.32 p.p. The source of the published +9.32 value is not established by the archived files inspected here.

## Paired transitions across all ten generations

| Pair and evaluation | Improvement | Regression | Both pass | Both fail |
|---|---:|---:|---:|---:|
| DeepSeek, archived labels | 1,362 | 840 | 3,814 | 5,384 |
| DeepSeek, v4 | 1,136 | 1,009 | 3,698 | 5,557 |
| CodeLlama, archived labels | 2,836 | 2,071 | 1,098 | 5,395 |
| CodeLlama, v4 | 50 | 2,818 | 221 | 8,311 |

These counts treat every task-generation pair as one observation. They must not be confused with a single-generation cohort such as the later 215-improvement or 291-regression mechanistic cohorts.

## Why v4 differs

The dominant discrepancy is candidate validity and extraction, especially for CodeLlama merged.

| Model | Archived candidates checked | Syntactically invalid | Invalid but archived as pass | v4 leading-prefix extraction |
|---|---:|---:|---:|---:|
| DeepSeek base | 11,400 | 33 | 33 | 33 |
| DeepSeek fine-tuned | 11,400 | 425 | 425 | 425 |
| CodeLlama base | 11,400 | 194 | 194 | 192 |
| CodeLlama merged | 11,390 non-empty | 3,701 | 3,701 | 3,700 |

CodeLlama merged additionally has ten empty continuations for BigCodeBench/8, all already labeled fail in the archive and retained as fail in the v4 totals.

Every syntactically invalid archived candidate marked as pass is an internal inconsistency: the exact stored Python candidate cannot execute as written. Extraction v4 attempts to retain a longest compilable leading prefix when the historical candidate does not compile. In many CodeLlama merged cases, this removes an invalid trailing or incomplete region but does not recover a passing program. Consequently, the merged pass count falls sharply.

The difference cannot therefore be attributed primarily to generation length. It appears before any new generation: it is exposed by applying the newer extraction and evaluation pipeline to the same archived outputs. Remaining disagreements among syntactically valid candidates may reflect evaluator-version, dependency, test nondeterminism, timeout, or other harness differences and require a separate audit before assigning a single cause.

## Per-model label agreement

| Model | Original pass rate | v4 pass rate | Agreement |
|---|---:|---:|---:|
| DeepSeek base | 40.82% | 41.29% | 98.48% |
| DeepSeek fine-tuned | 45.40% | 42.40% | 95.07% |
| CodeLlama base | 27.80% | 26.66% | 97.33% |
| CodeLlama merged | 34.51% | 2.38% | 67.11% |

## Generation configuration recorded in the archive

The archived BigCodeBench `config.json` files record sampling with temperature 0.1, top-k 10, top-p 0.95, and `max_length=256`. However, the public generator does not use that field: `max_length=MAX_LENGTH` is commented out, while the actual open-weight pipeline call uses `max_new_tokens=MAX_NEW_TOKENS`, whose constant is 1,024. Thus, the metadata says 256 while the effective open-weight generation limit is 1,024 new tokens.

The archived outputs independently confirm that 256 was not the effective limit. Under the corresponding locally cached tokenizers, 2,184 DeepSeek-base, 1,399 DeepSeek-fine-tuned, 2,902 CodeLlama-base, and 6,178 CodeLlama-merged continuations exceed 256 tokens. Many terminate close to 1,024 tokens; the CodeLlama-merged median is approximately 1,020 tokens. Small counts slightly above 1,024 under retrospective tokenization can arise from tokenizer/version mismatch, particularly because the merged outputs were measured with the base CodeLlama tokenizer.

The separate `MAX_TOKENS=2048` constant is used by the OpenAI generator, not by the DeepSeek and CodeLlama generation path audited here. Consequently, neither 256 nor 2,048 describes the effective continuation limit for these four open-weight artifacts; the supported value is 1,024 new tokens.

## Interpretation for the paper

- Do not state that the mechanistic CodeLlama regression numerically reproduces Table 1. Table 1's +6.71 p.p. is reproducible under the archived labels, whereas v4 produces a large negative delta on the same stored generations.
- Do not state that the DeepSeek +9.32 p.p. cell was reproduced from the Zenodo labels. The recoverable value is +4.58 p.p.; v4 gives +1.11 p.p.
- Describe the CrossCoder behavior labels as outcomes under the canonical v4 pipeline, not as an exact rerun of Table 1.
- The archived invalid-pass inconsistency should be investigated in the original evaluator before the discrepancy is assigned solely to extraction policy.

## Reproduction artifacts

- `reconstruct_table1_v4.py`: validates cardinalities and recomputes model totals and paired transitions.
- `model_summary.csv`: original-versus-v4 results per model.
- `pair_summary.csv`: deltas and transition counts per pair.
- `summary.json`: machine-readable copy of both summaries.

Source: https://zenodo.org/records/14997627
