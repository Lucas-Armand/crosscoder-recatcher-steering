# Validation Protocol

The paper release uses evidence gates. A stage is complete only when its gate
passes; the existence of a directory or checkpoint is not sufficient.

## Gate 1: generation

- Expected task count and unique task IDs for every model and benchmark.
- Exactly one generation per task for `paper_v1`.
- Expected model ID, seed formula, benchmark label, and model label.
- Generated token count no greater than 512.
- Layer 16 listed in the saved activation metadata.
- Activation path and token-count metadata present.

Historical rows do not embed temperature and top-p. The release validator checks
these parameters against both archived family-level experiment configs.

## Gate 2: post-processing lineage

- Raw, repaired, and evaluator rows have identical task sets.
- The original candidate in each repair row matches the exported raw candidate.
- Every modification uses an allow-listed deterministic rule.
- `changed`, lengths, compile flags, and suspicious-repair flags are internally
  consistent.
- No glued-token heuristic is allowed in the canonical metrics.
- Report raw compile rate and repaired compile rate separately.

Post-processing cannot generally prove semantic equivalence. Whitespace repair
that changes Python block structure can change behavior even when deterministic.
For that reason, repaired metrics must remain visibly distinct from raw metrics,
and a stratified manual review should be retained for publication.

## Gate 3: evaluator evidence

- HumanEval+ has one evaluation row per task and explicit correctness/error
  fields.
- BigCodeBench runs under version 0.1.5 with `--subset complete --no-gt`.
- Every evaluator job records exit code 0 and a final metric.
- Timeouts, dependency errors, harness errors, and missing results are not
  converted into ordinary model failures.

Generated code is untrusted. Re-evaluation must run in isolated, disposable
environments with network access disabled and strict CPU, memory, process, and
wall-clock limits.

## Gate 4: activation coverage

- Layer-16 activation exists for every declared task except a manifest-listed
  exception.
- Input IDs and layer arrays are non-empty and row aligned.
- Layer arrays are finite float32 with hidden size 4,096 in the canonical set.
- Object identity/checksum is recorded before final publication freeze.

The canonical conversion validated required keys, alignment, finite values,
float32 dtype, and hidden size before each upload. Its complete log is preserved
as release evidence. The 12 task-0 objects that predated the full conversion are
revalidated with `tools/validate_activation_payloads.py`.

## Gate 5: CrossCoder training

- Four expected run directories exist.
- `exitcode.txt` is zero and `final.pt` exists.
- Metrics reach exactly step 20,000 without non-finite numeric values.
- Stored configuration matches the shared release contract.
- Checkpoint model pair and layer match the manifest.
- Activation source is recorded.

## Recommended commands

```bash
python tools/validate_paper_release.py \
  --manifest manifests/paper_v1.json \
  --output-json reports/paper_v1_validation.json \
  --output-markdown reports/paper_v1_validation.md

python -m unittest discover -s tests -v
```

The bucket validator is read-only. A canonical release prefix should be created
only after all blocking gates pass and the remaining cautions are accepted and
documented.
