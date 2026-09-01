# DeepSeek reverse-baseline reproducibility audit

Date: 2026-09-01

## Question

Why does the current reverse alpha-zero generation pass only 60/80 tasks when the 80-task cohort was defined as historical base-fail / fine-tuned-pass improvements and the per-task seeds are unchanged?

## Artifacts compared

- Historical fine-tuned generation: `recatcher_crosscoder_humaneval/deepseek_rerun_1gen_max512/results/bigcodebench__deepseek_finetuned_results.jsonl`
- Current reverse baseline: `runs/focused_bbasv_v2_deepseek/gate/baseline_reverse_alpha0.jsonl`
- Current HF-generate alpha-zero control: `runs/dstk100_f10168_symmetric_ft80_v1/generations/bigcodebench__f10168_ft_alpha0_results.jsonl`
- Cohort input: `runs/focused_subtype_dstk100_alpha3_canonical_v1/input.jsonl`
- Historical canonical labels: `reports/paper_v1_v4_evaluation_labels.csv`

## Findings

1. The cohort input preserves the historical **base** completion, not the historical fine-tuned completion. Consequently, the earlier 80/80 byte-reproduction gate validates only the base-side generation.
2. The historical labels classify all 80 fine-tuned generations as passing (`label=0`, where the canonical label convention is `1=fail`).
3. Historical and current fine-tuned generations use the same 80 task IDs, exact prompts, and per-task seeds (`1000 + 100 * task_idx`).
4. Both use the same model identifier (`JetBrains/deepseek-coder-6.7B-kexer`), 512 generated tokens, temperature 0.2, top-p 0.95, NF4 double quantization, float16 compute, and eager attention.
5. The base and fine-tuned tokenizer instances produce identical prompt token IDs for all 80 tasks. Tokenizer selection is not the cause.
6. Only 3/80 current fine-tuned completions reproduce the historical raw completion exactly. The median first character divergence occurs at approximately 29.7% of the shorter completion.
7. A current `hf_generate` alpha-zero run and the current `paired_cached` alpha-zero run reproduce each other exactly for 80/80 tasks. Both reproduce the historical generation in only 3/80 cases. The current backend implementation is therefore not the source of the historical/current discrepancy.
8. The currently cached Hugging Face model points to snapshot `a1ca3b262e94a5277098aa759e79f2b548c62d3d`. No evidence of a second local snapshot was found.
9. The historical run did not preserve a complete software and hardware environment lock. The current environment is PyTorch 2.5.1+cu121, Transformers 4.45.2, bitsandbytes 0.49.2, and NVIDIA driver 595.71.05. The corresponding June package/driver versions cannot be reconstructed from the preserved metadata.

## Conclusion

The seed is unchanged, but the historical execution environment was not captured strongly enough to guarantee cross-environment bitwise sampling reproducibility. The evidence rules out task selection, prompts, seeds, tokenizer token IDs, and the current `hf_generate` versus `paired_cached` distinction. The remaining likely cause is an unrecorded numerical/runtime difference between the June and current environments (for example PyTorch, Transformers, bitsandbytes, CUDA/driver, or quantized-kernel behavior). The exact component cannot be identified from the preserved artifacts.

The statement "sampling caused the 60/80 result" is incomplete. Sampling makes small numerical changes capable of changing a token choice; the missing environment lock is what prevents the seed from reproducing the historical sample.

## Scientific consequence

- The direct experiment remains strongly gated: its alpha-zero base completion reproduces the stored base completion byte-for-byte for 80/80 tasks.
- The current inverse experiment is internally paired with its current alpha-zero fine-tuned baseline. Pass-to-fail results are valid only among the 60 tasks that pass under that current baseline.
- It must not be presented as a symmetric reversal of all 80 historical improvements.
- A confirmatory bidirectional experiment should construct its cohort from alpha-zero outputs generated in the same frozen environment as the intervention arms, preserve both model-side baselines, and require byte-level reproduction gates on both sides.
- Prefer deterministic decoding for the confirmatory experiment if the scientific question permits it. If sampling is retained, record package versions, CUDA/driver, GPU identity, model revision, tokenizer revision, generation implementation, and per-task RNG state in addition to the seed.

