# Dataset-aligned steering protocol validation

## Objective

This experiment tests current CrossCoder feature 6258 under the same generation
conditions used to create the DeepSeek activation dataset from which the
layer-16 CrossCoder was trained and the feature was selected. It separates this
primary causal test from the exploratory historical-protocol replication.

## Configuration audit

The source evidence is
`recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/metadata/experiment_config.json`,
the per-solution result rows, `run_recatcher_benchmarks.py`, and the CrossCoder
training manifest/configuration.

| Property | Activation dataset | Aligned steering |
|---|---|---|
| Model | `deepseek-ai/deepseek-coder-6.7b-base` | same |
| Quantization | NF4, double quantization, fp16 compute | same |
| Attention | eager | same |
| Tokenizer | forced `PreTrainedTokenizerFast` with DeepSeek special tokens | same |
| Prompt | stored benchmark prompt | same stored prompt |
| Seed | `1000 + task_idx * 100 + gen_idx` | stored per-row seed |
| Sampling | `do_sample=True`, temperature 0.2, top-p 0.95 | same |
| Generation backend | HF `model.generate`, cache enabled | same |
| Token budget | 512 | 512 |
| CrossCoder layer | 16 | 16 |
| Steering scope | not applicable during capture | last token at every cached decoding step |
| Direction | not applicable during capture | base-side decoder vector |

The CrossCoder was trained in float32 from layer-16 activations stored as
float16. This is a training/storage property, not a reason to load the source
language model in float32: the source activations were captured from the NF4
model described above.

## Reproduction gate

Before steering, alpha zero was regenerated for the fixed 20-task cohort.
The aligned backend reproduced:

- 20/20 raw completions byte-for-byte;
- 20/20 generated-token counts;
- 20/20 stored seeds and prompts by construction.

Earlier controls failed this gate for two identified reasons: the manual runner
recomputed the complete sequence with `use_cache=False`, and it loaded the
DeepSeek tokenizer through `AutoTokenizer`. The aligned backend uses the same
cached HF generation path and tokenizer construction as the capture script.

## Feature 6258 result

The intervention used traditional base-side decoder steering at
`-2 * token-level-positive-P99`, corresponding to alpha `-7.771262`.

| Metric | Alpha 0 | Feature 6258, -2 P99 |
|---|---:|---:|
| Passing solutions | 3/20 (15%) | 3/20 (15%) |
| Raw completions changed | - | 5/20 (25%) |
| Evaluated programs changed | - | 4/20 (20%) |
| Fail to pass | - | 0 |
| Pass to fail | - | 0 |

The passing tasks in both arms are HumanEval/49, HumanEval/56, and
HumanEval/82. Evaluated code changes occurred for HumanEval/5, HumanEval/65,
HumanEval/74, and HumanEval/87; none crossed the evaluator decision boundary.

## Interpretation

Under exact dataset-generation conditions, this 20-task experiment does not
show a functional causal improvement for feature 6258. It does show that the
intervention changes model output, but output change alone is insufficient
evidence of a feature-specific beneficial mechanism.

The earlier greedy, 192-token experiment produced two improvements without
regressions, but it used a different decoding distribution. It remains useful
as exploratory evidence that the decoder direction can affect particular code
trajectories, not as the primary paper result for the current activation
dataset.

This cohort was inherited from the historical feature-962 study. A definitive
current-paper experiment should next select cases prospectively from the current
dataset using a frozen feature-selection rule, retain this exact aligned
generation backend, and include a same-norm random-direction control.
