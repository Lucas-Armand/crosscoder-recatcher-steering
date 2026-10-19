#!/usr/bin/env python3
"""Single-file, auditable review of all 50 CodeLlama failure localizations."""
import csv
import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path
import numpy as np
from transformers import AutoTokenizer

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reports/section67_semantic_temporal_20261019_v1'
DEST=ROOT/'reports/CODELLAMA_4309_ALL_50_ANNOTATED_PTBR.md'

def main():
    loc=json.loads((SRC/'codellama_error_localization.json').read_text())
    arrays=np.load(SRC/'codellama_feature_activations.npz')
    source={}
    p=ROOT/'reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv'
    for r in csv.DictReader(p.open()):
        if r['benchmark']=='bigcodebench':source[r['task_id']]=r['merged_code']
    tok=AutoTokenizer.from_pretrained('meta-llama/CodeLlama-7b-hf',use_fast=True,local_files_only=True)
    tier={'runtime_execution_sites':'Local de execução confirmado pelo traceback; não necessariamente a primeira causa.',
          'probable_line':'Linha proposta pela inspeção do código e dos testes; sem validação humana independente.',
          'probable_region':'Trecho proposto pela inspeção do código e dos testes; sem validação humana independente.',
          'omission_region':'Região associada a uma operação ausente; não existe necessariamente uma linha que lança o erro. Localização provisória.'}
    out=['# CodeLlama — feature 4309: os 50 casos anotados','',
         'Todos os casos são regressões BigCodeBench: base passa e merged falha. O código mostrado é a solução merged efetivamente avaliada no baseline α=0, incluindo o prompt quando presente.','',
         '## Como ler','',
         '- `=>` abre e `<=` fecha a região localizada, inclusive quando ocupa uma única linha.',
         '- `*` INSERIDO marca o início do primeiro token com ativação natural positiva da 4309. O token exato, sua representação escapada e a linha/coluna estão registrados antes de cada código. Asteriscos originalmente presentes no Python NÃO são marcadores; use a linha/coluna informada para identificar o inserido.',
         '- Para um token newline, o asterisco aparece no final da linha anterior: a ativação foi medida no estado desse newline, depois de a expressão anterior já ter sido emitida.',
         '- Números à esquerda são linhas da solução original, antes das anotações. O código anotado não deve ser executado.',
         '- A região é uma linha/intervalo relacionado à falha, NÃO um primeiro erro semântico comprovado. Racionais e evidências de cada caso estão abaixo. Não houve validação humana independente das regiões propostas.',
         '- Ativações são medições offline do CrossCoder compartilhado sobre o texto merged congelado. A posição é transferida por blocos de caracteres exatamente iguais para a solução reextraída atual. Não são medições online do modelo sob steering; tokens do prompt não foram analisados.',
         '- Sem ativação no texto capturado e ativação sem alinhamento são situações diferentes, explicitadas caso a caso. Não inventamos um asterisco para casos sem alinhamento.','',
         '## Proveniência','',
         '`reports/section67_semantic_temporal_20261019_v1/codellama_error_localization.json` (regiões, soluções e evidências); `codellama_feature_activations.npz` (tokens, offsets e ativações); `reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv` (texto congelado).',
         '',f"SHA-256 localizações: `{hashlib.sha256((SRC/'codellama_error_localization.json').read_bytes()).hexdigest()}`",'',
         'Alinhamento: `difflib.SequenceMatcher(..., autojunk=False)`; exige correspondência exata do início do token e verifica separadamente o span inteiro. Nenhuma nova geração ou avaliação foi executada.','',
         '## Índice','']
    out += [f"- [{r['task_id']}](#caso-{r['task_id'].split('/')[-1]})" for r in loc]
    counts=Counter()
    for r in loc:
        tid=r['task_id'];ident=tid.split('/')[-1];key=ident+'__codellama_merged';code=r['code'];frozen=source[tid]
        z=arrays[key+'__z'];ids=arrays[key+'__ids'];offsets=arrays[key+'__offsets'];active=np.flatnonzero(z>0)
        char=None;full=False;tokeninfo=None
        if len(active):
            j=int(active[0]);lo,hi=map(int,offsets[j]);tokeninfo=dict(index=j,token_id=int(ids[j]),decoded=tok.decode([int(ids[j])]),source_span=frozen[lo:hi],value=float(z[j]),lo=lo,hi=hi)
            for b in difflib.SequenceMatcher(None,frozen,code,autojunk=False).get_matching_blocks():
                if b.a<=lo<b.a+b.size:
                    char=b.b+lo-b.a;full=hi<=b.a+b.size;break
        out += ['',f'<a id="caso-{ident}"></a>',f'## {tid}','',
                f"**Região:** linhas {r['solution_line_start']}–{r['solution_line_end']}.",
                f"**Tipo de evidência:** {tier[r['localization_type']]}",'',
                '**Racional específico da escolha (nota original de inspeção):** '+r['note'],'',
                'A escolha é apoiada pelo trecho da implementação e pelas falhas oficiais reproduzidas abaixo; não exclui outros erros ou regiões relevantes.']
        if not len(active):
            counts['inactive']+=1;out += ['','**Primeira ativação:** não observada nos tokens de código capturados. Nenhum `*` inserido.']
        else:
            out += ['',f"**Token natural:** índice {tokeninfo['index']} (zero-based), ID {tokeninfo['token_id']}, decodificado `{json.dumps(tokeninfo['decoded'],ensure_ascii=False)}`; texto coberto `{json.dumps(tokeninfo['source_span'],ensure_ascii=False)}`; ativação {tokeninfo['value']:.6f}."]
            if char is None:
                counts['unmapped']+=1;out+=['','**Alinhamento indisponível:** há ativação no texto congelado, mas seu início não pertence a um bloco exato preservado no código abaixo. Nenhum `*` inserido. Não interpretar como inatividade.',
                    '','Contexto no texto congelado (não é o código reextraído mostrado abaixo):','```text',frozen[max(0,tokeninfo['lo']-100):tokeninfo['lo']]+'*'+frozen[tokeninfo['lo']:tokeninfo['hi']+100],'```']
            else:
                counts['mapped']+=1;line=code.count('\n',0,char)+1;col=char-(code.rfind('\n',0,char)+1)+1
                out+=['',f'**Asterisco inserido:** linha {line}, coluna {col} do código original (ambas 1-based). Span inteiro preservado: {"sim" if full else "não; apenas início alinhado"}.']
        out+=['','### Solução merged anotada','```text']
        offset=0
        for n,s in enumerate(code.splitlines(keepends=True),1):
            marked=s
            if char is not None and offset<=char<offset+len(s):marked=s[:char-offset]+'*'+s[char-offset:]
            marked=marked.rstrip('\n\r')
            out.append(f"{n:04d} | "+('=> ' if n==r['solution_line_start'] else '   ')+marked+(' <=' if n==r['solution_line_end'] else ''))
            offset+=len(s)
        out+=['```','','### Evidência da avaliação oficial','',
              'Os tracebacks abaixo podem incluir linhas dos testes oficiais. Somente os frames dentro de `task_func` foram usados como locais de execução da solução.','```text']
        out += [test+'\n'+str(error) for test,error in r['failing_tests'].items()]
        out+=['```']
    assert len(loc)==50 and counts=={'mapped':43,'inactive':6,'unmapped':1},counts
    out+=['','## Conferência final','',f'50 casos; {counts["mapped"]} marcadores de ativação alinhados; {counts["inactive"]} casos sem ativação no código capturado; {counts["unmapped"]} com ativação não alinhada.']
    DEST.write_text('\n'.join(out)+'\n')
    print(DEST,counts,DEST.stat().st_size)

if __name__=='__main__':main()
