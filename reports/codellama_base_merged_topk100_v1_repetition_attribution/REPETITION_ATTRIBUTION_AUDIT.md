# CodeLlama pre-repetition causal-attribution screen

## Question

Which naturally active TopK-100 CrossCoder features favor the first repeated token at the onset of a degenerative loop?

This is a first-order attribution screen, not an intervention result.

## Cohort and boundary

- Population: BigCodeBench base-pass → merged-fail regressions.
- Initial candidates: 89/291 merged outputs with at least 500 evaluated tokens.
- Deterministic boundary rule: earliest consecutive repeated token n-gram, motif length 1–16, at least four copies and at least eight repeated tokens.
- Eligible cases: 41/89; the remaining 48 were excluded because no unambiguous boundary was found.
- Manual audit: all 41 detected boundaries showed clear degeneration (repeated statements, comments, separators, digits, or words); no evident false positive was retained.

At the token immediately before the second motif occurrence, the objective was:

`logit(first repeated token) - logit(EOS)`

The gradient was projected onto naturally active canonical TopK-100 latents using the merged-side decoder. Positive attribution predicts that suppressing the feature should reduce the unwanted margin.

## Raw pre-repetition ranking

The leading broadly supported features were 9608, 7915, 13428, 5411, 8313, and 14673. Several were active in nearly every text, so the raw ranking could partly measure generic continuation versus EOS.

Feature 1058 was rank 49, supported in 19/41 tasks, and positive in 17/19 supported tasks. Observational repetition features 2857 and 14881 did not show positive pre-boundary attribution.

## First-occurrence placebo

For each repeated motif, the same attribution was computed at its first occurrence, before repetition was established. Forty tasks had a non-empty prefix for both boundaries. The paired score is:

`normalized attribution at second occurrence - normalized attribution at first occurrence`

This is a specificity sensitivity analysis. It is not a null experiment with exchangeable labels.

| Feature | Paired rank | Support | Positive contrast | Mean contrast | Contrast/task SD |
|---:|---:|---:|---:|---:|---:|
| 9608 | 3 | 35 | 22/35 | 0.00731 | 0.513 |
| 8313 | 11 | 39 | 27/39 | 0.00429 | 0.372 |
| 5411 | 31 | 40 | 29/40 | 0.00206 | 0.445 |
| 1058 | 62 | 19 | 12/19 | 0.00092 | 0.309 |
| 7915 | 67 | 37 | 19/37 | 0.00085 | 0.117 |
| 14673 | 342 | 40 | 21/40 | 0.00017 | 0.047 |
| 2857 | 879 | 5 | 3/5 | 0.00003 | 0.169 |
| 14881 | 2285 | 20 | 10/20 | -0.00010 | -0.051 |

## Interpretation

- **9608 is the preferred first intervention candidate.** It is sparse enough to be less generic than 5411/8313, has 35-task support, and its activation contexts emphasize newlines, separators, comments, and structural boundaries—the surface where many loops begin.
- **8313 is a broad secondary candidate.** Its paired signal is strong but it activates in 2,607/2,608 texts and therefore risks generic disruption.
- **5411 is a high-support control/candidate, but extremely broad.** It activates in all texts and 464,003 tokens.
- **1058 remains mechanistically plausible for repeated operations**, but it is no longer the leading choice after the matched first-occurrence placebo.
- **2857 and 14881 are primarily observational degeneration detectors**, not supported as initiators of the first repeated token by this objective.

## Recommended causal test

Use single-position steering at the highest positive-attribution pre-boundary position for feature 9608, followed by 1058 as a semantic comparator. Include:

- negative alphas to suppress the unwanted margin;
- the same feature at the first motif occurrence as a position placebo;
- a matched feature with similar support/timing;
- raw token, repetition-length, exact-code, and official pass/fail outcomes.

Because the screen is exploratory and the comparator is EOS, successful steering must be checked for premature termination rather than genuine recovery.
