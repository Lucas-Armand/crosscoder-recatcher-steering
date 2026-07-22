# Evaluating Baseline and Steering Generations Identically

The evaluation path must consume the newly generated steering completion, never
the baseline `candidate_code` inherited from an input row. The canonical record
contract is:

```text
prompt + raw_completion == candidate_code
```

`tools/run_crosscoder_intervention.py` now updates all three fields and clears
historical correctness labels. `tools/prepare_evaluation_input.py` enforces the
same contract for any baseline, ablation, or steering generator.

## Normalize and post-process one run

Use a unique model label that encodes the intervention, for example
`deepseek_finetuned__feature_5666__alpha_neg_1`:

```bash
scripts/prepare_and_postprocess_generation.sh \
  runs/interventions/feature_5666_alpha_neg_1.jsonl \
  humanevalplus \
  deepseek_finetuned__feature_5666__alpha_neg_1 \
  runs/evaluation/feature_5666_alpha_neg_1
```

This produces:

```text
raw_results/       normalized generated result, preserving steering metadata
zips_raw/          exact pre-repair Python candidates
postprocessed/
  results_repaired/
  repaired_zips/
  samples_for_external_eval/
  repair_summary.csv
```

## HumanEval+

Activate the pinned HumanEval environment and evaluate the repaired record:

```bash
python tools/evaluate_humaneval_local.py \
  --repaired-jsonl runs/evaluation/feature_5666_alpha_neg_1/postprocessed/results_repaired/humanevalplus__deepseek_finetuned__feature_5666__alpha_neg_1_repaired.jsonl \
  --output-jsonl runs/evaluation/feature_5666_alpha_neg_1/eval/humanevalplus_eval.jsonl
```

## BigCodeBench

Activate the environment containing `bigcodebench==0.1.5`, then run the same
command and flags used by `paper_v1`:

```bash
python -m bigcodebench.evaluate \
  --subset complete \
  --samples runs/evaluation/feature_5666_alpha_neg_1/postprocessed/samples_for_external_eval/bigcodebench__deepseek_finetuned__feature_5666__alpha_neg_1_samples.jsonl \
  --parallel 16 \
  --no-gt
```

## Comparability requirements

- Keep benchmark task IDs and prompts unchanged across alpha values.
- Use a distinct output directory and model label for every feature/alpha pair.
- Preserve `feature_id`, `alpha`, checkpoint URI, model IDs, tokenizer ID, seed,
  and generation settings in every row.
- Report raw compilation, repair counts, and evaluated correctness separately.
- Never reuse a correctness label inherited from the baseline row.
- Run `alpha=0` through this exact path as the causal control.
