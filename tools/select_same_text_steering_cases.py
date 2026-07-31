#!/usr/bin/env python3
"""Select high joint-latent failure and pass cases for a steering smoke."""
import argparse, json
from pathlib import Path
import numpy as np

def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--run-dir",type=Path,required=True)
    p.add_argument("--source-results",type=Path,required=True)
    p.add_argument("--feature-id",type=int,required=True)
    p.add_argument("--aggregation",choices=["mean","max","p95","p99","active_fraction"],required=True)
    p.add_argument("--failures",type=int,default=10); p.add_argument("--controls",type=int,default=5)
    p.add_argument("--output-jsonl",type=Path,required=True); p.add_argument("--metadata-json",type=Path,required=True)
    args=p.parse_args()
    a=np.load(args.run_dir/"solution_feature_aggregates.npz")
    meta=json.loads((args.run_dir/"solution_metadata.json").read_text())
    source={r["task_id"]:r for r in rows(args.source_results)}
    candidates=[]
    for i,r in enumerate(meta):
        if r["source_model"]!="deepseek_base": continue
        item=dict(source[r["task_id"]]); item.update({
            "historical_label":"failure" if int(a["labels"][i]) else "pass_control",
            "historical_failure":int(a["labels"][i]), "feature_id":args.feature_id,
            "historical_feature_score":float(a[args.aggregation][i,args.feature_id]),
        }); candidates.append(item)
    pick=lambda label,n: sorted((r for r in candidates if r["historical_failure"]==label),key=lambda r:r["historical_feature_score"],reverse=True)[:n]
    selected=pick(1,args.failures)+pick(0,args.controls)
    vals=a[args.aggregation][[i for i,r in enumerate(meta) if r["source_model"]=="deepseek_base"],args.feature_id]
    scale=float(np.percentile(vals[vals>0],99))
    args.output_jsonl.parent.mkdir(parents=True,exist_ok=True)
    args.output_jsonl.write_text("".join(json.dumps(r)+"\n" for r in selected))
    out={"feature_id":args.feature_id,"aggregation":args.aggregation,"p99_scale":scale,"n_failures":args.failures,"n_controls":args.controls,"task_ids":[r["task_id"] for r in selected]}
    args.metadata_json.write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps(out,indent=2))
if __name__=="__main__": main()
