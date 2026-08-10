#!/usr/bin/env python3
"""Taxonomize DeepSeek pass/fail transitions and join DSTK100 feature statistics."""
import argparse, csv, json, re
from pathlib import Path

FEATURES = {16383:"validation_raise",14481:"mixed_dataframe_plot",12956:"expected_output_usage",6404:"boilerplate_assumptions",8587:"numeric_literals",8294:"python_meta_comment",11785:"model_fit"}

def read_jsonl(path):
    return {r["task_id"]: r for r in map(json.loads, path.open())}

def error_category(error):
    s = error or ""
    rules = [(r"No module named ['\"]?(task|task_func|task_)","generated_test_import_contamination"),(r"AssertionError","wrong_output_or_logic"),(r"NameError|is not defined","missing_name_or_import"),(r"TypeError","wrong_type"),(r"ValueError","unexpected_value_error"),(r"FileNotFound|No such file|does not exist","file_or_path_handling"),(r"AttributeError","wrong_api_or_attribute"),(r"IndexError","index_edge_case"),(r"KeyError","key_edge_case"),(r"RecursionError","recursion"),(r"timeout|timed out","timeout"),(r"SyntaxError|invalid syntax","syntax"),(r"NotImplementedError","not_implemented")]
    return next((v for p,v in rules if re.search(p,s,re.I)), "other_runtime")

def flags(row, evaluated_tokens):
    code=row.get("candidate_code_repaired",""); lo=code.lower(); lines=code.splitlines()
    comments=[x for x in lines if x.lstrip().startswith("#")]
    test=bool(re.search(r"(^|\n)\s*(#\s*)?(tests?/|test_|class\s+Test|import\s+unittest|import\s+pytest|from\s+(task|task_func|task_)\s+import)",code,re.I))
    positions=[p for p in (lo.find(".fit("),lo.find("curve_fit(")) if p>=0]
    return {"test_contamination":test,"comment_heavy":len(comments)/max(1,len(lines))>.38,"comment_ratio":len(comments)/max(1,len(lines)),"likely_truncated":not row.get("compile_ok_repaired",True) or evaluated_tokens>=500,"evaluated_tokens":evaluated_tokens,"has_raise":"raise " in lo,"raise_count":lo.count("raise "),"has_fit":".fit(" in lo or "curve_fit(" in lo,"fit_char_percent":100*min(positions,default=-1)/max(1,len(code)),"numeric_literals":len(re.findall(r"(?<!\w)[+-]?(?:\d+\.?\d*|\.\d+)",code)),"code_chars":len(code),"raw_chars":len(row.get("raw_completion",""))}

def write_csv(path, rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    for name in ("repo","eval-root","post-root","activation-root","feature-stats","output"): p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((a.activation_root/"capture_manifest.json").read_text())
    token_counts={(r["benchmark"],r["task_id"],r["source_text"].replace("deepseek_","")):int(r["tokens"]) for r in manifest}
    labels={}
    for r in csv.DictReader((a.repo/"reports/paper_v1_v4_evaluation_labels.csv").open()):
        if int(r["generation_idx"])==0 and r["model"] in ("deepseek_base","deepseek_finetuned"): labels[(r["model"],r["benchmark"],r["task_id"])]=int(r["label"])
    repairs={(b,m):read_jsonl(a.post_root/f"{b}__deepseek_{m}_repaired.jsonl") for b in ("bigcodebench","humanevalplus") for m in ("base","finetuned")}
    errors={}
    for m in ("base","finetuned"):
        d=json.load((a.eval_root/"bigcodebench015"/f"bigcodebench__deepseek_{m}_eval_results.json").open())["eval"]
        for tid,v in d.items(): errors[("bigcodebench",m,tid)]=" | ".join(f"{k}: {x}" for k,x in (v[0].get("details") or {}).items())
        for line in (a.eval_root/"humanevalplus"/f"humanevalplus__deepseek_{m}_eval.jsonl").open():
            r=json.loads(line); errors[("humanevalplus",m,r["task_id"])]=r.get("eval_candidate_code_repaired_error") or ""
    fs={(r["source_text"].replace("deepseek_",""),r["benchmark"],r["task_id"],int(r["feature_id"])):r for r in csv.DictReader(a.feature_stats.open())}
    cases=[]
    for b in ("bigcodebench","humanevalplus"):
        tids=sorted(t for model,bb,t in labels if model=="deepseek_base" and bb==b)
        for tid in tids:
            lb,lf=labels[("deepseek_base",b,tid)],labels[("deepseek_finetuned",b,tid)]
            if lb==lf: continue
            transition="regression" if lb==0 else "improvement"; fail="finetuned" if transition=="regression" else "base"; passed="base" if fail=="finetuned" else "finetuned"
            rr,pr=repairs[(b,fail)][tid],repairs[(b,passed)][tid]
            fl,pl=flags(rr,token_counts[(b,tid,fail)]),flags(pr,token_counts[(b,tid,passed)])
            err=errors[(b,fail,tid)]; cat=error_category(err)
            primary="generated_test_import_contamination" if fl["test_contamination"] and cat=="generated_test_import_contamination" else "commentary_or_overgeneration" if fl["comment_heavy"] else "truncation_or_extraction" if fl["likely_truncated"] else cat
            cases.append({"benchmark":b,"task_id":tid,"transition":transition,"failing_model":fail,"passing_model":passed,"primary_failure_category":primary,"evaluator_category":cat,"error_excerpt":err.replace("\n"," ")[:700],**{f"fail_{k}":v for k,v in fl.items()},**{f"pass_{k}":v for k,v in pl.items()},"failing_code":rr["candidate_code_repaired"],"passing_code":pr["candidate_code_repaired"]})
    write_csv(a.output/"transition_failure_cases.csv",cases)
    counts={}
    for c in cases: counts[(c["benchmark"],c["transition"],c["primary_failure_category"])]=counts.get((c["benchmark"],c["transition"],c["primary_failure_category"]),0)+1
    write_csv(a.output/"failure_category_summary.csv",[{"benchmark":k[0],"transition":k[1],"category":k[2],"count":v} for k,v in sorted(counts.items())])
    rel=[]
    for c in cases:
        for fid,sem in FEATURES.items():
            s=fs.get((c["failing_model"],c["benchmark"],c["task_id"],fid))
            if not s: continue
            active=int(s["active_tokens"])>0; first=float(s["first_percent"]); score=int(active and first<50); reasons=["active_before_50pct"] if score else []
            if fid in (12956,6404,8294) and (c["fail_test_contamination"] or c["fail_comment_heavy"] or c["fail_likely_truncated"]): score+=3; reasons.append("semantic_match_overgeneration")
            if fid==16383 and c["fail_has_raise"] and c["primary_failure_category"] in ("unexpected_value_error","file_or_path_handling","wrong_output_or_logic"): score+=2; reasons.append("semantic_match_validation")
            if fid==11785 and c["fail_has_fit"]: score+=2; reasons.append("semantic_match_fit")
            rel.append({k:c[k] for k in ("benchmark","task_id","transition","failing_model","primary_failure_category","error_excerpt")}|{"feature_id":fid,"feature_semantics":sem,"max_activation":float(s["max_activation"]),"active_tokens":int(s["active_tokens"]),"first_percent":first,"argmax_percent":float(s["argmax_percent"]),"token_at_max":s["token_at_max"],"plausibility_score":score,"plausibility_reasons":";".join(reasons)})
    write_csv(a.output/"feature_failure_relations.csv",rel)
    (a.output/"run_summary.json").write_text(json.dumps({"transition_cases":len(cases),"regressions":sum(x["transition"]=="regression" for x in cases),"improvements":sum(x["transition"]=="improvement" for x in cases),"taxonomy":"rule-based; audit candidates manually"},indent=2)+"\n")

if __name__=="__main__": main()
