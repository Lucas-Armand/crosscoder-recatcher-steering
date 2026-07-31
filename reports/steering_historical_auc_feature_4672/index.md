# Historical-style ROC-AUC steering: DeepSeek feature 4672

## Design

This smoke replicates the old feature-962 protocol with the new layer-16 DeepSeek base-versus-merged CrossCoder. Feature 4672 was the strongest failure-associated feature in the existing base-side HumanEval+ ROC-AUC screen (ROC-AUC 0.7944; maxT-adjusted p=0.0002).

The fixed sample contains 10 historical failures and 10 historical pass controls with the largest feature scores. The natural scale is P99 of positive base-side encoder contribution over exact evaluated tokens: `7.072720`. Generation was greedy with 192 new tokens, and the layer-16 base decoder vector was subtracted from the last token at every decoding step.

## Results

| Nominal alpha | Effective alpha | Passed | Fail→pass | Pass→fail | Changed evaluated code | Mean ||delta||/||residual|| |
|---:|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.000 | 5/20 | 0 | 0 | 0/20 | 0.0000 |
| -0.10 | -0.707 | 4/20 | 0 | 1 | 3/20 | 0.0041 |
| -0.25 | -1.768 | 4/20 | 0 | 1 | 2/20 | 0.0102 |
| -0.50 | -3.536 | 4/20 | 0 | 1 | 2/20 | 0.0203 |
| -1.00 | -7.073 | 4/20 | 0 | 1 | 5/20 | 0.0407 |

## Interpretation

The historical result was not reproduced for feature 4672. No intervention corrected a control failure, while every nonzero arm regressed HumanEval/23. Most generations were invariant, showing that the hook was active but this decoder direction rarely crossed a greedy decoding boundary. The regression was caused by a longer continuation ending inside an unterminated docstring; postprocessing made no repair and reported no suspicious repair.

This is a valid negative result for one statistically strong feature, not a general rejection of historical-style selection. The old protocol also used decoder-side specificity and qualitative coherence. Feature 4672 has strong failure prediction, but ROC-AUC alone does not establish that subtracting its decoder vector removes the failure mechanism.
