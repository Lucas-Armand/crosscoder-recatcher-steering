#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,subprocess
from pathlib import Path
import numpy as np
import torch

REPO=Path('/home/lucas/crosscoder-recatcher-steering'); MAGS=[1,2,3,4,5]
CFG={
 'deepseek':dict(run='runs/focused_bbasv_v2_deepseek',n=80,input='runs/focused_subtype_dstk100_alpha3_canonical_v1/input.jsonl',checkpoint='runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt',model_a='deepseek-ai/deepseek-coder-6.7b-base',model_b='JetBrains/deepseek-coder-6.7B-kexer',tokenizer='deepseek-ai/deepseek-coder-6.7b-base',direct='a',reverse='b',targets=[2468,2621,15235,14175,2913],random={8628:-1,12728:1,2482:-1},backend='paired_cached',trust=True,seeds=[20260827,20260828,20260829]),
 'codellama':dict(run='runs/focused_bbasv_v2_codellama',n=50,input='runs/focused_subtype_codellama_alpha3_canonical_v1/input.jsonl',checkpoint='runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt',model_a='meta-llama/CodeLlama-7b-hf',model_b='DevQuasar-5/coma-7B-v0.1',tokenizer='meta-llama/CodeLlama-7b-hf',direct='b',reverse='a',targets=[7692,10818,5642,11596,4309],random={15035:-1,6019:1,5412:1},backend='hf_generate',trust=False,seeds=[20260830,20260831,20260832])}

def nlines(p):return sum(1 for _ in p.open()) if p.exists() else -1
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--family',choices=CFG,required=True);a=ap.parse_args();c=CFG[a.family];os.chdir(REPO)
 run=Path(c['run']);outdir=run/'controls_generations';logdir=run/'controls_logs';ctrldir=run/'controls_v2'
 for d in (outdir,logdir,ctrldir):d.mkdir(parents=True,exist_ok=True)
 rows=[json.loads(x) for x in open(c['input'])];assert len(rows)==c['n'];assert all(r['seed']==1000+100*int(r['task_idx']) for r in rows)
 gate=run/'gate/baseline_reverse_alpha0.jsonl';assert nlines(gate)==c['n']
 state=torch.load(c['checkpoint'],map_location='cpu',weights_only=False)['model_state_dict'];task_ids=np.asarray([r['task_id'] for r in rows])
 sham_files={}
 for j,seed in enumerate(c['seeds'],1):
  for side in (c['direct'],c['reverse']):
   ds=torch.stack([state[f'decoder_{side}.weight'][:,fid].float() for fid in c['targets']],dim=1);q=torch.linalg.qr(ds,mode='reduced').Q
   g=torch.Generator().manual_seed(seed+(0 if side=='a' else 100));v=torch.randn(ds.shape[0],generator=g);v=v-q@(q.T@v);v=v/v.norm()*torch.median(torch.linalg.vector_norm(ds,dim=0))
   p=ctrldir/f'sham{j}_{side}.npz';np.savez(p,task_ids=task_ids,directions=v.numpy()[None,:].repeat(len(rows),axis=0));sham_files[(j,side)]=p
 manifest={'experiment':'focused_controls_v2','family':a.family,'canonical_seed_rule':'1000 + task_idx * 100','magnitudes':MAGS,'random_latents':c['random'],'random_selection':'uniform after excluding focused screening pool; no causal-outcome selection','shams':[{'id':i+1,'seed':s,'construction':'Gaussian; orthogonal to five target decoder vectors; median target norm; side-specific'} for i,s in enumerate(c['seeds'])],'directions':{'direct_side':c['direct'],'reverse_side':c['reverse']},'baseline_gate':str(gate)}
 (ctrldir/'EXPERIMENT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 common=['.venv/bin/python','tools/run_crosscoder_intervention.py','--checkpoint',c['checkpoint'],'--model-a-id',c['model_a'],'--model-b-id',c['model_b'],'--tokenizer-id',c['tokenizer'],'--layer','16','--intervention-mode','traditional','--token-scope','last_token','--generation-backend',c['backend'],'--input-jsonl',c['input'],'--max-new-tokens','512','--temperature','0.2','--top-p','0.95','--seed','1000','--dtype','nf4']
 if c['trust']:common.append('--trust-remote-code')
 def gen(name,fid,side,alpha,extra=()):
  out=outdir/f'bigcodebench__{name}_results.jsonl'
  if nlines(out)==c['n']:return
  cmd=[*common,'--target-side',side,'--feature-id',str(fid),'--alpha',str(alpha),f'--device-{side}','cuda:0','--output-jsonl',str(out),*extra]
  with (logdir/f'{name}.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  assert nlines(out)==c['n']
 for fid,sign in c['random'].items():
  for mag in MAGS:
   gen(f'random_f{fid}_direct_{sign*mag:+d}',fid,c['direct'],sign*mag)
   gen(f'random_f{fid}_reverse_{-sign*mag:+d}',fid,c['reverse'],-sign*mag)
 for j in range(1,4):
  for mag in MAGS:
   gen(f'sham{j}_direct_{-mag:+d}',0,c['direct'],-mag,('--per-example-direction-npz',str(sham_files[(j,c['direct'])]),'--preserve-per-example-direction-norm'))
   gen(f'sham{j}_reverse_{mag:+d}',0,c['reverse'],mag,('--per-example-direction-npz',str(sham_files[(j,c['reverse'])]),'--preserve-per-example-direction-norm'))
 (run/'CONTROLS_V2_GENERATIONS_COMPLETE').touch()
if __name__=='__main__':main()
