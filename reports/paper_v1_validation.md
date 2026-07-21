# Validation report: paper_v1

Overall blocking status: **PASS**

Warnings are non-blocking evidence gaps that must be resolved or accepted before the publication freeze.

| Gate | Check | Status | Detail |
|---|---|---|---|
| postprocessing | postprocess manifest | PASS | gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_final_dataset_v1_postprocessed_minimal_v3/POSTPROCESS_MANIFEST.txt |
| generation | humanevalplus__deepseek_base task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__deepseek_base metadata contract | PASS | ok |
| postprocessing | humanevalplus__deepseek_base repair lineage | PASS | rows=164, changed=0, errors=[] |
| evaluation | humanevalplus__deepseek_base HumanEval+ evidence | PASS | rows=164, correct=62, explicit_status=True |
| generation | humanevalplus__deepseek_finetuned task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__deepseek_finetuned metadata contract | PASS | ok |
| postprocessing | humanevalplus__deepseek_finetuned repair lineage | PASS | rows=164, changed=0, errors=[] |
| evaluation | humanevalplus__deepseek_finetuned HumanEval+ evidence | PASS | rows=164, correct=99, explicit_status=True |
| generation | humanevalplus__deepseek_merged task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__deepseek_merged metadata contract | PASS | ok |
| postprocessing | humanevalplus__deepseek_merged repair lineage | PASS | rows=164, changed=0, errors=[] |
| evaluation | humanevalplus__deepseek_merged HumanEval+ evidence | PASS | rows=164, correct=122, explicit_status=True |
| generation | humanevalplus__codellama_base task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__codellama_base metadata contract | PASS | ok |
| postprocessing | humanevalplus__codellama_base repair lineage | PASS | rows=164, changed=118, errors=[] |
| evaluation | humanevalplus__codellama_base HumanEval+ evidence | PASS | rows=164, correct=52, explicit_status=True |
| generation | humanevalplus__codellama_finetuned task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__codellama_finetuned metadata contract | PASS | ok |
| postprocessing | humanevalplus__codellama_finetuned repair lineage | PASS | rows=164, changed=1, errors=[] |
| evaluation | humanevalplus__codellama_finetuned HumanEval+ evidence | PASS | rows=164, correct=0, explicit_status=True |
| generation | humanevalplus__codellama_merged task coverage | PASS | rows=164, unique=164, expected=164 |
| generation | humanevalplus__codellama_merged metadata contract | PASS | ok |
| postprocessing | humanevalplus__codellama_merged repair lineage | PASS | rows=164, changed=139, errors=[] |
| evaluation | humanevalplus__codellama_merged HumanEval+ evidence | PASS | rows=164, correct=17, explicit_status=True |
| generation | bigcodebench__deepseek_base task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__deepseek_base metadata contract | PASS | ok |
| postprocessing | bigcodebench__deepseek_base repair lineage | PASS | rows=1140, changed=0, errors=[] |
| evaluation | bigcodebench__deepseek_base BigCodeBench evidence | PASS | exitcode=0, pass@1=0.232, version_recorded=False |
| generation | bigcodebench__deepseek_finetuned task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__deepseek_finetuned metadata contract | PASS | ok |
| postprocessing | bigcodebench__deepseek_finetuned repair lineage | PASS | rows=1140, changed=0, errors=[] |
| evaluation | bigcodebench__deepseek_finetuned BigCodeBench evidence | PASS | exitcode=0, pass@1=0.304, version_recorded=False |
| generation | bigcodebench__deepseek_merged task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__deepseek_merged metadata contract | PASS | ok |
| postprocessing | bigcodebench__deepseek_merged repair lineage | PASS | rows=1140, changed=0, errors=[] |
| evaluation | bigcodebench__deepseek_merged BigCodeBench evidence | PASS | exitcode=0, pass@1=0.401, version_recorded=False |
| generation | bigcodebench__codellama_base task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__codellama_base metadata contract | PASS | ok |
| postprocessing | bigcodebench__codellama_base repair lineage | PASS | rows=1140, changed=635, errors=[] |
| evaluation | bigcodebench__codellama_base BigCodeBench evidence | PASS | exitcode=0, pass@1=0.272, version_recorded=False |
| generation | bigcodebench__codellama_finetuned task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__codellama_finetuned metadata contract | PASS | ok |
| postprocessing | bigcodebench__codellama_finetuned repair lineage | PASS | rows=1140, changed=8, errors=[] |
| evaluation | bigcodebench__codellama_finetuned BigCodeBench evidence | PASS | exitcode=0, pass@1=0.002, version_recorded=False |
| generation | bigcodebench__codellama_merged task coverage | PASS | rows=1140, unique=1140, expected=1140 |
| generation | bigcodebench__codellama_merged metadata contract | PASS | ok |
| postprocessing | bigcodebench__codellama_merged repair lineage | PASS | rows=1140, changed=747, errors=[] |
| evaluation | bigcodebench__codellama_merged BigCodeBench evidence | PASS | exitcode=0, pass@1=0.023, version_recorded=False |
| generation | sampling parameter provenance | PASS | archived experiment configs match |
| evaluation | BigCodeBench version provenance | WARN | The v3 launcher enforced bigcodebench==0.1.5 before evaluation, but that version line was not copied into the per-model evaluator logs. |
| activations | humanevalplus/deepseek_base | PASS | present=164, expected=164, declared_omissions=[] |
| activations | humanevalplus/deepseek_finetuned | PASS | present=164, expected=164, declared_omissions=[] |
| activations | humanevalplus/deepseek_merged | PASS | present=164, expected=164, declared_omissions=[] |
| activations | humanevalplus/codellama_base | PASS | present=164, expected=164, declared_omissions=[] |
| activations | humanevalplus/codellama_finetuned | PASS | present=164, expected=164, declared_omissions=[] |
| activations | humanevalplus/codellama_merged | PASS | present=164, expected=164, declared_omissions=[] |
| activations | bigcodebench/deepseek_base | PASS | present=1139, expected=1139, declared_omissions=[764] |
| activations | bigcodebench/deepseek_finetuned | PASS | present=1139, expected=1139, declared_omissions=[764] |
| activations | bigcodebench/deepseek_merged | PASS | present=1139, expected=1139, declared_omissions=[764] |
| activations | bigcodebench/codellama_base | PASS | present=1140, expected=1140, declared_omissions=[] |
| activations | bigcodebench/codellama_finetuned | PASS | present=1140, expected=1140, declared_omissions=[] |
| activations | bigcodebench/codellama_merged | PASS | present=1140, expected=1140, declared_omissions=[] |
| activations | payload conversion evidence | PASS | summary={'converted_and_validated': 7809, 'preexisting_revalidated': 12, 'declared_failures': 3}, expected_total=7824; 12 pre-existing task-0 payloads are covered by the supplemental revalidation report |
| crosscoders | deepseek_base_finetuned_layer16 | PASS | exitcode=0, final=True, final_uri=gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/releases/paper_v1/artifacts/crosscoders/deepseek_base_finetuned_layer16/final.pt, final_step=20000, pair=True, config_errors=[], finite_metrics=True |
| crosscoders | deepseek_base_merged_layer16 | PASS | exitcode=0, final=True, final_uri=gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_training_v1/deepseek_base_vs_deepseek_merged_layer16_lat16384_steps20000/final.pt, final_step=20000, pair=True, config_errors=[], finite_metrics=True |
| crosscoders | codellama_base_finetuned_layer16 | PASS | exitcode=0, final=True, final_uri=gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_codellama_base_finetuned_layer16_float32_v1/codellama_base_vs_codellama_finetuned_layer16_lat16384_steps20000/final.pt, final_step=20000, pair=True, config_errors=[], finite_metrics=True |
| crosscoders | codellama_base_merged_layer16 | PASS | exitcode=0, final=True, final_uri=gs://data-intelligence-bucket/tests/recatcher_crosscoder_humaneval/crosscoder_codellama_base_merged_layer16_float32_v1/codellama_base_vs_codellama_merged_layer16_lat16384_steps20000/final.pt, final_step=20000, pair=True, config_errors=[], finite_metrics=True |
