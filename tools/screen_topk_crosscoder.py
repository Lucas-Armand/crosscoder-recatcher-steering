#!/usr/bin/env python3
"""Screen DSTK100 latents for causal steering candidates."""
from __future__ import annotations

import argparse, csv, json, math
from pathlib import Path
import numpy as np
import torch

AGGS = ("max", "mean", "active_fraction", "early_max")

def auc_ap(y, score):
    """Tie-aware ROC-AUC and threshold-grouped average precision."""
    order=np.argsort(score,kind="mergesort")
    s=score[order]; yy=y[order]; npos=int(yy.sum()); nneg=len(yy)-npos
    rank_sum=0.0; i=0
    while i<len(s):
      j=i+1
      while j<len(s) and s[j]==s[i]: j+=1
      rank_sum += yy[i:j].sum() * ((i+1+j)/2.0)
      i=j
    auc=(rank_sum-npos*(npos+1)/2)/(npos*nneg)
    order=np.argsort(-score,kind="mergesort"); s=score[order]; yy=y[order]
    tp=0; seen=0; ap=0.0; recall_prev=0.0; i=0
    while i<len(s):
      j=i+1
      while j<len(s) and s[j]==s[i]: j+=1
      tp += int(yy[i:j].sum()); seen=j
      recall=tp/npos; precision=tp/seen
      ap += (recall-recall_prev)*precision; recall_prev=recall; i=j
    return float(auc),float(ap)

def args():
    p=argparse.ArgumentParser()
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--activation-root",type=Path,required=True)
    p.add_argument("--labels",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",default="cuda:0")
    p.add_argument("--permutations",type=int,default=200)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--model-a-label",default="deepseek_base")
    p.add_argument("--model-b-label",default="deepseek_finetuned")
    return p.parse_args()

def encode_pair(a,b,w,bias,k,device):
    x=torch.from_numpy(np.concatenate((a,b),axis=1)).float().to(device)
    with torch.inference_mode():
        dense=torch.relu(torch.nn.functional.linear(x,w,bias))
        val,idx=torch.topk(dense,k,dim=1,sorted=False)
        z=torch.zeros_like(dense).scatter_(1,idx,val)
        n=z.shape[0]; q=max(1,math.ceil(n*.25))
        return {
          "max":z.max(0).values.cpu().numpy(),
          "mean":z.mean(0).cpu().numpy(),
          "active_fraction":(z>0).float().mean(0).cpu().numpy(),
          "early_max":z[:q].max(0).values.cpu().numpy(),
        }

def main():
    a=args(); a.output.mkdir(parents=True,exist_ok=True)
    ck=torch.load(a.checkpoint,map_location="cpu",weights_only=False)
    cfg=ck["config"]; sd=ck["model_state_dict"]; k=int(cfg["top_k"])
    device=torch.device(a.device)
    w=sd["encoder.weight"].float().to(device); bias=sd["encoder.bias"].float().to(device)
    da=sd["decoder_a.weight"].float(); db=sd["decoder_b.weight"].float()
    na=torch.linalg.vector_norm(da,dim=0).numpy(); nb=torch.linalg.vector_norm(db,dim=0).numpy()
    ft_spec=nb/(na+nb+1e-12); nf=w.shape[0]
    manifest=json.loads((a.activation_root/"capture_manifest.json").read_text())
    label={}
    with a.labels.open(newline="") as f:
      for r in csv.DictReader(f):
        if int(r["generation_idx"])==0 and r["model"] in (a.model_a_label,a.model_b_label):
          label[(r["model"],r["benchmark"],r["task_id"])]=int(r["label"])
    rows=[]; skipped=[]
    for n,m in enumerate(manifest,1):
      pa=a.activation_root/m["benchmark"]/a.model_a_label/m["filename"]
      pb=a.activation_root/m["benchmark"]/a.model_b_label/m["filename"]
      try:
        xa=np.load(pa); xb=np.load(pb)
        if not np.array_equal(xa["input_ids"],xb["input_ids"]): raise ValueError("token IDs differ")
        agg=encode_pair(xa["layer_16"],xb["layer_16"],w,bias,k,device)
      except Exception as e:
        skipped.append({**m,"reason":str(e)}); continue
      key=(m["benchmark"],m["task_id"])
      try: lb=label[(a.model_a_label,*key)]; lf=label[(a.model_b_label,*key)]
      except KeyError: skipped.append({**m,"reason":"missing label"}); continue
      rows.append({"benchmark":m["benchmark"],"task_id":m["task_id"],"source_text":m["source_text"],"base_label":lb,"model_b_label_value":lf,"tokens":m["tokens"],"agg":agg})
      if n%100==0: print(f"encoded {n}/{len(manifest)}",flush=True)
    del w,bias; torch.cuda.empty_cache()
    grouped={}
    for r in rows: grouped.setdefault((r["benchmark"],r["task_id"]),{})[r["source_text"]]=r
    pairs=[]
    for key,g in grouped.items():
      if set(g)!={a.model_a_label,a.model_b_label}: skipped.append({"benchmark":key[0],"task_id":key[1],"reason":"missing source-text pair"}); continue
      pairs.append((key,g[a.model_a_label],g[a.model_b_label]))
    rng=np.random.default_rng(a.seed); out=[]
    for bench in sorted({x[0][0] for x in pairs}):
      bp=[x for x in pairs if x[0][0]==bench]
      for transition in ("regression","improvement"):
        if transition=="regression": pop=[x for x in bp if x[1]["base_label"]==0]; y=np.array([x[1]["model_b_label_value"] for x in pop])
        else: pop=[x for x in bp if x[1]["base_label"]==1]; y=np.array([1-x[1]["model_b_label_value"] for x in pop])
        if len(np.unique(y))<2: continue
        for stat in AGGS:
          xb=np.stack([x[1]["agg"][stat] for x in pop]); xf=np.stack([x[2]["agg"][stat] for x in pop]); X=xf-xb
          pos=y==1; neg=~pos; effect=X[pos].mean(0)-X[neg].mean(0)
          null=np.empty((a.permutations,nf),dtype=np.float32)
          for bi in range(a.permutations):
            yp=rng.permutation(y).astype(bool)
            null[bi]=X[yp].mean(0)-X[~yp].mean(0)
          null_sd=null.std(0,ddof=1)
          ev=np.divide(effect,null_sd,out=np.zeros_like(effect),where=null_sd>0)
          p_perm=(1+(np.abs(null)>=np.abs(effect)[None,:]).sum(0))/(a.permutations+1)
          for j in range(nf):
            col=X[:,j]; unique=np.unique(col).size
            auc,ap=auc_ap(y,col) if unique>1 else (.5,float(y.mean()))
            out.append({"benchmark":bench,"transition":transition,"aggregation":stat,"feature_id":j,"n":len(y),"positives":int(y.sum()),"prevalence":float(y.mean()),"roc_auc":auc,"pr_auc":ap,"pr_lift":ap/float(y.mean()),"effect":float(effect[j]),"permutation_null_sd":float(null_sd[j]),"effect_to_permutation_variability":float(ev[j]),"permutation_p_nominal":float(p_perm[j]),"positive_support":int((xf[pos,j]>0).sum()),"positive_delta_support":int((X[pos,j]>0).sum()),"control_support":int((xf[neg,j]>0).sum()),"decoder_model_a_norm":float(na[j]),"decoder_model_b_norm":float(nb[j]),"decoder_model_b_specificity":float(ft_spec[j]),"unique_delta_values":unique})
    fields=list(out[0]);
    with (a.output/"all_feature_statistics.csv").open("w",newline="") as f: wri=csv.DictWriter(f,fieldnames=fields); wri.writeheader(); wri.writerows(out)
    # Steering candidates: direction consistent with the transition, repeated support, early evidence, and model-B-side decoder.
    candidates=[]
    for transition in ("regression","improvement"):
      eligible=[r for r in out if r["transition"]==transition and r["aggregation"] in ("max","early_max") and r["effect"]>0 and r["positive_support"]>=max(3,math.ceil(.1*r["positives"])) and r["roc_auc"]>.55]
      eligible.sort(key=lambda r:(r["effect_to_permutation_variability"],r["pr_lift"],r["positive_delta_support"],r["decoder_model_b_specificity"]),reverse=True)
      seen=set()
      for r in eligible:
        if r["feature_id"] not in seen: candidates.append({**r,"candidate_rank":len(seen)+1}); seen.add(r["feature_id"])
        if len(seen)>=25: break
    cfields=["candidate_rank"]+[x for x in fields if x!="candidate_rank"]
    with (a.output/"top_feature_candidates.csv").open("w",newline="") as f: wri=csv.DictWriter(f,fieldnames=cfields); wri.writeheader(); wri.writerows(candidates)
    evidence=[]
    for c in candidates:
      bench=c["benchmark"]; transition=c["transition"]; stat=c["aggregation"]; fid=int(c["feature_id"])
      bp=[x for x in pairs if x[0][0]==bench]
      if transition=="regression": pop=[x for x in bp if x[1]["base_label"]==0 and x[1]["model_b_label_value"]==1]
      else: pop=[x for x in bp if x[1]["base_label"]==1 and x[1]["model_b_label_value"]==0]
      scored=[]
      for key,rb,rf in pop:
        vb=float(rb["agg"][stat][fid]); vf=float(rf["agg"][stat][fid])
        scored.append((vf-vb,key[1],vb,vf,rb["tokens"],rf["tokens"]))
      for rank,(delta,task,vb,vf,tb,tf) in enumerate(sorted(scored,reverse=True)[:10],1):
        evidence.append({"transition":transition,"candidate_rank":c["candidate_rank"],"benchmark":bench,"feature_id":fid,"aggregation":stat,"evidence_rank":rank,"task_id":task,"base_text_score":vb,"model_b_text_score":vf,"delta":delta,"base_text_tokens":tb,"model_b_text_tokens":tf})
    if evidence:
      with (a.output/"candidate_task_evidence.csv").open("w",newline="") as f: wri=csv.DictWriter(f,fieldnames=list(evidence[0])); wri.writeheader(); wri.writerows(evidence)
    summary={"checkpoint":str(a.checkpoint),"step":ck["step"],"top_k":k,"manifest_rows":len(manifest),"encoded_rows":len(rows),"paired_tasks":len(pairs),"permutations":a.permutations,"seed":a.seed,"model_a_label":a.model_a_label,"model_b_label":a.model_b_label,"skipped":skipped,"labels":"1=fail; regression positive=model A pass -> model B fail; improvement positive=model A fail -> model B pass","score":"model-B-source-text aggregate minus model-A-source-text aggregate","candidate_rule":"positive differential, ROC-AUC > .55, >= max(3,10% positive tasks) support; rank effect/permutation-null SD then PR lift/support/model-B decoder specificity"}
    (a.output/"run_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!="skipped"},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
