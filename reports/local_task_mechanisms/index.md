# Local dimensions of the base-to-finetuned difference

## Question

This exploratory analysis does not seek a universal failure direction. It asks
which task-local residual dimensions explain behavior differences between the
DeepSeek base and finetuned checkpoints, with special attention to tasks whose
verdict changes.

The initial cohort contains `HumanEval/158` (direction-specific causal
candidate), `HumanEval/68` (perturbation-sensitive positive control), and
`HumanEval/96` (opposite/random-direction control).

## Representation decomposition

Both checkpoints were forwarded on exactly the same token IDs for each stored
base-generated and finetuned-generated program. Layer-16 residuals were RMS
normalized. For each task and source text, the analysis extracted the mean
finetuned-minus-base displacement and PC1--PC5 of the tokenwise displacement.

The leading component is large, but text dependent:

| Task | Mean-direction cosine across the two texts | PC1 cosine across the two texts | PC1 energy, base text | PC1 energy, finetuned text |
|---|---:|---:|---:|---:|
| HumanEval/158 | 0.244 | 0.241 | 0.671 | 0.467 |
| HumanEval/68 | 0.277 | 0.270 | 0.357 | 0.504 |
| HumanEval/96 | 0.303 | 0.279 | 0.626 | 0.482 |

This means that the largest checkpoint displacement is not a stable direction
independent of the program being processed.

For HumanEval/158, the successful held-out discriminant direction has cosine
0.532 with the different-own-text displacement. That one-dimensional local
axis accounts for 28.3% of its squared norm. The combined PC1--PC5 subspace
from both source texts accounts for 40.8%. CrossCoder decoder projections are
diffuse: the strongest single-feature absolute cosine for the local directions
is below 0.20. A single latent is therefore not an adequate explanation of this
candidate.

## Causal decomposition on HumanEval/158

All generations reproduce the paper-v1 capture contract: DeepSeek base in NF4,
layer 16, `temperature=0.2`, `top_p=0.95`, 512 generated tokens, stored seed
16800, and last-token traditional steering at every cached autoregressive step.
The same postprocessor and HumanEval evaluator were used for every arm.

The reference intervention is the unit LOTO discriminant at alpha `+6`, which
previously changed this task from fail to pass. We decomposed it as
`reference = projection + residual`. Magnitudes were preserved in the causal
ablation; the two parts therefore sum exactly to the reference direction.

| Direction at alpha +6 | Effective vector norm | Verdict | Behavior |
|---|---:|---|---|
| Reference LOTO discriminant | 6.000 | Pass | Explicit loop with correct lexicographically-smallest tie break |
| Projection onto different-own-text axis | 3.192 | Fail | Does not define `find_max` |
| Residual after removing different-own-text axis | 5.081 | **Pass** | Same correct explicit-loop algorithm |
| Projection onto local PC1--PC5 span | 3.831 | Fail | Retains incorrect `max(..., (count, word))` tie break |
| Residual after removing local PC1--PC5 span | 4.618 | **Pass** | Same correct explicit-loop algorithm |

The conclusion is local and mechanistic: for HumanEval/158, the causal
fail-to-pass effect is not carried by the dominant base-to-finetuned variation.
It survives removal of the first five tokenwise PCs from both programs. The
relevant dimension is a lower-variance residual that changes the semantic
choice from lexicographically largest to lexicographically smallest on ties.

This does **not** show that the residual is universally associated with
correctness. It shows that, for this task and intervention, a specific
model-difference dimension outside the dominant local subspace is sufficient
to produce the correct decision.

## Additional task-local causal contrasts

The identical magnitude-preserving decomposition was then applied to the two
most informative controls from the original smoke test.

| Task | Local subspace | Squared reference fraction | Projection verdict | Residual verdict |
|---|---|---:|---|---|
| HumanEval/68 | different-own-text | 0.347 | Fail | **Pass** |
| HumanEval/68 | joint PC1--PC5 | 0.285 | Fail | **Pass** |
| HumanEval/96 | different-own-text | 0.217 | **Pass** | Fail |
| HumanEval/96 | joint PC1--PC5 | 0.438 | **Pass** | Fail |

`HumanEval/68` repeats the HE158 residual-carried pattern. The base checkpoint
historically emits only `pass` for `pluck`. Both local projections still emit
only `pass`, whereas both residuals produce a complete loop that tracks the
smallest even value and its first index. This is nearly the same algorithm as
the historically successful finetuned solution. The causal effect is thus
associated with completing the implementation, but it lies outside the
dominant local displacement subspace.

`HumanEval/96` shows the opposite decomposition. Both local projections pass,
while both residuals fail with `NameError: is_prime is not defined`. The
passing projections generate both `count_up_to` and the required `is_prime`
helper. The failure mechanism is therefore structural program completeness,
not primarily an incorrect primality rule. Here the causally useful behavior
is carried by the observed local subspace rather than its residual.

These opposing results are evidence against treating a PCA projection or its
orthogonal residual as a universal success direction. They instead form a
small mechanism catalog:

- HE158: lower-variance residual changes a lexicographic tie-breaking rule;
- HE68: lower-variance residual changes an empty implementation into a complete
  selection algorithm;
- HE96: dominant local component induces the missing helper continuation.

The common object is not one geometric direction. It is a task-conditioned
dimension of the base-to-finetuned difference whose causal role must be tested
by projection/residual ablation.

## Reproducibility and limitations

- `tools/analyze_local_task_mechanisms.py` creates same-token local components
  and CrossCoder decoder projections.
- `tools/decompose_reference_directions.py` creates normalized exploratory
  components and magnitude-preserving causal projection/residual ablations.
- `scripts/run_local_task_decomposition.sh TASK_ID 6` reproduces the four
  causal decomposition arms for any task whose local directions exist. The
  original HE158-specific launcher is retained for provenance.
- Machine-readable outputs are under
  `runs/local_task_mechanisms/deepseek_base_finetuned_layer16/`.

This is a post-hoc single-task mechanism candidate. It needs replication on
other transition tasks before making a broader claim. PCA is descriptive and
variance-ordered; it is not expected to rank low-variance causal directions
highly. The decomposition also depends on the selected texts, layer, and RMS
normalization.
