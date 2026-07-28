# Bidirectional PR-AUC feature screening

Permutation count: **200**; seed: **42**.

Failure and success are analyzed as separate positive classes. Raw PR-AUC is interpreted relative to each class prevalence. The normalized effect is `(PR-AUC - prevalence) / (1 - prevalence)`. `E/V` is `(observed normalized effect - permutation mean) / permutation SD`; it is a permutation signal-to-noise score, not a Gaussian z-test.

Top-five support filter: activation count ≥ 5 and activation proportion ≥ 0.010.

## Analyzed cases

### `deepseek_base_finetuned_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens`

n=138; failure prevalence=0.601; degenerate features=3813; skipped solutions=26; reconstructed legacy masks=138; non-prefix masks=2.

Top five by E/V: 6873 (failure, PR=0.8463, lift=0.6144, E/V=6.35, p_maxT=0.0050); 3142 (success, PR=0.6126, lift=0.3559, E/V=6.17, p_maxT=0.7413); 14374 (failure, PR=0.7215, lift=0.3012, E/V=5.67, p_maxT=1.0000); 13147 (failure, PR=0.8197, lift=0.5477, E/V=5.43, p_maxT=0.0149); 15907 (failure, PR=0.8276, lift=0.5675, E/V=5.34, p_maxT=0.0050)

[Figure](deepseek_base_finetuned_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_finetuned_layer16__b_deepseek_finetuned__humanevalplus__layer16__evaluated_tokens`

n=111; failure prevalence=0.369; degenerate features=3733; skipped solutions=53; reconstructed legacy masks=111; non-prefix masks=1.

Top five by E/V: 11052 (failure, PR=0.6481, lift=0.4420, E/V=5.94, p_maxT=0.7015); 2629 (failure, PR=0.6327, lift=0.4175, E/V=5.44, p_maxT=0.8607); 5696 (failure, PR=0.6391, lift=0.4277, E/V=5.36, p_maxT=0.7910); 5089 (failure, PR=0.6169, lift=0.3925, E/V=5.22, p_maxT=0.9900); 8291 (failure, PR=0.6092, lift=0.3802, E/V=4.99, p_maxT=1.0000)

[Figure](deepseek_base_finetuned_layer16__b_deepseek_finetuned__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__b_deepseek_finetuned__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_finetuned_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens`

n=1108; failure prevalence=0.770; degenerate features=2319; skipped solutions=32; reconstructed legacy masks=1108; non-prefix masks=15.

Top five by E/V: 15562 (failure, PR=0.9162, lift=0.6358, E/V=12.79, p_maxT=0.0050); 7074 (failure, PR=0.9168, lift=0.6385, E/V=11.77, p_maxT=0.0050); 2925 (failure, PR=0.9168, lift=0.6383, E/V=11.10, p_maxT=0.0050); 7434 (failure, PR=0.8969, lift=0.5520, E/V=10.97, p_maxT=0.0050); 9437 (failure, PR=0.8921, lift=0.5312, E/V=10.95, p_maxT=0.0050)

[Figure](deepseek_base_finetuned_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_finetuned_layer16__b_deepseek_finetuned__bigcodebench__layer16__evaluated_tokens`

n=833; failure prevalence=0.678; degenerate features=2682; skipped solutions=307; reconstructed legacy masks=833; non-prefix masks=8.

Top five by E/V: 3787 (failure, PR=0.7798, lift=0.3156, E/V=6.06, p_maxT=0.0050); 12970 (failure, PR=0.7601, lift=0.2543, E/V=5.41, p_maxT=0.0050); 5476 (failure, PR=0.7604, lift=0.2553, E/V=5.40, p_maxT=0.0050); 13915 (failure, PR=0.7624, lift=0.2616, E/V=5.40, p_maxT=0.0050); 7593 (failure, PR=0.7561, lift=0.2419, E/V=5.31, p_maxT=0.0199)

[Figure](deepseek_base_finetuned_layer16__b_deepseek_finetuned__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_finetuned_layer16__b_deepseek_finetuned__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_merged_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens`

n=136; failure prevalence=0.603; degenerate features=4564; skipped solutions=28; reconstructed legacy masks=136; non-prefix masks=2.

Top five by E/V: 6873 (failure, PR=0.8396, lift=0.5960, E/V=5.70, p_maxT=0.0050); 15612 (failure, PR=0.8321, lift=0.5773, E/V=5.60, p_maxT=0.0100); 11780 (failure, PR=0.8114, lift=0.5251, E/V=4.93, p_maxT=0.0149); 339 (success, PR=0.6127, lift=0.3577, E/V=4.90, p_maxT=0.7413); 16083 (failure, PR=0.7246, lift=0.3063, E/V=4.80, p_maxT=1.0000)

[Figure](deepseek_base_merged_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_merged_layer16__a_deepseek_base__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_merged_layer16__b_deepseek_merged__humanevalplus__layer16__evaluated_tokens`

n=110; failure prevalence=0.236; degenerate features=4402; skipped solutions=54; reconstructed legacy masks=110; non-prefix masks=1.

Top five by E/V: 4789 (failure, PR=0.5834, lift=0.4544, E/V=7.53, p_maxT=0.9104); 7525 (failure, PR=0.5045, lift=0.3512, E/V=5.57, p_maxT=1.0000); 8196 (failure, PR=0.5409, lift=0.3988, E/V=5.33, p_maxT=0.9950); 10550 (failure, PR=0.5127, lift=0.3619, E/V=5.22, p_maxT=1.0000); 9179 (failure, PR=0.4777, lift=0.3160, E/V=4.96, p_maxT=1.0000)

[Figure](deepseek_base_merged_layer16__b_deepseek_merged__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_merged_layer16__b_deepseek_merged__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_merged_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens`

n=1115; failure prevalence=0.765; degenerate features=2659; skipped solutions=25; reconstructed legacy masks=1115; non-prefix masks=14.

Top five by E/V: 5535 (failure, PR=0.9137, lift=0.6327, E/V=12.55, p_maxT=0.0050); 5728 (failure, PR=0.9161, lift=0.6428, E/V=12.20, p_maxT=0.0050); 13605 (failure, PR=0.9122, lift=0.6265, E/V=11.85, p_maxT=0.0050); 3341 (failure, PR=0.9118, lift=0.6245, E/V=11.69, p_maxT=0.0050); 10925 (failure, PR=0.9036, lift=0.5899, E/V=11.56, p_maxT=0.0050)

[Figure](deepseek_base_merged_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_merged_layer16__a_deepseek_base__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `deepseek_base_merged_layer16__b_deepseek_merged__bigcodebench__layer16__evaluated_tokens`

n=710; failure prevalence=0.614; degenerate features=3468; skipped solutions=430; reconstructed legacy masks=710; non-prefix masks=20.

Top five by E/V: 8609 (failure, PR=0.7023, lift=0.2287, E/V=5.57, p_maxT=0.0348); 5318 (failure, PR=0.7105, lift=0.2499, E/V=5.44, p_maxT=0.0149); 9783 (failure, PR=0.7120, lift=0.2538, E/V=5.21, p_maxT=0.0149); 16048 (failure, PR=0.7154, lift=0.2625, E/V=5.00, p_maxT=0.0100); 6908 (failure, PR=0.7084, lift=0.2445, E/V=4.94, p_maxT=0.0249)

[Figure](deepseek_base_merged_layer16__b_deepseek_merged__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](deepseek_base_merged_layer16__b_deepseek_merged__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_finetuned_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens`

n=164; failure prevalence=0.665; degenerate features=5764; skipped solutions=0; reconstructed legacy masks=164; non-prefix masks=2.

Top five by E/V: 9763 (success, PR=0.5727, lift=0.3570, E/V=6.28, p_maxT=0.7264); 12982 (success, PR=0.5396, lift=0.3073, E/V=5.61, p_maxT=0.9751); 15596 (failure, PR=0.8570, lift=0.5737, E/V=5.45, p_maxT=0.0050); 6596 (failure, PR=0.8844, lift=0.6553, E/V=5.38, p_maxT=0.0050); 6579 (failure, PR=0.8455, lift=0.5394, E/V=5.35, p_maxT=0.0100)

[Figure](codellama_base_finetuned_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_finetuned_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_finetuned_layer16__b_codellama_finetuned__humanevalplus__layer16__evaluated_tokens`

n=153; failure prevalence=0.647; degenerate features=5692; skipped solutions=11; reconstructed legacy masks=153; non-prefix masks=0.

Top five by E/V: 15000 (failure, PR=0.8430, lift=0.5550, E/V=5.52, p_maxT=0.0050); 715 (failure, PR=0.8271, lift=0.5102, E/V=4.64, p_maxT=0.0398); 6690 (failure, PR=0.8085, lift=0.4574, E/V=4.56, p_maxT=0.2040); 4955 (failure, PR=0.8137, lift=0.4721, E/V=4.52, p_maxT=0.1493); 4698 (failure, PR=0.8066, lift=0.4519, E/V=4.46, p_maxT=0.2139)

[Figure](codellama_base_finetuned_layer16__b_codellama_finetuned__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_finetuned_layer16__b_codellama_finetuned__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_finetuned_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens`

n=1140; failure prevalence=0.725; degenerate features=3075; skipped solutions=0; reconstructed legacy masks=1140; non-prefix masks=48.

Top five by E/V: 4681 (failure, PR=0.8383, lift=0.4129, E/V=9.72, p_maxT=0.0050); 13508 (failure, PR=0.8336, lift=0.3957, E/V=9.25, p_maxT=0.0050); 12067 (failure, PR=0.8389, lift=0.4152, E/V=9.12, p_maxT=0.0050); 5265 (failure, PR=0.8389, lift=0.4151, E/V=9.09, p_maxT=0.0050); 14637 (failure, PR=0.8353, lift=0.4021, E/V=9.08, p_maxT=0.0050)

[Figure](codellama_base_finetuned_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_finetuned_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_finetuned_layer16__b_codellama_finetuned__bigcodebench__layer16__evaluated_tokens`

n=990; failure prevalence=0.722; degenerate features=3430; skipped solutions=150; reconstructed legacy masks=990; non-prefix masks=0.

Top five by E/V: 10966 (failure, PR=0.8155, lift=0.3357, E/V=7.45, p_maxT=0.0050); 6216 (failure, PR=0.8178, lift=0.3443, E/V=7.21, p_maxT=0.0050); 4619 (failure, PR=0.8196, lift=0.3506, E/V=7.11, p_maxT=0.0050); 13722 (failure, PR=0.8207, lift=0.3546, E/V=6.96, p_maxT=0.0050); 13860 (failure, PR=0.8133, lift=0.3280, E/V=6.87, p_maxT=0.0050)

[Figure](codellama_base_finetuned_layer16__b_codellama_finetuned__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_finetuned_layer16__b_codellama_finetuned__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_merged_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens`

n=161; failure prevalence=0.665; degenerate features=5662; skipped solutions=3; reconstructed legacy masks=161; non-prefix masks=2.

Top five by E/V: 14672 (success, PR=0.6619, lift=0.4912, E/V=8.94, p_maxT=0.0547); 11929 (success, PR=0.6296, lift=0.4426, E/V=8.31, p_maxT=0.1891); 8480 (success, PR=0.5907, lift=0.3842, E/V=6.29, p_maxT=0.5721); 10753 (success, PR=0.5814, lift=0.3701, E/V=6.26, p_maxT=0.6965); 13577 (success, PR=0.5649, lift=0.3454, E/V=5.89, p_maxT=0.8507)

[Figure](codellama_base_merged_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_merged_layer16__a_codellama_base__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_merged_layer16__b_codellama_merged__humanevalplus__layer16__evaluated_tokens`

n=158; failure prevalence=0.892; degenerate features=5633; skipped solutions=6; reconstructed legacy masks=158; non-prefix masks=8.

Top five by E/V: 11929 (success, PR=0.4862, lift=0.4243, E/V=10.52, p_maxT=0.9652); 412 (success, PR=0.3209, lift=0.2390, E/V=6.29, p_maxT=1.0000); 7969 (success, PR=0.3765, lift=0.3013, E/V=6.27, p_maxT=1.0000); 14672 (success, PR=0.3497, lift=0.2713, E/V=6.17, p_maxT=1.0000); 14880 (success, PR=0.3212, lift=0.2393, E/V=5.67, p_maxT=1.0000)

[Figure](codellama_base_merged_layer16__b_codellama_merged__humanevalplus__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_merged_layer16__b_codellama_merged__humanevalplus__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_merged_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens`

n=1089; failure prevalence=0.729; degenerate features=4631; skipped solutions=51; reconstructed legacy masks=1089; non-prefix masks=43.

Top five by E/V: 7011 (failure, PR=0.8577, lift=0.4747, E/V=9.81, p_maxT=0.0050); 4953 (failure, PR=0.8451, lift=0.4280, E/V=8.70, p_maxT=0.0050); 3089 (failure, PR=0.8385, lift=0.4038, E/V=8.37, p_maxT=0.0050); 5694 (failure, PR=0.8401, lift=0.4096, E/V=8.26, p_maxT=0.0050); 15198 (failure, PR=0.8316, lift=0.3782, E/V=8.02, p_maxT=0.0050)

[Figure](codellama_base_merged_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_merged_layer16__a_codellama_base__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

### `codellama_base_merged_layer16__b_codellama_merged__bigcodebench__layer16__evaluated_tokens`

n=1059; failure prevalence=0.979; degenerate features=4133; skipped solutions=81; reconstructed legacy masks=1059; non-prefix masks=63.

Top five by E/V: 1287 (success, PR=0.1120, lift=0.0932, E/V=9.65, p_maxT=1.0000); 16105 (success, PR=0.1112, lift=0.0923, E/V=9.65, p_maxT=1.0000); 10921 (success, PR=0.1225, lift=0.1039, E/V=8.22, p_maxT=1.0000); 11476 (success, PR=0.0717, lift=0.0521, E/V=7.82, p_maxT=1.0000); 11764 (success, PR=0.0963, lift=0.0771, E/V=6.87, p_maxT=1.0000)

[Figure](codellama_base_merged_layer16__b_codellama_merged__bigcodebench__layer16__evaluated_tokens/ranked_pr_auc_permutation_envelope.png) · [Feature table](codellama_base_merged_layer16__b_codellama_merged__bigcodebench__layer16__evaluated_tokens/feature_statistics.csv)

## Skipped cases


## Warnings

Exact v4 extraction spans and stored-token-ID equality are required for reconstructed masks.

Raw failure and success PR-AUC values are not directly comparable because their prevalence baselines differ; compare normalized effect or E/V.

The ranked 95% envelopes are exploratory. `p_maxT` uses the maximum positive normalized effect across both directions and all valid features in each permutation.

With 200 permutations, the minimum attainable p_maxT is 1/201 ≈ 0.00498.
