#!/usr/bin/env python3
"""Capture strictly token-aligned, RMS-normalized residual pairs for CrossCoder training."""
from __future__ import annotations

import argparse, json, re, time
from pathlib import Path
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

def read(path): return [json.loads(x) for x in path.read_text().splitlines() if x]
def safe_task(task_id): return re.sub(r"[^A-Za-z0-9]+", "_", task_id).strip("_")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True)
    p.add_argument("--model-a-id",required=True); p.add_argument("--model-b-id",required=True)
    p.add_argument("--model-a-label",required=True); p.add_argument("--model-b-label",required=True)
    p.add_argument("--benchmarks",nargs="+",default=["humanevalplus","bigcodebench"])
    p.add_argument("--layer",type=int,default=16); p.add_argument("--device-a",default="cuda:0"); p.add_argument("--device-b",default="cuda:1")
    p.add_argument("--max-examples",type=int); p.add_argument("--trust-remote-code",action="store_true")
    p.add_argument("--native-special-tokens",action="store_true",help="Use each checkpoint native special-token configuration; default preserves the historical DeepSeek profile.")
    a=p.parse_args(); a.output_root.mkdir(parents=True,exist_ok=True)
    tok_kw=dict(use_fast=True,local_files_only=True,trust_remote_code=a.trust_remote_code)
    if not a.native_special_tokens:
      tok_kw.update(bos_token="<｜begin▁of▁sentence｜>",eos_token="<｜end▁of▁sentence｜>",pad_token="<｜end▁of▁sentence｜>")
    ta=AutoTokenizer.from_pretrained(a.model_a_id,**tok_kw); tb=AutoTokenizer.from_pretrained(a.model_b_id,**tok_kw)
    common=dict(torch_dtype=torch.float16,local_files_only=True,trust_remote_code=a.trust_remote_code,attn_implementation="eager")
    ma=AutoModelForCausalLM.from_pretrained(a.model_a_id,**common).to(a.device_a).eval(); mb=AutoModelForCausalLM.from_pretrained(a.model_b_id,**common).to(a.device_b).eval()
    manifest=[]; count=0; started=time.time()
    for benchmark in a.benchmarks:
      for source_idx,source in enumerate((a.model_a_label,a.model_b_label)):
        path=a.results_dir/f"{benchmark}__{source}_repaired.jsonl"
        for row in read(path):
          if a.max_examples is not None and count>=a.max_examples: break
          code=row["candidate_code_repaired"]; prompt=row["prompt"].rstrip()+"\n"; start=len(prompt) if code.startswith(prompt) else 0
          ea=ta(code,return_tensors="pt",return_offsets_mapping=True,add_special_tokens=False); eb=tb(code,return_tensors="pt",add_special_tokens=False)
          if not torch.equal(ea["input_ids"],eb["input_ids"]): raise ValueError(f"token mismatch {source}/{row['task_id']}")
          offsets=ea["offset_mapping"][0].numpy(); mask_np=(offsets[:,1]>start)&(offsets[:,0]<len(code)); mask=torch.from_numpy(mask_np)
          ids=ea["input_ids"]; att=ea["attention_mask"]
          with torch.inference_mode():
            oa=ma(input_ids=ids.to(a.device_a),attention_mask=att.to(a.device_a),output_hidden_states=True,use_cache=False,return_dict=True)
            ha=oa.hidden_states[a.layer+1][0,mask].float(); del oa
            ob=mb(input_ids=ids.to(a.device_b),attention_mask=att.to(a.device_b),output_hidden_states=True,use_cache=False,return_dict=True)
            hb=ob.hidden_states[a.layer+1][0,mask].float(); del ob
            valid=(torch.isfinite(ha).all(1).cpu() & torch.isfinite(hb).all(1).cpu())
            ha=ha[valid.to(a.device_a)]; hb=hb[valid.to(a.device_b)]
            ha=ha/torch.sqrt(torch.mean(ha**2,dim=-1,keepdim=True)+1e-6); hb=hb/torch.sqrt(torch.mean(hb**2,dim=-1,keepdim=True)+1e-6)
          if not len(ha): continue
          task_idx=int(row["task_idx"]); stem=f"same_text__{benchmark}__task_{task_idx:04d}__gen_{source_idx:02d}__{safe_task(row['task_id'])}"
          payload=dict(input_ids=ids[0,mask][valid].numpy(),layer_16_a=ha.cpu().half().numpy(),layer_16_b=hb.cpu().half().numpy())
          for label,key in ((a.model_a_label,"layer_16_a"),(a.model_b_label,"layer_16_b")):
            out=a.output_root/benchmark/label/f"{stem}.npz"; out.parent.mkdir(parents=True,exist_ok=True)
            np.savez(out,input_ids=payload["input_ids"],layer_16=payload[key])
          manifest.append(dict(benchmark=benchmark,task_id=row["task_id"],task_idx=task_idx,source_text=source,tokens=len(ha),filename=stem+".npz",rms_normalized=True))
          count+=1
          if count%25==0:
            (a.output_root/"capture_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
            print(json.dumps({"examples":count,"tokens":sum(x["tokens"] for x in manifest),"seconds":time.time()-started}),flush=True)
        if a.max_examples is not None and count>=a.max_examples: break
      if a.max_examples is not None and count>=a.max_examples: break
    (a.output_root/"capture_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"examples":count,"tokens":sum(x["tokens"] for x in manifest),"seconds":time.time()-started},indent=2))
if __name__=="__main__": main()
