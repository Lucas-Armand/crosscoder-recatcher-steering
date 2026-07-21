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
