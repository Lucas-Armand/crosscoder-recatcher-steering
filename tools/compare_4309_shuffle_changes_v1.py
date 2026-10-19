#!/usr/bin/env python3
"""Compare every target/shuffle change at magnitude5 using identical criteria."""
import ast
from collections import Counter
import csv
import difflib
import json
from pathlib import Path
import numpy as np
from analyze_4309_behavior_hypothesis_v1 import describe,statements,descendants,callname
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
PREV=ROOT/'reports/section67_semantic_temporal_20261019_v1'
OUT=ROOT/'reports/codellama4309_change_comparison_20261019_v1'

def read(p):return json.loads(p.read_text())
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def body(code):
    try:
        f=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func');ns=statements(f)
        lines=code.splitlines();text='\n'.join(lines[ns[0].lineno-1:f.end_lineno]) if ns else ''
        nodes=[n for s in ns for n in descendants(s)]
        return ns,text,nodes
    except (SyntaxError,StopIteration):return None,'',[]
def failed_count(record,testnames):
    if record['correct']:return 0,'official_pass'
    detail=record['details']
    if not isinstance(detail,dict):return None,'unknown'
    if 'ALL' in detail:return len(testnames),'global_failure_blocked_tests'
    names=set(detail)&set(testnames)
    if set(detail)-set(testnames) or not names:return None,'unknown'
    return len(names),'recorded_test_failures'
def testnames(code):
    t=ast.parse(code)
    return sorted(n.name for c in t.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test'))
def save(fig,name):
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    baseline=read(ROOT/'runs/feature_stress_alpha0_20261015_v1/codellama/evaluations/bigcodebench__codellama_weak_alpha0_eval.json')['eval']
    bench=read(PREV/'codellama_localization_benchmark_inputs.json')
    target=read(ROOT/'runs/focused_bbasv_v2_codellama/direct_evaluations/bigcodebench__target_f4309_direct_-5_eval.json')['eval']
    arms=[('target4309_neg5','target',target)]
    for i in [1,2,3]:
        for sign in ['neg','pos']:
            name=f'codellama_shuffle{i}_{sign}5'
            ev=read(ROOT/'runs/feature_stress_shuffle_20261016_v1/codellama/evaluations'/f'bigcodebench__{name}_eval.json')['eval']
            arms.append((name,'shuffle',ev))
    details=[];summaries=[];examples=[]
    for name,kind,ev in arms:
        assert set(ev)==set(baseline)
        for tid in sorted(ev,key=lambda s:int(s.split('/')[-1])):
            before,after=baseline[tid][0],ev[tid][0];bcode,acode=before['solution'],after['solution'];changed=bcode!=acode
            assert not before['correct']
            bd,ad=describe(bcode),describe(acode);bn,bt,bnodes=body(bcode);an,at,anodes=body(acode)
            astchanged=bn is None or an is None or ast.dump(ast.Module(body=bn,type_ignores=[]),include_attributes=False)!=ast.dump(ast.Module(body=an,type_ignores=[]),include_attributes=False)
            testset=testnames(bench[tid]['test']);nb,mb=failed_count(before,testset);na,ma=failed_count(after,testset)
            # These are observable syntactic changes, not an automatic semantic-improvement label.
            calls_added=sorted(set(ad.get('calls',[]))-set(bd.get('calls',[])));calls_removed=sorted(set(bd.get('calls',[]))-set(ad.get('calls',[])))
            if_tests=lambda ns:sorted(ast.dump(n.test,include_attributes=False) for n in ns if isinstance(n,ast.If))
            counts=lambda ns:Counter(ast.dump(n,include_attributes=False) for n in ns if isinstance(n,ast.stmt))
            repb=max(counts(bnodes).values(),default=0);repa=max(counts(anodes).values(),default=0)
            conditions_changed=if_tests(bnodes)!=if_tests(anodes)
            row=dict(arm=name,kind=kind,task_id=tid,alpha=-5 if name.endswith('neg5') else 5,changed=changed,
                passed=after['correct'],main_body_ast_changed=changed and astchanged,
                main_body_ast_unchanged=changed and not astchanged,
                syntax_invalid=not ad['parseable'],body_removed=bool(bd.get('all_statements')) and ad.get('parseable',False) and ad.get('all_statements')==0,
                value_return_lost=not bd.get('no_value_return',True) and ad.get('parseable',False) and ad.get('no_value_return',True),
                value_return_added=bd.get('no_value_return',True) and ad.get('parseable',False) and not ad.get('no_value_return',True),
                return_only_expanded=bd.get('return_only',False) and ad.get('all_statements',0)>1,
                repetition_increased=repa>=3 and repa>repb,
                conditions_changed=changed and conditions_changed,
                calls_added=calls_added,calls_removed=calls_removed,
                failing_or_blocked_tests_before=nb,failing_or_blocked_tests_after=na,
                test_count_method_before=mb,test_count_method_after=ma,
                fewer_failing_tests=nb is not None and na is not None and na<nb,
                more_failing_tests=nb is not None and na is not None and na>nb,
                same_failing_test_count=nb is not None and na is not None and na==nb,
                failure_signature_changed=changed and before['details']!=after['details'],
                before_main=bt,after_main=at,baseline_failures=before['details'],arm_failures=after['details'])
            details.append(row)
            if changed:examples.append(row)
        rs=[r for r in details if r['arm']==name]
        fields=['changed','passed','main_body_ast_changed','main_body_ast_unchanged','syntax_invalid','body_removed','value_return_lost','value_return_added','return_only_expanded','repetition_increased','conditions_changed','fewer_failing_tests','more_failing_tests','same_failing_test_count']
        summary=dict(arm=name,kind=kind,n=50,**{f:sum(bool(r[f]) for r in rs) for f in fields})
        summary['fewer_failing_but_not_passed']=sum(r['fewer_failing_tests'] and not r['passed'] for r in rs)
        summary['test_count_unknown']=sum(r['failing_or_blocked_tests_before'] is None or r['failing_or_blocked_tests_after'] is None for r in rs)
        summaries.append(summary)
    assert len(details)==350 and len(examples)==150
    dump(OUT/'task_arm_comparison.json',details);dump(OUT/'SUMMARY.json',summaries)
    with (OUT/'arm_summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    workbook=['# All 150 changed task-arm programs at magnitude five','',
        'Uniform criteria across target and all six shuffle arms. AST categories are nonexclusive and not semantic correctness labels. Fewer failing tests is descriptive evidence under this fixed suite; global failures block the entire suite and are explicitly distinguished from individual failures.','']
    for r in examples:
        workbook += [f"## {r['arm']} / {r['task_id']} / {'PASS' if r['passed'] else 'FAIL'}",'',
            f"Failing/blocked tests: {r['failing_or_blocked_tests_before']} -> {r['failing_or_blocked_tests_after']}; count modes: {r['test_count_method_before']} -> {r['test_count_method_after']}",
            f"Body AST changed: {r['main_body_ast_changed']}; return lost: {r['value_return_lost']}; body removed: {r['body_removed']}; repetition increased: {r['repetition_increased']}",'','```diff']
        workbook+=list(difflib.unified_diff(r['before_main'].splitlines(),r['after_main'].splitlines(),fromfile='baseline main body',tofile='intervention main body',lineterm=''))
        workbook += ['```','','### Official outcome evidence','```text',str(r['arm_failures'])[:4000],'```','']
    (OUT/'ALL_CHANGED_MAIN_BODIES.md').write_text('\n'.join(workbook)+'\n')
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,axs=plt.subplots(1,2,figsize=(13,5.4));labels=[r['arm'].replace('codellama_','') for r in summaries];x=np.arange(len(labels))
    colors=['#D67A16']+['#777777']*6
    for ax,fields,title in [(axs[0],['main_body_ast_changed','main_body_ast_unchanged'],'What changed in the 50 programs?'),
                            (axs[1],['passed','fewer_failing_but_not_passed','more_failing_tests'],'Official test outcome changes')]:
        for i,field in enumerate(fields):
            vals=[r[field] for r in summaries]
            ax.barh(x+(i-(len(fields)-1)/2)*.23,vals,height=.22,label=field.replace('_',' '))
        ax.set_yticks(x,labels);ax.invert_yaxis();ax.set_title(title);ax.set_xlabel('Tasks / 50');ax.legend(fontsize=8,loc='lower right');ax.grid(axis='x',alpha=.15)
    fig.text(.5,.01,'Same task cohort and magnitude · categories are not all mutually exclusive · failing/blocked-test counts are not semantic proof.',ha='center',fontsize=8)
    fig.subplots_adjust(left=.17,wspace=.55,bottom=.13);save(fig,'01_target_shuffle_change_comparison')
    dump(OUT/'METHOD.json',dict(task_arms=350,changed_task_arms=150,primary_comparison='target -5 versus three shuffles -5',
        sensitivity='three shuffles +5',new_generation=False,human_independent_annotation=False,
        criteria='Uniform AST/diff and already recorded official-test evidence; no automatic coherent/beneficial semantic label.',
        caveats=['Source-dependent traceback strings can differ without changed behavior.',
                 'A change only outside task_func may still affect behavior via imports or global statements.',
                 'Fewer failures is not necessarily closer to the full intended specification.',
                 'Global suite failures are counted as all tests blocked, not as individually observed assertion failures.']))
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
