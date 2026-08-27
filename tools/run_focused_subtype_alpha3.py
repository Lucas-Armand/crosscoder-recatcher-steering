#!/usr/bin/env python3
"""Canonical error-focused alpha=3 sweep with an exact baseline gate."""
from __future__ import annotations
import argparse,csv,json,os,subprocess
from pathlib import Path

REPO=Path("/home/lucas/crosscoder-recatcher-steering")
RAW=REPO/"external_outputs/reprocessed/results_repaired"
CFG={
 "dstk":{
  "ranking":"reports/focused_subtype_screening_dstk100_contamination_v1",
  "run":"runs/focused_subtype_dstk100_alpha3_canonical_v1","n":80,
  "source":"bigcodebench__deepseek_base_repaired.jsonl","side":"a",
  "checkpoint":"runs/crosscoder_deepseek_base_finetuned_layer16_same_text_topk100_v1/final.pt",
  "model_a":"deepseek-ai/deepseek-coder-6.7b-base","model_b":"JetBrains/deepseek-coder-6.7B-kexer",
  "tokenizer":"deepseek-ai/deepseek-coder-6.7b-base","trust":True,"backend":"paired_cached","minimum_exact":80,
 },
 "codellama":{
  "ranking":"reports/focused_subtype_screening_codellama_wrong_logic_v1",
  "run":"runs/focused_subtype_codellama_alpha3_canonical_v1","n":50,
  "source":"bigcodebench__codellama_merged_repaired.jsonl","side":"b",
  "checkpoint":"runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt",
  "model_a":"meta-llama/CodeLlama-7b-hf","model_b":"DevQuasar-5/coma-7B-v0.1",
  "tokenizer":"meta-llama/CodeLlama-7b-hf","trust":False,"backend":"hf_generate","minimum_exact":50,
 }
}

CODELLAMA_ORIGINAL_NONREPRODUCED={"BigCodeBench/115","BigCodeBench/423","BigCodeBench/841","BigCodeBench/858"}

def rows_for(project):
 if project=="dstk":
  source="runs/dstk100_continuous_f6404_f10168_f13801_v1/input.jsonl"
 else:
  source="runs/codellama_bm_wrong_logic_50_alpha0_canonical_v1/input.jsonl"
 previous={r["task_id"]:r for r in map(json.loads,open("runs/codellama_bm_wrong_logic_50_alpha0_canonical_v1/generations/alpha0.jsonl"))} if project=="codellama" else {}
 c=CFG[project];out=[]
 for r in map(json.loads,open(source)):
  q={k:r[k] for k in ("benchmark","task_id","task_idx","entry_point","prompt")}
  raw=r.get("raw_completion")
  if raw is None:
   raw=previous[r["task_id"]]["completion"]
  q["raw_completion"]=raw
  q["original_prompt"]=q["prompt"];q["seed"]=1000+100*int(q["task_idx"]);out.append(q)
 out.sort(key=lambda r:int(r["task_idx"]))
 assert len(out)==c["n"],(project,len(out))
 return out

def candidates(project):
 c=CFG[project];best={}
 for p in Path(c["ranking"]).glob("*_absolute.csv"):
  cell=p.name.replace("_absolute.csv","")
  for r in list(csv.DictReader(p.open()))[:10]:
   fid=int(r["feature_id"]);score=float(r["abs_ev"])
   x={"feature_id":fid,"orientation":r["orientation"],"summary":r["summary"],"ev":float(r["ev"]),"abs_ev":score,"source_cells":[]}
   if fid not in best or score>best[fid]["abs_ev"]:
    old=best.get(fid,{}).get("source_cells",[]);x["source_cells"]=old;best[fid]=x
   best[fid]["source_cells"].append(cell)
 expected=35 if project=="dstk" else 32
 assert len(best)==expected,(project,len(best))
 for x in best.values():
  specialized=x["orientation"]=="specialized_enriched"
  x["alpha"]=(3 if specialized else -3) if project=="dstk" else (-3 if specialized else 3)
 return sorted(best.values(),key=lambda x:(-x["abs_ev"],x["feature_id"]))

def count(p):return sum(1 for _ in p.open()) if p.exists() else -1

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--project",choices=CFG,required=True);a=ap.parse_args()
 os.chdir(REPO);c=CFG[a.project];run=Path(c["run"])
 for d in ("generations","logs","postprocessed","evaluations","audit"): (run/d).mkdir(parents=True,exist_ok=True)
 rows=rows_for(a.project);inp=run/"input.jsonl"
 inp.write_text("".join(json.dumps(r)+"\n" for r in rows))
 arms=candidates(a.project)
 manifest={"experiment":"focused_subtype_alpha3","version":"canonical_v1","project":a.project,
  "cohort":{"n":c["n"],"deepseek":"80 contamination improvements only" if a.project=="dstk" else None,"codellama":"50 wrong-logic regressions only; CodeLlama improvements excluded" if a.project=="codellama" else None},
  "generation":{"seed_rule":"1000 + task_idx * 100","temperature":0.2,"top_p":0.95,"max_new_tokens":512,"dtype":"nf4","backend":c["backend"]},
  "intervention":{"mode":"traditional continuous","token_scope":"last_token","layer":16,"magnitude":3},
  "candidate_count":len(arms),"candidates":arms,
  "analysis_gate":"DeepSeek: original byte-exact tasks. CodeLlama: 46 original-v4-exact tasks; four documented nonreproductions excluded from primary analysis.",
  "codellama_original_nonreproduced":sorted(CODELLAMA_ORIGINAL_NONREPRODUCED) if a.project=="codellama" else []}
 (run/"EXPERIMENT_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
 with (run/"ARM_MANIFEST.csv").open("w",newline="") as f:
  fields=["feature_id","alpha","orientation","summary","ev","abs_ev","source_cells"]
  w=csv.DictWriter(f,fields);w.writeheader()
  for x in arms:w.writerow({**{k:x[k] for k in fields[:-1]},"source_cells":";".join(x["source_cells"])})
 common=[".venv/bin/python","tools/run_crosscoder_intervention.py","--checkpoint",c["checkpoint"],
  "--model-a-id",c["model_a"],"--model-b-id",c["model_b"],"--tokenizer-id",c["tokenizer"],
  "--target-side",c["side"],"--layer","16","--intervention-mode","traditional","--token-scope","last_token",
  "--generation-backend",c["backend"],"--input-jsonl",str(inp),"--max-new-tokens","512",
  "--temperature","0.2","--top-p","0.95","--seed","1000",f"--device-{c['side']}","cuda:0","--dtype","nf4"]
 if c["trust"]:common.append("--trust-remote-code")
 def generate(fid,alpha,name):
  out=run/"generations"/f"bigcodebench__{name}_results.jsonl"
  if count(out)==c["n"]:return out
  cmd=[*common,"--feature-id",str(fid),"--alpha",str(alpha),"--output-jsonl",str(out)]
  with (run/"logs"/f"{name}.log").open("w") as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  assert count(out)==c["n"]
  return out
 baseline=generate(0,0,"baseline_alpha0")
 observed={r["task_id"]:r for r in map(json.loads,baseline.open())}
 audit=[{"task_id":r["task_id"],"seed":r["seed"],"exact_reference_reproduction":observed[r["task_id"]]["completion"]==r["raw_completion"],"primary_original_v4_eligible":a.project!="codellama" or r["task_id"] not in CODELLAMA_ORIGINAL_NONREPRODUCED} for r in rows]
 exact=sum(x["exact_reference_reproduction"] for x in audit)
 (run/"audit"/"BASELINE_REPRODUCTION.json").write_text(json.dumps({"exact_reference":exact,"total":len(audit),"primary_original_v4_eligible":sum(x["primary_original_v4_eligible"] for x in audit),"minimum_required":c["minimum_exact"],"tasks":audit},indent=2)+"\n")
 if exact<c["minimum_exact"]:raise RuntimeError(f"baseline gate failed: {exact}/{len(audit)}")
 (run/"BASELINE_GATE_PASSED").write_text(f"{exact}/{len(audit)} exact\n")
 for i,x in enumerate(arms,1):
  sign="pos" if x["alpha"]>0 else "neg"
  generate(x["feature_id"],x["alpha"],f"f{x['feature_id']}_{sign}3")
  (run/"ARM_PROGRESS.txt").write_text(f"{i}/{len(arms)}\n")
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
