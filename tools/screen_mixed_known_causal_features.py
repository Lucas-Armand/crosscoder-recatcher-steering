#!/usr/bin/env python3
from __future__ import annotations
import csv,json,math,argparse
from pathlib import Path
import numpy as np
import torch

NF=16384

def topk_z(pa,pb,w,bias,k,device):
    a=np.load(pa); b=np.load(pb)
    assert np.array_equal(a['input_ids'],b['input_ids'])
    x=torch.from_numpy(np.concatenate([a['layer_16'],b['layer_16']],1)).float().to(device)
    with torch.inference_mode():
        d=torch.relu(torch.nn.functional.linear(x,w,bias)); v,i=torch.topk(d,k,dim=1,sorted=False)
        z=torch.zeros_like(d).scatter_(1,i,v)
    return z

def summaries(z,region,temporal_kind):
    n=len(z); lo,hi=region; part=z[lo:hi]
    if len(part)==0: part=z[:1]*0
    t=torch.linspace(0,1,n,device=z.device)[:,None]
    wt=(1-t if temporal_kind=='early' else t)
    return {
      'full_max':z.max(0).values.cpu().numpy(),
      'full_mean':z.mean(0).cpu().numpy(),
      'full_active_fraction':(z>0).float().mean(0).cpu().numpy(),
      'region_max':part.max(0).values.cpu().numpy(),
      'region_mean':part.mean(0).cpu().numpy(),
      'region_active_fraction':(part>0).float().mean(0).cpu().numpy(),
      'temporal_weighted_mean':(z*wt).sum(0).div(wt.sum()).cpu().numpy(),
      'temporal_weighted_max':(z*wt).max(0).values.cpu().numpy(),
    }

def paired_ev(X,seed=42,perms=200):
    effect=X.mean(0); rng=np.random.default_rng(seed)
    null=np.empty((perms,X.shape[1]),np.float32)
    for p in range(perms):
        signs=rng.choice(np.array([-1,1],np.float32),len(X))
        null[p]=(X*signs[:,None]).mean(0)
    sd=null.std(0,ddof=1)
    ev=np.divide(effect,sd,out=np.zeros_like(effect),where=sd>0)
    return effect,sd,ev

def best_metric(mats,prefix):
    rows=[]
    for name,X in mats.items():
        if not name.startswith(prefix): continue
        effect,sd,ev=paired_ev(X)
        rows.append((name,effect,sd,ev))
    E=np.stack([np.abs(x[3]) for x in rows]); choice=E.argmax(0); out=[]
    for j in range(NF):
        name,effect,sd,ev=rows[int(choice[j])]
        out.append({'feature_id':j,'summary':name,'effect':float(effect[j]),'null_sd':float(sd[j]),'ev':float(ev[j]),'abs_ev':float(abs(ev[j]))})
    return out

def transition_rows(path,transition):
    raw=[r for r in csv.DictReader(open(path)) if r['benchmark']=='bigcodebench' and r['transition']==transition]; by={}
    for r in raw:
        fid=int(r['feature_id']); ev=float(r.get('effect_to_permutation_variability',r.get('effect_to_null_sd')))
        rr={'feature_id':fid,'summary':r.get('aggregation',r.get('metric')),'effect':float(r['effect']),'null_sd':float(r.get('permutation_null_sd',r.get('null_sd'))),'ev':ev,'abs_ev':abs(ev)}
        if fid not in by or rr['abs_ev']>by[fid]['abs_ev']: by[fid]=rr
    return [by[j] for j in range(NF)]

def pct_scores(rows):
    order=np.argsort([r['abs_ev'] for r in rows]); pct=np.empty(len(rows),np.float32); pct[order]=np.linspace(0,1,len(rows),endpoint=True)
    return pct

def write_rankings(out,criterion,rows):
    rows=sorted(rows,key=lambda r:r['abs_ev'],reverse=True)
    fields=['rank','feature_id','orientation','summary','effect','null_sd','ev','abs_ev']
    with open(out/f'{criterion}_absolute.csv','w',newline='') as f:
        w=csv.DictWriter(f,fields); w.writeheader(); w.writerows([{'rank':i+1,'orientation':'positive' if r['ev']>0 else 'negative',**r} for i,r in enumerate(rows)])
    for sign in ('positive','negative'):
        ss=[r for r in rows if (r['ev']>0)==(sign=='positive')]
        with open(out/f'{criterion}_{sign}.csv','w',newline='') as f:
            w=csv.DictWriter(f,fields); w.writeheader(); w.writerows([{'rank':i+1,'orientation':sign,**r} for i,r in enumerate(ss)])

def run_project(name,checkpoint,root,model_a,model_b,wanted,boundaries,transition_csv,transition,out,device,region_kind,orientation):
    out.mkdir(parents=True,exist_ok=True)
    ck=torch.load(checkpoint,map_location='cpu',weights_only=False); sd=ck['model_state_dict']; k=int(ck['config']['top_k'])
    dev=torch.device(device); w=sd['encoder.weight'].float().to(dev); bias=sd['encoder.bias'].float().to(dev)
    manifest=json.loads((root/'capture_manifest.json').read_text()); index={}
    for m in manifest:
        if m['benchmark']=='bigcodebench' and m['task_id'] in wanted: index[(m['task_id'],m['source_text'])]=m
    records=[]
    for task in sorted(wanted):
        pair=[]
        for source in (model_a,model_b):
            m=index[(task,source)]; pa=root/'bigcodebench'/model_a/m['filename']; pb=root/'bigcodebench'/model_b/m['filename']
            z=topk_z(pa,pb,w,bias,k,dev); n=len(z)
            if region_kind=='first10': region=(0,min(10,n)); temporal='early'
            else:
                p=boundaries.get(task,80.0)/100.; c=min(n-1,max(0,round(p*n))); radius=max(2,math.ceil(.1*n)); region=(max(0,c-radius),min(n,c+radius+1)); temporal='late'
            pair.append(summaries(z,region,temporal))
        delta={q:(pair[1][q]-pair[0][q])*orientation for q in pair[0]}
        records.append(delta)
        print(name,task,len(records),'/',len(wanted),flush=True)
    mats={q:np.stack([r[q] for r in records]).astype(np.float32) for q in records[0]}
    criteria={
      'transition_vs_rest':transition_rows(transition_csv,transition),
      'paired_model_diff':best_metric(mats,'full_'),
      'error_region':best_metric(mats,'region_'),
      'temporal_weighted':best_metric(mats,'temporal_'),
    }
    for c,r in criteria.items(): write_rankings(out,c,r)
    pcts={c:pct_scores(r) for c,r in criteria.items()}; mixed=[]
    for j in range(NF):
        score=float(np.mean([pcts[c][j] for c in criteria])); signs=[np.sign(criteria[c][j]['ev']) for c in criteria]
        mixed.append({'feature_id':j,'mixed_score':score,'sign_consistency':float(abs(sum(signs))/len(signs)),**{f'{c}_ev':criteria[c][j]['ev'] for c in criteria}})
    mixed.sort(key=lambda r:(r['mixed_score'],r['sign_consistency']),reverse=True)
    with open(out/'mixed_rank.csv','w',newline='') as f:
        fields=['rank']+list(mixed[0]); wr=csv.DictWriter(f,fields); wr.writeheader(); wr.writerows([{'rank':i+1,**r} for i,r in enumerate(mixed)])
    known=27 if name=='codellama_f27' else 10168
    summary={'project':name,'tasks':len(wanted),'orientation_definition':('base_text-minus-model_b_text' if orientation==-1 else 'model_b_text-minus-base_text'),'region':region_kind,'known_feature':known,'known_ranks':{c:next(i+1 for i,r in enumerate(sorted(rows,key=lambda x:x['abs_ev'],reverse=True)) if r['feature_id']==known) for c,rows in criteria.items()},'known_mixed_rank':next(i+1 for i,r in enumerate(mixed) if r['feature_id']==known)}
    (out/'run_summary.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--device',default='cuda:0'); a=ap.parse_args()
    repo=Path('.')
    tax=list(csv.DictReader(open('reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv')))
    cset={r['task_id'] for r in tax if r['benchmark']=='bigcodebench' and r['primary_failure_category']=='wrong_logic_or_other_runtime'}
    dset={json.loads(x)['task_id'] for x in open('runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl')}
    bounds={r['task_id']:float(r['boundary_percent']) for r in csv.DictReader(open('reports/dstk100_causal_attribution_contamination_v1/boundary_manifest.csv'))}
    run_project('codellama_f27',Path('runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt'),Path('runs/same_text_activations/codellama_base_merged_layer16_rms'),'codellama_base','codellama_merged',cset,{},Path('reports/codellama_base_merged_topk100_v1_feature_screening/all_feature_statistics.csv'),'regression',Path('reports/mixed_screening_codellama_f27_v1'),a.device,'first10',-1)
    run_project('dstk10168',Path('runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt'),Path('runs/same_text_activations/deepseek_base_finetuned_layer16_rms'),'deepseek_base','deepseek_finetuned',dset,bounds,Path('reports/dstk100_feature_screening_improvement_slide5_rerun_20260814/all_feature_statistics.csv'),'improvement',Path('reports/mixed_screening_dstk10168_v1'),a.device,'boundary',-1)
if __name__=='__main__': main()
