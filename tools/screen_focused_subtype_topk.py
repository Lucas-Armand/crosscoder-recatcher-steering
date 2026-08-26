#!/usr/bin/env python3
"""Focused subtype CrossCoder screen with association/paired x global/local cells."""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import torch

METRICS=("max","mean","active_fraction")

def prefix_len(a,b):
 n=min(len(a),len(b));i=0
 while i<n and a[i]==b[i]:i+=1
 return i

def summarize(z):
 return {"max":z.max(0).values.cpu().numpy().astype(np.float16),"mean":z.mean(0).cpu().numpy().astype(np.float16),"active_fraction":(z>0).float().mean(0).cpu().numpy().astype(np.float16)}

def encode(pa,pb,w,bias,k,device,frac):
 a=np.load(pa);b=np.load(pb)
 if not np.array_equal(a["input_ids"],b["input_ids"]):raise ValueError("unaligned token IDs")
 x=torch.from_numpy(np.concatenate([a["layer_16"],b["layer_16"]],1)).float().to(device)
 with torch.inference_mode():
  dense=torch.relu(torch.nn.functional.linear(x,w,bias));val,idx=torch.topk(dense,k,dim=1,sorted=False);z=torch.zeros_like(dense).scatter_(1,idx,val)
  n=len(z);center=min(n-1,max(0,round(frac*n)));radius=max(2,math.ceil(.10*n));local=z[max(0,center-radius):min(n,center+radius+1)]
  return {"global":summarize(z),"local":summarize(local)}

def rank_cell(Xs,active,y,perms,seed):
 rng=np.random.default_rng(seed);minimum=max(3,math.ceil(.10*int(y.sum())));variants=[]
 for metric,X in Xs.items():
  X=X.astype(np.float32);effect=X[y].mean(0)-X[~y].mean(0);null=np.empty((perms,X.shape[1]),np.float32)
  for p in range(perms):
   yp=rng.permutation(y);null[p]=X[yp].mean(0)-X[~yp].mean(0)
  sd=null.std(0,ddof=1);ev=np.divide(effect,sd,out=np.zeros_like(effect),where=sd>0);variants.append((metric,effect,sd,ev))
 support=active[y].sum(0);out=[]
 for j in range(variants[0][1].shape[0]):
  metric,effect,sd,ev=max(variants,key=lambda q:abs(float(q[3][j])))
  if support[j]<minimum:continue
  out.append({"feature_id":j,"orientation":"specialized_enriched" if effect[j]>0 else "base_enriched","summary":metric,"effect":float(effect[j]),"null_sd":float(sd[j]),"ev":float(ev[j]),"abs_ev":abs(float(ev[j])),"positive_support":int(support[j]),"minimum_support":minimum})
 return sorted(out,key=lambda r:r["abs_ev"],reverse=True)

def write(path,rs):
 fs=["rank","feature_id","orientation","summary","effect","null_sd","ev","abs_ev","positive_support","minimum_support"]
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fs);w.writeheader();w.writerows([{"rank":i+1,**r} for i,r in enumerate(rs)])

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--project",choices=["dstk","codellama"],required=True);ap.add_argument("--device",default="cuda:0");ap.add_argument("--permutations",type=int,default=200);ap.add_argument("--seed",type=int,default=42);a=ap.parse_args()
 if a.project=="dstk":
  ckpt=Path("runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt");root=Path("runs/same_text_activations/deepseek_base_finetuned_layer16_rms");ma,mb="deepseek_base","deepseek_finetuned";fa="bigcodebench__deepseek_base_repaired.jsonl";fb="bigcodebench__deepseek_finetuned_repaired.jsonl";out=Path("reports/focused_subtype_screening_dstk100_contamination_v1");transition="improvement";expected=(80,135)
  tax={r["task_id"]:r for r in csv.DictReader(open("reports/dstk100_transition_failure_analysis_v1/transition_failure_cases.csv"))};is_positive=lambda t:tax[t]["primary_failure_category"]=="generated_test_import_contamination" and t in semantic_tasks
  semantic_tasks={json.loads(x)["task_id"] for x in open("runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl")}
 else:
  ckpt=Path("runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt");root=Path("runs/same_text_activations/codellama_base_merged_layer16_rms");ma,mb="codellama_base","codellama_merged";fa="bigcodebench__codellama_base_repaired.jsonl";fb="bigcodebench__codellama_merged_repaired.jsonl";out=Path("reports/focused_subtype_screening_codellama_wrong_logic_v1");transition="regression";expected=(50,241)
  tax={r["task_id"]:r for r in csv.DictReader(open("reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv")) if r["benchmark"]=="bigcodebench"};is_positive=lambda t:tax[t]["primary_failure_category"]=="wrong_logic_or_other_runtime"
 out.mkdir(parents=True,exist_ok=True);device=torch.device(a.device);ck=torch.load(ckpt,map_location="cpu",weights_only=False);sd=ck["model_state_dict"];k=int(ck["config"]["top_k"]);w=sd["encoder.weight"].float().to(device);bias=sd["encoder.bias"].float().to(device)
 labels={}
 for r in csv.DictReader(open("reports/paper_v1_v4_evaluation_labels.csv")):
  if r["benchmark"]=="bigcodebench" and r["model"] in (ma,mb):labels[(r["model"],r["task_id"])]=int(r["label"])
 rr=Path("/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired");code={}
 for m,fn in ((ma,fa),(mb,fb)):
  for r in map(json.loads,open(rr/fn)):code[(m,r["task_id"])]=r.get("candidate_code_repaired") or r.get("extraction_generated_text") or r.get("raw_completion") or ""
 manifest=json.loads((root/"capture_manifest.json").read_text());idx={(m["task_id"],m["source_text"]):m for m in manifest if m["benchmark"]=="bigcodebench"}
 tasks=[]
 for t in sorted({t for m,t in labels if m==ma and (mb,t) in labels}):
  la,lb=labels[(ma,t)],labels[(mb,t)];tr="regression" if (la,lb)==(0,1) else "improvement" if (la,lb)==(1,0) else "other"
  if tr==transition:tasks.append(t)
 y=np.array([is_positive(t) for t in tasks],bool);assert (int(y.sum()),int((~y).sum()))==expected,(a.project,len(tasks),y.sum())
 spec={s:{q:[] for q in METRICS} for s in ("global","local")};base={s:{q:[] for q in METRICS} for s in ("global","local")};act_spec={s:[] for s in ("global","local")};act_pair={s:[] for s in ("global","local")}
 for ni,t in enumerate(tasks,1):
  ca,cb=code[(ma,t)],code[(mb,t)];cp=prefix_len(ca,cb);pair=[]
  for source,text in ((ma,ca),(mb,cb)):
   m=idx[(t,source)];pair.append(encode(root/"bigcodebench"/ma/m["filename"],root/"bigcodebench"/mb/m["filename"],w,bias,k,device,cp/max(1,len(text))))
  for scope in ("global","local"):
   for q in METRICS:base[scope][q].append(pair[0][scope][q]);spec[scope][q].append(pair[1][scope][q])
   act_spec[scope].append(pair[1][scope]["max"]>0);act_pair[scope].append(np.maximum(pair[0][scope]["max"],pair[1][scope]["max"])>0)
  if ni%50==0:print(a.project,ni,"/",len(tasks),flush=True)
 for z in (base,spec):
  for scope in z:
   for q in z[scope]:z[scope][q]=np.stack(z[scope][q])
 act_spec={s:np.stack(v) for s,v in act_spec.items()};act_pair={s:np.stack(v) for s,v in act_pair.items()};summary=[]
 for kind in ("association","paired"):
  for scope in ("global","local"):
   X={q:(spec[scope][q] if kind=="association" else spec[scope][q].astype(np.float32)-base[scope][q].astype(np.float32)) for q in METRICS};support_active=act_spec[scope] if kind=="association" else act_pair[scope];rs=rank_cell(X,support_active,y,a.permutations,a.seed);cell=f"{kind}_{scope}";write(out/f"{cell}_absolute.csv",rs)
   for ori in ("specialized_enriched","base_enriched"):write(out/f"{cell}_{ori}.csv",[r for r in rs if r["orientation"]==ori])
   summary.append({"cell":cell,"positives":int(y.sum()),"controls":int((~y).sum()),"top10":[r["feature_id"] for r in rs[:10]]})
 meta={"project":a.project,"transition":transition,"positive_subtype":"test_import_contamination" if a.project=="dstk" else "wrong_logic_or_other_runtime","positives":int(y.sum()),"controls_same_transition":int((~y).sum()),"metrics":METRICS,"association":"specialized-source-text aggregate: positives minus same-transition subtype controls","paired":"(specialized-source-text minus base-source-text) per task: positives minus same-transition subtype controls","local_window":"±10% around normalized first textual divergence in extraction-v4 candidate_code_repaired","permutations":a.permutations,"seed":a.seed,"support":"max(3,10% positives); specialized-text activation for association, either-source activation for paired","cells":summary}
 (out/"run_summary.json").write_text(json.dumps(meta,indent=2)+"\n");print(json.dumps(meta,indent=2))
if __name__=="__main__":main()
