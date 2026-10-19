#!/usr/bin/env python3
"""Preserve the original review and append all subsequent 4309 analyses."""
import json,hashlib,re,subprocess,textwrap
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
OUT=REPORTS/'section67_consolidated_review_20261019_v2'
OLD=REPORTS/'section67_semantic_temporal_20261019_v1'
HYP=REPORTS/'codellama4309_behavior_hypothesis_20261019_v1'
CHG=REPORTS/'codellama4309_change_comparison_20261019_v1'
TMP=REPORTS/'codellama4309_temporal_precedence_20261019_v1'
VIS=REPORTS/'codellama4309_temporal_return_visuals_20261019_v1'
def read(p):return json.loads(p.read_text())
def npages(p):return int(re.search(r'Pages:\s+(\d+)',subprocess.check_output(['pdfinfo',str(p)],text=True)).group(1))
def page(title,subtitle=''):
    fig=plt.figure(figsize=(13.3,8));fig.text(.055,.94,title,fontsize=21,weight='bold',va='top')
    if subtitle:fig.text(.055,.885,subtitle,fontsize=10,color='#555555',va='top')
    fig.text(.055,.025,'CrossCoder / ReCatcher | internal exploratory review | 2026-10-19 | no new inference',fontsize=8,color='#666666')
    return fig
def paras(fig,blocks,y=.79,width=140,size=12,gap=.045,line_step=.028,head_step=.038):
    for head,body in blocks:
        fig.text(.06,y,head,fontsize=size+1,weight='bold',va='top');y-=head_step
        wrapped=textwrap.fill(body,width=width)
        fig.text(.06,y,wrapped,fontsize=size,va='top',linespacing=1.45)
        y-=(wrapped.count('\n')+1)*line_step+gap
    return y
def table(fig,headers,rows,box,fontsize=10,colwidths=None):
    ax=fig.add_axes(box);ax.axis('off');t=ax.table(cellText=rows,colLabels=headers,cellLoc='left',loc='center',colWidths=colwidths)
    t.auto_set_font_size(False);t.set_fontsize(fontsize);t.scale(1,1.5)
    for (r,c),cell in t.get_celld().items():
        cell.set_edgecolor('#dddddd')
        if r==0:cell.set_facecolor('#263448');cell.set_text_props(color='white',weight='bold')
        elif r%2:cell.set_facecolor('#f1f3f6')
    return t
def emit(pdf,fig):pdf.savefig(fig);plt.close(fig)
def codepanel(fig,box,title,code,color='#e0e4ee',limit=14):
    ax=fig.add_axes(box);ax.set_facecolor('#1e2230');ax.set_xticks([]);ax.set_yticks([])
    ax.set_title(title,loc='left',fontsize=11,color='#b26611',pad=9)
    lines=code.splitlines() or ['[No executable statement after the docstring]']
    if len(lines)>limit:lines=lines[:limit-2]+['... [display excerpt; full source in companion report]']+lines[-1:]
    wrapped=[]
    for s in lines:wrapped.extend(textwrap.wrap(s,width=66,replace_whitespace=False,drop_whitespace=False) or [''])
    ax.text(.025,.95,'\n'.join(wrapped),ha='left',va='top',color=color,fontsize=9,fontfamily='monospace',transform=ax.transAxes)

def main():
    OUT.mkdir(parents=True,exist_ok=True);plt.rcParams.update({'pdf.fonttype':42,'font.size':11})
    rows=read(CHG/'task_arm_comparison.json');target={r['task_id']:r for r in rows if r['kind']=='target'}
    timing={r['task_id']:r for r in read(TMP/'task_temporal_relations.json')}
    structural=read(HYP/'intervention_behavior_details.json');ret=[r for r in structural if r['kind']=='target' and r['before'].get('return_only')]
    summaries=read(CHG/'SUMMARY.json')
    with PdfPages(OUT/'02_UPDATED_FINDINGS.pdf') as pdf:
        fig=page('What differs from shuffled directions at magnitude five?','4309 alpha -5 versus three shuffled decoder directions at alpha -5 | same 50 failing merged tasks')
        fields=['changed','main_body_ast_changed','passed','fewer_failing_but_not_passed','more_failing_tests','return_only_expanded','value_return_lost']
        labels=['Changed programs','Changed main-body AST','Official fail-to-pass','Fewer failures, still fail','More failures','Return-only expansion','Explicit value-return lost']
        selected=[summaries[0]]+[r for r in summaries if r['arm'].endswith('neg5') and r['kind']=='shuffle']
        table(fig,['Observation','4309','Shuffle 1','Shuffle 2','Shuffle 3'],[[lab]+[str(s[f]) for s in selected] for f,lab in zip(fields,labels)],[.06,.29,.88,.48],fontsize=12)
        paras(fig,[('Interpretation','More edits or longer programs are not specific to the target. Its two official corrections (/183 and /490) are absent from all six shuffle arms; partial improvements also occur under controls. Counts are exploratory, not an independent confirmatory comparison.')],y=.22,width=135,size=11)
        emit(pdf,fig)
        fig=page('All 27 changed target programs','Uniform saved-evaluation / AST comparison at alpha -5. Test-count direction is descriptive, not a semantic correctness score.')
        changed=[r for r in target.values() if r['changed']];changed.sort(key=lambda r:int(r['task_id'].split('/')[-1]))
        rr=[]
        for r in changed:
            b,a=r['failing_or_blocked_tests_before'],r['failing_or_blocked_tests_after']
            rr.append([r['task_id'].replace('BigCodeBench',''), 'PASS' if r['passed'] else 'FAIL', 'yes' if r['main_body_ast_changed'] else 'no',f'{b} -> {a}',r['relation'] if 'relation' in r else timing[r['task_id']]['relation'].replace('same_token_or_within_region','within').replace('not_observed_or_unmapped','unavailable')])
        t=table(fig,['Task','Outcome','Main AST changed','Failing tests','First activation vs region'],rr,[.07,.1,.86,.73],fontsize=9)
        t.scale(1,.75)
        fig.text(.07,.075,'Of 25 changed but still-failing outputs: 2 have fewer recorded failures, 4 more, 19 the same count.',fontsize=10)
        emit(pdf,fig)
        fig=page('Does natural activation explain a general omission pattern?','Original base-generated versus merged-generated texts | same shared CrossCoder feature | 50 regression pairs')
        table(fig,['Structural indicator','Passing base /50','Failing merged /50'],[
            ['Return-only main function','1','7'],['No explicit value return','3','17'],['Potential fallthrough (proxy)','4','23'],['Mean activation, task average','0.1997','0.1979']],[.07,.53,.86,.25],fontsize=12)
        paras(fig,[('Outside the two discovery examples','Among the other 48 tasks, only four newly become return-only. Their paired activation contrast versus the other 44 has E/V +0.015 (mean), -0.527 (max), +0.841 (active fraction). These results do not strongly support a general incomplete-implementation detector; the positive group is small.'),
            ('Scope and confounding','The 48-task subset is not an independent held-out dataset. Mean activation correlates with newline density (Spearman about 0.35). Return-only and no-value-return are not automatic failure labels: legitimate passing implementations can have either structure.')],y=.45,width=143,size=11)
        emit(pdf,fig)
        fig=page('All seven failing return-only implementations','Feature 4309, continuous steering alpha -5 | expansion does not imply correction')
        rr=[]
        for r in ret:
            tid=r['task_id'];tr=target[tid]
            effect='Expanded' if r['expands_return_only'] else 'Return removed' if r['return_only_to_empty_body'] else 'Main body unchanged'
            rr.append([tid.replace('BigCodeBench',''),str(r['before']['all_statements'])+' -> '+str(r['after']['all_statements']),effect,'PASS' if r['passed'] else 'FAIL','inactive' if not timing[tid]['active'] else 'within return region'])
        table(fig,['Task','AST statements','Observed change','Outcome','Natural first activation'],rr,[.06,.39,.88,.39],fontsize=11)
        paras(fig,[('Three expansions, two repairs','/183 restores response handling and UUID header; /490 restores JSON persistence. /634 expands into repetitive chain assignments and remains wrong.'),
            ('Three unchanged bodies and one deterioration','/357 is unchanged entirely; /371 and /738 change outside the main body only. /931 loses its return and retains no executable body beyond the docstring.')],y=.30,width=145,size=11)
        emit(pdf,fig)
        fig=page('What the temporal evidence does - and does not - establish','Natural activation is not the same thing as a continuous additive intervention')
        paras(fig,[('Observed timing','First mapped activation: 13 before the localized region, 27 within it, 3 after, 7 unavailable (6 inactive in captured code, 1 unaligned). Regions mix runtime execution sites, provisional lines/intervals and omission regions; they are not validated first semantic errors.'),
            ('The corrected tasks','In /183 and /490 the first natural activation is the newline after the already-emitted return expression. Continuous steering changes the earlier return-versus-assignment decision. The direction has causal leverage, but these observations do not establish that natural activation at that newline caused the original omission.'),
            ('The return-newline preference','Activation occurs on 49/51 return-ending newline tokens in merged text (96.1%), versus 92/327 other newline tokens (28.1%). Passing base text also shows this preference: 48/53 (90.6%) versus 127/403 (31.5%). This is not an error-specific detector.'),
            ('The most defensible reading','A shared sparse direction associated with line/return boundaries can cause specific implementation repairs, but also neutral and harmful rewrites. Neither a universal error detector nor a general natural mediator has been established.')],y=.80,width=140,size=11)
        emit(pdf,fig)
    with PdfPages(OUT/'03_CODE_CASES.pdf') as pdf:
        for title,ids in [('Both official corrections',['BigCodeBench/183','BigCodeBench/490']),('Failed expansion and removal',['BigCodeBench/634','BigCodeBench/931'])]:
            fig=page(title,'Exact evaluated main-function bodies before and after continuous 4309 steering at alpha -5; snippets are not full programs.')
            for i,tid in enumerate(ids):
                r=target[tid];y=.52-i*.35
                codepanel(fig,[.05,y,.44,.27],tid+' | merged baseline FAIL',r['before_main'],limit=11)
                codepanel(fig,[.52,y,.44,.27],tid+' | steering '+('PASS' if r['passed'] else 'FAIL'),r['after_main'],color='#a6e3a1' if r['passed'] else '#f3b5aa',limit=11)
            emit(pdf,fig)
        fig=page('Return-only failures that did not expand','All three main-function bodies below remain exactly unchanged at alpha -5.')
        for i,tid in enumerate(['BigCodeBench/357','BigCodeBench/371','BigCodeBench/738']):
            codepanel(fig,[.07,.60-i*.22,.86,.15],tid+' | '+('entire evaluated code unchanged' if not target[tid]['changed'] else 'changes outside main function only'),target[tid]['before_main'])
        emit(pdf,fig)
    parts=[('Original visual review (preserved)',OLD/'SECTION67_VISUAL_REVIEW.pdf'),
           ('Updated findings and complete change tables',OUT/'02_UPDATED_FINDINGS.pdf'),
           ('Exploratory behavior hypothesis figures',HYP/'BEHAVIOR_HYPOTHESIS_REVIEW.pdf'),
           ('Uniform target / shuffle comparison',CHG/'01_target_shuffle_change_comparison.pdf'),
           ('Temporal regions, return-newline statistics and eight examples',VIS/'VISUAL_REVIEW.pdf'),
           ('Code before / after and unchanged counterexamples',OUT/'03_CODE_CASES.pdf')]
    offset=3;toc=[]
    for title,p in parts:
        n=npages(p);toc.append((title,offset,offset+n-1,p));offset+=n
    with PdfPages(OUT/'00_COVER_AND_GUIDE.pdf') as pdf:
        fig=page('Semantic and temporal review - consolidated V2','DeepSeek 4810 + CodeLlama 4309 | original figures retained; new discussion and 4309 analyses appended')
        paras(fig,[('Purpose','An internal evidence review for choosing what belongs in the paper and slides. This is not a finished manuscript narrative. Existing results, counterexamples and limitations are intentionally retained.'),
            ('What is new','Comparison of all 27 changed CodeLlama target outputs with six shuffled-direction arms; structural hypotheses on natural base/merged texts; temporal localization across 50 regressions; return-newline preference; eight activation examples; all seven return-only cases, including unchanged and worsened implementations.'),
            ('How to read older pages','The first 14 original pages are preserved without modification. Where later pages add nuance, use the newer analysis: return-newline preference is not error specificity, and continuous steering does not establish mediation by late natural activation.'),
            ('Data scope','DeepSeek: 119 contamination improvements; CodeLlama: 50 logic/runtime regressions. Main report doses are 0 to 5. No new inference, generation, training or benchmark evaluation was performed for this compilation.')],y=.79,width=140,size=11)
        emit(pdf,fig)
        fig=page('Reading guide and reproducibility','All page ranges refer to this consolidated PDF.')
        table(fig,['Section','Pages'],[[title,f'{a}-{b}'] for title,a,b,_ in toc],[.06,.43,.88,.36],fontsize=11,colwidths=[.85,.15])
        paras(fig,[('All 50 annotated programs','reports/CODELLAMA_4309_ALL_50_ANNOTATED_PTBR.md contains complete code with => / <= error regions, * first-activation marker, original line numbers, rationale and evaluator evidence.'),
            ('Natural capture versus intervention baseline','Frozen captured code differs from currently re-extracted alpha-zero code in some cases. Activation anchors are aligned by exact matching blocks. Offline shared-latent activation is not an online per-model measurement; prompt activations were excluded.'),
            ('Controls and experimental status','Three negative shuffled arms form the primary same-sign comparison; positive arms are sensitivity checks. Random CrossCoder latents are distinct from shuffled decoder coordinates. Current interpretations are exploratory on selected cohorts, without independent held-out validation.')],y=.38,width=175,size=9,gap=.02,line_step=.021,head_step=.028)
        emit(pdf,fig)
    final=OUT/'SECTION67_CONSOLIDATED_VISUAL_REVIEW_V2.pdf'
    inputs=[OUT/'00_COVER_AND_GUIDE.pdf']+[p for _,p in parts]
    subprocess.run(['pdfunite',*[str(p) for p in inputs],str(final)],check=True)
    expected=offset-1;assert npages(final)==expected
    manifest=dict(output=final.name,pages=expected,original_preserved=True,new_inference=False,
        inputs=[dict(path=str(p.relative_to(ROOT)),pages=npages(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in inputs],
        sections=[dict(title=t,start=a,end=b) for t,a,b,_ in toc])
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'README.md').write_text('# Consolidated semantic / temporal visual review V2\n\n'+
        f'`{final.name}`: {expected} pages. Preserves the prior 14-page review and appends every subsequent 4309 analysis discussed. No inference or manuscript/deck changes.\n\n'+
        '\n'.join(f'- Pages {a}-{b}: {title}.' for title,a,b,_ in toc)+'\n\n'+
        'See MANIFEST.json for exact input PDF hashes and page counts. The annotated 50-case Markdown is linked from the reading guide. Regenerate with `.venv/bin/python tools/build_section67_consolidated_review_v2.py`.\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
