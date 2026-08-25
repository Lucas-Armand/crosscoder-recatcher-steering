#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,os,subprocess
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--model',choices=['CodeLlama','DSTK100'],required=True); a=ap.parse_args()
    repo=Path('/home/lucas/crosscoder-recatcher-steering'); os.chdir(repo)
    if a.model=='CodeLlama':
        run=Path('runs/semantic_top10_codellama_alpha3_v1'); inp=Path('runs/eight_cell_top10_codellama_alpha3_semantic_v2/inputs/regression.jsonl'); side='b'
        common=['--checkpoint','runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt','--model-a-id','meta-llama/CodeLlama-7b-hf','--model-b-id','DevQuasar-5/coma-7B-v0.1','--tokenizer-id','meta-llama/CodeLlama-7b-hf']
    else:
        run=Path('runs/semantic_top10_dstk100_alpha3_v1'); inp=Path('runs/eight_cell_top10_dstk_alpha3_semantic_v2/inputs/improvement.jsonl'); side='a'
        common=['--checkpoint','runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt','--model-a-id','deepseek-ai/deepseek-coder-6.7b-base','--model-b-id','JetBrains/deepseek-coder-6.7B-kexer','--tokenizer-id','deepseek-ai/deepseek-coder-6.7b-base','--trust-remote-code']
    for d in ('generations','logs','postprocessed','evaluations'): (run/d).mkdir(parents=True,exist_ok=True)
    arms=[r for r in csv.DictReader(open('reports/eight_cell_semantic_alpha3_candidate_manifest_v1.csv')) if r['model']==a.model]
    expected=sum(1 for _ in inp.open())
    with (run/'arm_manifest.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(arms[0])); w.writeheader(); w.writerows(arms)
    def generate(fid,alpha,name):
        out=run/'generations'/f'bigcodebench__{name}_results.jsonl'
        if out.exists() and sum(1 for _ in out.open())==expected: return
        cmd=['.venv/bin/python','tools/run_crosscoder_intervention.py',*common,'--target-side',side,'--layer','16','--feature-id',str(fid),'--alpha',str(alpha),'--intervention-mode','traditional','--token-scope','last_token','--generation-backend','hf_generate','--input-jsonl',str(inp),'--output-jsonl',str(out),'--max-new-tokens','512','--temperature','0.2','--top-p','0.95','--seed','1000',f'--device-{side}','cuda:0','--dtype','nf4']
        with (run/'logs'/f'{name}.log').open('w') as log: subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        assert sum(1 for _ in out.open())==expected
    generate(0,0,'alpha0')
    for r in arms:
        alpha=int(r['alpha']); generate(int(r['feature_id']),alpha,f"f{r['feature_id']}_{'pos' if alpha>0 else 'neg'}3")
    (run/'GENERATIONS_COMPLETE').touch()
    with (run/'logs'/'reprocess.log').open('w') as log: subprocess.run(['.venv/bin/python','tools/reprocess_outputs_minimal.py','--raw-results-dir',str(run/'generations'),'--output-dir',str(run/'postprocessed')],stdout=log,stderr=subprocess.STDOUT,check=True)
    for sample in sorted((run/'postprocessed'/'samples_for_external_eval').glob('*_samples.jsonl')):
        stem=sample.name.replace('_samples.jsonl',''); out=run/'evaluations'/f'{stem}_eval.json'
        if out.exists(): continue
        with (run/'logs'/f'eval_{stem}.log').open('w') as log: subprocess.run(['/home/lucas/venvs/bigcodebench015/bin/python','tools/evaluate_bigcodebench_subset.py','--samples',str(sample),'--output',str(out),'--parallel','4'],stdout=log,stderr=subprocess.STDOUT,check=True)
    (run/'EVALUATION_COMPLETE').touch()
if __name__=='__main__': main()
