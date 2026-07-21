# Data and Artifact Provenance

## Canonical source dataset

`paper_v1` points to:

```text
gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/
  crosscoder_final_dataset_v1_postprocessed_minimal_v3/
```

Its `POSTPROCESS_MANIFEST.txt` identifies
`crosscoder_final_dataset_v1` as the source. The v3 prefix preserves source rows
under `raw_results/`, stores repair records under `results/` and
`results_repaired/`, provides evaluator inputs, and stores evaluator evidence.

## Canonical activations

Canonical float32 activations are stored under:

```text
crosscoder_activations_canonical_float32_v1/
  {benchmark}/{model}/*.npz
```

They were converted by `tools/build_canonical_crosscoder_activations.py`, which
checks required keys, alignment, finite values, hidden size 4,096, and float32
conversion. The release uses `layer_16`; layer 8 and 24 remain historical data.

## CrossCoder artifacts

DeepSeek layer-16 artifacts are selected from `crosscoder_training_v1`.
CodeLlama layer-16 artifacts are selected from the two later canonical float32
runs. The exact four prefixes and their shared contract are defined in
`manifests/paper_v1.json`.

The historical DeepSeek base-vs-fine-tuned training prefix is missing its large
`final.pt` object. Its local final checkpoint is preserved under
`releases/paper_v1/artifacts/crosscoders/` with the SHA-256 recorded in the
release manifest. No historical object is overwritten.

## Immutability policy

Existing experimental prefixes are historical records and must not be renamed,
overwritten, or deleted as part of repository cleanup. A publication release
should add a versioned manifest that records GCS object generations and
checksums. Large objects do not need to be copied when immutable identifiers
and access policy are sufficient.
