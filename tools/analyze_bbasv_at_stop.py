#!/usr/bin/env python3
import argparse,csv,json,re,statistics
from difflib import SequenceMatcher
from pathlib import Path

def load(p):
    return {r["task_id"]:r for r in map(json.loads,p.open())}

def marks(code):
    ls=code.splitlines()
    return {
      "imports":{x.strip() for x in ls if re.match(r"\s*(?:from\s+\S+\s+import|import\s+)",x)},
      "returns":{x.strip() for x in ls if re.match(r"\s*return\b",x)},
      "defs":{x.strip() for x in ls if re.match(r"\s*(?:async\s+)?def\s+",x)},
      "tests":bool(re.search(r"(?im)^\s*(?:#.*tests?|class\s+Test|def\s+test_|import\s+(?:unittest|pytest)|from\s+(?:unittest|pytest))",code)),
      "comments":sum(bool(re.match(r"\s*#",x)) for x in ls),
    }

def category(a,b):
    if a==b:return "unchanged"
    x,y=marks(a),marks(b)
    if x["tests"]!=y["tests"]:return "test_marker"
    if x["imports"]!=y["imports"]:return "imports"
    if x["returns"]!=y["returns"]:return "returns"
    if x["defs"]!=y["defs"]:return "function_structure"
    if x["comments"]!=y["comments"]:return "comments"
    return "other_logic_text"

def parse(stem):
    if stem.startswith("target_"):kind="target"
    elif stem.startswith("random_"):kind="random_latent"
    elif stem.startswith("sham_"):kind="orthogonal_sham"
    else:return None
    side="reverse" if "_reverse_" in stem else "direct"
    m=re.search(r"_f(\d+)_",stem);fid=int(m.group(1)) if m else 0
    z=re.search(r"_(pos|neg)([0-9.]+)$",stem);alpha=(1 if z.group(1)=="pos" else -1)*float(z.group(2))
    return kind,side,fid,alpha

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--samples",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    bases={s:load(a.samples/f"bigcodebench__baseline_{s}_samples.jsonl") for s in ("direct","reverse")}
    arms=[];tasks=[]
    for p in sorted(a.samples.glob("bigcodebench__*_samples.jsonl")):
        stem=p.name.removeprefix("bigcodebench__").removesuffix("_samples.jsonl");meta=parse(stem)
        if not meta:continue
        kind,side,fid,alpha=meta;cur=load(p);cats={};ratios=[];prefixes=[];lend=[]
        for tid,r in cur.items():
            before=bases[side][tid]["solution"];after=r["solution"];cat=category(before,after);cats[cat]=cats.get(cat,0)+1
            if before!=after:
                ratios.append(1-SequenceMatcher(None,before,after,autojunk=False).ratio());common=0
                for x,y in zip(before,after):
                    if x!=y:break
                    common+=1
                prefixes.append(common/max(1,min(len(before),len(after))));lend.append(len(after)-len(before))
            tasks.append(dict(arm=stem,kind=kind,side=side,feature_id=fid,alpha=alpha,task_id=tid,category=cat,changed=int(before!=after),length_delta=len(after)-len(before)))
        n=len(cur);arms.append(dict(arm=stem,kind=kind,side=side,feature_id=fid,alpha=alpha,tasks=n,changed=n-cats.get("unchanged",0),changed_fraction=(n-cats.get("unchanged",0))/n,median_edit_fraction=statistics.median(ratios) if ratios else 0,median_common_prefix=statistics.median(prefixes) if prefixes else 1,median_length_delta=statistics.median(lend) if lend else 0,**{k:cats.get(k,0) for k in ("unchanged","test_marker","imports","returns","function_structure","comments","other_logic_text")}))
    for name,rows in (("arm_change_summary.csv",arms),("task_change_details.csv",tasks)):
        with (a.output/name).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(arms,indent=2))
if __name__=="__main__":main()
