# Same-text joint-latent analysis: implementation notes

## Scope

`tools/run_same_text_joint_latent_pr_auc.py` analyzes previously evaluated
HumanEval+ solutions. The exact same repaired code and tokenizer IDs are passed
through the DeepSeek base and merged models. The script does not generate or
evaluate new solutions.

For each retained solution it captures the post-layer-16 hidden state from both
models, selects only evaluated-code tokens, RMS-normalizes each token vector,
and evaluates the trained joint latent:

```text
z = ReLU(linear(rms(h_base), encoder_base)
       + linear(rms(h_merged), encoder_merged)
       + encoder_bias)
```

The code verifies identical token IDs across the two forwards. Literal prompt
prefixes are excluded by tokenizer offset mappings. Full-function replacements
that do not preserve the prompt begin at character zero. Prompt tokens, padding,
and special tokens with empty offsets are excluded.

## Per-solution summaries and screening

For every feature the script stores mean, maximum, P95, P99, active fraction,
activation sum, first P95 position, first- and second-quarter mean, and the
maximum-token index. Failure is the positive class for PR-AUC. Because average
precision depends on prevalence, the report also gives prevalence-normalized PR
effect and its deviation from the permutation null in null-standard-deviation
units (`effect_to_variability`).

Two hundred permutations are exploratory. The maxT p-value jointly covers all
16,384 features and all five requested aggregations. A final analysis should use
5,000 permutations.

Additional diagnostics are decoder-vector norm specificity, the mean base and
merged additive encoder contributions, observed activation share between source
solution groups, activation entropy across tasks, first P95 position, and early
code-quarter activation. They are reported separately and are not combined into
an unvalidated composite selection score.

## Numerical limitation

The current merged model produces non-finite or extreme layer-16 states for a
subset of same-text inputs even with eager attention and bfloat16. To match the
historical analysis, tokens are retained only when both hidden vectors are finite
and both norms are below 500. A solution is skipped if no paired evaluated token
survives.

In the recorded run, 295/328 solutions were retained, 33 were fully skipped, and
3,295 individual tokens were removed. This 10.1% solution exclusion is material
and may bias PR-AUC. The report therefore remains exploratory. The exact skipped
task list and reasons are in `run_summary.json`; the retained token offsets and
counts are in `solution_metadata.json`.

## Artifacts

Large, regenerable artifacts are kept out of Git:

- `solution_feature_aggregates.npz`;
- `feature_aggregation_statistics.csv`;
- `solution_metadata.json`.

Compact report artifacts, candidate tables, contexts, and run metadata may be
versioned. The repository and bucket policies should continue to treat the large
forward-pass products as external analysis artifacts.
