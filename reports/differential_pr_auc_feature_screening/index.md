# Paired differential PR-AUC feature screening

Permutations: **200**; seed: **42**.

The score is the task-level difference between the variant-side and base-side maximum positive additive encoder contributions. Regressions are tested only among tasks passed by the base model (variant failure versus preserved success). Improvements are tested only among tasks failed by the base model (variant success versus persistent failure).

The four jointly corrected searches are: variant increase associated with regression, variant decrease associated with regression, variant increase associated with improvement, and variant decrease associated with improvement. `p_maxT` searches all valid features and all four categories in every label permutation.

These are model-side contributions to a shared joint latent, not independently encoded model-specific latent activations.

[Implementation notes](IMPLEMENTATION_NOTES.md) · [Candidate recommendations](CANDIDATE_RECOMMENDATIONS.md) · [Candidate task examples](candidate_task_examples.csv)

## Cases

### `deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions`

paired=85; discordant=25; base-pass/variant-fail=2; base-fail/variant-pass=23; skipped=79.

Top candidates: 5619 (variant_increase_associated_with_regression, E/V=6.72, p=1.0000); 4216 (variant_increase_associated_with_regression, E/V=6.38, p=1.0000); 13909 (variant_increase_associated_with_regression, E/V=6.37, p=1.0000); 12072 (variant_decrease_associated_with_regression, E/V=6.21, p=1.0000); 12679 (variant_decrease_associated_with_regression, E/V=6.00, p=1.0000)

[Figure](deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions`

paired=802; discordant=203; base-pass/variant-fail=57; base-fail/variant-pass=146; skipped=338.

Top candidates: 2562 (variant_increase_associated_with_regression, E/V=5.79, p=0.0448); 3446 (variant_increase_associated_with_regression, E/V=5.28, p=0.0547); 16289 (variant_increase_associated_with_regression, E/V=5.49, p=0.1244); 302 (variant_increase_associated_with_regression, E/V=5.57, p=0.1294); 1403 (variant_increase_associated_with_regression, E/V=4.88, p=0.1493)

[Figure](deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions`

paired=82; discordant=33; base-pass/variant-fail=1; base-fail/variant-pass=32; skipped=82.

Top candidates: 1312 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 1430 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 2703 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 4849 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000); 7051 (variant_decrease_associated_with_regression, E/V=5.25, p=1.0000)

[Figure](deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_merged_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions`

paired=686; discordant=220; base-pass/variant-fail=47; base-fail/variant-pass=173; skipped=454.

Top candidates: 10786 (variant_increase_associated_with_regression, E/V=5.06, p=0.1940); 6865 (variant_increase_associated_with_regression, E/V=5.99, p=0.4179); 15943 (variant_increase_associated_with_regression, E/V=5.12, p=0.5174); 10589 (variant_decrease_associated_with_regression, E/V=5.61, p=0.5373); 8844 (variant_decrease_associated_with_regression, E/V=4.93, p=0.5423)

[Figure](deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](deepseek_base_merged_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions`

paired=153; discordant=35; base-pass/variant-fail=17; base-fail/variant-pass=18; skipped=11.

Top candidates: 8847 (variant_increase_associated_with_regression, E/V=6.08, p=0.1592); 7993 (variant_decrease_associated_with_regression, E/V=5.14, p=0.2388); 2674 (variant_decrease_associated_with_regression, E/V=5.06, p=0.4129); 4187 (variant_increase_associated_with_regression, E/V=5.12, p=0.5423); 4843 (variant_decrease_associated_with_regression, E/V=5.17, p=0.6517)

[Figure](codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_finetuned_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions`

paired=990; discordant=202; base-pass/variant-fail=92; base-fail/variant-pass=110; skipped=150.

Top candidates: 12529 (variant_decrease_associated_with_regression, E/V=5.31, p=0.1542); 11225 (variant_decrease_associated_with_regression, E/V=4.99, p=0.3980); 12694 (variant_decrease_associated_with_regression, E/V=6.01, p=0.4328); 12582 (variant_decrease_associated_with_regression, E/V=4.68, p=0.5224); 13990 (variant_decrease_associated_with_regression, E/V=4.68, p=0.5522)

[Figure](codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_finetuned_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions`

paired=155; discordant=39; base-pass/variant-fail=38; base-fail/variant-pass=1; skipped=9.

Top candidates: 2531 (variant_increase_associated_with_improvement, E/V=7.00, p=1.0000); 4437 (variant_decrease_associated_with_improvement, E/V=6.76, p=1.0000); 13010 (variant_decrease_associated_with_improvement, E/V=6.75, p=1.0000); 4149 (variant_decrease_associated_with_improvement, E/V=6.74, p=1.0000); 9859 (variant_increase_associated_with_improvement, E/V=6.64, p=1.0000)

[Figure](codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_merged_layer16__humanevalplus__layer16__paired_transitions/feature_statistics.csv)

### `codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions`

paired=1008; discordant=249; base-pass/variant-fail=246; base-fail/variant-pass=3; skipped=132.

Top candidates: 8994 (variant_decrease_associated_with_regression, E/V=3.31, p=0.0348); 11586 (variant_decrease_associated_with_regression, E/V=3.31, p=0.0498); 4789 (variant_decrease_associated_with_regression, E/V=3.48, p=0.0597); 11600 (variant_decrease_associated_with_regression, E/V=3.16, p=0.0945); 9150 (variant_decrease_associated_with_regression, E/V=3.36, p=0.1343)

[Figure](codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions/ranked_differential_pr_auc_envelope.png) · [Feature table](codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions/feature_statistics.csv)

## Skipped cases


## Limitations

Stored paper-v1 activations come from different model-generated texts and are paired by the historical last-N rule. Model-side contributions are therefore exploratory until the candidate is validated by forwarding the same text through both models.

Feature selection uses evaluator outcomes from these benchmarks. Causal confirmation should use frozen candidates and held-out tasks or cross-benchmark replication.
