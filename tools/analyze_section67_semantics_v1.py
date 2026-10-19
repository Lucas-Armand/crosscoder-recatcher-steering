#!/usr/bin/env python3
"""Frozen-cohort token/timing analysis; reuses saved same-text residuals."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import time
import numpy as np
import torch
from transformers import AutoTokenizer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/section67_semantic_temporal_20261019_v1'
STRESS=ROOT/'runs/feature_stress_shuffle_20261016_v1'

def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def dump(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def prefix(a,b):
    n=min(len(a),len(b));i=0
    while i<n and a[i]==b[i]:i+=1
    return i
def csvwrite(p,rs):
    if not rs:return
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def pos(index,n):return index/max(1,n-1)
def boundary_position(offsets,char):
    n=len(offsets)
    if char>=int(offsets[-1,1]):return 1.0
    hit=np.flatnonzero(offsets[:,1]>char)
    return pos(int(hit[0]) if len(hit) else n-1,n)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--device',default='cuda:0');args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);torch.set_num_threads(4)
    frozen=json.loads((STRESS/'EXPERIMENT_MANIFEST.json').read_text())
    results=[];contexts=[];activation_files={};source_hashes={};allcurves=[];steering=[]
    for family in ['deepseek','codellama']:
        c=frozen['configs'][family];ds=family=='deepseek';fid=c['feature'];ma='deepseek_base' if ds else 'codellama_base';mb='deepseek_finetuned' if ds else 'codellama_merged'
        cohort=rows(Path(c['input']));ids={r['task_id'] for r in cohort};refs={r['task_id']:r for r in cohort}
        checkpoint=Path(c['checkpoint']);ck=torch.load(checkpoint,map_location='cpu',weights_only=False)
        state=ck['model_state_dict'];k=int(ck['config']['top_k']);assert k==100
        w=state['encoder.weight'].float().to(args.device);bias=state['encoder.bias'].float().to(args.device)
        assert w.shape[0]==16384
        activation_root=ROOT/'runs/same_text_activations'/('deepseek_base_finetuned_layer16_rms' if ds else 'codellama_base_merged_layer16_rms')
        capture=activation_root/'capture_manifest.json';index={(r['task_id'],r['source_text']):r for r in json.loads(capture.read_text()) if r['benchmark']=='bigcodebench'}
        source_hashes[str(capture)]=hashlib.sha256(capture.read_bytes()).hexdigest()
        codes={}
        if ds:
            for label in [ma,mb]:
                p=Path('/tmp/dstk119_source_evaluation')/f'bigcodebench__{label}_repaired.jsonl'
                source_hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
                codes.update({(r['task_id'],label):r['candidate_code_repaired'] for r in rows(p) if r['task_id'] in ids})
        else:
            p=ROOT/'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv'
            source_hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            for r in csv.DictReader(p.open()):
                if r['benchmark']=='bigcodebench' and r['task_id'] in ids:
                    codes[(r['task_id'],ma)]=r['base_code'];codes[(r['task_id'],mb)]=r['merged_code']
        kw=dict(use_fast=True,local_files_only=True,trust_remote_code=ds)
        if ds:kw.update(bos_token='<｜begin▁of▁sentence｜>',eos_token='<｜end▁of▁sentence｜>',pad_token='<｜end▁of▁sentence｜>')
        tokenizer=AutoTokenizer.from_pretrained(c['model_a'],**kw)
        tokenstats={source:defaultdict(lambda:dict(total=0,active=0,sum=0.,max=0.,tasks=set())) for source in [ma,mb]}
        arrays={};offset_cache={};localrows=[]
        for ti,task in enumerate(sorted(ids),1):
            cp=prefix(codes[(task,ma)],codes[(task,mb)])
            for source in [ma,mb]:
                code=codes[(task,source)];meta=index[(task,source)]
                pa=activation_root/'bigcodebench'/ma/meta['filename'];pb=activation_root/'bigcodebench'/mb/meta['filename']
                a=np.load(pa);b=np.load(pb);tokens=a['input_ids']
                assert np.array_equal(tokens,b['input_ids']) and len(tokens)==meta['tokens']
                enc=tokenizer(code,return_offsets_mapping=True,add_special_tokens=False)
                offsets=np.asarray(enc['offset_mapping']);fullids=np.asarray(enc['input_ids'])
                prompt=refs[task]['prompt'].rstrip()+'\n';start=len(prompt) if code.startswith(prompt) else 0
                mask=(offsets[:,1]>start)&(offsets[:,0]<len(code))
                assert np.array_equal(fullids[mask],tokens),(family,task,source,'token mask mismatch',len(fullids[mask]),len(tokens))
                offsets=offsets[mask];offset_cache[(task,source)]=offsets
                zlist=[]
                with torch.inference_mode():
                    for lo in range(0,len(tokens),128):
                        x=torch.from_numpy(np.concatenate([a['layer_16'][lo:lo+128],b['layer_16'][lo:lo+128]],axis=1)).float().to(args.device)
                        dense=torch.relu(torch.nn.functional.linear(x,w,bias))
                        values,indices=torch.topk(dense,k,dim=1,sorted=False)
                        z=torch.where(indices==fid,values,torch.zeros_like(values)).sum(dim=1)
                        zlist.append(z.cpu().numpy())
                z=np.concatenate(zlist);active=np.flatnonzero(z>0);n=len(z)
                for p in [pa,pb]:activation_files[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
                marker=re.search(r'(?im)^\s*(?:#\s*tests?[/\\]|#\s*test_task|from\s+task_func\s+import|class\s+Test\w*\s*\()',code[start:])
                markerchar=start+marker.start() if marker else None
                divpos=boundary_position(offsets,cp)
                firstpos=pos(int(active[0]),n) if len(active) else None
                r=dict(family=family,feature=fid,task_id=task,source_text=source,n_tokens=n,active_tokens=len(active),
                       active_fraction=len(active)/n,max_activation=float(z.max()),mean_activation=float(z.mean()),
                       first_active_position=firstpos,first_active_token=int(active[0]) if len(active) else None,
                       model_divergence_position=divpos,common_prefix_chars=cp,all_code_identical=codes[(task,ma)]==codes[(task,mb)],
                       evaluated_code_start_char=start,contamination_marker_position=boundary_position(offsets,markerchar) if markerchar is not None else None,
                       active_at_or_before_divergence=firstpos is not None and firstpos<=divpos)
                localrows.append(r);results.append(r)
                arrays[f'{task.split("/")[-1]}__{source}__z']=z
                arrays[f'{task.split("/")[-1]}__{source}__ids']=tokens
                arrays[f'{task.split("/")[-1]}__{source}__offsets']=offsets
                for j,(token,value) in enumerate(zip(tokens,z)):
                    stat=tokenstats[source][int(token)];stat['total']+=1
                    if value>0:
                        stat['active']+=1;stat['sum']+=float(value);stat['max']=max(stat['max'],float(value));stat['tasks'].add(task)
                # Up to three strongest activations per text; not three independent tasks.
                for j in sorted(active,key=lambda j:float(z[j]),reverse=True)[:3]:
                    left,right=map(int,offsets[j]);contexts.append(dict(family=family,feature=fid,task_id=task,source_text=source,
                        token_id=int(tokens[j]),token=tokenizer.decode([int(tokens[j])],clean_up_tokenization_spaces=False),
                        activation=float(z[j]),position=pos(int(j),n),context=code[max(start,left-90):min(len(code),right+110)]))
            if ti%25==0:print(family,ti,'/',len(ids),flush=True)
        np.savez_compressed(OUT/f'{family}_feature_activations.npz',**arrays)
        for source,stats in tokenstats.items():
            table=[]
            for token,s in stats.items():
                if not s['active']:continue
                table.append(dict(family=family,feature=fid,source_text=source,token_id=token,
                    token=tokenizer.decode([token],clean_up_tokenization_spaces=False),total_occurrences=s['total'],
                    active_occurrences=s['active'],active_task_support=len(s['tasks']),active_probability=s['active']/s['total'],
                    mean_activation_all_occurrences=s['sum']/s['total'],mean_activation_when_active=s['sum']/s['active'],
                    activation_sum=s['sum'],max_activation=s['max']))
            table.sort(key=lambda r:r['activation_sum'],reverse=True)
            csvwrite(OUT/f'{source}_token_statistics.csv',table)
        # Curves: all doses 0..5, sources identical to published dose-response release.
        previous=json.loads((ROOT/'reports/dose_response_section66_20261015/curves.json').read_text())['DeepSeek' if ds else 'CodeLlama']
        for kind in ['target','random']:
            for r in previous[kind]:
                if kind=='target' and r['feature_id']!=fid:continue
                allcurves.append(dict(family=family,kind=kind,identity=str(r['feature_id']),alpha=r['alpha'],
                    magnitude=abs(r['alpha']),passed=r['passed'],n=r['n'],changed=r['evaluated_code_changed']))
        for run in [STRESS,ROOT/'runs/feature_shuffle_doses24_20261018_v1']:
            mf=json.loads((run/'EXPERIMENT_MANIFEST.json').read_text())
            for arm in mf['arms']:
                if arm['family']!=family or arm['kind']!='shuffle' or abs(arm['alpha'])>5:continue
                sub=run/family;name=arm['name'];p=sub/'evaluations'/f'bigcodebench__{name}_eval.json'
                ev=json.loads(p.read_text());post=sub/'postprocessed/results_repaired'/f'bigcodebench__{name}_repaired.jsonl'
                basepost=ROOT/'runs/feature_stress_alpha0_20261015_v1'/family/'postprocessed/results_repaired'/f'bigcodebench__{family}_weak_alpha0_repaired.jsonl'
                bc={r['task_id']:r['candidate_code_repaired'] for r in rows(basepost)}
                sr=rows(post);assert {r['task_id'] for r in sr}==ids
                allcurves.append(dict(family=family,kind='shuffle',identity=str(arm['index']),alpha=arm['alpha'],magnitude=abs(arm['alpha']),
                    passed=ev['passed'],n=ev['n_tasks'],changed=sum(r['candidate_code_repaired']!=bc[r['task_id']] for r in sr)))
        # First steering divergence on weak-side evaluated baseline for target doses 1..5.
        baselinepath=ROOT/'runs/feature_stress_alpha0_20261015_v1'/family/'postprocessed/results_repaired'/f'bigcodebench__{family}_weak_alpha0_repaired.jsonl'
        baselines={r['task_id']:r['candidate_code_repaired'] for r in rows(baselinepath)}
        source_hashes[str(baselinepath)]=hashlib.sha256(baselinepath.read_bytes()).hexdigest()
        for mag in [1,2,3,4,5]:
            if ds:
                run=ROOT/('runs/dstk100_focused_subtype_alpha3_119_v1' if mag==3 else 'runs/dstk100_focused_subtype_multialpha_top5_119_v1')
                post=run/'postprocessed/results_repaired'/f'bigcodebench__f4810_neg{mag}_repaired.jsonl'
                ev=run/'evaluations'/f'bigcodebench__f4810_neg{mag}_eval.json'
            else:
                run=ROOT/'runs/focused_bbasv_v2_codellama'
                post=run/'direct_postprocessed/results_repaired'/f'bigcodebench__target_f4309_direct_-{mag}_repaired.jsonl'
                ev=run/'direct_evaluations'/f'bigcodebench__target_f4309_direct_-{mag}_eval.json'
                if mag==3:
                    run=ROOT/'runs/focused_subtype_codellama_alpha3_canonical_v1'
                    post=run/'postprocessed/results_repaired/bigcodebench__f4309_neg3_repaired.jsonl'
                    ev=run/'evaluations/bigcodebench__f4309_neg3_eval.json'
            er=json.loads(ev.read_text());sr=rows(post)
            baseline_source=ma if ds else mb
            for r in sr:
                import difflib
                task=r['task_id'];naturalcode=codes[(task,baseline_source)];basecode=baselines[task];newcode=r['candidate_code_repaired'];cp=prefix(basecode,newcode)
                passed=any(v['correct'] for v in er['eval'][task]);nr=next(v for v in localrows if v['task_id']==task and v['source_text']==baseline_source)
                enc=tokenizer(basecode,return_offsets_mapping=True,add_special_tokens=False)
                baselineoffsets=np.asarray(enc['offset_mapping'])
                prompt=refs[task]['prompt'].rstrip()+'\n';start=len(prompt) if basecode.startswith(prompt) else 0
                baselineoffsets=baselineoffsets[(baselineoffsets[:,1]>start)&(baselineoffsets[:,0]<len(basecode))]
                natural_mapped=None
                if nr['first_active_token'] is not None:
                    char=int(offset_cache[(task,baseline_source)][nr['first_active_token'],0])
                    for block in difflib.SequenceMatcher(None,naturalcode,basecode,autojunk=False).get_matching_blocks():
                        if block.a<=char<block.a+block.size:
                            natural_mapped=boundary_position(baselineoffsets,block.b+char-block.a);break
                steering.append(dict(family=family,feature=fid,alpha=-mag,task_id=task,passed=passed,changed=newcode!=basecode,
                    first_change_position=boundary_position(baselineoffsets,cp) if newcode!=basecode else None,
                    natural_first_activation=natural_mapped,natural_first_activation_frozen=nr['first_active_position'],
                    natural_active=nr['active_tokens']>0,natural_first_position_mapped=natural_mapped is not None,
                    frozen_code_equals_reextracted_baseline=naturalcode==basecode,
                    code_before=basecode,code_after=newcode))
        del w,bias,ck,state
        if torch.cuda.is_available():torch.cuda.empty_cache()
        print('FINISHED',family,flush=True)
    csvwrite(OUT/'natural_timing.csv',results);csvwrite(OUT/'curves.csv',allcurves)
    csvwrite(OUT/'steering_timing.csv',[{k:v for k,v in r.items() if k not in ['code_before','code_after']} for r in steering])
    dump(OUT/'activation_contexts.json',sorted(contexts,key=lambda r:r['activation'],reverse=True))
    dump(OUT/'steering_cases.json',steering)
    meta=dict(features={'deepseek':4810,'codellama':4309},cohorts={'deepseek':119,'codellama':50},
        representation='Shared same-text ReLU + per-token TopK100, canonical step10000',
        position='0-based evaluated-token index divided by n-1; inactive is missing, not 100%',
        model_divergence='first differing character of original extracted code mapped to saved evaluated-token offsets',
        marker='heuristic first generated test/import marker; not annotated semantic onset',
        semantic_statistics='activating token/context statistics, not correlations or unique feature meanings',
        baseline_alignment='Steering changes compare same-extractor alpha0 and arm. Frozen natural codes may differ from re-extracted alpha0. Natural activation character anchors mapped through exact matching blocks to the alpha0 token scale; missing mappings remain missing.',
        token_alignment='Exact captured input_ids versus tokenizer offsets checked for every text',
        source_sha256=source_hashes,activation_sha256=activation_files)
    dump(OUT/'METHOD_AND_INPUT_AUDIT.json',meta)
    (OUT/'ANALYSIS_COMPLETE').touch()

if __name__=='__main__':main()
