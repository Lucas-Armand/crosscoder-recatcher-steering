# Token semantics: symmetric token clouds and a separate CodeLlama context chart

Revision 2026-11-02. Preserves the earlier 2026-10-27 four-panel figure as history.

## Scope

Only the original failing focal programs are analyzed: 119 DeepSeek base texts (feature 4810) and 50 CodeLlama merged texts (feature 4309). No passing-base CodeLlama comparison or conditional token-activation-rate panel is included in this subsection.

## Overleaf

- `token_semantics_section.tex`: complete replacement subsubsection.
- `emse-submission/crosscoder_case_studies/figures/feature_token_clouds.{png,pdf,svg}`: symmetric purple/orange clouds.
- `emse-submission/crosscoder_case_studies/figures/codellama_active_newline_contexts.{png,pdf,svg}`: one orange horizontal bar chart, with 141 active newline occurrences as its single denominator.
- `preview.pdf`: compiled standalone preview, for layout checking.

Copy the figure files to the same folder in the Overleaf project, then replace the old subsubsection with the supplied text. Bibliography keys reuse `bricken2023monosemanticity` and `CrossCoderReplication` already in the manuscript. The standalone preview uses abbreviated bibliography entries for those same keys.

## Counts and interpretation

Of 141 active CodeLlama newline occurrences: return 49, raise 28, block header 15, assignment 14, blank line 12, other 23. These sum to 141. They are token-occurrence proportions, not task proportions. Repeated occurrences within one task are counted separately. Return end lines can be conditional and do not mean the last return of a function.

Newlines carry 80.8% of total positive activation mass on the fixed 50 failing merged texts. This mass fraction and the line-occurrence proportions answer different descriptive questions and are explicitly distinguished in the text.

Clouds use up to 40 token IDs supported in at least 3 tasks, with font size scaled to the square root of activation mass independently within each feature. They are not controlled token correlations or absolute cross-feature activation comparisons.

## Reproduce

Run `.venv/bin/python tools/build_token_semantics_split_v3.py` from the repository root. Existing frozen token statistics and the previously audited 141 newline contexts are the only inputs. `DATA_MANIFEST.json` records source hashes and `VALIDATION.json` records cohort/count checks. No GPU or new generation is needed. The script does not overwrite editable LaTeX.

Occurrence-level evidence remains in `reports/feature_token_semantics_20261027_v1/active_newline_contexts.json`, including source line text, token indices, character offsets and activations. This revision intentionally changes presentation, not those measured counts.
