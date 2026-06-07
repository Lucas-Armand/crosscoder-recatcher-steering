# ReCatcher / CrossCoder Reproducibility Package

This package contains the reproducibility scripts for generating code completions, saving selected-layer activations, applying minimal deterministic parse fixes, and evaluating HumanEval/BigCodeBench results.

It includes the latest tokenizer fix for DeepSeek-family models discovered during debugging: use `PreTrainedTokenizerFast` and abort if a code whitespace round-trip fails.

## Contents

```text
run_recatcher_benchmarks.py        # main generation + activation script, tokenizer guard included
run_with_bucket_sync.sh            # optional local/GCS runner, no bucket hard-coded
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
unzip recatcher_crosscoder_repro.zip
cd recatcher_crosscoder_repro
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

If you need gated models, log in with your own token on the server. Do not commit tokens.

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
