# CodeLlama base→merged regression taxonomy and screening audit

## Scope

This audit uses extraction-v4 generation-0 labels and includes every base-pass → merged-fail transition: **291 BigCodeBench**, **39 HumanEval+**, and **330 total regressions**.

The taxonomy is versioned as `codellama_regressions_v1`. It separates terminal evaluator exceptions from rule-based behavioral tags. Tags are multilabel and are not ground-truth causal explanations.

## Failure distribution

| BigCodeBench primary label | Count | Fraction |
|---|---:|---:|
| API/type mismatch | 120 | 41.2% |
| Wrong logic/other runtime | 50 | 17.2% |
| Edge-case/exception | 43 | 14.8% |
| Generation limit/overgeneration | 32 | 11.0% |
| Missing required name/import | 18 | 6.2% |
| Syntax/incomplete code | 17 | 5.8% |
| Commentary-heavy | 11 | 3.8% |

For HumanEval+, the primary labels are 32 wrong-logic/other-runtime, two API/type, two missing-name/import, two edge-case/exception, and one syntax/incomplete case.

The multilabel view is more useful. In BigCodeBench, **89/291 (30.6%)** merged failures reached at least 500 evaluated tokens, 79/291 (27.1%) were comment-heavy, and 17/291 (5.8%) were syntactically invalid/incomplete. These labels can overlap.

## Manual audit

A deterministic stratified sample of **39 cases** (up to four per benchmark/primary stratum) was inspected. This is a single-reviewer audit, not inter-rater validation.

- Syntax/incomplete: 5/5 visibly supported.
- Missing name/import/entry point: 6/6 visibly supported.
- Generation-limit/overgeneration: 3/4 showed unmistakable repetitive degeneration; one merely reached the limit, so token count alone is insufficient.
- Commentary-heavy: the flag was present in 4/4, but all four had a more concrete implementation defect. It should remain an auxiliary tag, not a causal primary category.
- API/type, edge-case, and wrong-logic labels accurately summarize terminal outcomes in the inspected examples, but do not uniquely explain the underlying model error.

The taxonomy is adequate for **stratified exploratory screening**, but not yet for prevalence claims about semantic root causes. A second annotator would be required for agreement estimates.

## Why taxonomy matters for screening

The global regression screen compares 291 regressions with only 23 both-pass controls in BigCodeBench. The output-length distributions differ substantially:

| Cohort | n | Median merged tokens | P90 | ≥500 tokens |
|---|---:|---:|---:|---:|
| Regression | 291 | 134 | 513 | 30.6% |
| Both pass | 23 | 67 | 127 | 0% |

This is a concrete confound for `max`: longer generations provide more opportunities for a large maximum. Within regressions, the Spearman correlation between merged length and Δmax was 0.762 for feature 2857, 0.673 for 14881, 0.496 for 1058, 0.330 for 6128, and 0.270 for 3612.

The semantic contexts agree with this diagnosis:

| Feature | Observed contexts | Interpretation status |
|---:|---|---|
| 2857 | repeated separators, punctuation, `os os...`, repeated words | strong degeneration/length detector |
| 14881 | repeated newlines, zeros, `os os...`, repeated decimal fragments | strong degeneration/overgeneration signal |
| 1058 | repeated dataframe operations and repeated lines, often near 5–7% | early repetitive-degeneration candidate |
| 12671 | docstrings, doctests, newline structure | documentation/redefinition/overgeneration candidate |
| 3612 | broad structural tokens, numbers, `Error`, late incomplete constructs | broad error/structure feature; semantics not yet specific |
| 6128 | generic newline/dataframe/code structure | broad code-structure feature; semantics not yet specific |
| 4300, 8471, 2910, 10890 | plotting tokens and matplotlib contexts | likely domain/style features, not failure-specific explanations yet |

## Failure-tag enrichment within regressions

Comparing each tag against the other regressions (200 nominal label permutations), the strongest associations were:

- 2857 × generation-limit/overgeneration: E/V 14.42, ROC-AUC 0.944, support 89.
- 14881 × generation-limit/overgeneration: E/V 12.39, ROC-AUC 0.931, support 89.
- 1058 × generation-limit/overgeneration: E/V 10.19, ROC-AUC 0.795, support 89.
- 14881 × syntax/incomplete: E/V 6.06, ROC-AUC 0.864, support 17.
- 12671 × generation-limit/overgeneration: E/V 4.96, ROC-AUC 0.748, support 89.

These are exploratory, uncorrected, and partly length-mediated. The global top-10 is heterogeneous: some features encode a concrete degeneration phenotype, while others appear broad or domain-specific.

## Length-matched sensitivity analysis

Each of the 23 both-pass controls was greedily matched 1:1 to a regression using log base-text and merged-text token lengths. Median lengths were nearly identical (controls: base 80, merged 67; regressions: base 79, merged 64). The original top-10 were retested with 2,000 nominal permutations:

| Feature | Original rank | Matched E/V | Nominal p |
|---:|---:|---:|---:|
| 1058 | 8 | 3.01 | 0.0020 |
| 3612 | 2 | 2.80 | 0.0025 |
| 6128 | 9 | 2.13 | 0.0180 |
| 12671 | 6 | 1.69 | 0.0940 |
| 2910 | 5 | 1.66 | 0.1044 |
| 8471 | 3 | 1.66 | 0.0440 |
| 14881 | 4 | 1.65 | 0.0980 |
| 4300 | 1 | 1.60 | 0.1039 |
| 10890 | 7 | 1.37 | 0.0600 |
| 2857 | 10 | 0.81 | 1.0000 |

These p-values are **post-selection, nominal, and not maxT-corrected**. They are not confirmatory. Feature 2857's global rank is largely explained by length/degeneration, whereas 1058, 3612, and 6128 retain the strongest contrasts in a small length-matched cohort.

## Consequences for the next screen

1. Keep the global transition screen as association analysis, but do not treat its top-10 as equivalent causal candidates.
2. Add a length-controlled specification: matched sampling or permutations within length bins.
3. Run subtype screens within regressions (tag-positive versus other regressions) using `active_fraction`, `mean`, and early summaries in addition to `max`.
4. Prefer candidates with coherent **meaning ↔ failure mode ↔ activation timing**. Feature 1058 is currently the clearest early degeneration candidate; 3612 and 6128 survive length matching but need sharper semantic interpretation.
5. Validate the taxonomy with a second annotator before reporting subtype prevalence as a scientific result.

## Artifacts

- `regression_failure_cases.csv`: all 330 cases, evaluator categories, tags, lengths, similarity, and paired code.
- `failure_category_summary.csv`: primary and multilabel counts.
- `manual_audit_sample.csv` and `manual_audit_review.csv`: exact review sample and conclusions.
- `top10_feature_failure_tag_associations.csv`: within-regression tag associations.
- `length_matched_cohort.csv`: exact 23-pair sensitivity cohort.
- `top10_length_matched_sensitivity.csv`: retest of the original BigCodeBench top-10.
- `../codellama_base_merged_topk100_v1_feature_interpretation/`: task-level activation, timing, tokens, contexts, and geometry.
