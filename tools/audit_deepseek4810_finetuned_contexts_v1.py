#!/usr/bin/env python3
"""Locate saved feature activations relative to the first main-function end."""
import ast,csv,json
from collections import Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/deepseek4810_finetuned_contexts_20261022_v1'
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    meta=list(csv.DictReader((SRC/'natural_timing.csv').open()));meta=[r for r in meta if r['family']=='deepseek']
    arrays=np.load(SRC/'deepseek_feature_activations.npz');records=[]
    for source in ['deepseek_base','deepseek_finetuned']:
        codes={r['task_id']:r['candidate_code_repaired'] for r in map(json.loads,(Path('/tmp/dstk119_source_evaluation')/f'bigcodebench__{source}_repaired.jsonl').read_text().splitlines())}
        for r in meta:
            if r['source_text']!=source:continue
            tid=r['task_id'];code=codes[tid];f=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func')
            lines=code.splitlines(keepends=True);end=sum(map(len,lines[:f.end_lineno]))
            key=tid.split('/')[-1]+'__'+source;z=arrays[key+'__z'];off=arrays[key+'__offsets'];active=np.flatnonzero(z>0)
            # Full line boundary includes the ending newline, avoiding false after-body labels for that token.
            inside=off[:,0]<end
            first=int(active[0]) if len(active) else None
            stage='inactive' if first is None else 'at_or_before_main_end' if inside[first] else 'after_main_end'
            lo,hi=map(int,off[first]) if first is not None else (0,0)
            records.append(dict(task_id=tid,source=source,first_stage=stage,
                first_token_span=code[lo:hi] if first is not None else None,
                first_context=code[max(int(r['evaluated_code_start_char']),lo-90):hi+140] if first is not None else None,
                main_end_line=f.end_lineno,mass_at_or_before_main_end=float(z[inside].sum()),mass_after_main_end=float(z[~inside].sum()),
                any_active_after_main=bool(np.any(z[~inside]>0)),main_definition_count=sum(isinstance(n,ast.FunctionDef) and n.name=='task_func' for n in ast.parse(code).body)))
    summary={}
    for source in ['deepseek_base','deepseek_finetuned']:
        rr=[r for r in records if r['source']==source];summary[source]=dict(n=len(rr),first_stages=dict(Counter(r['first_stage'] for r in rr)),
            mass_at_or_before_main_end=sum(r['mass_at_or_before_main_end'] for r in rr),mass_after_main_end=sum(r['mass_after_main_end'] for r in rr),
            any_active_after_main=sum(r['any_active_after_main'] for r in rr),multiple_main_definitions=sum(r['main_definition_count']>1 for r in rr))
    summary['method']='AST first task_func end line (including trailing newline). Before-main-end includes any captured helpers/imports before task_func. Later redefinitions are not the first main function. Frozen offline shared-latent measurements; no prompt, no new inference.'
    for name,obj in [('SUMMARY.json',summary),('task_contexts.json',records)]:
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
