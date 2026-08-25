#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import torch

METRICS=('max','mean','active_fraction')

def prefix_len(a,b):
    n=min(len(a),len(b)); i=0
    while i<n and a[i]==b[i]: i+=1
    return i

def encode(path_a,path_b,w,bias,k,device,boundary_fraction):
    a=np.load(path_a); b=np.load(path_b)
    if not np.array_equal(a['input_ids'],b['input_ids']): raise ValueError('unaligned token IDs')
    x=torch.from_numpy(np.concatenate([a['layer_16'],b['layer_16']],1)).float().to(device)
    with torch.inference_mode():
        dense=torch.relu(torch.nn.functional.linear(x,w,bias)); val,idx=torch.topk(dense,k,dim=1,sorted=False)
        z=torch.zeros_like(dense).scatter_(1,idx,val); n=len(z)
        center=min(n-1,max(0,round(boundary_fraction*n))); radius=max(2,math.ceil(.10*n))
        local=z[max(0,center-radius):min(n,center+radius+1)]
        def sm(q): return {'max':q.max(0).values.cpu().numpy().astype(np.float16),'mean':q.mean(0).cpu().numpy().astype(np.float16),'active_fraction':(q>0).float().mean(0).cpu().numpy().astype(np.float16)}
        return sm(z),sm(local)

def ev_association(X,y,perms,rng):
    pos=y; effect=X[pos].mean(0)-X[~pos].mean(0); null=np.empty((perms,X.shape[1]),np.float32)
    for p in range(perms):
        yp=rng.permutation(y); null[p]=X[yp].mean(0)-X[~yp].mean(0)
    sd=null.std(0,ddof=1); return effect,sd,np.divide(effect,sd,out=np.zeros_like(effect),where=sd>0)

def ev_paired(X,perms,rng):
    effect=X.mean(0); null=np.empty((perms,X.shape[1]),np.float32)
    for p in range(perms):
        sign=rng.choice(np.array([-1,1],np.float32),len(X)); null[p]=(X*sign[:,None]).mean(0)
    sd=null.std(0,ddof=1); return effect,sd,np.divide(effect,sd,out=np.zeros_like(effect),where=sd>0)

def rank_cell(delta,active,y,kind,scope,perms,seed):
    rng=np.random.default_rng(seed); pos=y if kind=='association' else np.ones(len(y),bool)
    min_support=max(3,math.ceil(.10*int(pos.sum()))); variants=[]
    for metric in METRICS:
        X=delta[(scope,metric)].astype(np.float32)
        effect,sd,ev=(ev_association(X,y,perms,rng) if kind=='association' else ev_paired(X[y],perms,rng))
        variants.append((metric,effect,sd,ev))
    nf=variants[0][1].shape[0]; rows=[]
    support=active[scope][pos].sum(0)
    for j in range(nf):
        best=max(variants,key=lambda q:abs(float(q[3][j])))
        metric,effect,sd,ev=best
        if support[j] < min_support: continue
        rows.append({'feature_id':j,'orientation':'specialized_enriched' if ev[j]>0 else 'base_enriched','summary':metric,'effect':float(effect[j]),'null_sd':float(sd[j]),'ev':float(ev[j]),'abs_ev':float(abs(ev[j])),'support':int(support[j]),'minimum_support':min_support})
    rows.sort(key=lambda r:r['abs_ev'],reverse=True); return rows

def write_rows(path,rows):
    fields=['rank','feature_id','orientation','summary','effect','null_sd','ev','abs_ev','support','minimum_support']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields); w.writeheader(); w.writerows([{'rank':i+1,**r} for i,r in enumerate(rows)])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--project',choices=['codellama','dstk'],required=True); ap.add_argument('--device',default='cuda:0'); ap.add_argument('--permutations',type=int,default=200); ap.add_argument('--seed',type=int,default=42); a=ap.parse_args()
    if a.project=='codellama':
        ckpt=Path('runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt'); root=Path('runs/same_text_activations/codellama_base_merged_layer16_rms'); ma,mb='codellama_base','codellama_merged'; repaired_a='bigcodebench__codellama_base_repaired.jsonl'; repaired_b='bigcodebench__codellama_merged_repaired.jsonl'; out=Path('reports/eight_cell_screening_codellama_base_merged_v1')
    else:
        ckpt=Path('runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt'); root=Path('runs/same_text_activations/deepseek_base_finetuned_layer16_rms'); ma,mb='deepseek_base','deepseek_finetuned'; repaired_a='bigcodebench__deepseek_base_repaired.jsonl'; repaired_b='bigcodebench__deepseek_finetuned_repaired.jsonl'; out=Path('reports/eight_cell_screening_dstk100_v1')
    out.mkdir(parents=True,exist_ok=True); device=torch.device(a.device)
    ck=torch.load(ckpt,map_location='cpu',weights_only=False); sd=ck['model_state_dict']; k=int(ck['config']['top_k']); w=sd['encoder.weight'].float().to(device); bias=sd['encoder.bias'].float().to(device)
    labels={}
    for r in csv.DictReader(open('reports/paper_v1_v4_evaluation_labels.csv')):
        if r['benchmark']=='bigcodebench' and r['model'] in (ma,mb): labels[(r['model'],r['task_id'])]=int(r['label'])
    rr=Path('/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired')
    code={}
    for model,file in [(ma,repaired_a),(mb,repaired_b)]:
        for r in map(json.loads,open(rr/file)):
            code[(model,r['task_id'])]=r.get('extraction_generated_text') or r.get('raw_completion') or ''
    manifest=json.loads((root/'capture_manifest.json').read_text()); idx={(m['task_id'],m['source_text']):m for m in manifest if m['benchmark']=='bigcodebench'}
    tasks=sorted({t for m,t in labels if m==ma and (mb,t) in labels}); deltas={('global',q):[] for q in METRICS}; deltas.update({('local',q):[] for q in METRICS}); act={'global':[],'local':[]}; meta=[]
    for ni,t in enumerate(tasks,1):
        ca,cb=code[(ma,t)],code[(mb,t)]; cp=prefix_len(ca,cb); fractions={ma:(cp/max(1,len(ca))),mb:(cp/max(1,len(cb)))}; pair=[]
        for source in (ma,mb):
            m=idx[(t,source)]; pa=root/'bigcodebench'/ma/m['filename']; pb=root/'bigcodebench'/mb/m['filename']; pair.append(encode(pa,pb,w,bias,k,device,fractions[source]))
        for si,scope in enumerate(('global','local')):
            for q in METRICS: deltas[(scope,q)].append(pair[1][si][q].astype(np.float32)-pair[0][si][q].astype(np.float32))
            act[scope].append(np.maximum(pair[0][si]['max'],pair[1][si]['max'])>0)
        la,lb=labels[(ma,t)],labels[(mb,t)]; transition='regression' if (la,lb)==(0,1) else 'improvement' if (la,lb)==(1,0) else 'both_pass' if (la,lb)==(0,0) else 'both_fail'; meta.append((t,transition))
        if ni%50==0: print(a.project,ni,'/',len(tasks),flush=True)
    delta={q:np.stack(v) for q,v in deltas.items()}; active={q:np.stack(v) for q,v in act.items()}; transition=np.array([x[1] for x in meta])
    summaries=[]
    for tr,condition,control in [('regression','regression','both_pass'),('improvement','improvement','both_fail')]:
        pop=np.isin(transition,[condition,control]); yp=transition[pop]==condition
        for kind in ('association','paired'):
            for scope in ('global','local'):
                d={q:v[pop] for q,v in delta.items()}; ac={q:v[pop] for q,v in active.items()}; rows=rank_cell(d,ac,yp,kind,scope,a.permutations,a.seed)
                cell=f'{tr}_{kind}_{scope}'; write_rows(out/f'{cell}_absolute.csv',rows)
                for orient in ('specialized_enriched','base_enriched'): write_rows(out/f'{cell}_{orient}.csv',[r for r in rows if r['orientation']==orient])
                summaries.append({'cell':cell,'population':int(pop.sum()),'positives':int(yp.sum()),'controls':int((~yp).sum()) if kind=='association' else 0,'top10':[int(r['feature_id']) for r in rows[:10]]})
    known=27 if a.project=='codellama' else 10168
    for s in summaries:
        rows=list(csv.DictReader(open(out/f"{s['cell']}_absolute.csv"))); s['known_absolute_rank']=next((int(r['rank']) for r in rows if int(r['feature_id'])==known),None); s['known_signed_rank']=None
        if s['known_absolute_rank'] is not None:
            hit=next(r for r in rows if int(r['feature_id'])==known); signed=list(csv.DictReader(open(out/f"{s['cell']}_{hit['orientation']}.csv"))); s['known_orientation']=hit['orientation']; s['known_signed_rank']=next(int(r['rank']) for r in signed if int(r['feature_id'])==known); s['known_ev']=float(hit['ev']); s['known_summary']=hit['summary']
    summary={'project':a.project,'checkpoint':str(ckpt),'top_k':k,'tokens':'extraction-v4 evaluated code only','local_window':'±10% of each source text around normalized first divergence','permutations':a.permutations,'sign':'positive=specialized text enriched; negative=base text enriched','support_rule':'max(3,10% positives)','known_feature':known,'cells':summaries}
    (out/'run_summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
