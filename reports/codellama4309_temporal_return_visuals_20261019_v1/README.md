# Feature 4309: temporal regions and return-line boundaries

## Figures

1. `01_temporal_regions_50`: all 50 failing merged outputs, with mapped first activation and evidence-tier-separated regions. The summary is 13 before, 27 within, 3 after, and 7 unavailable (6 inactive, 1 unmapped). Runtime execution sites and provisional omission/error regions are not validated earliest semantic errors.
2. `02_return_newline_specificity`: activation mass and token activation rate, explicitly distinguished. Labels refer to base-generated and merged-generated text jointly encoded in the same latent space, not independently learned model-specific features.
3. `03_annotated_activation_examples`: eight exact frozen-text snippets, marking the first active token. Includes both successes, unsuccessful expansion, before-region cases, and newline/non-newline counterexamples. Examples are purposefully selected and not a random prevalence sample.

All figures are available in PDF, PNG and SVG. `VISUAL_REVIEW.pdf` contains all three pages. No slides or paper text were modified.

## Key measurements

| Captured token category | Base positive / available | Merged positive / available |
|---|---:|---:|
| Newline ending a main-function return statement | 48/53 (90.6%) | 49/51 (96.1%) |
| Other newline-containing token | 127/403 (31.5%) | 92/327 (28.1%) |
| Non-newline token | 77/5125 (1.50%) | 53/4320 (1.23%) |

In merged text, 26.7% of total activation mass occurs on return-line newlines, 54.0% on other newlines, and 19.2% on non-newline tokens. Thus, a high activation probability at return newlines does NOT mean most activation mass is there. Return newlines are relatively rare.

The first activation in merged text is a return-line newline in 16 tasks, another newline in 18, and a non-newline token in 10; 6 texts are inactive. These frozen-text counts do not require mapping to current re-extracted code, hence they include the one active source whose temporal anchor could not be aligned.

## Interpretation

The feature preferentially activates at return-line newlines relative to other newlines, but this preference occurs in passing base text too. It is not an error-specific detector by this measurement. A return statement can be conditional and need not be the final statement of the function. The AST classification excludes returns inside nested helper definitions; it is a textual/syntactic indicator, not a dynamic control-flow analysis.

The two corrected cases (/183 and /490) first activate on the newline after their original return expressions. Current continuous steering can alter earlier decisions because it is added at every generation step; it does not establish natural activation-gated mediation. Earlier temporal activation in other cases is descriptive evidence, not proof of causation.

All rates are pooled token-level descriptions of the fixed 50-task cohort. They are not significance tests; tokens are not independent task replications. Natural activations are frozen offline measurements from the shared CrossCoder, not online measurements during intervention. Prompt tokens are excluded.

## Reproduce

From the repository root, use `.venv/bin/python tools/plot_4309_temporal_return_v1.py` after the saved localization and temporal-precedence analyses exist. Input files are in `reports/section67_semantic_temporal_20261019_v1/`, `reports/codellama4309_temporal_precedence_20261019_v1/`, and the original CodeLlama regression taxonomy. No model execution or new official evaluations are needed. The script uses the AST helpers in `tools/analyze_4309_behavior_hypothesis_v1.py`.

Numerical outputs: `SUMMARY.json`, `task_token_categories.json`, `first_activation_contexts.json`.
