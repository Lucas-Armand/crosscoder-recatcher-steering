# Bidirectional PR-AUC feature screening implementation notes

## Scientific definition

Each analysis case is a CrossCoder run, model side, benchmark, layer 16, and
`evaluated_tokens`. One generated solution is one observation. For every feature,
the score is its maximum latent activation over the exact generated-token rows
whose decoded character spans overlap code submitted to the evaluator.

Failure and success are evaluated separately:

- failure analysis: `y=1` means the solution failed;
- success analysis: `y=1` means the solution passed.

For direction `d`, with positive-class prevalence `pi_d`, the reported normalized
effect is

`normalized_effect_d = (PR_AUC_d - pi_d) / (1 - pi_d)`.

This puts the random-ranking baseline at zero for both directions, despite their
different raw PR-AUC baselines. Negative effects remain in the feature table but
are not treated as evidence of useful prediction.

The permutation effect/variability score is

`E/V_d = (observed_normalized_effect_d - null_mean_d) / null_sd_d`.

`E/V` is a reproducible permutation signal-to-noise ranking statistic, not a
Gaussian z-test. For each feature, `selected_direction` is whichever of failure
or success has the larger `E/V`. The plotted/summary top five are selected by
descending `E/V`, then normalized effect, after requiring activation count at
least 5 and activation proportion at least 0.01.

## Permutation inference

Labels are permuted within an analysis case with seed 42. The implementation
computes exact tie-aware average precision for both positive classes. For every
permutation it records the maximum positive normalized effect across every
nondegenerate feature and both directions. `p_maxT` is the add-one corrected
tail probability relative to that distribution.

Paper-v1 uses 200 permutations. Consequently, the smallest attainable adjusted
p-value is `1/201 = 0.00498`; this is a screening run rather than high-resolution
confirmatory inference. The ranked 95% permutation envelopes are exploratory and
do not replace `p_maxT`.

## Repository integration and exact alignment

The implementation extends the existing pipeline rather than adding loaders:

- `tools/crosscoder_common.py` supplies label indexing, activation discovery,
  checkpoint loading, CrossCoder encoding, and exact evaluated-token masks;
- `manifests/paper_v1_extraction_v4.json` discovers the paper cases;
- `reports/paper_v1_v4_evaluation_labels.csv` supplies evaluator outcomes;
- extraction-v4 raw/postprocessed rows supply the literal retained spans.

Exact historical alignment is possible for included rows. The loader reconstructs
the historical forward-pass string, uses tokenizer offsets, and requires complete
stored-token-ID equality before deriving a mask. It does not retokenize cleaned
code and assume positions stayed fixed. Prompt, padding, prompt-side special
tokens, removed suffixes, and post-cutoff EOS are excluded; a boundary token is
included if any decoded character overlaps retained evaluated text. Literal
non-prefix fenced blocks are supported through retained spans.

Some historical paired examples select zero positions after applying the target
side's exact mask to the last-N cross-model pairing used during CrossCoder
training. Those observations are rejected and listed per case; they are not
imputed. A case with only one outcome class is skipped because PR-AUC separation
is undefined.

## Computation and outputs

Activations are loaded one paired file at a time. Only per-solution feature maxima
are retained, avoiding accumulation of all token-level activations. Latents are
expected to be nonnegative after the CrossCoder ReLU; each case records its
minimum and fraction below `-1e-8`. Constant features are marked degenerate.

Every valid case contains:

- `feature_statistics.csv`, including both PR-AUC directions, prevalence
  baselines, normalized effects, permutation moments, E/V, `p_maxT`, support,
  class summaries, and envelope flags;
- `ranked_pr_auc_permutation_envelope.png`, with separate failure and success
  panels and the selected top-five feature IDs.

Global outputs are `index.md`, `all_cases_summary.csv`,
`top_feature_candidates.csv`, and `skipped_cases.json`.

## Reproduction

The Python entry point accepts repeated `--activation-root` arguments when
canonical artifacts are split across roots:

```bash
python tools/run_pr_auc_feature_screening.py \
  --manifest manifests/paper_v1_extraction_v4.json \
  --activation-root /path/to/deepseek/activations \
  --activation-root /path/to/codellama/activations \
  --checkpoint-root /path/to/checkpoints \
  --labels-csv reports/paper_v1_v4_evaluation_labels.csv \
  --dataset /path/to/extraction_v4/out \
  --output-root reports/pr_auc_feature_screening \
  --permutations 200 \
  --seed 42 \
  --device cuda
```

Use `--smoke-test` for 20 permutations and at most 48 observations per case.

## Assumptions and limitations

- Paper-v1 contains one generation per model/task (`generation_idx=0`).
- Association does not establish that a feature causally controls correctness.
- Small minority classes can make PR-AUC and E/V unstable; prevalence, class
  counts, support, and adjusted evidence must be read together.
- Repeated base-model cases use different CrossCoder dictionaries and are not
  duplicate statistical tests.
- Missing/duplicate labels, missing activations/checkpoints, ID mismatches,
  inexact masks, empty arrays, and one-class cases are reported rather than
  silently repaired.

## Modified files

- `tools/run_pr_auc_feature_screening.py` (new)
- `scripts/run_pr_auc_feature_screening.sh` (new)
- `tests/test_pr_auc_feature_screening.py` (new)
- `requirements.txt` (`numba`)
- `README.md`
- `reports/pr_auc_feature_screening/IMPLEMENTATION_NOTES.md` (new)
