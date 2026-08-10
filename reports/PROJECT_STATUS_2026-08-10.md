# CrossCoder/ReCatcher Project Status — 2026-08-10

## Executive summary

Over the last several days, the project moved from a completed, technically sound same-text TopK CrossCoder (`DSTK100`) to a reproducible causal steering result with semantic and geometric controls.

The main finding is that DSTK100 feature **6404**, interpreted as a feature associated with expectation/assumption language, comments, and solution-following boilerplate, causally controls a concrete BigCodeBench failure mode in the DeepSeek base model: generating tests or imports after an otherwise plausible solution. In a preselected mechanistic cohort of 80 such failures, online TopK-gated suppression at `alpha=-2` converted **19/80** failures to official BigCodeBench passes and removed the test/import contamination in **41/80** cases. At the same alpha, a norm-matched orthogonal sham passed **0/80**, and three temporally and geometrically matched CrossCoder features passed at most **3/80**.

This is strong evidence of feature-specific causal control in the selected cohort. It is not yet an estimate of out-of-sample generalization because the cohort was selected using the observed failure mode and natural activation of feature 6404.

## Repository and canonical experiment state

- Repository: `/home/lucas/crosscoder-recatcher-steering`
- Branch: `paper-v1-reproducibility`
- Experiment base commit: `784bd49` (`Screen DSTK100 features for steering`)\n- Status and reproducibility commit: `22d92f4` (`Document and validate DSTK100 causal steering`)
- Previous canonical DSTK100 training commit: `8018a2a`
- Canonical checkpoint: `runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt`
- Canonical checkpoint step: 10,000
- Technical model identifier: `deepseek_base_finetuned_l16_sametext_topk100_10k`
- Communication name: `DSTK100`

The repository currently has uncommitted work from the analyses and steering experiments described below. Historical artifacts and checkpoints were not overwritten.

## Starting point: DSTK100

DSTK100 is a same-text CrossCoder trained on DeepSeek base and finetuned layer-16 residuals.

- 2,608 evaluated code texts
- 617,959 evaluated tokens
- HumanEval+ and BigCodeBench
- Identical token IDs passed through both models
- Prompt and non-evaluated text excluded
- RMS normalization before storage
- Grouped validation split by task
- 16,384 latents
- TopK = 100
- 10,000 canonical training steps
- Validation L0 = 100
- Validation loss = 0.442
- Validation MSE: base 0.208, finetuned 0.234

The critical implementation requirement is retained throughout the new work:

```text
dense = relu(encoder(concat(base_residual, finetuned_residual)))
values, indices = topk(dense, k=100)
z = scatter(values, indices)
```

All new screening and online gating use the TopK-100 representation, not the dense ReLU encoder output.

## Feature screening and semantic interpretation

New tooling was added to screen temporal feature behavior and inspect high-activation contexts:

- `tools/screen_dstk100_temporal.py`
- `tools/analyze_dstk100_features.py`
- `reports/dstk100_temporal_feature_screening/`
- `reports/dstk100_feature_interpretability_v1/`

The feature-level audit combined activation strength, support, first activation position, early-code concentration, decoder geometry, transition labels, active tokens, and high-activation textual contexts.

### Main interpreted features

| Feature | Working semantic interpretation | Assessment |
|---:|---|---|
| 16383 | Input validation, `raise`, `ValueError` | Semantically clear; causal behavior was fragile and not simply related to activation magnitude. |
| 14481 | Plotting, DataFrames, constraints | Broad and likely polysemantic; steering was null in the initial smoke test. |
| 12956 | Expected output, example usage, explanatory comments | Clear but generally late; better interpreted as a style/continuation marker than an early algorithmic feature. |
| 6404 | `expected`, `should`, assumptions, comments, boilerplate | Strongest semantic and causal result; associated with continuation into tests/imports. |
| 8587 | Numeric literals, especially `0` | Predominantly lexical; weak evidence for a causal numerical-reasoning interpretation. |
| 8294 | Python/meta-commentary/file-language | Related to metadata and comments, but some activations are ordinary early uses of “Python.” |
| 11785 | Model fitting, train/test, regression, `.fit` | Semantically coherent on ML tasks; promising for a future targeted experiment. |

Decoder-side cosines between base and finetuned were high for the inspected features, so they are mostly shared features rather than strongly model-exclusive latents.

## Preliminary gated steering

Early gated experiments tested features 16383 and 14481 on four selected regression tasks.

| Arm | BCB/138 | BCB/259 | BCB/409 | BCB/756 |
|---|---|---|---|---|
| Baseline | fail | fail | fail | fail |
| 16383, -0.25 | pass | pass | fail | fail |
| 16383, -0.5 | fail | fail | fail | fail |
| 16383, -1 | fail | fail | fail | fail |
| 16383, +1 | fail | fail | fail | fail |
| Sham, -1 | fail | fail | fail | fail |
| All 14481 arms | fail | fail | fail | fail |

This established that gated feature steering could produce real corrections, while also showing that response to alpha was not monotonic.

## Transition-level failure audit

A rule-based failure taxonomy was created and joined with DSTK100 feature evidence:

- `tools/analyze_transition_failures.py`
- `reports/dstk100_transition_failure_analysis_v1/`

The audit covered all DeepSeek base/finetuned one-sided transitions:

- 343 total transitions
- 86 regressions: base pass → finetuned fail
- 257 improvements: base fail → finetuned pass

### BigCodeBench regressions (79)

- 19 truncation/token-limit or extraction cases
- 18 wrong-output/logic cases
- 11 file/path handling cases
- 11 missing-name/import cases
- 20 distributed across wrong types, wrong APIs, unexpected values, commentary, and other runtime failures

### HumanEval+ regressions (7)

- 6 wrong-output/logic cases
- 1 recursion failure

### Major BigCodeBench improvement mode

The most important discovery was that **119/215 BigCodeBench improvements (55%)** were base-model test/import contamination. The base model frequently generated a function and then continued with content such as:

```python
# tests
from task_func import task_func
```

The finetuned model often passed by stopping cleanly rather than by implementing a different algorithm.

Feature 6404 was active in 67% of these contamination cases versus 31% of other improvements (exploratory odds ratio approximately 4.44). Feature 12956 had even higher raw enrichment, but its activations were generally later and less suitable for early causal control.

## Feature 6404 causal experiment

### Cohort

The mechanistic cohort contains 80 BigCodeBench tasks satisfying all of the following:

- DeepSeek base failed
- DeepSeek finetuned passed
- the base failure contained generated tests/import contamination
- feature 6404 was naturally active in the base generation

This is a deliberately selected mechanistic cohort, not a held-out generalization set.

### Reproduction gate and protocol corrections

The first baseline attempts correctly stopped before steering because they did not reproduce the historical generations. Two issues were diagnosed:

1. repaired rows did not carry the canonical per-task seeds;
2. the initial runner used the finetuned tokenizer for the base target.

The corrected protocol uses:

```text
seed = 1000 + task_idx * 100 + gen_idx
tokenizer = deepseek-ai/deepseek-coder-6.7b-base
```

After correction, the paired cached backend reproduced **80/80 raw completions exactly** at `alpha=0`. Invalid baseline attempts were preserved under the run's `audit/` directory.

### Intervention

The experiment uses online TopK-gated suppression:

1. run the current context through base and finetuned models;
2. capture the layer-16 residual at the last token;
3. RMS-normalize and concatenate the two residuals;
4. apply the DSTK100 encoder, ReLU, and TopK-100;
5. intervene only if feature 6404 is in the active TopK set;
6. add the scaled base-side decoder direction before predicting the next token.

Conceptually:

```text
h_t' = h_t + alpha * z_6404,t * RMS(h_t) * d_6404,base
```

The intervention affects the next token. It does not retroactively modify already generated tokens.

### Dense alpha sweep

| Alpha | Official passes | Pass rate | Test/import contamination removed |
|---:|---:|---:|---:|
| 0 | 0/80 | 0.0% | 0/80 |
| -0.25 | 0/80 | 0.0% | 3/80 |
| -0.5 | 12/80 | 15.0% | 28/80 |
| -0.75 | 3/80 | 3.75% | 11/80 |
| -1 | 1/80 | 1.25% | 1/80 |
| -1.25 | 1/80 | 1.25% | 4/80 |
| -1.5 | 1/80 | 1.25% | 3/80 |
| -2 | **19/80** | **23.75%** | **41/80** |
| -2.5 | 4/80 | 5.0% | 6/80 |
| -3 | 3/80 | 3.75% | 11/80 |
| -4 | 1/80 | 1.25% | 3/80 |

The response is strongly non-monotonic. There is a secondary effective regime near `-0.5` and a primary regime at `-2`. Stronger suppression does not improve performance.

High-resolution curve artifacts:

- `reports/dstk100_f6404_dense_curve_v1/curve.csv`
- `reports/dstk100_f6404_dense_curve_v1/f6404_dense_steering_curve.png`

## Placebo and matched-feature controls

### Orthogonal sham

A deterministic random direction was constructed with:

- seed 6404
- the same norm as the native base-side feature-6404 decoder direction
- cosine with feature 6404 approximately `-5.5e-10`
- the same 6404 gate, activation value, RMS scaling, tasks, and seeds

The runner was extended with an explicit option to preserve externally supplied direction norms. This prevents the sham from being silently unit-normalized and ensures an energy-matched comparison.

At `alpha=-2`:

| Direction | Passes | Contamination removed |
|---|---:|---:|
| Feature 6404 | 19/80 | 41/80 |
| Orthogonal sham | 0/80 | 0/80 |

Paired exact McNemar results:

- pass outcome: `p ≈ 3.8e-6`
- contamination removal: `p ≈ 9.1e-13`

At lower strength, the sham also demonstrated why controls are necessary: at `alpha=-0.5`, feature 6404 passed 12/80 while the sham passed 7/80. The difference at that strength was not statistically clear (`p ≈ 0.302`).

### Matched DSTK100 feature controls

Control features were selected to match feature 6404 in activation support, temporal profile, decoder norm, model specificity, and low decoder cosine, while having unrelated semantic interpretations.

| Feature | Interpretation |
|---:|---|
| 9388 | Comparisons, `<`, `<=`, “less than,” numeric validation |
| 6757 | Loop index `i`, `range`, iteration |
| 6509 | Chunked reads, files, sockets, `read`/`recv` loops |

At `alpha=-2`:

| Feature/direction | Passes | Contamination removed | Tasks with active gate |
|---|---:|---:|---:|
| 6404 | **19/80** | **41/80** | 66/80 |
| 9388 | 2/80 | 6/80 | 68/80 |
| 6757 | 3/80 | 6/80 | 61/80 |
| 6509 | 0/80 | 2/80 | 61/80 |
| Orthogonal sham | 0/80 | 0/80 | gate based on 6404 |

Feature 6404 significantly exceeded each matched feature in paired pass outcomes (`p < 4.1e-4`) and contamination removal (`p < 3e-9`). The controls were genuinely active online, so their weaker effects cannot be explained by lack of gating.

At stronger coefficients, specificity degraded:

| Direction | Passes at -3 | Passes at -4 |
|---|---:|---:|
| 6404 | 3/80 | 1/80 |
| Orthogonal sham | 1/80 | 0/80 |
| 9388 | 7/80 | 3/80 |
| 6757 | 0/80 | 0/80 |
| 6509 | 0/80 | 0/80 |

This reinforces the conclusion that `alpha=-2` is a task- and protocol-specific effective window, not evidence that larger interventions are universally better.

## Interpretation of the non-monotonic curve

The jagged response is plausible for this protocol because:

- token sampling is discrete even when residual changes are continuous;
- top-p membership and token ordering can change abruptly;
- a changed token changes the entire future autoregressive context;
- future CrossCoder activations and gate positions then change;
- pass/fail is a discontinuous binary metric;
- a single generation seed per task produces a noisy pass@1 curve;
- large interventions can leave the model's locally natural activation regime and damage unrelated code behavior.

The controls show that the `alpha=-2` result is not explained by generic residual perturbation alone. However, the exact shape and sharpness of the peak should not be treated as stable until replicated across generation seeds.

## Important tooling changes and operational lessons

### New or extended tools

- `tools/analyze_dstk100_features.py`
- `tools/analyze_transition_failures.py`
- `tools/screen_dstk100_temporal.py`
- `tools/run_crosscoder_intervention.py`
  - synchronized paired-cache generation
  - online TopK-100 gating
  - per-step gate traces
  - externally supplied per-example directions
  - optional preservation of external direction norms

### New runners

- `scripts/run_dstk100_f6404_general_v1.sh`
- `scripts/run_dstk100_f6404_sham_v1.sh`
- `scripts/run_dstk100_matched_features_v1.sh`
- `scripts/run_dstk100_extended_neg3_neg4_v1.sh`
- `scripts/run_dstk100_f6404_dense_curve_v1.sh`

### Pipeline issues found and corrected

- Canonical seeds must be materialized in intervention input rows.
- The target model's tokenizer must be used for exact baseline reproduction.
- The baseline reproduction gate must compare raw completions exactly before steering arms run.
- BigCodeBench evaluation must consume `samples_for_external_eval`, not repaired internal rows.
- External sham directions must preserve their intended norm for an energy-matched control.

## Current evidence strength

### Supported

- Feature 6404 has a reproducible semantic association with expectations, comments, assumptions, and post-solution boilerplate.
- In the selected contamination cohort, suppressing feature 6404 can causally remove generated tests/imports.
- At `alpha=-2`, the direction is substantially more effective than a norm-matched orthogonal sham and three matched DSTK100 features.
- The effect changes the exact code evaluated by extraction v4 and produces official BigCodeBench passes.

### Not yet supported

- Generalization to tasks not used to define the contamination cohort.
- A monotonic causal relationship between feature activation and behavior.
- The claim that every activation of feature 6404 represents test generation.
- Stability of the narrow alpha peaks across sampling seeds.
- A general pass/fail direction applicable across unrelated failure modes.

## Recommended next steps

1. **Multi-seed replication around the effective region.** Repeat a focused grid such as `-0.5, -1, -1.5, -2, -2.5` with multiple generation seeds per task. Estimate mean pass probability and contamination-removal probability with paired uncertainty.
2. **Held-out negative cohort.** Apply the same intervention to tasks without test/import contamination to measure collateral damage and false-positive behavioral suppression.
3. **Selection/evaluation split.** Define feature and alpha using one task subset, then report final performance on a held-out subset.
4. **Token-level mechanism audit.** For corrected and harmed cases, record first natural activation, first changed token, gate sequence, EOS probability, test-marker boundary, and preservation of the function body before contamination.
5. **Feature 11785 targeted study.** Build a small ML-specific cohort involving premature `.fit`, missing `transform`, discarded training history, or incorrect train/evaluate sequencing.
6. **Reproducibility cleanup.** Add concise READMEs/run manifests to the new run directories, fix any metadata serialization issues, run syntax checks, and commit the new tools, scripts, reports, and this status document as a coherent reproducibility update.

## Main artifact map

- Feature interpretation: `reports/dstk100_feature_interpretability_v1/`
- Temporal screening: `reports/dstk100_temporal_feature_screening/`
- Failure taxonomy: `reports/dstk100_transition_failure_analysis_v1/`
- Matched-control semantics: `reports/dstk100_matched_control_features_v1/`
- Main 6404 experiment: `runs/dstk100_f6404_test_contamination_general_v1/`
- Orthogonal sham: `runs/dstk100_f6404_sham_orthogonal_v1/`
- Matched features at `-2`: `runs/dstk100_matched_feature_controls_v1/`
- Extended `-3/-4` controls: `runs/dstk100_extended_controls_neg3_neg4_v1/`
- Dense 6404 curve generations: `runs/dstk100_f6404_dense_negative_curve_v1/`
- Dense curve report: `reports/dstk100_f6404_dense_curve_v1/`

## Compute environment at status time

- Host: `FormulAI-1`
- CPU: 2 × AMD EPYC 9224, 48 physical cores / 96 threads
- RAM: 503 GiB
- GPUs: 2 × NVIDIA L40S, approximately 46 GiB each
- `/home`: 1.8 TiB total, approximately 549 GiB free at last check
- Both GPUs were idle after completion of the reported experiments.\n