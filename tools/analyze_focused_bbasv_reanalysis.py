#!/usr/bin/env python3
import argparse, csv, json, re, statistics
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

CONTAM = re.compile(r"(?im)^\s*(?:#\s*)?(?:tests?/|test_|import\s+(?:pytest|unittest)|from\s+(?:pytest|unittest))")

def load_jsonl(path):
    return {r["task_id"]: r for r in map(json.loads, path.open())}

def load_eval(path):
    obj=json.load(path.open())
    return {k: bool(v and v[0].get("correct")) for k,v in obj["eval"].items()}

def code_of(row):
    return row.get("candidate_code_repaired", row.get("solution", ""))

def marks(code):
    lines=code.splitlines()
    return {
      "imports": {x.strip() for x in lines if re.match(r"\s*(?:from\s+\S+\s+import|import\s+)",x)},
      "returns": {x.strip() for x in lines if re.match(r"\s*return\b",x)},
      "defs": {x.strip() for x in lines if re.match(r"\s*(?:async\s+)?def\s+",x)},
      "tests": bool(re.search(r"(?im)^\s*(?:#.*tests?|class\s+Test|def\s+test_|import\s+(?:unittest|pytest)|from\s+(?:unittest|pytest))",code)),
      "comments": sum(bool(re.match(r"\s*#",x)) for x in lines),
    }

def category(a,b):
    if a==b: return "unchanged"
    x,y=marks(a),marks(b)
    if x["tests"]!=y["tests"]: return "test_marker"
    if x["imports"]!=y["imports"]: return "imports"
    if x["returns"]!=y["returns"]: return "returns"
    if x["defs"]!=y["defs"]: return "function_structure"
    if x["comments"]!=y["comments"]: return "comments"
    return "other_logic_text"

def parse(stem):
    if stem.startswith("target_"): kind="target"
    elif stem.startswith("random_"): kind="random"
    elif stem.startswith("sham"): kind="sham"
    else: return None
    side="reverse" if "_reverse_" in stem else "direct"
    m=re.search(r"_f(\d+)_",stem)
    fid=int(m.group(1)) if m else int(re.search(r"sham(\d+)",stem).group(1))
    z=re.search(r"_([+-]?\d+(?:\.\d+)?)$",stem)
    return kind,side,fid,float(z.group(1))

def median(xs, default=0): return statistics.median(xs) if xs else default
def write_csv(path, rows):
    if not rows: return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def analyze_family(root, family, out):
    base=root/family
    sdir=base/"postprocessed/results_repaired"; edir=base/"evaluations"
    samples={}
    evals={}
    for side in ("direct","reverse"):
        samples[side]=load_jsonl(sdir/f"bigcodebench__baseline_{side}_0_repaired.jsonl")
        evals[side]=load_eval(edir/f"bigcodebench__baseline_{side}_0_eval.json")
    arm_rows=[]; task_rows=[]; directional=defaultdict(set)
    paths=sorted(sdir.glob("bigcodebench__*_repaired.jsonl"))
    for p in paths:
        stem=p.name.removeprefix("bigcodebench__").removesuffix("_repaired.jsonl")
        meta=parse(stem)
        if not meta: continue
        kind,side,fid,alpha=meta
        ep=edir/f"bigcodebench__{stem}_eval.json"
        if not ep.exists(): continue
        cur=load_jsonl(p); ev=load_eval(ep); b=samples[side]; bev=evals[side]
        details=[]
        for tid,row in cur.items():
            before=code_of(b[tid]); after=code_of(row); changed=before!=after
            common=0
            if changed:
                for x,y in zip(before,after):
                    if x!=y: break
                    common+=1
            bp=bev[tid]; ap=ev[tid]; f2p=(not bp and ap); p2f=(bp and not ap)
            desired=f2p if side=="direct" else p2f
            if desired: directional[(side,kind,fid,abs(alpha))].add(tid)
            d=dict(family=family,arm=stem,kind=kind,side=side,feature_id=fid,alpha=alpha,
                   task_id=tid,baseline_pass=int(bp),arm_pass=int(ap),fail_to_pass=int(f2p),pass_to_fail=int(p2f),
                   directional_transition=int(desired),changed=int(changed),category=category(before,after),
                   edit_fraction=(1-SequenceMatcher(None,before,after,autojunk=False).ratio()) if changed else 0,
                   first_divergence_fraction=(common/max(1,min(len(before),len(after)))) if changed else 1,
                   length_delta=len(after)-len(before),contamination_cleanup=int(bool(CONTAM.search(before)) and not bool(CONTAM.search(after))))
            details.append(d); task_rows.append(d)
        changed=[d for d in details if d["changed"]]
        cats=Counter(d["category"] for d in details)
        arm_rows.append(dict(family=family,arm=stem,kind=kind,side=side,feature_id=fid,alpha=alpha,n=len(details),
          baseline_passes=sum(d["baseline_pass"] for d in details),passes=sum(d["arm_pass"] for d in details),
          fail_to_pass=sum(d["fail_to_pass"] for d in details),pass_to_fail=sum(d["pass_to_fail"] for d in details),
          net=sum(d["fail_to_pass"]-d["pass_to_fail"] for d in details),directional_transitions=sum(d["directional_transition"] for d in details),
          changed=len(changed),changed_fraction=len(changed)/len(details),median_edit_fraction_changed=median([d["edit_fraction"] for d in changed]),
          median_first_divergence_changed=median([d["first_divergence_fraction"] for d in changed],1),median_length_delta_changed=median([d["length_delta"] for d in changed]),
          contamination_cleanups=sum(d["contamination_cleanup"] for d in details),
          **{k:cats[k] for k in ("unchanged","test_marker","imports","returns","function_structure","comments","other_logic_text")}))

    target=[r for r in arm_rows if r["kind"]=="target"]
    curves=sorted(target,key=lambda r:(r["side"],r["feature_id"],abs(r["alpha"])))
    controls=[]
    by=defaultdict(list)
    for r in arm_rows: by[(r["side"],abs(r["alpha"]),r["kind"])].append(r)
    for side in ("direct","reverse"):
      for mag in (1,2,3,4,5):
        for kind in ("target","random","sham"):
          rs=by[(side,mag,kind)]
          if rs:
            vals=[x["directional_transitions"] for x in rs]
            controls.append(dict(family=family,side=side,magnitude=mag,kind=kind,n_arms=len(rs),median=median(vals),minimum=min(vals),maximum=max(vals),mean=sum(vals)/len(vals)))

    susc=[]
    target_tasks=defaultdict(list)
    for d in task_rows:
      if d["kind"]=="target": target_tasks[(d["side"],d["task_id"])].append(d)
    for (side,tid),ds in sorted(target_tasks.items()):
      hit=[d for d in ds if d["directional_transition"]]
      susc.append(dict(family=family,side=side,task_id=tid,n_target_arms=len(ds),n_directional_transitions=len(hit),
                       n_features=len({d["feature_id"] for d in hit}),max_magnitude=max([abs(d["alpha"]) for d in hit],default=0),
                       features=";".join(map(str,sorted({d["feature_id"] for d in hit})))))
    nesting=[]
    for side in ("direct","reverse"):
      for fid in sorted({r["feature_id"] for r in target if r["side"]==side}):
        sets={m:directional[(side,"target",fid,m)] for m in (1,2,3,4,5)}
        rets=[]
        for m in (1,2,3,4): rets.append(len(sets[m]&sets[m+1])/len(sets[m]) if sets[m] else None)
        nesting.append(dict(family=family,side=side,feature_id=fid,unique_tasks=len(set().union(*sets.values())),
          hits_by_magnitude=";".join(str(len(sets[m])) for m in (1,2,3,4,5)),
          consecutive_retention=";".join("NA" if x is None else f"{x:.3f}" for x in rets)))
    write_csv(out/f"{family}_arm_outcomes_and_changes.csv",arm_rows)
    write_csv(out/f"{family}_task_details.csv",task_rows)
    write_csv(out/f"{family}_target_curves.csv",curves)
    write_csv(out/f"{family}_available_control_comparison.csv",controls)
    write_csv(out/f"{family}_task_susceptibility.csv",susc)
    write_csv(out/f"{family}_dose_retention.csv",nesting)
    summary={
      "family":family,
      "baseline":{"direct":sum(evals["direct"].values()),"reverse":sum(evals["reverse"].values()),"n_direct":len(evals["direct"]),"n_reverse":len(evals["reverse"])},
      "complete_arms":len(arm_rows),"target_arms":len(target),"control_arms":len(arm_rows)-len(target),
      "direct_unique_tasks_changed_outcome":len({d["task_id"] for d in task_rows if d["kind"]=="target" and d["side"]=="direct" and d["fail_to_pass"]}),
      "reverse_unique_tasks_changed_outcome":len({d["task_id"] for d in task_rows if d["kind"]=="target" and d["side"]=="reverse" and d["pass_to_fail"]}),
      "direct_feature_task_transitions":sum(d["fail_to_pass"] for d in task_rows if d["kind"]=="target" and d["side"]=="direct"),
      "reverse_feature_task_transitions":sum(d["pass_to_fail"] for d in task_rows if d["kind"]=="target" and d["side"]=="reverse"),
    }
    return summary

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    summaries=[analyze_family(a.root,f,a.output) for f in ("deepseek","codellama")]
    (a.output/"summary.json").write_text(json.dumps(summaries,indent=2)+"\n")
    print(json.dumps(summaries,indent=2))
if __name__=="__main__": main()
