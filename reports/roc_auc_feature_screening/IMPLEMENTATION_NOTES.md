# ROC-AUC feature screening implementation notes

## Repository findings

- `run_recatcher_benchmarks.py` generates one completion per task in paper-v1,
  builds `candidate_code` by stripping Markdown and truncating at explicit test,
  explanation, print, assertion, or repeated-function markers, and then performs a
  second forward pass to capture activations.
- `tools/reprocess_outputs_minimal.py` does not select a shorter function body. It
  applies deterministic visible-BPE-marker, whole-fence, and three-space-indent
  repairs. Comments are retained whenever they remain in the evaluated candidate.
- Evaluator labels are joined to raw and repaired rows by task in
  `tools/audit_evaluation_pipeline.py`. The audit now emits the same authoritative
  labels as `paper_v1_evaluation_labels.csv`, with failure encoded as 1.
- Activation filenames are indexed and checked for duplicates by
  `tools/crosscoder_common.py`. The screening implementation reuses this index,
  layer loader, checkpoint loader, and CrossCoder encoder path.
- Analysis cases are discovered from `manifests/paper_v1.json`: every declared
  CrossCoder, benchmark, and model side becomes a candidate case.

## Exact-alignment finding for existing paper-v1 data

Exact alignment is **not possible** for the existing canonical paper-v1
activations. The legacy NPZ files contain token IDs and layer rows but no token
character offsets or capture-time evaluated-token mask. Activation capture also
tokenized `prompt.rstrip() + "\n" + completion`, while calculating its prompt
boundary by tokenizing the unmodified prompt separately. Retokenizing the repaired
code cannot prove that its token positions match the stored forward pass. This is
especially material for fenced/truncated generations and CodeLlama rows changed by
postprocessing.

Consequently, the strict runner does not fabricate an approximate prefix. It skips
each legacy case with a precise `missing evaluated_token_mask` or related alignment
reason and records it in `index.md` and `skipped_cases.json`.

## Forward-compatible alignment contract

New activation payloads now store row-aligned:

- `input_ids` (only the rows whose hidden states are stored);
- `token_char_spans` from the exact activation forward-pass tokenization;
- `evaluated_token_mask`, true exactly when the generated token's character span
  overlaps generated text retained in `candidate_code`;
- `evaluated_generated_char_spans`, the retained generated-character provenance.

Special/prompt/padding tokens have no selected span. A boundary token is selected
when any part overlaps retained text. EOS after the prefix is excluded. No comment
heuristic is used. `tools/build_canonical_crosscoder_activations.py` preserves and
validates these optional alignment arrays.

The capture uses matching spans between the exact forward-pass string and the exact
candidate string; it does not retokenize cleaned code. If a future postprocessor
introduces a new content-deleting transformation after capture, that transformation
must update the mask from source-span provenance before screening.

## Statistical implementation

`tools/run_roc_auc_feature_screening.py` incrementally loads one paired activation
file at a time, selects the target model side's `evaluated_tokens`, applies the
existing ReLU CrossCoder encoder, and retains only the per-feature maximum per
solution. It computes tie-aware AUC from average ranks, marks constant features as
degenerate, reports activation support and class summaries, and uses reproducible
label permutations for null mean/SD, ranked envelopes, and max-statistic adjusted
`p_maxT`. Ranked null AUCs are disk-backed rather than retained as a large in-memory
array.

CrossCoder latent values are produced after ReLU and should therefore be
nonnegative. Every case still reports its observed minimum and fraction below
`-1e-8`; a nonzero fraction is a warning rather than silently being discarded.

Smoke mode uses 200 permutations and at most 24 solutions per case. Full mode uses
5,000 permutations by default. Seeds are case-local and reproducible.

## Assumptions and limitations

- Paper-v1 has exactly one generation per model/task (`generation_idx=0`), as
  declared by the manifest and confirmed by the prior row-level audit.
- The CrossCoder was trained by same-position pairing after taking the final shared
  token count of the two model-side arrays. Screening preserves that pairing rule,
  then applies the target side's exact mask to those paired rows.
- A ranked-envelope excursion is exploratory. `p_maxT`, effect magnitude, and
  activation support are the intended screening evidence.
- Missing checkpoints, labels, paired activations, masks, task IDs, empty arrays,
  one-class labels, and duplicates are case-stopping errors, not imputations.

## Modified files

- `run_recatcher_benchmarks.py`
- `tools/build_canonical_crosscoder_activations.py`
- `tools/crosscoder_common.py`
- `tools/audit_evaluation_pipeline.py`
- `tools/run_roc_auc_feature_screening.py` (new)
- `scripts/run_roc_auc_feature_screening.sh` (new)
- `tests/test_roc_auc_feature_screening.py` (new)
- `requirements-analysis.txt`
- `.gitignore`
- `README.md`
- `reports/roc_auc_feature_screening/IMPLEMENTATION_NOTES.md` (new)
