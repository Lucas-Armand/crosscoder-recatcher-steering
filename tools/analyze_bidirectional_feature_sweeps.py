#!/usr/bin/env python3
"""Summarize evaluated-code changes in the 3048/13147 bidirectional sweeps."""
import argparse, csv, json, re, statistics
from pathlib import Path

SPECS = [
    dict(project="DSTK100", run="dstk100_f3048_bidirectional_controls_v1", n=80,
         target=3048, own0="dstk_own_alpha0", reverse0="dstk_reverse_alpha0"),
    dict(project="CodeLlama", run="codellama_bm_f13147_bidirectional_controls_v1", n=50,
         target=13147, own0="codellama_own_alpha0", reverse0="codellama_reverse_alpha0"),
]

def load_rows(path):
    return {r["task_id"]: r for r in map(json.loads, path.open())}

def load_passes(path):
    payload=json.loads(path.read_text())
    return {k for k,v in payload["eval"].items()
            if (v[0] if isinstance(v,list) else v).get("correct",False)}

def markers(code):
    lines=code.splitlines()
    return {
        "imports": {x.strip() for x in lines if re.match(r"\s*(from\s+\S+\s+import|import\s+)",x)},
        "returns": {x.strip() for x in lines if re.match(r"\s*return\b",x)},
        "defs": {x.strip() for x in lines if re.match(r"\s*(async\s+)?def\s+",x)},
        "tests": bool(re.search(r"(?im)^\s*(#.*tests?|class\s+Test|def\s+test_|import\s+(unittest|pytest)|from\s+(unittest|pytest))",code)),
        "comments": sum(bool(re.match(r"\s*#",x)) for x in lines),
    }

def category(before,after):
    if before==after: return "unchanged"
    a,b=markers(before),markers(after)
    if a["tests"]!=b["tests"]: return "test_marker"
    if a["imports"]!=b["imports"]: return "imports"
    if a["returns"]!=b["returns"]: return "returns"
    if a["defs"]!=b["defs"]: return "function_structure"
    if a["comments"]!=b["comments"]: return "comments"
    return "other_logic_text"

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,default=Path(".")); ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    arm_rows=[]; task_rows=[]
    for spec in SPECS:
        root=args.repo/"runs"/spec["run"]
        samples=root/"postprocessed"/"samples_for_external_eval"; evals=root/"evaluations"
        base_rows={}; base_pass={}
        for side,key in (("own","own0"),("reverse","reverse0")):
            stem=spec[key]
            base_rows[side]=load_rows(samples/f"bigcodebench__{stem}_samples.jsonl")
            base_pass[side]=load_passes(evals/f"bigcodebench__{stem}_eval.json")
        for sample in sorted(samples.glob("*_samples.jsonl")):
            arm=sample.name.replace("bigcodebench__","").replace("_samples.jsonl","")
            if arm in (spec["own0"],spec["reverse0"]): continue
            side="reverse" if "reverse" in arm else "own"
            current=load_rows(sample); current_pass=load_passes(evals/sample.name.replace("_samples.jsonl","_eval.json"))
            if f"f{spec['target']}_reverse" in arm: family="target_reverse"
            elif f"f{spec['target']}_own" in arm: family="target_own"
            elif arm.startswith("sham"): family="sham"
            else: family="feature_control"
            alpha=float(re.search(r"(?:neg|pos)([0-9.]+)",arm).group(1))
            cats={}; lengths=[]; prefixes=[]
            for tid,row in current.items():
                before=base_rows[side][tid]["solution"]; after=row["solution"]
                c=category(before,after); cats[c]=cats.get(c,0)+1
                if before!=after:
                    lengths.append(len(after)-len(before)); common=0
                    for x,y in zip(before,after):
                        if x!=y: break
                        common+=1
                    prefixes.append(common/max(1,min(len(before),len(after))))
                task_rows.append(dict(project=spec["project"],feature=spec["target"],arm=arm,family=family,
                                      side=side,alpha=alpha,task_id=tid,category=c,
                                      baseline_pass=int(tid in base_pass[side]),current_pass=int(tid in current_pass),
                                      length_delta=len(after)-len(before)))
            arm_rows.append(dict(project=spec["project"],feature=spec["target"],arm=arm,family=family,side=side,alpha=alpha,
                tasks=spec["n"],changed_tasks=spec["n"]-cats.get("unchanged",0),
                pass_gain=len(current_pass-base_pass[side]),pass_loss=len(base_pass[side]-current_pass),
                net_pass=len(current_pass)-len(base_pass[side]),baseline_passes=len(base_pass[side]),current_passes=len(current_pass),
                median_length_delta=statistics.median(lengths) if lengths else 0,
                median_common_prefix_fraction=statistics.median(prefixes) if prefixes else 1,
                **{k:cats.get(k,0) for k in ("unchanged","test_marker","imports","returns","function_structure","comments","other_logic_text")}))
    for name,rows in (("arm_change_summary.csv",arm_rows),("task_change_details.csv",task_rows)):
        with (args.output/name).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (args.output/"run_summary.json").write_text(json.dumps({"schema_version":1,"comparison":"exact extraction-v4 evaluated code versus same-model alpha=0 baseline","specs":SPECS,"limitations":["rule-based mutually exclusive change taxonomy","seed 50000 in the focused sweeps differs from the original alpha=3 discovery seed convention 1000+task_idx"]},indent=2)+"\n")

if __name__=="__main__": main()
