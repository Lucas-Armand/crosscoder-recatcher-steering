# Token-only semantic interpretation: features 4810 and 4309

Saved-data-only revision requested on 2026-10-27. No GPU, new generation, or evaluation was run.

## Outputs

- `token_clouds_and_line_contexts.{png,pdf,svg}`: two token clouds and two descriptive CodeLlama context panels.
- `token_semantics_section.tex`: replacement subsubsection for Overleaf. Upload the figure into `emse-submission/crosscoder_case_studies/figures`.
- `active_newline_contexts.json`: all 141 active CodeLlama newline occurrences with exact source lines, token indices, offsets, categories, and activation values.
- `SUMMARY.json`: counts, denominators, mass fractions, and category definitions.
- `cloud_layout.json`: token-ID support, activation mass, visible labels, and display eligibility.
- `DATA_MANIFEST.json`: frozen-input hashes.

Reproduce with `.venv/bin/python tools/build_token_semantics_v2.py` from the repository root. The script regenerates data/figures, not the editable LaTeX text.

## Important denominator distinction

- Of 141 **active** newline occurrences, 49 end a main-function return statement (34.8%).
- Of 51 **available** return-ending newline occurrences, 49 activate (96.1%).
- Other newline activation: 92/327 (28.1%). Non-newline activation: 53/4320 (1.2%).
- Newlines carry 80.8% of total feature 4309 activation mass on the 50 original failing merged texts.
- Return statements may be conditional; the category does not mean final return of a function.
- Pooled counts weight token occurrences, not tasks equally; repeated statements within one task contribute multiple occurrences.

Line categories: main-function return end first; then blank/comment/block-header lexical checks; then AST raise/assignment end lines; remaining lines are other. The 23 other lines include calls/expressions and continue statements. This classification is not an error taxonomy.

Clouds use original shared TopK activations on failing base DeepSeek texts (119 tasks) and failing merged CodeLlama texts (50 tasks). Each cloud scales independently, with support >=3 tasks and up to 40 token IDs. Font/placement are qualitative; cross-cloud font sizes are not absolute activation comparisons. Statistics measure activation-weighted token profiles, not token-frequency-controlled correlations.

The existing reference `bricken2023monosemanticity` supports examining activating tokens/contexts as an interpretive technique. It is not cited as a source for this specific word-cloud visualization or custom AST categorization.
