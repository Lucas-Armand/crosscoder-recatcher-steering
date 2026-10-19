# Section 6.7 — semantic and temporal analysis draft

Prepared 2026-10-19 for discussion. No manuscript or presentation was edited. All plotted intervention magnitudes are between 0 and 5. This is a descriptive, within-cohort analysis, not independent confirmation or a multi-seed study.

## Scope and definitions

- DeepSeek: feature **4810**, 119 contamination improvements, steering **base** in the negative direction.
- CodeLlama: feature **4309**, 50 wrong-logic/runtime regressions, steering **merged** in the negative direction.
- Natural activation analysis uses both original texts of every task: 238 DeepSeek and 100 CodeLlama sequences. Each sequence was previously replayed through both models; the plotted latent is a **joint same-text feature**, not a separate feature activation for each model.
- Residuals are the saved layer-16, RMS-normalized capture arrays. Encoding uses the canonical step-10,000 checkpoint, ReLU and the **complete per-token TopK-100 competition over 16,384 latents**. No new language-model generations were performed for this analysis.
- Every saved input-token ID was verified against the tokenization/offset mask of its source text. Prompts are excluded according to the original capture rule. Input/checkpoint/activation checksums are recorded in `METHOD_AND_INPUT_AUDIT.json` and the original experiment manifests.
- First activation means the earliest token with strictly positive activation after TopK. Positions are evaluated-token index divided by `n-1`. Inactive tasks remain missing; they are not assigned to 100%.
- Natural timing is measured on the **frozen screening/capture code**. The first model divergence is the first differing character mapped to saved token offsets, not an annotated semantic error. The DeepSeek contamination marker is a documented regex heuristic, not a complete error detector.

## Figures

Each figure is available as PDF, PNG and editable SVG. `SECTION67_VISUAL_REVIEW.pdf` combines the nine figures.

1. **01_correctness_controls** — selected feature versus three pre-existing random CrossCoder latents and the three new negative shuffle directions. All curves include alpha-zero. Same percentage scale across models.
2. **02_code_changes_controls** — same arms, but exact evaluated-code change instead of correctness. Comments and formatting count as text changes.
3. **03_shuffle_both_signs** — all three shuffles in both signs, against the target's negative direction. This avoids hiding a better positive-control result.
4. **04_natural_timing_boxplots** — first natural activation on base/variant text, model divergence and the DeepSeek test/import marker. Boxes show median and quartiles, whiskers use 1.5 IQR, dots show individual tasks. Active-task denominators are explicit. Variant-text activation is not a variant-only encoder.
5. **05_activation_position_profile** — mean feature activation in 20 normalized-position bins, computed within each task before averaging tasks. This prevents longer texts from dominating the mean. Short sequences can have empty bins; those task/bin observations are missing, not zero.
6. **06_top_activating_tokens** — activation-mass shares, with support in at least three tasks. The denominator includes all activating tokens, even ones not displayed. Whitespace is made visible. These are activating-token statistics, not statistical correlations or a validated semantic label.
7. **07_steering_divergence_timing** — first code change by magnitude and official outcome. Unchanged outputs are excluded from the timing distribution rather than placed at 100%. Counts above boxes are task counts. Tasks recur across magnitudes; observations are not independent replications.
8. **08_case_studies** — inspected alpha-minus-five examples: DeepSeek /937 and /475; CodeLlama /490 and /878. Full diffs are in `CASE_INSPECTION.md`; complete before/after programs are in `steering_cases.json`. Snippets are explicitly truncated where necessary.
9. **09_natural_vs_intervention_timing** — baseline natural activation versus first steering-induced code change, at alpha-minus-five, using a common baseline token scale. Unconditional steering can change tokens before the feature activates naturally; such a point is not evidence for activation-gated suppression.

## Descriptive findings to discuss

### Curves and specificity

At magnitude five, DeepSeek 4810 corrects **14/119**, versus a best random latent of **7/119**, negative shuffle **6/119**, or positive shuffle **8/119**. CodeLlama 4309 corrects **2/50**, versus a best random latent or shuffle of **1/50**. The selected DeepSeek direction exceeds every tested shuffle at each magnitude 1–5. CodeLlama does not dominate at every dose: at magnitude two, one random latent corrects a task while the selected feature corrects none.

The comparison covers only these frozen controls, tasks and per-task seeds. Magnitude three was reused from selection; selection and evaluation share the same cohorts. No multi-seed significance claim is made. Shuffles are fixed coordinate permutations of a decoder direction, preserving its values/norm, with absolute cosine <=0.05 against the original and each other. They are **not learned CrossCoder features** or per-token independent noise. Pre-existing random latent controls have their frozen signs; they are not the same construction as shuffle controls.

### Natural timing and semantics

| Feature / text source | Tasks active | Median first activation among active tasks |
|---|---:|---:|
| 4810 / DeepSeek base text | 119/119 | 34.5% |
| 4810 / DeepSeek fine-tuned text | 75/119 | 65.7% |
| 4309 / CodeLlama base text | 50/50 | 31.5% |
| 4309 / CodeLlama merged text | 44/50 | 58.9% |

For DeepSeek base text, first activation is within ten percentage points of the heuristic contamination marker in **99/119** tasks. Contexts frequently contain generated test-file markers, `import`, `pytest`/`unittest`, and harness imports. This supports a test/import-boundary interpretation in this cohort, not a universal feature definition. The most frequent activation-mass tokens include newline (27.7%), `import` (24.4%), and `test` (6.5%).

CodeLlama 4309 is dominated by newline activations: **75.8%** of activation mass on base text and **80.8%** on merged text. Contexts include line boundaries, indentation, returns and validation branches. This is weaker evidence for an abstract "logic-error feature"; a structural/continuation interpretation is more cautious. Stronger behavior-level labels would require a separate validation study.

### Cases

- **DeepSeek /937, pass:** the solution body is unchanged; the failing generated test-module import is replaced by a direct example call. This is not simply "the model stopped": it continues, but without that failing import.
- **DeepSeek /475, fail:** the generated test/import tail disappears, but the official evaluator reports `NameError: locale is not defined`. There is also a plotting-parameter change; this is not a pure stopping-only example.
- **CodeLlama /490, pass:** writing JSON to the requested file is restored. The generated output still contains a duplicate helper function, so the outcome does not imply fully clean generation.
- **CodeLlama /878, fail:** validation code changes, but repeated checks persist and the task is not repaired.

## Important baseline/text alignment audit

Raw alpha-zero generation previously reproduced the weak-side references byte-for-byte. Nevertheless, the *frozen extracted source code used for activation capture* does not always equal the code produced by the current baseline re-extraction: exact equality holds in 44/119 DeepSeek and 21/50 CodeLlama cases. Many differences are trailing generated code retained by one extraction path but not the other.

This analysis **does not count these differences as steering changes**. Intervention diffs compare the current arm against alpha-zero extracted through the same current path. At magnitude five this reproduces the published **57/119 DeepSeek** and **27/50 CodeLlama** changed-code counts. Frozen natural activation anchors are mapped to the current alpha-zero text through exact matching blocks before comparing their timing to intervention divergence. One naturally active CodeLlama anchor cannot be mapped and is explicitly omitted from that scatter plot, separately from inactive features. The natural-timing box plots retain their original frozen-text coordinate system. The two timing coordinate systems should not be conflated.

Natural representations were captured offline using the training-corpus capture configuration; they are not online feature measurements under the NF4-steered generation. Most first model divergences precede first natural feature activation, reinforcing that textual divergence is not automatically the relevant error boundary. Static additive steering is applied at every generation step regardless of whether the feature would naturally activate.

## Reproduction and files

Run from the server repository root, with an available GPU selected for the encoder-only stage:

```bash
CUDA_VISIBLE_DEVICES=<available GPU UUID> .venv/bin/python tools/analyze_section67_semantics_v1.py --device cuda:0
.venv/bin/python tools/plot_section67_v1.py
```

Sources: canonical 119-task release; frozen original CodeLlama taxonomy and cohorts; completed dose-response release; the shuffle stress experiment and its +/-2,+/-4 extension. No artifact in the earlier runs was overwritten. No manuscript, slide deck or historical manifest was changed.

Machine-readable data: `natural_timing.csv`, `steering_timing.csv`, `curves.csv`, per-source `*_token_statistics.csv`, `activation_contexts.json`, `steering_cases.json`, and the two `*_feature_activations.npz` archives. `ACTIVATION_CONTEXTS.md` lists strongest contexts from 15 distinct tasks per source, selected by activation strength. Context interpretation and error taxonomy are not independently blinded annotations.
