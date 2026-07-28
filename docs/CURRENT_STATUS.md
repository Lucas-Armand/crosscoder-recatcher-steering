# Current Experimental Status

This document describes the `paper_v1` candidate checkpoint as of 2026-07-21.
It distinguishes completed artifacts from validation evidence and future work.

## Completed generation scope

Six model variants were run on HumanEval+ (164 tasks) and BigCodeBench (1,140
tasks), one generation per task:

- DeepSeek Coder: base, fine-tuned, and merged;
- CodeLlama: base, fine-tuned, and merged.

Together these outputs support eight paper comparison cells: two families,
base-vs-fine-tuned and base-vs-merged, on two benchmarks. The canonical
post-processed dataset is
`crosscoder_final_dataset_v1_postprocessed_extraction_v4`.

Extraction v4 corrects two verified sources of false-negative evaluation labels:
selection of the largest fenced block instead of a leading Python continuation,
and truncation before required helper definitions. The previous v3 dataset is
retained as immutable historical evidence.

All 12 model/benchmark datasets were re-evaluated. Exact evaluated-token masks
were reconstructed for all 7,821 available activation artifacts; the three
absent masks correspond to the declared missing BigCodeBench task 764 activation
for the three DeepSeek models. ROC-AUC screening has intentionally not been
rerun because its analysis design is under revision.

The recorded generation contract is one sampled generation, at most 512 new
tokens, temperature 0.2, top-p 0.95, and deterministic per-task seeds. The
release validator checks all metadata that is stored per row and the archived
CodeLlama and DeepSeek `experiment_config.json` files. Temperature and top-p are
not repeated in every result row, so the archived experiment configs remain
required provenance evidence.

## Post-processing and evaluation

All 12 model/benchmark result files have 164 or 1,140 rows as expected. The v3
pipeline preserves raw rows, records original and repaired code, records every
repair rule, and evaluates the repaired candidate separately.

All six HumanEval+ evaluator jobs and all six BigCodeBench 0.1.5 jobs have
recorded exit code 0. BigCodeBench logs contain final `pass@1` lines. A successful
process is necessary but not sufficient evidence that every row represents a
model outcome; the release validator also checks task coverage, lineage, and
repair metadata.

A second row-level audit joins all 12 raw result files to their repaired records
and evaluator verdicts. It found no missing task verdicts and no raw-to-repair
candidate mismatch. Recomputed rates and deterministic pass/fail samples are
stored under `reports/paper_v1_evaluation_*`. BigCodeBench timeouts are reported
separately from functional failures.

CodeLlama required many deterministic whitespace repairs. This is a material
analysis choice, not a cosmetic implementation detail. The paper must report
raw-compilation and repaired-evaluation results separately. See
`POSTPROCESSING_AND_EVALUATION.md`.

## Canonical activations

The canonical float32 activation prefix contains layer 8, 16, and 24 arrays,
but the paper checkpoint uses layer 16 only. Coverage is complete for CodeLlama
and HumanEval+. DeepSeek BigCodeBench is missing task 764 for each of its three
model variants:

| Benchmark/model | Expected | Present |
|---|---:|---:|
| HumanEval+ / each model | 164 | 164 |
| BigCodeBench / each CodeLlama model | 1,140 | 1,140 |
| BigCodeBench / each DeepSeek model | 1,140 | 1,139 |

This three-file omission is declared in the release manifest. Any additional
missing activation is a validation failure.

## Canonical CrossCoders

Four layer-16 CrossCoders are in scope:

- DeepSeek base vs. fine-tuned;
- DeepSeek base vs. merged;
- CodeLlama base vs. fine-tuned;
- CodeLlama base vs. merged.

All four have a final checkpoint locally, metrics through step 20,000, and exit
code 0. The original DeepSeek base-vs-fine-tuned GCS run omitted `final.pt` even
though its successful metadata was uploaded. The release preserves that local
checkpoint under a new, versioned, non-destructive release URI and records its
SHA-256; the historical training prefix remains unchanged.
The validator compares their stored configs against one shared hyperparameter
contract. DeepSeek and CodeLlama runs were produced in different orchestration
runs, so input activation provenance and configuration parity are explicitly
checked instead of inferred from directory names.

## Not part of the frozen checkpoint

Feature relevance screening and causal interventions are ongoing. Existing
results identify promising DeepSeek features, but they are exploratory and are
not prerequisites for declaring the generation-to-CrossCoder checkpoint valid.
Future steering outputs can enter the same normalization, post-processing, and
evaluator path described in `STEERING_EVALUATION.md`.

## Release blockers and cautions

1. Re-run the bucket-backed validator and retain its JSON and Markdown reports.
2. Independently re-evaluate a deterministic sample in isolated benchmark
   environments to confirm stored labels.
3. Record immutable object generations or checksums in the final publication
   manifest before calling the release frozen.
4. Decide and document whether repaired CodeLlama metrics are primary,
   secondary, or sensitivity-analysis results.
5. Document the methodological limitation of `same_position` pairing when two
   models generated different continuations.
