# Analysis Diary: ReCatcher / CrossCoder Reproducibility Follow-up

## Main findings since the previous diary

### 1. BigCodeBench evaluation

The official BigCodeBench evaluator expects a sample for every task in the selected dataset. Passing only a 100-line JSONL chunk fails unless `--selective_evaluate` is also provided with the exact task IDs in the chunk.

We also observed that evaluating all 1140 tasks in one process can cause RAM growth and OOM. The reproducibility package therefore includes a chunk-preparation helper:

```bash
python tools/prepare_bigcodebench_chunks.py \
  --samples path/to/bigcodebench__model_samples.jsonl \
  --out-dir bigcodebench_eval/model \
  --chunk-size 100
```

This generates a `run_chunks.sh` script using `--selective_evaluate`.

### 2. CodeLlama parse artifacts

Several CodeLlama outputs had a systematic indentation issue: lines inside a function sometimes started with exactly 3 spaces rather than 4. This is repairable by a deterministic local whitespace rule.

The included `tools/reprocess_outputs_minimal.py` applies this conservative repair without selecting variants, trimming bodies, or adding code.

### 3. DeepSeek tokenizer issue

The most important discovery was that many strange DeepSeek outputs like:

```python
ifnotstrings:returnNonemax_string
```

were not caused by the zip export, bucket sync, or repair script.

Token-level diagnostics showed that `input_ids.npy` exactly matched the tokenization of `prompt + raw_completion` from the result JSONL. The original prompt string contained spaces, but the tokenizer route used by `AutoTokenizer` produced tokens such as:

```text
from, ty, ping, import, List
```

and decoded them as:

```text
fromtypingimportList
```

When loading `tokenizer.json` directly through `PreTrainedTokenizerFast`, the round-trip was correct:

```text
from typing import List, Optional
```

Therefore, the DeepSeek-family generation results from the affected run should be treated as contaminated by tokenizer-loading behavior unless rerun with the tokenizer guard.

### 4. Fix implemented

`run_recatcher_benchmarks.py` now uses `load_tokenizer_safe()`:

- DeepSeek-family models use `PreTrainedTokenizerFast`.
- A code whitespace round-trip probe is required to pass before generation.
- If the tokenizer decodes `from typing` as `fromtyping`, the run aborts immediately.

This prevents silent corruption of prompts and generated completions.

## Reproducibility recommendation

For final runs:

1. Start a fresh server with working GPU and `nvidia-smi`.
2. Run a tokenizer smoke test first.
3. Run one HumanEval task with `--no-activations`.
4. Inspect `raw_completion`.
5. Only then run full generation + activation capture.
6. Run minimal post-processing.
7. Evaluate HumanEval locally/EvalPlus and BigCodeBench in chunks.
