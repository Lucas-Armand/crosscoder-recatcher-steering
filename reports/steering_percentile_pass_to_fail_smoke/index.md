# Low-percentile CrossCoder pass-to-fail steering smoke

## Objective

Test whether restoring merged-side decoder directions for corrected
P80-or-lower regression-associated features rescues historically paired
CodeLlama base-pass/merged-fail BigCodeBench tasks.

## Design

- CrossCoder: CodeLlama base versus merged, layer 16, 16,384 features.
- Features: 4815/P80, 13439/P80, and 4567/P60.
- Five tasks per feature, selected by the largest negative paired
model-side contribution differential among historical regressions.
- All 21 unique alpha-zero candidates reproduced failure (0/21 pass);
the top five per feature were retained.
- Traditional merged-side last-token steering at alpha +1, +2, +4,
with alpha -2 as a directionality control.
- Paper-v1 generation settings and per-task seeds; extraction v4 and
BigCodeBench 0.1.5 subset evaluation.

The selection percentile is an observational aggregation, not the alpha
unit. Actual intervention norms are reported below.

## Results

| Feature | P | Alpha | Vector norm | Changed | Passed |
|---:|---:|---:|---:|---:|---:|
| 4567 | P60 | -2 | 1.2969 | 2/5 | 0/5 |
| 4567 | P60 | 1 | 0.6484 | 0/5 | 0/5 |
| 4567 | P60 | 2 | 1.2969 | 1/5 | 0/5 |
| 4567 | P60 | 4 | 2.5938 | 2/5 | 0/5 |
| 4815 | P80 | -2 | 1.1787 | 0/5 | 0/5 |
| 4815 | P80 | 1 | 0.5894 | 1/5 | 0/5 |
| 4815 | P80 | 2 | 1.1787 | 2/5 | 0/5 |
| 4815 | P80 | 4 | 2.3574 | 3/5 | 0/5 |
| 13439 | P80 | -2 | 1.2773 | 1/5 | 0/5 |
| 13439 | P80 | 1 | 0.6387 | 1/5 | 0/5 |
| 13439 | P80 | 2 | 1.2773 | 1/5 | 0/5 |
| 13439 | P80 | 4 | 2.5547 | 3/5 | 0/5 |

No arm rescued a task: 0/60 steered generations passed. The null
result is not caused by an inert hook: at alpha +4, 4815 and 13439 each
changed 3/5 completions and 4567 changed 2/5.

## Qualitative effects

- **4815/P80:** task 566 moves from no useful implementation toward an
attempted argument-inspection implementation, but the generated iteration
is invalid. Task 504 only renames intermediate variables. Task 288 changes
a repetitive trajectory without implementing the required directory logic.
- **13439/P80:** task 722 becomes more complete but returns matched ERROR
strings rather than their count. Task 563 replaces a helper with a malformed
doctest, and task 592 shifts repetition from executable statements into
comments without completing CSV generation.
- **4567/P60:** positive steering sends task 722 to the same still-wrong
implementation reached by 13439. It reduces or changes repetition in tasks
288 and 976 but does not restore the requested computation.

The three merged decoder vectors are nearly orthogonal (pairwise cosine
range -0.0054 to 0.0399). Task 722 responding similarly to two different
features is therefore better treated as a perturbation-sensitive generation
attractor than as shared semantic evidence.

## Interpretation

The percentile screen successfully identifies stable observational
differences, but direct addition of an individual merged-side decoder vector
does not reconstruct the useful base behavior in this smoke. This rejects
the tested traditional intervention, doses, and selected tasks; it does not
prove the features are non-causal under activation-matched clamping or a
joint multi-feature intervention.

A stronger alpha is not the immediate next step because alpha +4 already
changes 40--60% of target completions without any recovery. The next useful
diagnostic is same-text joint-latent measurement for these features, followed
by clamping the latent/contribution toward the base value rather than adding
a constant decoder direction at every generation step.

Machine-readable outputs: [arm summary](arm_summary.csv) and
[task-level results](task_level_results.csv).
