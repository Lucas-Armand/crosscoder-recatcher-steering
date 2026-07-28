# Post-processing and Evaluation Policy

The canonical v3 pipeline separates four concepts:

1. model output (`raw_results`);
2. deterministic repair record (`results` and `results_repaired`);
3. evaluator input (`samples_for_external_eval`);
4. evaluator evidence (`eval` and `reports`).

## Allowed canonical repairs

- visible byte-level newline, tab, and space markers;
- a Markdown fence surrounding the complete response;
- the observed CodeLlama three-space indentation artifact.

The optional glued-token repair is exploratory and is forbidden for canonical
metrics. The tokenizer issue that produced glued DeepSeek tokens was addressed
by re-running generation with a tokenizer round-trip guard.

## Interpretation

A deterministic repair is reproducible, but reproducibility does not imply
semantic neutrality. In Python, indentation is syntax and can affect block
structure. Reports must therefore expose:

- raw compile success;
- repaired compile success;
- number and type of modifications;
- raw correctness when available;
- repaired evaluator correctness;
- evaluator/infrastructure errors.

The publication should state which metric is primary and include an unrepaired
sensitivity analysis for model comparisons affected by repair.

## Known v3 repair volume

DeepSeek required no v3 changes. CodeLlama changed many rows, especially for the
three-space indentation artifact. Exact counts are read from the 12
`repair_summary__*.csv` files by the release validator; they should not be copied
manually into the paper without regenerating the report.
# Extraction v4

The paper-v1 evaluation dataset now uses deterministic extraction v4. Historical
v3 artifacts remain immutable for comparison.

Extraction v4 operates directly on `prompt` and `raw_completion`; it does not
use evaluator outcomes to select code. It:

1. preserves a valid historical candidate by default;
2. prefers a leading literal Python continuation when the historical heuristic
   discarded it for later fenced prose or non-Python code;
3. selects the first Python-labelled fence rather than the largest fence;
4. retains complete helper definitions referenced by the entry point;
5. removes explicit test, demonstration, main-guard, and explanation suffixes;
6. drops only an incomplete trailing definition, using the longest line-aligned
   syntactically complete prefix;
7. records the exact generated-character spans and selection strategy.

Conservative visible-token and three-space indentation repairs run only after
literal extraction. Every selected span must reproduce the stored generated
text exactly.

The reproducible launcher is:

```bash
bash scripts/run_postprocess_and_eval_from_scratch_v4.sh
```

The canonical versioned artifact prefix is:

```text
crosscoder_final_dataset_v1_postprocessed_extraction_v4/
```

See `reports/postprocessing_v4_validation.md` for the v3/v4 evaluation
comparison and mask integrity results.
