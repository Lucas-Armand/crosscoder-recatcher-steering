#!/usr/bin/env python3
"""Evidence-tiered localization of 50 existing failures; no new model execution."""
import ast
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from transformers import AutoTokenizer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/section67_semantic_temporal_20261019_v1'
BASE=ROOT/'runs/feature_stress_alpha0_20261015_v1/codellama'
# Analyst-proposed regions from inspecting main-function bodies and failure evidence.
# These are NOT automatically recovered root causes or human-validated annotations.
# start/end are lines in the exact evaluated alpha-zero solution, including the prompt.
REGIONS={
96:(37,39,'probable_region','CSV parsing and reversed count/word tuple; sorting is after return.'),
115:(35,35,'probable_line','Returns scipy ModeResult instead of the scalar mode required by failing assertions.'),
119:(29,31,'probable_region','Calls nonexistent pyplot methods; traceback identifies set_title execution.'),
122:(29,32,'omission_region','Returns the appended values rather than the requested random array sized by their sum.'),
149:(34,43,'probable_region','DataFrame constructor receives column dictionaries as separate positional arguments.'),
173:(30,33,'probable_region','Indexes by dictionary keys rather than requested country values; missing Name population.'),
183:(24,24,'probable_line','Serializes an already serialized JSON string and omits the UUID response header.'),
194:(33,34,'probable_region','Returns an integer color index where assertions require a color string.'),
206:(39,42,'probable_region','Builds a CSV writer on a file opened read-only; task expects CSV-to-JSON conversion.'),
240:(30,33,'probable_region','Constructs only Value column and does not build the required populated User/Value result.'),
275:(31,31,'probable_line','range(1,n) excludes n; failing assertions require pairs through n inclusive.'),
339:(33,37,'probable_region','Invalid HMAC construction/update; non-dictionary input also falls through without error.'),
357:(31,31,'probable_line','Returns a fixed linspace instead of the requested computation; return is the only body statement.'),
370:(45,50,'probable_region','Reuses file as a stream then passes it as a path to open; separate validation omission.'),
371:(29,29,'probable_line','Uses transform on an unfitted MinMaxScaler.'),
398:(32,35,'probable_region','Indexes data[0] on an empty list and checks only the first element for validity.'),
412:(40,46,'probable_region','Passes decoded bytes to Unicode normalization; other failures involve result type/writing.'),
423:(41,45,'probable_region','Threshold call lacks a required positional argument; later validation is unreachable.'),
430:(36,37,'omission_region','Only constructs example DataFrames; no required calculation/return implementation.'),
431:(42,42,'omission_region','Only normalizes a path; required histogram and return behavior are absent.'),
490:(28,28,'omission_region','Returns the XML dictionary without writing the required JSON file.'),
577:(39,42,'omission_region','Iterates names but does not construct/return the requested dictionary.'),
578:(32,38,'probable_region','Status handling raises HTTPError on mocked responses; normalization call also lacks form argument.'),
603:(28,29,'omission_region','Constructs hard-coded matrices instead of implementing the requested operation/validation.'),
604:(35,35,'probable_line','Compiler invocation omits the expected -o output argument, as shown by mock assertion.'),
629:(33,37,'probable_region','CSV separator has multiple characters; other required output behavior is missing.'),
630:(31,31,'probable_line','Default to_json orientation differs from the list-of-records format required by tests.'),
634:(34,34,'probable_line','Passes a chain iterator as data to mode rather than computing the requested modal elements.'),
670:(25,64,'omission_region','Nested continuation logic never returns a result; no unique missing-operation line.'),
738:(22,22,'probable_line','Computes standard deviation instead of the requested interquartile range.'),
743:(32,39,'probable_region','Prefix collection used with wrong startswith argument type; counts also lack initialization.'),
756:(30,35,'omission_region','Validates paths but omits required file operation/count and return.'),
790:(41,42,'omission_region','Stops after validating one column; requested computation and return are absent.'),
823:(35,39,'probable_region','Uses absolute time plus delay rather than timing elapsed sleep duration.'),
841:(46,49,'probable_region','Repeated translate calls and nonexistent string.letters; traceback identifies execution sites.'),
846:(52,86,'probable_region','Returns empty frames for different list lengths instead of computing requested counts.'),
858:(42,81,'omission_region','Repeated initialization/validation without requested counting result or return.'),
875:(47,52,'probable_region','Does not seed random and uses randint without both bounds for missing-value filling.'),
878:(54,85,'omission_region','Repeated validation without training/output; multiple expected error checks also absent.'),
926:(32,34,'probable_region','SQL statement hardcodes content instead of the specified column.'),
931:(27,27,'probable_line','Always returns an empty defaultdict instead of requested counts.'),
939:(28,33,'probable_region','Sanitizes full paths instead of basenames; ordering/normalization also differs.'),
954:(41,43,'omission_region','Starts constructing sentences but never completes/returns requested output.'),
971:(48,54,'omission_region','Collects local file attributes without returning the requested list; invalid-path handling differs.'),
983:(37,38,'omission_region','Only validates emptiness; covariance/result construction and return are absent.'),
989:(40,44,'omission_region','Validates inputs then converts predicates; requested selection/result is not implemented.'),
1062:(41,51,'omission_region','Plots only in empty-input branch and never returns the required Axes.'),
1063:(34,34,'omission_region','Constructs a fixed array but omits plotting and return.'),
1076:(44,44,'omission_region','Only creates an empty DataFrame; time conversion, validation and output absent.'),
1092:(33,46,'probable_region','Returns after first matching script rather than collecting all; other paths return None.'),
}

def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def function(code):return next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='task_func')
def body(code):
    f=function(code);nodes=f.body
    if isinstance(nodes[0],ast.Expr) and isinstance(nodes[0].value,ast.Constant) and isinstance(nodes[0].value.value,str):nodes=nodes[1:]
    return '\n'.join(code.splitlines()[nodes[0].lineno-1:f.end_lineno])
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def position(offsets,char):
    ix=np.flatnonzero(offsets[:,1]>char)
    return float(ix[0]/max(1,len(offsets)-1)) if len(ix) else 1.
def save(fig,name):
    for ext in ['pdf','png','svg']:fig.savefig(OUT/f'{name}.{ext}',dpi=220,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def main():
    evalpath=BASE/'evaluations/bigcodebench__codellama_weak_alpha0_eval.json'
    ev=json.loads(evalpath.read_text());strong=json.loads((BASE/'evaluations/bigcodebench__codellama_strong_alpha0_eval.json').read_text())
    refs={r['task_id']:r for r in rows(BASE/'inputs/weak.jsonl')}
    cases=json.loads((OUT/'steering_cases.json').read_text());cases5={r['task_id']:r for r in cases if r['family']=='codellama' and r['alpha']==-5}
    assert len(refs)==len(ev['eval'])==len(REGIONS)==50
    command=['/home/lucas/venvs/bigcodebench015/bin/python','-c',
      'import json; from bigcodebench.data import get_bigcodebench; print(json.dumps(get_bigcodebench()))']
    benchmark=json.loads(subprocess.check_output(command,text=True))
    selected={tid:{k:benchmark[tid][k] for k in ['task_id','complete_prompt','test','canonical_solution']} for tid in refs}
    dump(OUT/'codellama_localization_benchmark_inputs.json',selected)
    tok=AutoTokenizer.from_pretrained('meta-llama/CodeLlama-7b-hf',use_fast=True,local_files_only=True)
    annotated=[]
    for tid,rs in sorted(ev['eval'].items(),key=lambda p:int(p[0].split('/')[-1])):
        record=rs[0];code=record['solution'];f=function(code);lines=code.splitlines();lo,hi,proposed,note=REGIONS[int(tid.split('/')[-1])]
        assert f.lineno<=lo<=hi<=f.end_lineno,(tid,lo,hi,f.end_lineno)
        frames=[]
        for test,error in record['details'].items():
            for line,fun in re.findall(r'File "__test__\.py", line (\d+), in ([^\n]+)',str(error)):
                if f.lineno<=int(line)<=f.end_lineno and fun.strip()=='task_func':
                    frames.append(dict(test=test,solution_line=int(line),statement=lines[int(line)-1],error=str(error)))
        sites=sorted({r['solution_line'] for r in frames})
        if sites:lo,hi=min(sites),max(sites);kind='runtime_execution_sites';confidence='traceback-confirmed execution site; not necessarily first cause'
        else:kind=proposed;confidence='provisional analyst localization; not independently human-validated'
        starts=np.cumsum([0]+[len(s)+1 for s in lines[:-1]])
        startchar=int(starts[lo-1])+len(lines[lo-1])-len(lines[lo-1].lstrip());endchar=int(starts[hi-1])+len(lines[hi-1])
        offsets=np.asarray(tok(code,return_offsets_mapping=True,add_special_tokens=False)['offset_mapping'])
        prompt=refs[tid]['prompt'].rstrip()+'\n';begin=len(prompt) if code.startswith(prompt) else 0
        offsets=offsets[(offsets[:,1]>begin)&(offsets[:,0]<len(code))]
        c=cases5[tid]
        annotated.append(dict(task_id=tid,localization_type=kind,confidence=confidence,solution_line_start=lo,solution_line_end=hi,
            runtime_solution_lines=sites,note=note,first_semantic_error_proven=False,
            error_region_start_position=position(offsets,startchar),error_region_end_position=position(offsets,endchar),
            first_natural_activation=c['natural_first_activation'],first_steering_change=c['first_change_position'],
            feature_active_in_frozen_text=c['natural_active'],alpha5_passed=c['passed'],alpha5_changed=c['changed'],
            failing_tests=record['details'],runtime_evidence=frames,code=code,main_body=body(code),
            selected_region='\n'.join(f'{i}: {lines[i-1]}' for i in range(lo,hi+1)),
            canonical_solution=selected[tid]['canonical_solution'],base_passing_body=body(strong['eval'][tid][0]['solution']),
            source_sha256=hashlib.sha256(code.encode()).hexdigest()))
    dump(OUT/'codellama_error_localization.json',annotated)
    simple=[{k:r[k] for k in ['task_id','localization_type','confidence','solution_line_start','solution_line_end','note','error_region_start_position','error_region_end_position','first_natural_activation','first_steering_change','alpha5_passed','alpha5_changed']} for r in annotated]
    with (OUT/'codellama_error_localization.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(simple[0]));writer.writeheader();writer.writerows(simple)
    report=['# CodeLlama error localization — 50 cases','',
       'Traceback sites are exact locations of observed exceptions, not proof of the earliest semantic cause. Assertion-only locations below are provisional analyst proposals from code/error inspection. Omission regions are not a literal line that throws. No independent human validation was performed.','',
       'The evaluator executes solution + newline + official tests. Therefore a __test__.py frame belongs to generated code only when its line is within task_func; frames in tests are never copied as solution error lines.','',
       '| Task | Evidence tier | Solution lines | Finding |','|---|---|---:|---|']
    for r in annotated:report.append(f"| {r['task_id']} | {r['localization_type']} | {r['solution_line_start']}–{r['solution_line_end']} | {r['note']} |")
    for r in annotated:
        report += ['',f"## {r['task_id']} — {r['localization_type']}",'',r['confidence'],r['note'],'','```python',r['selected_region'],'```','',
                   '**Passing base implementation:**','```python',r['base_passing_body'],'```','',
                   '**Observed failure evidence:**','```text',str(r['failing_tests'])[:6000],'```']
    (OUT/'CODELLAMA_ERROR_LOCALIZATION.md').write_text('\n'.join(report)+'\n')
    # Region chart: shaded interval is not falsely converted into a point onset.
    plt.rcParams.update({'font.size':8,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(10,13))
    for i,r in enumerate(annotated):
        color='#C66B10' if r['localization_type']=='runtime_execution_sites' else '#AAAAAA'
        x=100*r['error_region_start_position'];right=100*r['error_region_end_position']
        ax.plot([x,right],[i,i],color=color,lw=5,alpha=.7)
        if r['first_natural_activation'] is not None:ax.scatter(100*r['first_natural_activation'],i,marker='o',s=15,color='#7654CF')
        if r['first_steering_change'] is not None:ax.scatter(100*r['first_steering_change'],i,marker='D' if r['alpha5_passed'] else 'x',s=24 if r['alpha5_passed'] else 13,color='#008577' if r['alpha5_passed'] else '#444444')
    ax.set_yticks(range(len(annotated)),['/'+r['task_id'].split('/')[-1] for r in annotated]);ax.invert_yaxis();ax.set_xlim(-2,102)
    ax.set_xlabel('Position in alpha-zero evaluated generated tokens (%)');ax.xaxis.set_major_formatter(PercentFormatter(100));ax.grid(axis='x',alpha=.2)
    ax.set_title('CodeLlama / 4309: proposed error region, natural activation and first change at α=−5',pad=15)
    fig.text(.5,.025,'Orange: traceback sites · gray: provisional/omission region · purple dot: first natural activation\nGreen diamond: first change in corrected task · black x: first change in still-failing task\nLine numbers and supporting evidence are in CODELLAMA_ERROR_LOCALIZATION.md. No earliest-error claim.',ha='center',fontsize=8)
    fig.subplots_adjust(bottom=.09);save(fig,'13_codellama_error_regions')
    # Deep dive: both successes, exact main bodies, tests and natural contexts.
    npz=np.load(OUT/'codellama_feature_activations.npz');timing=list(csv.DictReader((OUT/'natural_timing.csv').open()))
    deep=[]
    for tid in ['BigCodeBench/183','BigCodeBench/490']:
        loc=next(r for r in annotated if r['task_id']==tid);c=cases5[tid];key=tid.split('/')[-1]+'__codellama_merged'
        z=npz[key+'__z'];tokenids=npz[key+'__ids'];off=npz[key+'__offsets'];active=np.flatnonzero(z>0)
        natural=next(r for r in timing if r['task_id']==tid and r['source_text']=='codellama_merged')
        activations=[dict(token_index=int(i),token=tok.decode([int(tokenids[i])]),activation=float(z[i]),
                         token_position=float(i/max(1,len(z)-1)),character_offset=list(map(int,off[i]))) for i in active]
        dose=[dict(alpha=r['alpha'],passed=r['passed'],changed=r['changed'],first_change=r['first_change_position']) for r in cases if r['family']=='codellama' and r['task_id']==tid]
        record=dict(task_id=tid,baseline_body=body(c['code_before']),steered_body=body(c['code_after']),passing_base_body=loc['base_passing_body'],
                    evaluator_failures=loc['failing_tests'],official_test=selected[tid]['test'],canonical_solution=selected[tid]['canonical_solution'],
                    natural_activation_tokens=activations,captured_evaluated_tokens=len(z),dose=dose,
                    frozen_first_activation_position=natural['first_active_position'],remapped_first_activation=c['natural_first_activation'],
                    first_steering_change=c['first_change_position'])
        deep.append(record)
    dump(OUT/'codellama_two_successes.json',deep)
    lines=['# CodeLlama feature 4309 — both official successes at alpha -5','',
       'These two tasks are selected because they are the complete set of alpha-minus-five successes, not because their snippets look favorable. Natural activations are offline shared CrossCoder measurements; interventions are unconditional, not activation-gated.','']
    for r in deep:
        lines += [f"## {r['task_id']}",'','### Baseline merged main body','```python',r['baseline_body'],'```','',
                  '### Steered merged main body (alpha -5)','```python',r['steered_body'],'```','',
                  '### Passing base main body','```python',r['passing_base_body'],'```','',
                  '### Official test code','```python',r['official_test'],'```','',
                  f"Captured evaluated tokens: {r['captured_evaluated_tokens']}. Active tokens: {r['natural_activation_tokens']}",
                  f"Dose outcomes: {r['dose']}",'']
    lines += ['## Interpretation supported by these cases','',
      '- /183: input is already a JSON string. Baseline serializes it again; steering removes the second serialization and adds the required UUID response header. Both changes match explicit test assertions.',
      '- /490: baseline returns a parsed XML dictionary without saving it. Steering adds open(..., w) and json.dump before returning. The official file-existence/content assertion then passes.',
      '- Shared observation: both interventions replace a short return-only implementation with a multi-statement implementation that performs required response/output operations. This is a hypothesis about implementation elaboration/control-flow structure, not evidence for a universal serialization or file-writing latent.',
      '- Counterevidence/limits: the feature activation mass is dominated by newlines; both outputs still duplicate function definitions. The corrected main bodies are behaviorally more complete, not globally clean outputs. Two successes do not explain the remaining 48 tasks.',
      '- The captured original solutions are short prefixes of the re-extracted alpha-zero completions in these cases. A frozen-text activation at 100% can map to a small percentage of the longer alpha-zero text. Both coordinate systems are reported; no late-activation claim should be made from 100% alone.',
      '- A token state predicts subsequent tokens: activation at the end of the baseline return cannot retrospectively cause earlier edits under activation-gated intervention. Our static intervention is already applied at those earlier positions, so these outcomes do not establish a natural activation-gated mechanism.']
    (OUT/'CODELLAMA_TWO_SUCCESSES.md').write_text('\n'.join(lines)+'\n')
    # Compact side-by-side body panels for the two successes.
    fig,axs=plt.subplots(2,2,figsize=(12,7))
    import textwrap
    for row,r in enumerate(deep):
        for col,kind in enumerate(['baseline_body','steered_body']):
            ax=axs[row,col];ax.set_facecolor('#1E1E2E');ax.set_xticks([]);ax.set_yticks([])
            text='\n'.join(textwrap.fill(s,width=64,replace_whitespace=False,drop_whitespace=False) for s in r[kind].splitlines())
            ax.text(.025,.88,text,transform=ax.transAxes,va='top',fontfamily='monospace',fontsize=9,color='#F38BA8' if col==0 else '#A6E3A1')
            ax.set_title(f"{r['task_id']} · {'merged baseline: FAIL' if col==0 else '4309 / α=−5: PASS'}",color='#D67A16',loc='left',pad=10)
    fig.suptitle('Both CodeLlama successes: restoring required behavior in the main function',fontsize=13)
    fig.text(.5,.02,'Main-function bodies only; full outputs still contain duplicate functions. Test assertions and natural activations are preserved in the accompanying report.',ha='center',fontsize=8)
    fig.subplots_adjust(hspace=.3,bottom=.09);save(fig,'14_codellama_two_successes')
    counts=Counter(r['localization_type'] for r in annotated)
    dump(OUT/'codellama_localization_summary.json',dict(n=50,evidence_tiers=dict(counts),
       independently_human_validated=False,earliest_semantic_error_established=False,
       evaluator_mapping='bigcodebench evaluates code + newline + test_code in __test__.py',
       baseline_eval_sha256=hashlib.sha256(evalpath.read_bytes()).hexdigest()))
    print('LOCALIZATION',dict(counts));print('SUCCESSES',[(r['task_id'],r['captured_evaluated_tokens'],r['natural_activation_tokens']) for r in deep])

if __name__=='__main__':main()
