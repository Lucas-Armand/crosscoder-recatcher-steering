# DSTK100 presentation

English presentation of the CrossCoder model-diffing methodology and the preliminary feature-6404 causal steering result.

## Build

The committed PPTX and charts were generated with:

```bash
python3 presentation/build_crosscoder_deck.py
```

The script expects the canonical large screening table at `/tmp/dstk100_all_feature_statistics.csv` and compact experiment inputs under `/tmp/cc_deck_data/`. These raw artifacts remain in the versioned GCS publication rather than Git. The derived compact CSVs, charts, source code, and final deck are committed here.

## Output

- `generated/crosscoder_model_diffing_causal_steering_2026-08-10.pptx`
- `generated/charts/`
- `generated/data/`

## Scope

The deck reports a deliberately selected mechanistic cohort. It does not present the 19/80 result as an out-of-sample benchmark improvement.
