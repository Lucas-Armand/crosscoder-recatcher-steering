#!/usr/bin/env python3
"""Run BBASV v1 for one model family with canonical per-task seeds."""
from __future__ import annotations
import argparse,csv,json,os,subprocess
from pathlib import Path
import numpy as np
import torch

REPO=Path("/home/lucas/crosscoder-recatcher-steering")
MAGS=[1,2,3,4,5]

CFG={
 "dstk":{
  "label":"DSTK100","run":"runs/dstk100_bbasv_v1","gpu":"0","n":80,
  "input":"runs/eight_cell_top10_dstk_alpha3_semantic_v2/inputs/improvement.jsonl",
  "checkpoint":"runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt",
  "model_a":"deepseek-ai/deepseek-coder-6.7b-base","model_b":"JetBrains/deepseek-coder-6.7B-kexer",
  "tokenizer":"deepseek-ai/deepseek-coder-6.7b-base","trust":True,
  "direct_side":"a","reverse_side":"b",
  "targets":{3048:-1,13801:-1,7828:-1,15669:-1,13191:-1},
  "random":{16054:1,5022:1,12322:-1},"sham_sign":-1,"sham_seed":20260825,
  "alpha3_source":"runs/semantic_top10_dstk100_alpha3_v1"},
 "codellama":{
  "label":"CodeLlama","run":"runs/codellama_base_merged_bbasv_v1","gpu":"1","n":50,
  "input":"runs/eight_cell_top10_codellama_alpha3_semantic_v2/inputs/regression.jsonl",
  "checkpoint":"runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt",
  "model_a":"meta-llama/CodeLlama-7b-hf","model_b":"DevQuasar-5/coma-7B-v0.1",
  "tokenizer":"meta-llama/CodeLlama-7b-hf","trust":False,
  "direct_side":"b","reverse_side":"a",
  "targets":{13147:-1,12253:1,10570:-1,14359:1,2310:1},
  "random":{13879:1,2881:-1,2616:-1},"sham_sign":-1,"sham_seed":20260826,
  "alpha3_source":"runs/semantic_top10_codellama_alpha3_v1"}
}

def count_lines(p:Path)->int:
    return sum(1 for _ in p.open()) if p.exists() else -1

def canonical_seed_audit(inp:Path,n:int):
    rows=[json.loads(x) for x in inp.open()]
    assert len(rows)==n
    assert all("seed" in r for r in rows)
    assert all(int(r["seed"])==1000+int(r["task_idx"]) for r in rows)
    return rows

def make_sham(c,run,rows):
    state=torch.load(c["checkpoint"],map_location="cpu",weights_only=False)["model_state_dict"]
    task_ids=np.asarray([r["task_id"] for r in rows])
    for side in (c["direct_side"],c["reverse_side"]):
        ds=torch.stack([state[f"decoder_{side}.weight"][:,fid].float() for fid in c["targets"]],dim=1)
        q=torch.linalg.qr(ds,mode="reduced").Q
        g=torch.Generator().manual_seed(c["sham_seed"]+(0 if side=="a" else 100))
        v=torch.randn(ds.shape[0],generator=g);v=v-q@(q.T@v)
        target_norm=torch.median(torch.linalg.vector_norm(ds,dim=0))
        v=v/v.norm()*target_norm
        np.savez(run/"controls"/f"sham_{side}.npz",task_ids=task_ids,directions=v.numpy()[None,:].repeat(len(rows),axis=0))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--family",choices=CFG,required=True);a=ap.parse_args()
    os.chdir(REPO);c=CFG[a.family];run=Path(c["run"]);inp=Path(c["input"])
    for d in ("generations","logs","postprocessed","evaluations","controls","audit"): (run/d).mkdir(parents=True,exist_ok=True)
    rows=canonical_seed_audit(inp,c["n"]);make_sham(c,run,rows)
    manifest={
      "experiment":"BBASV","version":"v1","family":a.family,"label":c["label"],
      "generation":{"input":c["input"],"seed_rule":"row seed = 1000 + task_idx","temperature":0.2,"top_p":0.95,"max_new_tokens":512,"backend":"hf_generate","dtype":"nf4"},
      "intervention":{"mode":"traditional continuous","layer":16,"token_scope":"last_token","magnitudes":MAGS,"direct_side":c["direct_side"],"reverse_side":c["reverse_side"]},
      "targets":c["targets"],"random_latents":c["random"],
      "random_selection":{"seed":20260825+(0 if a.family=="dstk" else 1),"rule":"uniform feature ID after excluding every alpha3 candidate; no outcome-based selection"},
      "sham":{"seed":c["sham_seed"],"direct_sign":c["sham_sign"],"rule":"Gaussian direction orthogonal to span of five target decoders; median target norm; separately constructed per model side"},
      "reused_direct_alpha3":{"source":c["alpha3_source"],"features":list(c["targets"])},
      "analysis_plan":["official pass/fail","raw and extraction-v4 exact change","normalized edit distance","first divergence","rule-based semantic change taxonomy","target-error improvement","semantic precision","benefit/harm"]
    }
    (run/"EXPERIMENT_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    fields=["arm_type","feature_id","side","orientation","magnitude","alpha","status","source"]
    arm_rows=[]
    common=["--checkpoint",c["checkpoint"],"--model-a-id",c["model_a"],"--model-b-id",c["model_b"],"--tokenizer-id",c["tokenizer"]]
    if c["trust"]:common+=["--trust-remote-code"]
    def generate(kind,fid,side,orientation,mag,alpha,name,extra=()):
        out=run/"generations"/f"bigcodebench__{name}_results.jsonl"
        if count_lines(out)==c["n"]:
            arm_rows.append(dict(arm_type=kind,feature_id=fid,side=side,orientation=orientation,magnitude=mag,alpha=alpha,status="existing",source=str(out)));return
        cmd=[".venv/bin/python","tools/run_crosscoder_intervention.py",*common,
          "--target-side",side,"--layer","16","--feature-id",str(fid),"--alpha",str(alpha),
          "--intervention-mode","traditional","--token-scope","last_token","--generation-backend","hf_generate",
          "--input-jsonl",str(inp),"--output-jsonl",str(out),"--max-new-tokens","512","--temperature","0.2","--top-p","0.95","--seed","1000",
          f"--device-{side}","cuda:0","--dtype","nf4",*extra]
        with (run/"logs"/f"{name}.log").open("w") as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        assert count_lines(out)==c["n"]
        arm_rows.append(dict(arm_type=kind,feature_id=fid,side=side,orientation=orientation,magnitude=mag,alpha=alpha,status="generated",source=str(out)))
        with (run/"ARM_PROGRESS.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(arm_rows)
    # Reproduction gates.
    generate("baseline",0,c["direct_side"],"direct",0,0,"baseline_direct")
    generate("baseline",0,c["reverse_side"],"reverse",0,0,"baseline_reverse")
    # Targets. Direct alpha=3 is canonical and reused at analysis time; reverse alpha=3 is generated.
    for fid,sgn in c["targets"].items():
        for mag in MAGS:
            if mag!=3:generate("target",fid,c["direct_side"],"direct",mag,sgn*mag,f"target_f{fid}_direct_{'pos' if sgn>0 else 'neg'}{mag}")
            else:arm_rows.append(dict(arm_type="target",feature_id=fid,side=c["direct_side"],orientation="direct",magnitude=3,alpha=sgn*3,status="reused",source=f"{c['alpha3_source']}/generations/bigcodebench__f{fid}_{'pos' if sgn>0 else 'neg'}3_results.jsonl"))
            generate("target",fid,c["reverse_side"],"reverse",mag,-sgn*mag,f"target_f{fid}_reverse_{'pos' if -sgn>0 else 'neg'}{mag}")
    # Uniform random latent controls with preregistered sign; reverse uses opposite sign/model.
    for fid,sgn in c["random"].items():
        for mag in MAGS:
            generate("random_latent",fid,c["direct_side"],"direct",mag,sgn*mag,f"random_f{fid}_direct_{'pos' if sgn>0 else 'neg'}{mag}")
            generate("random_latent",fid,c["reverse_side"],"reverse",mag,-sgn*mag,f"random_f{fid}_reverse_{'pos' if -sgn>0 else 'neg'}{mag}")
    # One norm-controlled orthogonal sham, separately represented on each side.
    sgn=c["sham_sign"]
    for mag in MAGS:
        generate("orthogonal_sham",0,c["direct_side"],"direct",mag,sgn*mag,f"sham_direct_{'pos' if sgn>0 else 'neg'}{mag}",
          ("--per-example-direction-npz",str(run/"controls"/f"sham_{c['direct_side']}.npz"),"--preserve-per-example-direction-norm"))
        generate("orthogonal_sham",0,c["reverse_side"],"reverse",mag,-sgn*mag,f"sham_reverse_{'pos' if -sgn>0 else 'neg'}{mag}",
          ("--per-example-direction-npz",str(run/"controls"/f"sham_{c['reverse_side']}.npz"),"--preserve-per-example-direction-norm"))
    with (run/"ARM_MANIFEST.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(arm_rows)
    (run/"GENERATIONS_COMPLETE").touch()
    with (run/"logs"/"reprocess.log").open("w") as log:
        subprocess.run([".venv/bin/python","tools/reprocess_outputs_minimal.py","--raw-results-dir",str(run/"generations"),"--output-dir",str(run/"postprocessed")],stdout=log,stderr=subprocess.STDOUT,check=True)
    for sample in sorted((run/"postprocessed"/"samples_for_external_eval").glob("*_samples.jsonl")):
        stem=sample.name.replace("_samples.jsonl","");out=run/"evaluations"/f"{stem}_eval.json"
        if out.exists():continue
        with (run/"logs"/f"eval_{stem}.log").open("w") as log:
            subprocess.run(["/home/lucas/venvs/bigcodebench015/bin/python","tools/evaluate_bigcodebench_subset.py","--samples",str(sample),"--output",str(out),"--parallel","4"],stdout=log,stderr=subprocess.STDOUT,check=True)
    (run/"EVALUATION_COMPLETE").touch()

if __name__=="__main__":main()
