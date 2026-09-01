# Direct steering control validation

Date: 2026-09-01

This audit determines which existing controls can be compared with the current direct-only dose-response experiment. Reverse-model arms are excluded.

## Acceptance criteria

A control is accepted only when it has the same task cohort, target model side, per-task seed, temperature, top-p, maximum generation length, quantization, steering mode, token scope, and an alpha-zero baseline that reproduces the current direct baseline byte-for-byte. Direction norm and cosine similarity to the current target features are audited separately.

## DeepSeek

Direct baseline: DeepSeek base, 80 contamination-focused tasks, 0/80 official passes, 80/80 byte-exact reproduction.

### Accepted orthogonal shams

Source: `runs/dstk100_f3048_bidirectional_controls_v1/`

Three seeded Gaussian directions have complete direct arms at magnitudes 1--5 (15 arms, 80 tasks each). Their source alpha-zero baseline reproduces the current direct baseline byte-for-byte for 80/80 tasks. All generation settings and per-task seeds match.

Although these directions were originally constructed to be exactly orthogonal to feature 3048, they were not selected using the outcomes of the current five targets. Retrospective geometry against the current targets validates them as matched orthogonal controls:

- sham norm: 0.69256;
- current target norm range: 0.68975--0.70264;
- maximum absolute cosine with any current target: 0.02762.

Official pass counts:

| Magnitude | Target median (range) | Sham values | Sham median |
|---:|---:|---:|---:|
| 1 | 2 (1--3) | 3, 1, 0 | 1 |
| 2 | 4 (2--5) | 2, 2, 2 | 2 |
| 3 | 6 (5--7) | 3, 2, 3 | 3 |
| 4 | 6 (5--7) | 4, 5, 3 | 4 |
| 5 | 6 (4--8) | 5, 7, 4 | 5 |

These shams are valid controls. Targets outperform the sham median at every dose, most clearly at magnitudes 2--4. The separation narrows at magnitude 5, and one sham reaches 7/80, so the data support selection enrichment rather than universal feature specificity.

### Accepted random latent, incomplete curve

Feature 8628 was sampled uniformly after excluding the focused screening pool and without using causal outcomes. Its norm is 0.71714 and its maximum absolute cosine with a current target is 0.03316. Two complete direct arms exist:

| Magnitude | Official passes |
|---:|---:|
| 1 | 2/80 |
| 2 | 3/80 |

This is a valid but incomplete random-feature control. It cannot define a complete random-control dose curve.

## CodeLlama

Direct baseline: CodeLlama merged, 50 logic/runtime tasks, 0/50 official passes, 50/50 byte-exact reproduction.

### Accepted orthogonal shams with norm caveat

Source: `runs/codellama_bm_f13147_bidirectional_controls_v1/`

Three seeded Gaussian directions have complete direct arms at magnitudes 1--5 (15 arms, 50 tasks each). Their alpha-zero baseline reproduces the current direct baseline byte-for-byte for 50/50 tasks. All generation settings and seeds match.

The directions are effectively orthogonal to the current five targets (maximum absolute cosine 0.03549), but their norm is 0.83883 versus a current-target median of 0.72296 (target range 0.65577--0.79408). Thus equal alpha gives the shams an approximately 16% larger intervention than the median target. This is a conservative outcome control, but not an exactly norm-matched dose comparison.

| Magnitude | Target median (range) | Sham values | Sham median |
|---:|---:|---:|---:|
| 1 | 0 (0--0) | 0, 0, 0 | 0 |
| 2 | 0 (0--1) | 0, 0, 0 | 0 |
| 3 | 1 (1--1) | 0, 0, 1 | 0 |
| 4 | 1 (1--2) | 0, 1, 1 | 1 |
| 5 | 1 (1--2) | 0, 1, 1 | 1 |

Targets separate weakly at magnitude 3 but not at magnitudes 4--5. This does not support strong CodeLlama target specificity.

### Accepted random latent controls, incomplete and unbalanced

The focused controls selected features 15035, 6019, and 5412 uniformly after excluding the screening pool and without using causal outcomes. Their norms are 0.70266, 0.71601, and 0.70990; maximum absolute cosine with a current target is below 0.020 for each.

- feature 15035: complete at magnitudes 1--5;
- feature 6019: complete at magnitudes 1--5;
- feature 5412: complete at magnitudes 1, 2, and 4;
- total: 13 complete direct arms.

| Magnitude | Target median | Random median | Random range | Random arms |
|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 0--0 | 3 |
| 2 | 0 | 0 | 0--0 | 3 |
| 3 | 1 | 0 | 0--0 | 2 |
| 4 | 1 | 1 | 0--2 | 3 |
| 5 | 1 | 0.5 | 0--1 | 2 |

The random controls agree with the sham result: a small target advantage appears at magnitude 3, while higher-dose effects overlap substantially with controls.

## Rejected or excluded controls

- `runs/dstk100_bbasv_v1/`: rejected for the present comparison because it used `1000 + task_idx` rather than `1000 + 100 * task_idx`; its direct alpha-zero outputs match the canonical baseline in 0/80 cases.
- historical alternative features chosen using prior screening or causal results: not treated as random negative controls.
- controls from feature 6404 gated suppression: different intervention mode and hypothesis; not pooled with continuous traditional steering.
- the partial 12/50 CodeLlama sham arm in `focused_bbasv_v2_codellama`: incomplete and excluded.
- all reverse-model controls: excluded from the direct-only analysis.

## Conclusion

Direct sham controls can be used in the presentation for both model families. DeepSeek has particularly strong protocol- and geometry-matched shams, and its selected targets outperform the sham median across all five doses, with the clearest separation at magnitudes 2--4. CodeLlama shams and random controls overlap substantially with targets at high doses, reinforcing the weaker-specificity boundary condition.

The controls should be described as reused, independently generated historical controls that passed a retrospective protocol and geometry audit. They were not preregistered specifically for the final five-feature target sets.

