# Historical-protocol replication with the current CrossCoder

## Question

This experiment tests whether current DeepSeek base-versus-merged CrossCoder
features reproduce the causal behavior previously observed for old feature 962.
It corrects protocol differences identified after the earlier steering smokes.

## Protocol recovered from the original notebook

- Exact first 20 `merged_only_correct` tasks printed by the notebook.
- DeepSeek base loaded in 4-bit NF4 with double quantization, float16 compute,
  eager attention, and greedy generation.
- Maximum 192 new tokens.
- Post-layer hook on layer 16 for the current checkpoint (the old checkpoint
  used layer 12).
- Only the last token is modified at every autoregressive step.
- Negative traditional steering uses the base decoder vector.
- Original alpha grid: `0, -0.10, -0.25, -0.50, -1.00`.
- Scale is P99 over all positive token-level joint-latent activations, not a
  percentile of per-solution aggregates.

The two independently generated zero arms were byte-identical for all 20 tasks.

## Recalculated scales

| Feature | Positive token values | P95 | P99 | Maximum |
|---:|---:|---:|---:|---:|
| 6258 | 19,749 | 2.6946 | 3.8856 | 7.3976 |
| 6873 | 19,216 | 2.4411 | 3.2243 | 4.8915 |

The capture retained 299/328 solutions after the historical paired finite-state
and hidden-norm `<500` filter. This numerical exclusion remains a limitation of
the scale estimate.

## Functional results

Both the original notebook extraction heuristic and the corrected extraction-v4
pipeline produce the same verdict transitions.

| Feature | Alpha | Passed | Fail to pass | Pass to fail | Net change |
|---:|---:|---:|---:|---:|---:|
| 6258 | 0 | 1/20 | 0 | 0 | 0 |
| 6258 | -0.10 | 1/20 | 0 | 0 | 0 |
| 6258 | -0.25 | 1/20 | 0 | 0 | 0 |
| 6258 | -0.50 | 1/20 | 0 | 0 | 0 |
| 6258 | -1.00 | 1/20 | 0 | 0 | 0 |
| 6873 | 0 | 1/20 | 0 | 0 | 0 |
| 6873 | -0.10 | 1/20 | 0 | 0 | 0 |
| 6873 | -0.25 | 1/20 | 0 | 0 | 0 |
| 6873 | -0.50 | 1/20 | 0 | 0 | 0 |
| 6873 | -1.00 | 1/20 | 1 (`HumanEval/78`) | 1 (`HumanEval/56`) | 0 |

Feature 6258 does not alter evaluated code under the historical extractor. The
v4 extractor retains one harmless suffix difference for HumanEval/65 at the
largest dose, without changing its verdict.

Feature 6873 at `-1 P99` has a real bidirectional causal effect:

- **HumanEval/78 improves.** The baseline ends inside an unfinished list and is
  syntactically invalid. Steering produces a complete `hex_key` implementation
  using `int(i, 16)` and the correct prime-valued digit set. It passes HumanEval+.
- **HumanEval/56 regresses.** The baseline contains a general stack-based
  bracket checker and passes. Steering replaces it with four hard-coded example
  branches. It fails held-out tests.

The HumanEval/78 change is especially notable because the same task was fixed by
old feature 962. However, the new feature does not reproduce the old result as a
net performance gain: the regression on HumanEval/56 exactly offsets it. The
scientifically defensible claim is partial mechanistic replication, not recovery
of the original beneficial feature.

## Evaluation-wrapper correction

`scripts/prepare_and_postprocess_generation.sh` previously exported steering
outputs to ZIP and invoked the legacy repair mode. That discarded prompt,
completion, extraction spans, and v4 strategy metadata. The wrapper now invokes
`reprocess_outputs_minimal.py --raw-results-dir`, which is the intended v4 path.
ZIP export remains only as a provenance artifact.

Before this correction, valid first-function prefixes could be obscured by an
unfinished repeated function later in the continuation. After correction, v4
selects the literal compilable prefix and agrees with the historical evaluator
on all causal transitions in this experiment.

## Conclusion

Matching the historical cohort, NF4 model, token-level scale, generation budget,
and hook protocol was decisive: it exposed a causal transition that the earlier
high-activation cohort did not. Task selection and scale definition mattered
more than escalating alpha. The next replication should test additional current
features on this fixed cohort and use a matched random decoder direction to
quantify how specific the HumanEval/78/56 swap is.
