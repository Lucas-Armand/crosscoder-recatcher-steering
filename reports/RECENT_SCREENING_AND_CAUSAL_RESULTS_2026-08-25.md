# Recent screening and causal steering audit — 2026-08-25

## Scope

This report consolidates the most recent extension of the CrossCoder model-diffing study:

1. eight complementary screening cells;
2. an alpha-magnitude-3 causal sweep over multiple screened features;
3. semantic interpretation of DSTK100 feature 3048 and CodeLlama feature 13147;
4. bidirectional dose curves at magnitudes 0.5, 1, 2, 3, 4, 5, and 6;
5. three norm-matched orthogonal sham directions and three alternative CrossCoder features per target;
6. a rule-based audit of exact extraction-v4 evaluated-code changes across all 116 arms.

All claims below distinguish association, semantic interpretation, trajectory change, official pass/fail transitions, and feature specificity.

## Eight-cell screening

The recent screen crossed:

- regression versus improvement;
- association against a behavior-conditioned control population versus paired base/specialized-text difference;
- global evaluated-code aggregation versus a local window around the first normalized divergence.

Each cell retained the earlier four summaries (`max`, `early_max`, `mean`, and `active_fraction`), 200 label permutations, E/V, and the support rule `max(3, 10% of positives)`.

Known causal candidate DSTK100 feature 10168 reappeared at rank 2 in the global improvement-association screen (`active_fraction`, E/V -7.67, support 165). CodeLlama feature 27 did not enter a Top 10; its best relevant result was rank 45 in the local paired regression screen. CodeLlama feature 13147 ranked first in the global regression-association screen (`mean`, E/V 5.24, support 95).

CodeLlama improvement cells contain only four positives and are unsuitable for strong ranking claims.

## Alpha-3 multi-feature causal sweep

### DSTK100

- 30 selected features plus baseline were evaluated on 80 selected BigCodeBench contamination improvements.
- Baseline reproduced 15/80 official passes in that run.
- 25/30 features had positive net change.
- Feature 3048 was the largest raw result: 19/80, or +4 net.
- Task BigCodeBench/1030 was corrected by 29/30 features.

### CodeLlama

- 37 selected features plus baseline were evaluated on 50 `wrong_logic_or_other_runtime` regressions.
- Baseline was 0/50.
- 11/37 features produced one official pass.
- Ten of the eleven successful arms corrected BigCodeBench/119.
- Feature 13147 was the only arm that corrected BigCodeBench/490.

These repeated-task patterns motivated explicit random-direction and alternative-feature controls. A pass transition establishes that an intervention changed the trajectory, but not that the nominated latent is uniquely responsible.

## Semantic interpretation

### DSTK100 feature 3048

Top natural activation tokens include `_`, ` test`, `Func`, `from`, `Task`, `import`, ` def`, `func`, and `def`. High-activation contexts frequently occur around helper functions, test blocks, imports, and transitions into additional code units.

The feature is broad: it activates in 1,427/2,608 captured texts. Its base/fine-tuned decoder cosine is 0.961, consistent with a largely shared program-structure direction rather than a fine-tuned-exclusive feature.

### CodeLlama feature 13147

Top natural activation tokens include indentation, newline, `#`, `...`, `TODO`, `return`, `pass`, `code`, and `here`. High-activation contexts repeatedly contain `# Hint: Use ...` sequences and placeholder or incomplete implementations.

It activates in 718/2,608 texts. Its base/merged decoder cosine is 0.275 and encoder-half cosine is 0.075, indicating a strongly model-differential representation.

## Focused bidirectional sweeps and controls

The focused sweeps used input seed 50000. This differs from the original alpha-3 discovery convention `1000 + task_idx`; for BigCodeBench/490 the original generation seed was 1490. The focused run is therefore a robustness run, not an exact replication.

### Feature 3048

Suppressing 3048 in the DeepSeek base model produced `[1, 1, 1, 3, 2, 2, 2]` passes across magnitudes `[0.5, 1, 2, 3, 4, 5, 6]`, from a 0/80 baseline.

The three shams produced mean pass counts `[0.0, 1.33, 2.0, 2.67, 4.0, 5.33, 6.0]`. The three alternative features produced means `[1.33, 1.0, 2.33, 4.33, 5.67, 6.67, 7.67]`. Feature 3048 therefore did not outperform either control family.

Adding 3048 to the fine-tuned model reduced its 60/80 baseline to `[59, 59, 59, 57, 57, 55, 55]`. This reverse dose trend is interesting, but reverse-direction sham and latent controls were not run.

### Feature 13147

Suppressing 13147 in the CodeLlama merged model produced `[0, 0, 0, 0, 1, 1, 1]` passes from a 0/50 baseline. BigCodeBench/490 was repaired at magnitudes 4, 5, and 6 by restoring XML parsing, JSON-file writing, and `return result`.

All three alternative CrossCoder features produced zero passes at every dose. The shams produced mean counts `[0, 0, 0, 0.33, 0.67, 0.67, 1.0]`; one sham also repaired BigCodeBench/490 at magnitude 6. The semantic match is coherent, but random-direction sensitivity prevents a strong feature-specific claim.

Adding 13147 to the CodeLlama base reduced its 50/50 baseline to `[50, 50, 49, 49, 49, 49, 47]`. Reverse controls remain absent.

## What changed beyond pass/fail

The exact extraction-v4 evaluated code was compared to the matching alpha-zero output. A mutually exclusive rule-based taxonomy used the first matching category: test marker, imports, returns, function structure, comments, or other logic/text.

For 3048 suppression, changed outputs increased from 13/80 at magnitude 0.5 to 37/80 at magnitude 6. At magnitude 3, 27 outputs changed: eight test-marker changes, four import changes, eight other logic/text changes, three function-structure changes, and four comment changes. Shams and latent controls showed similar or larger dose-dependent change counts.

For 13147 suppression, changed outputs increased from 8/50 to 35/50. Return-line changes increased from three to eighteen, matching the natural feature interpretation. However, high-dose shams also produced 14–18 return-line changes. Alternative latent controls changed fewer outputs and produced no official passes.

The reverse 3048 sweep changed 6–40/80 outputs and increasingly altered comments, test markers, return statements, and other logic. The reverse 13147 sweep changed 7–25/50 outputs and increasingly altered function structure, imports, tests, returns, and general logic.

## Revised claims

Supported:

- the CrossCoder screens identify reproducible behavioral contrasts;
- selected decoder directions causally alter autoregressive trajectories and sometimes official outcomes;
- semantic inspection can predict the *type* of code transformation induced by steering.

Exploratory:

- feature 13147 has a coherent meaning–failure-mode relationship and a stable repair of BigCodeBench/490 across three adjacent doses in seed 50000;
- reverse steering for 3048 and 13147 produces increasingly harmful changes in the better model.

Not supported:

- feature 3048 does not show feature-specific causal benefit relative to shams or alternative latents;
- a single fail-to-pass transition is not sufficient evidence of semantic specificity;
- the original 13147 alpha-3 result and the seed-50000 curve are not exact replications.

Feature 6404 remains the strongest controlled causal result in the project. The next confirmatory experiment should pair baseline, target, three shams, and three latent controls under the canonical seed convention and repeat several common seeds per alpha.
