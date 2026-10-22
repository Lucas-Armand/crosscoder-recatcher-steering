# Overleaf-ready sections 6.7 and 6.8

This package supplies the English manuscript text for **Semantic and Temporal Case Studies** and **Summary of Evidence**, paper-ready figures, the two agreed compact tables, a summary evidence table, and optional supporting visualizations. It uses existing results only; no model experiments were run for this writing task. The current main manuscript and presentation were not overwritten.

## Read first

- `preview.pdf`: compiled standalone manuscript preview.
- `crosscoder_case_studies/sections67_68.tex`: both subsections, ready to input or edit.
- `OVERLEAF_CASE_STUDIES.zip`: portable package with the preview source and the complete `crosscoder_case_studies` directory.
- `crosscoder_case_studies/figures`: four main figures in vector PDF/SVG and PNG.
- `crosscoder_case_studies/tables`: auto-generated natural-expression and same-text-contribution tables.
- `crosscoder_case_studies/supporting_figures`: detailed readout, timing, marker-ablation and control-sign reviews. These are intentionally not all in the main text.

## Add to an existing Overleaf project

1. Upload the complete `crosscoder_case_studies` directory to the project root, preserving its name and subdirectories.
2. Replace the two provisional subsections with:

   ```latex
   \input{crosscoder_case_studies/sections67_68}
   ```

3. The manuscript preamble needs `graphicx`, `booktabs`, and `amsmath`, which are the only dependencies of the inserted text. The standalone preview additionally uses geometry, lmodern and hyperref.
4. Keep the existing `CrossCoderReplication` bibliography entry if the manuscript already has it. Otherwise merge the supplied entry from `crosscoder_case_studies/references.bib` into the manuscript bibliography. Do not introduce a duplicate citation key.
5. Figure and table numbering is automatic. The preview sets section/subsection counters solely to display 6.7 and 6.8; do not copy those counter settings into the full manuscript.

To inspect the optional extra figures, input `crosscoder_case_studies/supporting_material.tex` separately. The full multipage same-text and marker reviews are also directly readable PDFs in `supporting_figures`.

## Narrative decisions

The main text compares DeepSeek 4810 and CodeLlama 4309 in parallel: sampled shuffled-coordinate directions (distinct from random learned latents in section 6.6), natural expression, same-text local readouts, behavioral temporal anchors, token contexts, code changes and scoped interpretation.

Natural-expression tables include ONLY task support and mean task activation. Same-text tables include ONLY the +/-10-token window. No median-first-position or after-function counts are brought back into the main narrative. Supporting PDFs retain the full analyses for audit.

The DeepSeek marker uses the first visible character, excluding leading blank lines allowed by the older regex. This explicit anchor definition is not silently equated with the original exploratory marker-start boxplot. CodeLlama uses previously localized regions of heterogeneous evidence quality; 48 anchors align to the frozen capture code. /115 and /423 are not assigned fabricated anchors.

Model-specific encoder terms contribute to one shared preactivation; they are not independently gated sparse activations. The CodeLlama decoder projection sensitivity is retained and acknowledged. Temporal precedence and semantic coherence are not presented as proof that the natural feature mediates a parameter-update effect. Controls are three sampled directions and inference uses one fixed seed per task; target selection and follow-up reuse cohorts.

## Reproduce figures and tables

From the repository root:

```bash
.venv/bin/python tools/build_overleaf_sections67_68_v1.py
cd reports/overleaf_sections67_68_20261022_v1
pdflatex -interaction=nonstopmode -halt-on-error preview.tex
bibtex preview
pdflatex -interaction=nonstopmode -halt-on-error preview.tex
pdflatex -interaction=nonstopmode -halt-on-error preview.tex
```

The builder regenerates figures, the two numeric table inputs, plot data and the input-hash manifest. It intentionally does NOT overwrite the manually editable subsection text. Analysis scripts and their detailed reports are published alongside this package. `crosscoder_case_studies/plot_data.json` retains the exact selected curves and task-level inputs used for the main visualizations; `DATA_MANIFEST.json` identifies the underlying reports and their hashes. Large raw activation files/checkpoints remain in their existing canonical storage rather than being duplicated inside an Overleaf download.

`crosscoder_case_studies/data` additionally preserves the exact 119 original evaluated strings per DeepSeek text source, with per-program hashes, because some historical analysis scripts read them from `/tmp/dstk119_source_evaluation`. To rerun those scripts on a fresh machine, restore these two JSONL snapshots to that directory first; keep the same filenames. Only task IDs and evaluated code are needed from these snapshots. This does not substitute the different, currently re-extracted intervention baseline.

## Source analyses

- `reports/section67_semantic_temporal_20261019_v1/`: canonical curves, token statistics, frozen sparse activations and source alignment audit.
- `reports/deepseek4810_marker_precedence_20261022_v1/`: original versus visible-token marker sensitivity.
- `reports/deepseek4810_marker_followup_20261022_v1/`: token-distance distributions, saved evaluator evidence and every changed alpha-minus-five program.
- `reports/deepseek4810_marker_components_20261022_v1/`: comment/import/class coverage ablation.
- `reports/deepseek4810_finetuned_contexts_20261022_v1/`: natural fine-tuned activation contexts.
- `reports/deepseek4810_same_text_branches_20261022_v1/`: same-input branch/readout comparisons and local-versus-global checks.
- `reports/codellama4309_same_text_tables_20261022_v1/`: natural and same-text analogues for CodeLlama.
- `reports/codellama4309_change_comparison_20261019_v1/` and `codellama4309_temporal_return_visuals_20261019_v1/`: uniform target/control code comparison and return-newline evidence.
- `reports/CODELLAMA_4309_ALL_50_ANNOTATED_PTBR.md`: all 50 localized examples with source lines, marker and rationale.

## Scope

This is a polished first manuscript draft, not independent validation or a claim of a complete mechanism for all regressions. Prior reports, including the previous consolidated review, are preserved. Package generation and compilation do not modify any GPU process or experiment run.
