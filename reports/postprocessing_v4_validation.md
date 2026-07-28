# Post-processing extraction-v4 validation

Overall status: **PASS**

The comparison uses the immutable v3 evaluator artifacts as the baseline. Extraction decisions are deterministic and never inspect evaluator outcomes.

## Evaluation impact

| Benchmark | Model | v3 pass | v4 pass | Delta | Rescued | Lost |
|---|---|---:|---:|---:|---:|---:|
| humanevalplus | codellama_base | 52 | 55 | +3 | 3 | 0 |
| humanevalplus | codellama_finetuned | 0 | 58 | +58 | 58 | 0 |
| humanevalplus | codellama_merged | 17 | 17 | +0 | 0 | 0 |
| humanevalplus | deepseek_base | 62 | 66 | +4 | 4 | 0 |
| humanevalplus | deepseek_finetuned | 99 | 101 | +2 | 2 | 0 |
| humanevalplus | deepseek_merged | 122 | 123 | +1 | 1 | 0 |
| bigcodebench | codellama_base | 310 | 314 | +4 | 4 | 0 |
| bigcodebench | codellama_finetuned | 2 | 319 | +317 | 317 | 0 |
| bigcodebench | codellama_merged | 26 | 27 | +1 | 1 | 0 |
| bigcodebench | deepseek_base | 264 | 268 | +4 | 4 | 0 |
| bigcodebench | deepseek_finetuned | 346 | 404 | +58 | 59 | 1 |
| bigcodebench | deepseek_merged | 457 | 471 | +14 | 14 | 0 |

## Alignment and extraction integrity

- Materialized masks: **7,821**.
- Mask reconstruction failures: **0**.
- Literal extraction-span errors: **0**.
- Lost passes after candidate code changed: **0**.
- Evaluator disagreements with byte-identical code: **1**.

The three absent DeepSeek masks correspond to the declared missing activation for BigCodeBench task 764 in each DeepSeek model. No activation was fabricated.

## Interpretation

The largest correction is CodeLlama fine-tuned, whose leading Python continuation was previously discarded in favor of later fenced prose or non-Python examples. Helper definitions are now retained when the historical candidate references them. Valid historical candidates remain unchanged unless a structural defect is detected.

ROC-AUC screening was intentionally not recomputed.
