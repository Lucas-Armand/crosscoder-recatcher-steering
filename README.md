# ReCatcher / CrossCoder Reproducibility Package

This package contains the reproducibility scripts for generating code completions, saving selected-layer activations, applying minimal deterministic parse fixes, and evaluating HumanEval/BigCodeBench results.

It includes the latest tokenizer fix for DeepSeek-family models discovered during debugging: use `PreTrainedTokenizerFast` and abort if a code whitespace round-trip fails.

## Contents

```text
run_recatcher_benchmarks.py        # main generation + activation script
run_with_bucket_sync.sh            # optional local/GCS runner
tools/export_generated_scripts_to_zips.py
tools/reprocess_outputs_minimal.py
tools/evaluate_humaneval_local.py
tools/prepare_bigcodebench_chunks.py
tools/summarize_bigcodebench_logs.py
tools/train_crosscoders_streaming.py
configs/model_map.template.json
.env.example
requirements.txt
docs/
```

## Setup on a new server

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

If you need gated models, log in with your own token on the server.

```bash
hf auth login
```

Check GPU:

```bash
nvidia-smi
python - <<'PY'
import torch
print(torch.cuda.is_available())
print(torch.cuda.device_count())
PY
```

## Tokenizer smoke test

Before any expensive run, test the DeepSeek tokenizer path:

```bash
python - <<'PY'
import run_recatcher_benchmarks as rb
from types import SimpleNamespace
rb.import_runtime_dependencies()
args = SimpleNamespace(trust_remote_code=True)
tok = rb.load_tokenizer_safe('deepseek-ai/deepseek-coder-6.7b-base', args)
probe = 'from typing import List, Optional\n\n\ndef f(x: int) -> int:\n    if x > 0:\n        return x\n    return None\n'
ids = tok(probe, add_special_tokens=False)['input_ids']
dec = tok.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
print(type(tok), getattr(tok, 'is_fast', None))
print(repr(dec))
print('OK:', 'from typing' in dec and 'def f' in dec and 'return None' in dec)
PY
```

Expected: `OK: True`.

## One-task smoke generation

The runner supports `--task-idx` for targeted smoke tests.

```bash
python run_recatcher_benchmarks.py \
  --benchmarks humanevalplus \
  --models deepseek_base \
  --model-map-json "$(cat configs/model_map.template.json)" \
  --task-idx 12 \
  --num-generations 1 \
  --max-new-tokens 128 \
  --no-activations \
  --experiment-name smoke_tokenizer_fix_humaneval12
```

Inspect output:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('recatcher_crosscoder_humaneval/smoke_tokenizer_fix_humaneval12/results/humanevalplus__deepseek_base_results.jsonl')
for line in p.open():
    row = json.loads(line)
    print(row['task_id'], row['syntax_ok'], row['correct'])
    print(row['raw_completion'][:1500])
PY
```

You should not see artifacts like `fromtyping`, `deflongest`, or `returnNone` caused by tokenizer round-trip failure.

## Full generation + activations

Local only:

```bash
python run_recatcher_benchmarks.py \
  --benchmarks humanevalplus bigcodebench \
  --models deepseek_base deepseek_merged codellama_base codellama_merged \
  --model-map-json "$(cat configs/model_map.template.json)" \
  --selected-layer-ids 8 16 24 \
  --num-generations 1 \
  --max-new-tokens 512 \
  --experiment-name full_table_6models_2benchmarks_layers_8_16_24_max512
```

With optional GCS sync, create `.env.local` from `.env.example` and set `REPRO_BUCKET` in your own environment. Then run:

```bash
./run_with_bucket_sync.sh humanevalplus deepseek_base
./run_with_bucket_sync.sh bigcodebench deepseek_base 400
./run_with_bucket_sync.sh bigcodebench deepseek_base
```

No bucket is hard-coded in this package.

## Export generated code to zips

```bash
python tools/export_generated_scripts_to_zips.py \
  --results-dir recatcher_crosscoder_humaneval/<EXP>/results \
  --out-dir generated_scripts_zips_raw
```

## Minimal parse repair

```bash
python tools/reprocess_outputs_minimal.py \
  --zip-dir generated_scripts_zips_raw \
  --output-dir generated_scripts_reprocessed
```

This applies conservative repairs only. It does not select variants, trim bodies, or invent code.

For qualitative exploration only, you may add:

```bash
--enable-glued-fix
```

Do not use glued-token repair as final metric unless you explicitly document it.

## HumanEval local evaluation

```bash
python tools/evaluate_humaneval_local.py \
  --repaired-jsonl generated_scripts_reprocessed/results_repaired/humanevalplus__deepseek_base_repaired.jsonl \
  --output-jsonl generated_scripts_reprocessed/eval/humanevalplus__deepseek_base_eval.jsonl
```

For publication-quality HumanEval+, also run the official EvalPlus evaluator on the sample files.

## BigCodeBench evaluation in chunks

Prepare chunks:

```bash
python tools/prepare_bigcodebench_chunks.py \
  --samples generated_scripts_reprocessed/samples_for_external_eval/bigcodebench__codellama_base_samples.jsonl \
  --out-dir bigcodebench_eval/codellama_base \
  --chunk-size 100 \
  --execution local \
  --parallel 1
```

Run:

```bash
bash bigcodebench_eval/codellama_base/run_chunks.sh
```

Summarize:

```bash
python tools/summarize_bigcodebench_logs.py \
  --log-dir bigcodebench_eval/codellama_base/logs
```

## Notes

- The previous DeepSeek run should be considered contaminated if it used the whitespace-breaking tokenizer route.
- CodeLlama had a separate parse issue: a common 3-space indentation artifact. The minimal repair script handles that deterministically.
- Store raw outputs and repaired outputs separately. Keep labels such as `raw_correct` and `parse_fixed_correct` distinct.


---

# CrossCoder ReCatcher Steering

This repository contains scripts for generating, post-processing, evaluating, and inspecting ReCatcher/CrossCoder code-generation benchmark runs.

The main validated artifact from the current reproduction pipeline is:

```text
gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3
```

This processed dataset was created from the raw generation run:

```text
gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1
```

---

## Repository structure

Important files:

```text
run_recatcher_benchmarks.py
    Main generation script for running models on HumanEval+/BigCodeBench and saving results/activations.

scripts/run_postprocess_and_eval_from_scratch_v3.sh
    Validated pipeline for creating an evaluation-ready copy, running evaluations, and uploading results.

tools/inspect_eval_examples.py
    Utility for inspecting examples that passed or failed evaluation.

tools/export_generated_scripts_to_zips.py
    Helper used by the post-processing pipeline.

tools/reprocess_outputs_minimal.py
    Minimal mechanical post-processing for generated code.

tools/evaluate_humaneval_local.py
    Local HumanEval+ evaluation helper.
```

---

## Evaluation-ready post-processing and evaluation pipeline

The validated script is:

```bash
scripts/run_postprocess_and_eval_from_scratch_v3.sh
```

It creates a clean evaluation-ready dataset from a raw generation run.

The pipeline:

1. Reads raw generation files from the source experiment.
2. Creates a new processed/evaluation-ready destination.
3. Preserves the original raw outputs under `raw_results/`.
4. Applies minimal mechanical post-processing to generated code.
5. Saves processed outputs under `results/`, `results_repaired/`, and `samples_for_external_eval/`.
6. Copies activation tensors unchanged under `selected_layer_activations/`.
7. Runs HumanEval+ evaluation.
8. Runs BigCodeBench evaluation using `bigcodebench==0.1.5`.
9. Writes a summary report to `reports/model_benchmark_summary.csv`.

The intended methodology is conservative: the original generations and activations are preserved. For execution-based evaluation, the pipeline creates an evaluation-ready copy of the generated code using minimal formatting repairs, such as removing markdown fences, normalizing line breaks, and fixing mechanical indentation artifacts. These changes are not applied to the activation tensors.

---

## Environment setup

HumanEval+ environment:

```bash
python -m venv ~/venvs/recatcher_humaneval
source ~/venvs/recatcher_humaneval/bin/activate
pip install -U pip
pip install datasets evalplus pytest tqdm
deactivate
```

BigCodeBench environment:

```bash
python -m venv ~/venvs/bigcodebench015
source ~/venvs/bigcodebench015/bin/activate
pip install -U pip
pip install "bigcodebench==0.1.5"
deactivate
```

The BigCodeBench pipeline is pinned to:

```text
bigcodebench==0.1.5
```

The BigCodeBench evaluator is run with:

```bash
python -m bigcodebench.evaluate   --subset complete   --samples <samples.jsonl>   --parallel 16   --no-gt
```

The runner only accepts a BigCodeBench score if the log contains a real metric line beginning with:

```text
pass@1:
```

This avoids false positives from helper messages or monitoring text.

---

## Running the validated v3 pipeline

Full validated run:

```bash
SRC_EXP="crosscoder_final_dataset_v1" DST_EXP="crosscoder_final_dataset_v1_postprocessed_minimal_v3" MODELS_STR="codellama_base codellama_finetuned codellama_merged deepseek_base deepseek_finetuned deepseek_merged" BENCHES_STR="humanevalplus bigcodebench" COPY_ACTIVATIONS=1 HUMANEVAL_VENV="$HOME/venvs/recatcher_humaneval" BIGCODEBENCH_VENV="$HOME/venvs/bigcodebench015" BIGCODEBENCH_PARALLEL=16 GRACE_AFTER_SCORE_SECONDS=20 HARD_TIMEOUT_SECONDS=1800 ./scripts/run_postprocess_and_eval_from_scratch_v3.sh
```

Small smoke test:

```bash
MODELS_STR="codellama_base" BENCHES_STR="humanevalplus bigcodebench" DST_EXP="crosscoder_final_dataset_v1_postprocessed_minimal_v3_test_codellama_base" COPY_ACTIVATIONS=0 ./scripts/run_postprocess_and_eval_from_scratch_v3.sh
```

---

## Output structure

The processed dataset has this structure:

```text
<destination>/
  POSTPROCESS_MANIFEST.txt

  raw_results/
    Original raw generation outputs.

  results/
    Processed/evaluation-ready result files using the standard result filenames.

  results_repaired/
    Detailed repaired result files.

  samples_for_external_eval/
    Sample files passed to external evaluators.

  selected_layer_activations/
    Activation tensors copied unchanged from the source run.

  eval/
    humanevalplus/
      HumanEval+ evaluation logs and JSONL files.

    bigcodebench015/
      BigCodeBench logs and evaluation result JSON files.

  reports/
    repair summaries
    model_benchmark_summary.csv
```

---

## Validated v3 results

The validated v3 run produced the following scores.

| Benchmark | Model | pass@1 |
|---|---:|---:|
| HumanEval+ | codellama_base | 0.3171 |
| HumanEval+ | codellama_finetuned | 0.0000 |
| HumanEval+ | codellama_merged | 0.1037 |
| HumanEval+ | deepseek_base | 0.3780 |
| HumanEval+ | deepseek_finetuned | 0.6037 |
| HumanEval+ | deepseek_merged | 0.7439 |
| BigCodeBench | codellama_base | 0.272 |
| BigCodeBench | codellama_finetuned | 0.002 |
| BigCodeBench | codellama_merged | 0.023 |
| BigCodeBench | deepseek_base | 0.232 |
| BigCodeBench | deepseek_finetuned | 0.304 |
| BigCodeBench | deepseek_merged | 0.401 |

The processed files were validated to contain:

```text
HumanEval+: 164 samples per model
BigCodeBench: 1140 samples per model
```

---

## Validation checks

Check the summary:

```bash
gsutil cat   gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3/reports/model_benchmark_summary.csv
```

Check processed result counts:

```bash
for f in $(gsutil ls gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3/results/*.jsonl | sort); do
  echo -n "$f "
  gsutil cat "$f" | wc -l
done
```

Expected counts:

```text
HumanEval+: 164 rows per model
BigCodeBench: 1140 rows per model
```

Check real BigCodeBench scores:

```bash
for f in $(gsutil ls gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3/eval/bigcodebench015/*full_eval_nogt.log | sort); do
  echo "=== $f ==="
  gsutil cat "$f" | grep -E '^pass@1:[[:space:]]*[0-9]+(\.[0-9]+)?[[:space:]]*$' || echo "NO SCORE"
done
```

Check activation copy counts:

```bash
gsutil ls -r gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3/selected_layer_activations/**/*.npz | wc -l
```

---

## Inspecting evaluated examples

Use the inspection script to print examples that passed and failed evaluation:

```bash
python tools/inspect_eval_examples.py   --root /tmp/crosscoder_postprocess_and_eval_v3/out   --benchmark all   --models "deepseek_merged"   --limit 5   --max-chars 5000
```

To inspect all models:

```bash
python tools/inspect_eval_examples.py   --root /tmp/crosscoder_postprocess_and_eval_v3/out   --benchmark all   --models "codellama_base codellama_finetuned codellama_merged deepseek_base deepseek_finetuned deepseek_merged"   --limit 5   --max-chars 5000   > inspect_all_models_examples.txt
```

Inspection outputs are local artifacts and should not be committed.

---

## Notes on post-processing

The current v3 post-processing is intentionally conservative.

It is designed to:

```text
- preserve the raw outputs;
- preserve activation tensors unchanged;
- avoid semantic repair;
- avoid inventing code;
- make outputs evaluation-ready through minimal mechanical cleanup.
```

Manual inspection showed that some model outputs still contain natural-language explanations, Kotlin fragments, TODOs, or extra example/test code. These are treated as model outputs, not silently repaired away. This makes the v3 dataset more conservative and easier to audit.

If a more aggressive cleanup is needed, create a new destination version, such as:

```text
crosscoder_final_dataset_v1_postprocessed_minimal_v4
```

and rerun the evaluations.

---

## Git hygiene

Do not commit local benchmark outputs, logs, caches, archives, databases, or inspection dumps.

Recommended `.gitignore` entries include:

```gitignore
__pycache__/
*.pyc
.ipynb_checkpoints/

*.log
*.zip
*.db
*.sqlite
*.sqlite3
*.tar
*.tar.gz
*.tgz
*.jsonl
*.npz

local_scratch/
recatcher_crosscoder_humaneval/
external_outputs/
official_recatcher_artifacts/
downloaded_files/
downloads/
unzipped_files/
data_processed/
destination/
output/
processed/
test_src/
test_dest/
logs_*/

inspect_*_examples.txt
```

Commit only the reproducible scripts and documentation.



