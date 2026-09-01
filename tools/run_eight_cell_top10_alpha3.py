#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,glob,json,os,subprocess
from pathlib import Path

def prepare(project,run):
    if project=='codellama':
        ranking=Path('reports/eight_cell_screening_codellama_base_merged_v1'); ma,mb='codellama_base','codellama_merged'
        files={'regression':'bigcodebench__codellama_merged_repaired.jsonl','improvement':'bigcodebench__codellama_base_repaired.jsonl'}
    else:
        ranking=Path('reports/eight_cell_screening_dstk100_v1'); ma,mb='deepseek_base','deepseek_finetuned'
        files={'regression':'bigcodebench__deepseek_finetuned_repaired.jsonl','improvement':'bigcodebench__deepseek_base_repaired.jsonl'}
    labels={}
    for r in csv.DictReader(open('reports/paper_v1_v4_evaluation_labels.csv')):
        if r['benchmark']=='bigcodebench' and r['model'] in (ma,mb): labels[(r['model'],r['task_id'])]=int(r['label'])
    arms={}
    for p in ranking.glob('*_absolute.csv'):
        cell=p.name.replace('_absolute.csv',''); tr=cell.split('_')[0]
        for r in list(csv.DictReader(p.open()))[:10]:
            fid=int(r['feature_id']); ori=r['orientation']
            sign=(1 if ori=='base_enriched' else -1) if tr=='regression' else (-1 if ori=='base_enriched' else 1)
            key=(tr,fid); arms.setdefault(key,{'sign':sign,'source_cells':[],'orientation':ori})
            if arms[key]['sign']!=sign: raise RuntimeError(f'conflicting sign {key}')
            arms[key]['source_cells'].append(cell)
    run.mkdir(parents=True,exist_ok=True); (run/'inputs').mkdir(exist_ok=True)
    source_root=Path('/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired')
    for tr,file in files.items():
        wanted={t for (m,t),v in labels.items() if m==ma and ((tr=='regression' and v==0 and labels.get((mb,t))==1) or (tr=='improvement' and v==1 and labels.get((mb,t))==0))}
        rows=[]
        for r in map(json.loads,open(source_root/file)):
            if r.get('task_id') in wanted: rows.append({'benchmark':'bigcodebench','task_id':r['task_id'],'task_idx':r['task_idx'],'entry_point':r['entry_point'],'prompt':r['prompt'],'original_prompt':r['prompt'],'seed':1000+int(r['task_idx'])})
        rows.sort(key=lambda r:r['task_idx']); assert len(rows)==len(wanted)
        (run/'inputs'/f'{tr}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    fields=['transition','feature_id','orientation','sign','alpha','source_cells']
    with (run/'arm_manifest.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fields); w.writeheader()
        for (tr,fid),v in sorted(arms.items()): w.writerow({'transition':tr,'feature_id':fid,'orientation':v['orientation'],'sign':v['sign'],'alpha':3*v['sign'],'source_cells':';'.join(v['source_cells'])})
    return list(csv.DictReader(open(run/'arm_manifest.csv')))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--project',choices=['codellama','dstk'],required=True); a=ap.parse_args()
    repo=Path('/home/lucas/crosscoder-recatcher-steering'); os.chdir(repo)
    run=Path('runs')/('eight_cell_top10_codellama_alpha3_v1' if a.project=='codellama' else 'eight_cell_top10_dstk_alpha3_v1')
    for d in ('generations','logs','postprocessed','evaluations'): (run/d).mkdir(parents=True,exist_ok=True)
    arms=prepare(a.project,run)
    if a.project=='codellama':
        common=['--checkpoint','runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt','--model-a-id','meta-llama/CodeLlama-7b-hf','--model-b-id','DevQuasar-5/coma-7B-v0.1','--tokenizer-id','meta-llama/CodeLlama-7b-hf']; sides={'regression':'b','improvement':'a'}
    else:
        common=['--checkpoint','runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt','--model-a-id','deepseek-ai/deepseek-coder-6.7b-base','--model-b-id','JetBrains/deepseek-coder-6.7B-kexer','--tokenizer-id','deepseek-ai/deepseek-coder-6.7b-base','--trust-remote-code']; sides={'regression':'b','improvement':'a'}
    def generate(tr,fid,alpha,name):
        inp=run/'inputs'/f'{tr}.jsonl'; expected=sum(1 for _ in inp.open()); out=run/'generations'/f'bigcodebench__{name}_results.jsonl'
        if out.exists() and sum(1 for _ in out.open())==expected: return
        side=sides[tr]; cmd=['.venv/bin/python','tools/run_crosscoder_intervention.py',*common,'--target-side',side,'--layer','16','--feature-id',str(fid),'--alpha',str(alpha),'--intervention-mode','traditional','--token-scope','last_token','--generation-backend','hf_generate','--input-jsonl',str(inp),'--output-jsonl',str(out),'--max-new-tokens','512','--temperature','0.2','--top-p','0.95','--seed','1000',f'--device-{side}','cuda:0','--dtype','nf4']
        with (run/'logs'/f'{name}.log').open('w') as log: subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        assert sum(1 for _ in out.open())==expected
    for tr in ('regression','improvement'): generate(tr,0,0,f'{tr}_alpha0')
    for r in arms: generate(r['transition'],int(r['feature_id']),int(r['alpha']),f"{r['transition']}_f{r['feature_id']}_{'pos' if int(r['alpha'])>0 else 'neg'}3")
    (run/'GENERATIONS_COMPLETE').touch()
    with (run/'logs'/'reprocess.log').open('w') as log: subprocess.run(['.venv/bin/python','tools/reprocess_outputs_minimal.py','--raw-results-dir',str(run/'generations'),'--output-dir',str(run/'postprocessed')],stdout=log,stderr=subprocess.STDOUT,check=True)
    for sample in sorted((run/'postprocessed'/'samples_for_external_eval').glob('*_samples.jsonl')):
        stem=sample.name.replace('_samples.jsonl',''); out=run/'evaluations'/f'{stem}_eval.json'
        if out.exists(): continue
        with (run/'logs'/f'eval_{stem}.log').open('w') as log: subprocess.run(['/home/lucas/venvs/bigcodebench015/bin/python','tools/evaluate_bigcodebench_subset.py','--samples',str(sample),'--output',str(out),'--parallel','4'],stdout=log,stderr=subprocess.STDOUT,check=True)
    (run/'EVALUATION_COMPLETE').touch()
if __name__=='__main__': main()
