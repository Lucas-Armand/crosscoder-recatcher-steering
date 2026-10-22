# DeepSeek 4810: same-text model comparison

`SAME_TEXT_BRANCH_REVIEW.pdf` contains six pages: reading guide; paired model differences; profiles around the visible marker on original base text; profiles around main-function end on both text sources; exact fixed-readout sensitivity; local contrast against the rest of the same code. All figures also have PDF/PNG/SVG versions.

## Design

119 BigCodeBench improvement tasks, with both original base-generated and fine-tuned-generated code: 238 texts. Each text was already replayed through both models using identical token IDs. This analysis reads those saved layer-16 RMS-normalized, FP16 activation arrays and the trained CrossCoder checkpoint; no model execution, GPU use, generation or evaluation is performed. Calculations use float32 on CPU.

For feature j=4810, separate encoder terms are `u_base = W_base[j] dot h_base` and `u_FT = W_FT[j] dot h_FT`. Their sum plus ONE shared bias gives the feature preactivation. ReLU and TopK act JOINTLY across all latents; the individual terms are not independently gated feature activations. Positive preactivation alone need not survive TopK. We use the previously saved exact TopK sparse activation for the shared-active scope, not a new per-branch gate.

Other measurements:

- Encoder alignment: cosine of each residual with its corresponding encoder row.
- Decoder alignment: cosine of each residual with its corresponding decoder column.
- Centered decoder alignment: subtract the corresponding learned decoder bias before cosine.
- Fixed reference checks: project BOTH residuals onto the SAME base-reference, FT-reference, or mean-of-unit-directions vector. This removes branch readout differences within each comparison. Same coordinates are available because the fine-tuned model retains the base architecture; geometric comparability is not an independently proven semantic equivalence.

The encoder row norms differ (0.91946 and 0.89721). Decoder norms are 0.72132 and 0.69260; their directional cosine is 0.96653. Raw encoder contributions are therefore supplemented by normalized and fixed-reference checks.

## Main results on the same original failing base text

| Region | Base encoder contribution, task mean | FT contribution, task mean | FT lower |
|---|---:|---:|---:|
| Whole evaluated sequence | -0.5238 | -0.5263 | 59/119 |
| Ten tokens before visible marker | See paired_summary.json | See paired_summary.json | 55/119 |
| Marker token plus next ten | See paired_summary.json | See paired_summary.json | 110/119 |
| Marker +/-10 tokens | 0.9276 | 0.6308 | 103/119 |

The whole-text raw contribution difference is near zero (mean FT-base -0.00248; task bootstrap interval spans zero). The original-branch encoder difference before the marker is also not clearly negative (mean +0.01455; interval spans zero). After the marker, mean FT-base is -0.58029 with 110/119 tasks lower. Thus these measurements do not support a blanket claim that the feature is suppressed everywhere or that its encoder contribution already differs consistently before comment emission.

Within +/-10 tokens, own-branch normalized decoder alignment is lower in FT in 113/119 tasks. Using exactly the base decoder vector for both models gives 119/119 lower; using the FT decoder vector gives 111/119 lower. Encoder fixed-reference comparisons also remain lower in FT: 114/119 with the base encoder row, 119/119 with the FT row. Centering the decoder residual does not reverse the own-branch result.

To check global representation shift, subtract each task's FT-base difference outside the marker window from its difference inside. The local contrast is more negative in 106/119 tasks for raw encoder contribution, 105/119 for normalized encoder alignment, 111/119 for own-branch decoder cosine, and 110/119 for common-reference decoder cosine. This is descriptive evidence for localization beyond a uniform global shift, not specificity against randomly selected features or other behaviors.

On original FT-generated texts, the all-code raw encoder contrast is again not clearly negative. Near their main-function end, the FT encoder contribution is on average HIGHER than the base contribution (+0.07552; 75/119 tasks higher), whereas the decoder alignment is lower. Encoder/decoder metrics are not interchangeable, and the text-source sensitivity must not be hidden.

## Interpretation and limits

Holding the text fixed, the models represent the test/import-marker region differently along readouts associated with 4810. On base-generated text the fine-tuned model provides a smaller contribution to this shared feature near/after the marker and lower decoder-direction alignment. This complements, but does not establish mediation of, the observed reduction in problematic natural continuations. Forced replay does not mean the fine-tuned model would naturally generate that text or that the identical program would pass when attributed to a different model.

This is exploratory within the selected cohort, without held-out validation or random-direction representational controls. All reported windows (+/-10, pre-10 and marker-plus-10) are explicitly documented and should not be interpreted as optimized or canonical boundaries. The lexical marker is not necessarily the first harmful operation. Prompt activations are excluded. At sequence boundaries only available tokens are used; per-offset sample sizes can vary.

Task summaries use equal task weights; they are not pooled independent-token tests. Summary bootstrap intervals resample paired tasks (2,000 replicates, seed 42) and do not correct exploratory multiple comparisons or establish population generalization. Profile shading is the interquartile task range, NOT a confidence interval.

## Validation / reproducibility

Token IDs match across both replayed models and the existing cached feature tokens for all 238 texts. Sum-of-encoder-terms plus bias matches the previously cached nonzero sparse activations to maximum absolute error 1.15e-5. `VALIDATION.json` records checkpoint, input activation file and cached-array hashes, branch norms, and CPU runtime.

Numerical outputs include all task/scope rows, all aligned profiles, per-token measurements, local-specificity statistics, and the exact readout vectors. Run `tools/analyze_4810_same_text_branches_v1.py` with the existing paired capture corpus and checkpoint available. The script performs no new inference.
