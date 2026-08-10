#!/usr/bin/env python3
"""Temporal DSTK100 screening over extraction-v4 evaluated-code tokens."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import torch

METRICS=("max","q10_max","q25_max","q50_max","discounted_max","discounted_mean","first_horizon","future_exposure")

def auc_ap(y,score):
    order=np.argsort(score,kind="mergesort"); s=score[order]; yy=y[order]
    npos=int(yy.sum()); nneg=len(yy)-npos; rank_sum=0.; i=0
    while i<len(s):
        j=i+1
        while j<len(s) and s[j]==s[i]: j+=1
        rank_sum+=yy[i:j].sum()*((i+1+j)/2.); i=j
    auc=(rank_sum-npos*(npos+1)/2)/(npos*nneg)
    order=np.argsort(-score,kind="mergesort"); s=score[order]; yy=y[order]
    tp=seen=0; ap=recall_prev=0.; i=0
    while i<len(s):
        j=i+1
        while j<len(s) and s[j]==s[i]: j+=1
        tp+=int(yy[i:j].sum()); seen=j; recall=tp/npos
        ap+=(recall-recall_prev)*(tp/seen); recall_prev=recall; i=j
    return float(auc),float(ap)

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--activation-root",type=Path,required=True)
    p.add_argument("--labels",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",default="cuda:0")
    p.add_argument("--permutations",type=int,default=500)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--bins",type=int,default=20)
    p.add_argument("--profile-features",type=int,default=20)
    p.add_argument("--profiles-only",action="store_true")
    return p.parse_args()

def encode_metrics(a,b,w,bias,k,device):
    x=torch.from_numpy(np.concatenate((a,b),axis=1)).float().to(device)
    with torch.inference_mode():
        dense=torch.relu(torch.nn.functional.linear(x,w,bias))
        val,idx=torch.topk(dense,k,dim=1,sorted=False)
        z=torch.zeros_like(dense).scatter_(1,idx,val)
        n=z.shape[0]; rem=(n-torch.arange(n,device=device,dtype=z.dtype))/n
        active=z>0; any_active=active.any(0); first=active.float().argmax(0)
        def prefix(frac): return z[:max(1,math.ceil(n*frac))].max(0).values
        out={
            "max":z.max(0).values,
            "q10_max":prefix(.10),"q25_max":prefix(.25),"q50_max":prefix(.50),
            "discounted_max":(z*rem[:,None]).max(0).values,
            "discounted_mean":(z*rem[:,None]).sum(0)/rem.sum(),
            "first_horizon":torch.where(any_active,(n-first).to(z.dtype)/n,torch.zeros_like(first,dtype=z.dtype)),
            "future_exposure":(active.to(z.dtype)*rem[:,None]).sum(0)/rem.sum(),
        }
        return {q:v.cpu().numpy().astype(np.float16) for q,v in out.items()}

def encode_profile(a,b,w,bias,k,device,features,bins):
    x=torch.from_numpy(np.concatenate((a,b),axis=1)).float().to(device)
    f=torch.tensor(features,device=device,dtype=torch.long)
    with torch.inference_mode():
        dense=torch.relu(torch.nn.functional.linear(x,w,bias))
        val,idx=torch.topk(dense,k,dim=1,sorted=False)
        z=torch.zeros((x.shape[0],len(features)),device=device)
        for col,fid in enumerate(f): z[:,col]=torch.where(idx==fid,val,torch.zeros_like(val)).sum(1)
        edges=np.linspace(0,x.shape[0],bins+1).round().astype(int)
        mx=[]; af=[]
        for lo,hi in zip(edges[:-1],edges[1:]):
            if hi<=lo or lo>=x.shape[0]:
                mx.append(torch.zeros(len(features),device=device)); af.append(torch.zeros(len(features),device=device))
                continue
            part=z[lo:hi]
            mx.append(part.max(0).values); af.append((part>0).float().mean(0))
        return torch.stack(mx).cpu().numpy(),torch.stack(af).cpu().numpy()

def main():
    a=parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    ck=torch.load(a.checkpoint,map_location="cpu",weights_only=False); sd=ck["model_state_dict"]
    k=int(ck["config"]["top_k"]); dev=torch.device(a.device)
    w=sd["encoder.weight"].float().to(dev); bias=sd["encoder.bias"].float().to(dev)
    da=sd["decoder_a.weight"].float(); db=sd["decoder_b.weight"].float()
    na=torch.linalg.vector_norm(da,dim=0).numpy(); nb=torch.linalg.vector_norm(db,dim=0).numpy()
    spec=nb/(na+nb+1e-12); nf=w.shape[0]
    manifest=json.loads((a.activation_root/"capture_manifest.json").read_text())
    labels={}
    for r in csv.DictReader(a.labels.open()):
        if int(r["generation_idx"])==0 and r["model"] in ("deepseek_base","deepseek_finetuned"):
            labels[(r["model"],r["benchmark"],r["task_id"])]=int(r["label"])
    rows=[]; skipped=[]
    for ni,m in enumerate(manifest,1):
        pa=a.activation_root/m["benchmark"]/"deepseek_base"/m["filename"]
        pb=a.activation_root/m["benchmark"]/"deepseek_finetuned"/m["filename"]
        try:
            xa=np.load(pa); xb=np.load(pb)
            if not np.array_equal(xa["input_ids"],xb["input_ids"]): raise ValueError("token IDs differ")
            agg=encode_metrics(xa["layer_16"],xb["layer_16"],w,bias,k,dev)
            key=(m["benchmark"],m["task_id"])
            lb=labels[("deepseek_base",*key)]; lf=labels[("deepseek_finetuned",*key)]
        except Exception as e:
            skipped.append({**m,"reason":str(e)}); continue
        rows.append({"benchmark":m["benchmark"],"task_id":m["task_id"],"source_text":m["source_text"],"base_label":lb,"finetuned_label":lf,"tokens":m["tokens"],"agg":agg})
        if ni%100==0: print(f"encoded {ni}/{len(manifest)}",flush=True)
    grouped={}
    for r in rows: grouped.setdefault((r["benchmark"],r["task_id"]),{})[r["source_text"]]=r
    pairs=[(key,g["deepseek_base"],g["deepseek_finetuned"]) for key,g in grouped.items() if set(g)=={"deepseek_base","deepseek_finetuned"}]
    rng=np.random.default_rng(a.seed); output=[]
    stats_path=a.output/"all_temporal_feature_statistics.csv"
    candidates_path=a.output/"temporal_feature_candidates.csv"
    if a.profiles_only:
        if not stats_path.exists() or not candidates_path.exists():
            raise FileNotFoundError("--profiles-only requires existing statistics and candidates CSVs")
        output=list(csv.DictReader(stats_path.open()))
        candidates=list(csv.DictReader(candidates_path.open()))
    else:
        candidates=None
    for bench in (() if a.profiles_only else sorted({x[0][0] for x in pairs})):
        bp=[x for x in pairs if x[0][0]==bench]
        for transition in ("regression","improvement"):
            if transition=="regression":
                pop=[x for x in bp if x[1]["base_label"]==0]; y=np.array([x[1]["finetuned_label"] for x in pop],dtype=np.int8)
            else:
                pop=[x for x in bp if x[1]["base_label"]==1]; y=np.array([1-x[1]["finetuned_label"] for x in pop],dtype=np.int8)
            if len(np.unique(y))<2: continue
            perms=np.stack([rng.permutation(y).astype(bool) for _ in range(a.permutations)])
            perm_max=np.zeros(a.permutations,dtype=np.float32); pending=[]
            for metric in METRICS:
                xb=np.stack([x[1]["agg"][metric] for x in pop]).astype(np.float32)
                xf=np.stack([x[2]["agg"][metric] for x in pop]).astype(np.float32)
                X=xf-xb; pos=y==1; neg=~pos; effect=X[pos].mean(0)-X[neg].mean(0)
                null=np.empty((a.permutations,nf),dtype=np.float32)
                for pi,yp in enumerate(perms): null[pi]=X[yp].mean(0)-X[~yp].mean(0)
                nsd=null.std(0,ddof=1); stat=np.divide(effect,nsd,out=np.zeros_like(effect),where=nsd>0)
                nullstat=np.divide(null,nsd[None,:],out=np.zeros_like(null),where=nsd[None,:]>0)
                perm_max=np.maximum(perm_max,np.abs(nullstat).max(1))
                pnom=(1+(np.abs(null)>=np.abs(effect)[None,:]).sum(0))/(a.permutations+1)
                for j in range(nf):
                    col=X[:,j]; unique=np.unique(col).size
                    auc,ap=auc_ap(y,col) if unique>1 else (.5,float(y.mean()))
                    pending.append({"benchmark":bench,"transition":transition,"metric":metric,"feature_id":j,"n":len(y),"positives":int(y.sum()),"prevalence":float(y.mean()),"roc_auc":auc,"pr_auc":ap,"pr_lift":ap/float(y.mean()),"effect":float(effect[j]),"null_sd":float(nsd[j]),"effect_to_null_sd":float(stat[j]),"permutation_p_nominal":float(pnom[j]),"positive_support":int((xf[pos,j]>0).sum()),"positive_delta_support":int((X[pos,j]>0).sum()),"control_support":int((xf[neg,j]>0).sum()),"decoder_finetuned_specificity":float(spec[j]),"unique_delta_values":unique})
                del null,nullstat
            for r in pending:
                r["permutation_p_maxT"]=float((1+(perm_max>=abs(r["effect_to_null_sd"])).sum())/(a.permutations+1))
            output.extend(pending)
    fields=list(output[0])
    if not a.profiles_only:
      with stats_path.open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=fields); wr.writeheader(); wr.writerows(output)
    preferred={"discounted_max","first_horizon","q10_max","q25_max","future_exposure"}
    if candidates is None: candidates=[]
    for bench in (() if a.profiles_only else sorted({r["benchmark"] for r in output})):
      for transition in ("regression","improvement"):
        eligible=[r for r in output if r["benchmark"]==bench and r["transition"]==transition and r["metric"] in preferred and r["effect"]>0 and r["roc_auc"]>.55 and r["positive_support"]>=max(3,math.ceil(.1*r["positives"]))]
        eligible.sort(key=lambda r:(-r["permutation_p_maxT"],r["effect_to_null_sd"],r["pr_lift"],r["positive_delta_support"]),reverse=True)
        seen=set()
        for r in eligible:
            if r["feature_id"] in seen: continue
            seen.add(r["feature_id"]); candidates.append({**r,"candidate_rank":len(seen)})
            if len(seen)>=a.profile_features: break
    cfields=["candidate_rank"]+[x for x in fields if x!="candidate_rank"]
    if not a.profiles_only:
      with candidates_path.open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=cfields); wr.writeheader(); wr.writerows(candidates)
    selected=sorted({int(r["feature_id"]) for r in candidates}); profile_rows=[]
    cache={}
    for ni,m in enumerate(manifest,1):
        pa=a.activation_root/m["benchmark"]/"deepseek_base"/m["filename"]; pb=a.activation_root/m["benchmark"]/"deepseek_finetuned"/m["filename"]
        try:
            xa=np.load(pa); xb=np.load(pb); mx,af=encode_profile(xa["layer_16"],xb["layer_16"],w,bias,k,dev,selected,a.bins)
            cache[(m["benchmark"],m["task_id"],m["source_text"])]=(mx,af)
        except Exception: continue
        if ni%200==0: print(f"profiled {ni}/{len(manifest)}",flush=True)
    for c in candidates:
        bench=c["benchmark"]; tr=c["transition"]; fid=int(c["feature_id"]); fi=selected.index(fid)
        bp=[x for x in pairs if x[0][0]==bench]
        if tr=="regression": pop=[x for x in bp if x[1]["base_label"]==0]; y=np.array([x[1]["finetuned_label"] for x in pop],dtype=bool)
        else: pop=[x for x in bp if x[1]["base_label"]==1]; y=np.array([1-x[1]["finetuned_label"] for x in pop],dtype=bool)
        for bi in range(a.bins):
            bm=np.array([cache[(x[0][0],x[0][1],"deepseek_base")][0][bi,fi] for x in pop]); fm=np.array([cache[(x[0][0],x[0][1],"deepseek_finetuned")][0][bi,fi] for x in pop]); d=fm-bm
            profile_rows.append({"benchmark":bench,"transition":tr,"feature_id":fid,"candidate_rank":c["candidate_rank"],"bin":bi,"percent_start":100*bi/a.bins,"percent_end":100*(bi+1)/a.bins,"positive_base_mean":float(bm[y].mean()),"positive_finetuned_mean":float(fm[y].mean()),"positive_delta_mean":float(d[y].mean()),"control_delta_mean":float(d[~y].mean()),"contrast":float(d[y].mean()-d[~y].mean()),"positive_delta_support":int((d[y]>0).sum())})
    if profile_rows:
        with (a.output/"candidate_temporal_profiles.csv").open("w",newline="") as f:
            wr=csv.DictWriter(f,fieldnames=list(profile_rows[0])); wr.writeheader(); wr.writerows(profile_rows)
    summary={"checkpoint":str(a.checkpoint),"step":ck["step"],"top_k":k,"mask":"extraction-v4 candidate_code_repaired evaluated tokens; prompt/padding excluded; non-finite pairs excluded","metrics":METRICS,"bins":a.bins,"permutations":a.permutations,"seed":a.seed,"encoded_rows":len(rows),"paired_tasks":len(pairs),"skipped":skipped,"maxT_family":"within benchmark x transition across all features and temporal metrics"}
    (a.output/"run_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({k:v for k,v in summary.items() if k!="skipped"},indent=2))
if __name__=="__main__": main()
