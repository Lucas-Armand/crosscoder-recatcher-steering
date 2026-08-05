# Paired differential PR-AUC feature screening

Permutations: **200**; seed: **42**.

The score is the task-level difference between the variant-side and base-side positive additive encoder-contribution percentiles over exact evaluated tokens (P50/P60/P70/P80/P90/P95/P99). Regressions are tested only among tasks passed by the base model (variant failure versus preserved success). Improvements are tested only among tasks failed by the base model (variant success versus persistent failure).

The four jointly corrected searches are: variant increase associated with regression, variant decrease associated with regression, variant increase associated with improvement, and variant decrease associated with improvement. `p_maxT` searches all valid features and all four categories, features, and percentiles in every label permutation.

These are model-side contributions to a shared joint latent, not independently encoded model-specific latent activations.

[Implementation notes](IMPLEMENTATION_NOTES.md) · [Candidate recommendations](CANDIDATE_RECOMMENDATIONS.md) · [Candidate task examples](candidate_task_examples.csv)

## Cases

### `deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions`

paired=85; discordant=25; base-pass/variant-fail=2; base-fail/variant-pass=23; skipped=79.

Top candidates: 10678/p90 (variant_decrease_associated_with_regression, E/V=6.84, p=1.0000); 10725/p90 (variant_decrease_associated_with_regression, E/V=6.84, p=1.0000); 12018/p90 (variant_decrease_associated_with_regression, E/V=6.84, p=1.0000); 15071/p90 (variant_decrease_associated_with_regression, E/V=6.84, p=1.0000); 5619/p99 (variant_increase_associated_with_regression, E/V=6.76, p=1.0000)

[Figure](deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions`

paired=802; discordant=203; base-pass/variant-fail=57; base-fail/variant-pass=146; skipped=338.

Top candidates: 7608/p95 (variant_increase_associated_with_regression, E/V=6.05, p=0.0348); 3446/p99 (variant_increase_associated_with_regression, E/V=5.16, p=0.0995); 8575/p99 (variant_increase_associated_with_regression, E/V=5.39, p=0.2139); 1716/p99 (variant_increase_associated_with_regression, E/V=5.23, p=0.2836); 1716/p95 (variant_increase_associated_with_regression, E/V=4.85, p=0.4229)

[Figure](deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions`

paired=82; discordant=33; base-pass/variant-fail=1; base-fail/variant-pass=32; skipped=82.

Top candidates: 303/p50 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 10304/p60 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 618/p70 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 9077/p70 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 10304/p70 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000)

[Figure](deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions`

paired=686; discordant=220; base-pass/variant-fail=47; base-fail/variant-pass=173; skipped=454.

Top candidates: 10727/p99 (variant_decrease_associated_with_regression, E/V=6.68, p=0.1741); 7510/p90 (variant_increase_associated_with_regression, E/V=6.53, p=0.2289); 15037/p50 (variant_decrease_associated_with_regression, E/V=6.34, p=0.3582); 15037/p80 (variant_decrease_associated_with_regression, E/V=5.98, p=0.3582); 11104/p70 (variant_decrease_associated_with_regression, E/V=5.93, p=0.4030)

[Figure](deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions`

paired=153; discordant=35; base-pass/variant-fail=17; base-fail/variant-pass=18; skipped=11.

Top candidates: 3719/p80 (variant_increase_associated_with_regression, E/V=6.53, p=0.1045); 8946/p50 (variant_increase_associated_with_regression, E/V=5.49, p=0.2587); 7993/p99 (variant_decrease_associated_with_regression, E/V=5.24, p=0.2886); 15596/p60 (variant_decrease_associated_with_regression, E/V=6.36, p=0.3085); 4187/p99 (variant_increase_associated_with_regression, E/V=6.02, p=0.3134)

[Figure](codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions`

paired=990; discordant=202; base-pass/variant-fail=92; base-fail/variant-pass=110; skipped=150.

Top candidates: 6322/p50 (variant_increase_associated_with_regression, E/V=4.98, p=0.7612); 373/p70 (variant_increase_associated_with_regression, E/V=5.16, p=0.8010); 3175/p50 (variant_increase_associated_with_regression, E/V=4.65, p=0.8358); 6322/p60 (variant_increase_associated_with_regression, E/V=5.10, p=0.8408); 3175/p60 (variant_increase_associated_with_regression, E/V=4.27, p=0.8955)

[Figure](codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions`

paired=155; discordant=39; base-pass/variant-fail=38; base-fail/variant-pass=1; skipped=9.

Top candidates: 2531/p99 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000); 8191/p95 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000); 10056/p95 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000); 9859/p99 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000); 13005/p99 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000)

[Figure](codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions`

paired=1008; discordant=249; base-pass/variant-fail=246; base-fail/variant-pass=3; skipped=132.

Top candidates: 4815/p80 (variant_decrease_associated_with_regression, E/V=4.10, p=0.0050); 8994/p99 (variant_decrease_associated_with_regression, E/V=3.70, p=0.0050); 13439/p80 (variant_decrease_associated_with_regression, E/V=3.57, p=0.0050); 14336/p90 (variant_decrease_associated_with_regression, E/V=3.90, p=0.0100); 4567/p60 (variant_decrease_associated_with_regression, E/V=3.82, p=0.0100)

[Figure](codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

## Skipped cases


## Limitations

Stored paper-v1 activations come from different model-generated texts and are paired by the historical last-N rule. Model-side contributions are therefore exploratory until the candidate is validated by forwarding the same text through both models.

Feature selection uses evaluator outcomes from these benchmarks. Causal confirmation should use frozen candidates and held-out tasks or cross-benchmark replication.
