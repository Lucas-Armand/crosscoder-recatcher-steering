#!/usr/bin/env python3
"""Rank DSTK100 features by pre-boundary causal attribution.

For each contaminated base completion, find the first generated unit-test/import
boundary, backpropagate the observed-token versus EOS logit margin to layer 16,
and project that gradient onto naturally active TopK-100 CrossCoder features.
Positive scores predict that suppressing the feature reduces the unwanted margin.
This is a first-order screening proxy, not a causal intervention result.
"""
from __future__ import annotations
import argparse, csv, json, math, re, time
from pathlib import Path
from typing import Any
import numpy as np
import torch
from transformers import BitsAndBytesConfig, AutoModelForCausalLM, PreTrainedTokenizerFast

BOUNDARY_PATTERNS=(
 r"(?im)^\s*#\s*(?:tests?(?:/|_|\b)|test[_/])",
 r"(?im)^\s*(?:from|import)\s+(?:unittest|pytest)\b",
 r"(?im)^\s*from\s+(?:task|task_func|task_[A-Za-z0-9_]*)\s+import\b",
 r"(?im)^\s*class\s+Test[A-Za-z0-9_]*\b",
)
def parse_args():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--checkpoint",type=Path,required=True); p.add_argument("--input-jsonl",type=Path,required=True)
 p.add_argument("--activation-root",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True)
 p.add_argument("--model-id",default="deepseek-ai/deepseek-coder-6.7b-base"); p.add_argument("--layer",type=int,default=16)
 p.add_argument("--top-k",type=int,default=100); p.add_argument("--model-device",default="cuda:0"); p.add_argument("--crosscoder-device",default="cuda:1")
 p.add_argument("--max-tasks",type=int); p.add_argument("--prepare-only",action="store_true"); p.add_argument("--trust-remote-code",action="store_true")
 return p.parse_args()
def read_jsonl(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def get_layers(model):
 for pn,cn in (("model","layers"),("transformer","h"),("gpt_neox","layers")):
  parent=getattr(model,pn,None); layers=getattr(parent,cn,None) if parent is not None else None
  if layers is not None:return layers
 raise AttributeError("Could not locate transformer layers")
def find_boundary(code,minimum):
 found=[]
 for pattern in BOUNDARY_PATTERNS:
  m=re.search(pattern,code[minimum:])
  if m:found.append((minimum+m.start(),m.group(0)))
 return min(found,default=None,key=lambda x:x[0])
def tokenizer_for(mid,trust):
 return PreTrainedTokenizerFast.from_pretrained(mid,trust_remote_code=trust,bos_token="<｜begin▁of▁sentence｜>",eos_token="<｜end▁of▁sentence｜>",pad_token="<｜end▁of▁sentence｜>")
def task_index(root):
 out={}
 for r in json.loads((root/"capture_manifest.json").read_text()):
  if r["benchmark"]=="bigcodebench" and r["source_text"]=="deepseek_base":
   out[r["task_id"]]=(root/"bigcodebench"/"deepseek_base"/r["filename"],root/"bigcodebench"/"deepseek_finetuned"/r["filename"])
 return out
def prepare(rows,tok,paths):
 prepared=[]; skipped=[]
 for row in rows:
  tid=row["task_id"]; code=row["candidate_code_repaired"]; prompt=row["prompt"].rstrip()+"\n"
  start=len(prompt) if code.startswith(prompt) else max(0,code.find(row["raw_completion"]))
  boundary=find_boundary(code,start)
  if boundary is None: skipped.append({"task_id":tid,"reason":"no_boundary"}); continue
  bchar,btext=boundary; enc=tok(code,add_special_tokens=False,return_offsets_mapping=True)
  ids=np.asarray(enc["input_ids"],dtype=np.int64); offsets=np.asarray(enc["offset_mapping"],dtype=np.int64)
  evaluated=np.flatnonzero((offsets[:,1]>start)&(offsets[:,0]<len(code))); bads=np.flatnonzero(offsets[:,0]>=bchar)
  if not len(evaluated) or not len(bads): skipped.append({"task_id":tid,"reason":"empty_evaluated_or_bad"}); continue
  bad=int(bads[0]); pre_n=int(np.searchsorted(evaluated,bad,side="left"))
  if bad<=0 or pre_n<=0: skipped.append({"task_id":tid,"reason":"empty_prefix"}); continue
  pa,pb=paths[tid]; za=np.load(pa); zb=np.load(pb); saved=za["input_ids"]
  if not np.array_equal(saved,zb["input_ids"]): raise ValueError(f"same-text mismatch {tid}")
  if not np.array_equal(ids[evaluated],saved): raise ValueError(f"capture/code mismatch {tid}: {len(evaluated)} vs {len(saved)}")
  prepared.append(dict(task_id=tid,boundary_char=bchar,boundary_text=btext,boundary_percent=100*(bchar-start)/max(1,len(code)-start),bad_token_id=int(ids[bad]),bad_token_text=tok.decode([int(ids[bad])]),prefix_ids=ids[:bad],evaluated_global_positions=evaluated[:pre_n],pre_eval_count=pre_n,path_a=str(pa),path_b=str(pb)))
 return prepared,skipped
def write_csv(path,rows):
 if not rows:return
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def main():
 a=parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True); rows=read_jsonl(a.input_jsonl)
 if a.max_tasks is not None:rows=rows[:a.max_tasks]
 tok=tokenizer_for(a.model_id,a.trust_remote_code); paths=task_index(a.activation_root)
 missing=[r["task_id"] for r in rows if r["task_id"] not in paths]
 if missing:raise KeyError(f"missing captures {missing[:10]}")
 prepared,skipped=prepare(rows,tok,paths)
 boundary_rows=[{k:v for k,v in r.items() if k not in ("prefix_ids","evaluated_global_positions","path_a","path_b")} for r in prepared]
 write_csv(a.output_dir/"boundary_manifest.csv",boundary_rows); (a.output_dir/"skipped.json").write_text(json.dumps(skipped,indent=2)+"\n")
 if a.prepare_only:print(json.dumps({"prepared":len(prepared),"skipped":len(skipped)},indent=2)); return
 ck=torch.load(a.checkpoint,map_location="cpu",weights_only=False); state=ck["model_state_dict"]
 ew=state["encoder.weight"].float().to(a.crosscoder_device); eb=state["encoder.bias"].float().to(a.crosscoder_device); decoder=state["decoder_a.weight"].float().to(a.model_device); latent=ew.shape[0]
 quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_compute_dtype=torch.float16,bnb_4bit_use_double_quant=True,bnb_4bit_quant_type="nf4")
 model=AutoModelForCausalLM.from_pretrained(a.model_id,trust_remote_code=a.trust_remote_code,quantization_config=quant,device_map={"":a.model_device},low_cpu_mem_usage=True,attn_implementation="eager").eval()
 for p in model.parameters():p.requires_grad_(False)
 layers=get_layers(model); n=len(prepared)
 sums=np.zeros((n,latent),np.float32); maxs=np.zeros((n,latent),np.float32); maxabs=np.zeros((n,latent),np.float32); amax=np.zeros((n,latent),np.float32); counts=np.zeros((n,latent),np.uint16); first=np.full((n,latent),-1,np.int16); task_rows=[]; started=time.time()
 for ti,item in enumerate(prepared):
  aa=np.load(item["path_a"])["layer_16"][:item["pre_eval_count"]]; ab=np.load(item["path_b"])["layer_16"][:item["pre_eval_count"]]
  pair=torch.from_numpy(np.concatenate([aa,ab],1)).to(a.crosscoder_device,dtype=torch.float32)
  with torch.no_grad(): dense=torch.relu(torch.nn.functional.linear(pair,ew,eb)); values,indices=torch.topk(dense,k=a.top_k,dim=1); values=values.cpu(); indices=indices.cpu()
  del dense,pair; captured={}
  def hook(_m,_i,out):
   h=out[0] if isinstance(out,tuple) else out; leaf=h.detach().requires_grad_(True); captured["h"]=leaf
   return (leaf,*out[1:]) if isinstance(out,tuple) else leaf
  handle=layers[a.layer].register_forward_hook(hook); ids=torch.as_tensor(item["prefix_ids"],device=a.model_device).unsqueeze(0)
  try:
   out=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,return_dict=True); logits=out.logits[0,-1].float(); margin=logits[item["bad_token_id"]]-logits[tok.eos_token_id]; margin.backward(); grad=captured["h"].grad[0]
  finally:handle.remove()
  pos=torch.as_tensor(item["evaluated_global_positions"],device=a.model_device,dtype=torch.long); im=indices.to(a.model_device); vm=values.to(a.model_device)
  assert int(pos.min()) >= 0 and int(pos.max()) < grad.shape[0]
  assert int(im.min()) >= 0 and int(im.max()) < decoder.shape[1]
  ge=grad.index_select(0,pos); torch.cuda.synchronize(); local=torch.empty_like(vm,dtype=torch.float32)
  for t in range(im.shape[0]):local[t]=vm[t].float()*torch.mv(decoder.index_select(1,im[t]).T,ge[t].float())
  ic=indices.cpu().numpy(); vc=values.cpu().numpy(); sc=local.detach().cpu().numpy()
  for t in range(ic.shape[0]):
   jj=ic[t]; np.add.at(sums[ti],jj,sc[t]); np.maximum.at(maxs[ti],jj,sc[t]); np.maximum.at(maxabs[ti],jj,np.abs(sc[t])); np.maximum.at(amax[ti],jj,vc[t]); np.add.at(counts[ti],jj,1); unset=first[ti,jj]<0; first[ti,jj[unset]]=t
  top=np.argsort(sums[ti])[-20:][::-1]; task_rows.append(dict(task_id=item["task_id"],boundary_percent=item["boundary_percent"],boundary_text=item["boundary_text"].replace("\n","\\n"),bad_token_text=item["bad_token_text"].replace("\n","\\n"),pre_boundary_tokens=item["pre_eval_count"],logit_margin_bad_minus_eos=float(margin.detach().cpu()),top_features=";".join(f"{int(j)}:{sums[ti,j]:.6g}" for j in top)))
  del out,logits,margin,grad,ge,local,values,indices; torch.cuda.empty_cache(); print(json.dumps({"task":ti+1,"total":n,"task_id":item["task_id"],"seconds":round(time.time()-started,1)}),flush=True)
 denom=np.sum(np.abs(sums),1,keepdims=True); norm=np.divide(sums,denom,out=np.zeros_like(sums),where=denom>0); support=(counts>0).sum(0); positives=(sums>0).sum(0); mean_raw=sums.mean(0); mean_norm=norm.mean(0); sd=norm.std(0,ddof=1) if n>1 else np.zeros(latent); ev=np.divide(mean_norm,sd,out=np.zeros_like(mean_norm),where=sd>0); sign=np.divide(positives,support,out=np.zeros(latent,dtype=np.float64),where=support>0); min_support=max(3,math.ceil(.1*n)); eligible=np.flatnonzero(support>=min_support); order=sorted(eligible.tolist(),key=lambda j:(mean_norm[j],ev[j],sign[j],support[j]),reverse=True)
 ranking=[]
 for rank,j in enumerate(order,1):ranking.append(dict(rank=rank,feature_id=j,mean_task_normalized_attribution=float(mean_norm[j]),attribution_to_task_sd=float(ev[j]),mean_raw_attribution=float(mean_raw[j]),support_tasks=int(support[j]),positive_attribution_tasks=int(positives[j]),positive_sign_fraction=float(sign[j]),mean_active_tokens=float(counts[:,j].mean()),mean_max_activation=float(amax[:,j].mean())))
 write_csv(a.output_dir/"feature_ranking.csv",ranking); write_csv(a.output_dir/"task_summary.csv",task_rows)
 np.savez_compressed(a.output_dir/"task_feature_attributions.npz",task_ids=np.asarray([x["task_id"] for x in prepared]),sum_scores=sums,normalized_scores=norm,max_scores=maxs,max_abs_scores=maxabs,activation_max=amax,active_counts=counts,first_positions=first)
 rankmap={r["feature_id"]:r["rank"] for r in ranking}; known={str(j):dict(rank=rankmap.get(j),support=int(support[j]),mean_task_normalized_attribution=float(mean_norm[j]),attribution_to_task_sd=float(ev[j]),positive_sign_fraction=float(sign[j])) for j in (6404,12883,9537)}
 summary=dict(schema_version=1,method="first_order_pre_boundary_topk_feature_attribution",objective="observed_first_contamination_token_logit_minus_eos_logit",interpretation="positive attribution predicts that feature suppression lowers the unwanted margin",tasks_requested=len(rows),tasks_analyzed=n,tasks_skipped=len(skipped),top_k=a.top_k,minimum_support=min_support,known_features=known,seconds=time.time()-started,limitations=["first-order approximation, not an intervention result","rule-based contamination boundary","single bad-token-vs-EOS objective","selection cohort is exploratory and not held out"])
 (a.output_dir/"run_summary.json").write_text(json.dumps(summary,indent=2)+"\n"); print(json.dumps(summary,indent=2),flush=True)
if __name__=="__main__":main()
