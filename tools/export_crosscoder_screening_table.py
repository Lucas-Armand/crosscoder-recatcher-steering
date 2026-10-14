#!/usr/bin/env python3
"""Export summary-marked paper table, validating every nomination against CSVs."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

CELLS = ('association_global', 'association_local', 'paired_global', 'paired_local')
REPORTS = {'DeepSeek': 'focused_subtype_screening_dstk100_contamination_119_v1',
           'CodeLlama': 'focused_subtype_screening_codellama_wrong_logic_v1'}
MARKERS = {'max': r'\ast', 'mean': r'\circ', 'active_fraction': r'\bullet'}


def generate(root):
    package = root / 'reproducibility/dstk100_119_v1'
    reference_rows = json.loads((package / 'tables/screening_top10.json').read_text())
    reference = {(r['model'], r['cell'], int(r['rank'])): r for r in reference_rows}
    assert len(reference_rows) == len(reference) == 80
    latex = [r'\begin{table*}[t]', r'\centering', r'\small', r'\setlength{\tabcolsep}{4pt}',
        r'\caption{Top ten features in each screening cell. Entries report feature ID and signed E/V; ranking uses absolute E/V after selecting the strongest activation summary. Superscripts identify that summary: $\ast$ maximum activation, $\circ$ mean activation, and $\bullet$ active fraction. Bold IDs appear in more than one cell within the same model. Deduplicating 40 nominations yields 38 DeepSeek and 32 CodeLlama candidates.}',
        r'\label{tab:crosscoder-screening-top10}', r'\begin{tabular}{@{}rllll@{}}', r'\toprule',
        r'Rank & Association global & Association local & Paired global & Paired local \\', r'\midrule']
    audit = {'validated_nominations': 80, 'comparison_source': 'Original cell CSVs and frozen screening_top10.json',
             'marker_mapping': MARKERS, 'counting_unit': 'Nominations, including duplicate features across cells', 'models': {}}
    for model, folder in REPORTS.items():
        report = root / 'reports' / folder
        selected = {}
        for cell in CELLS:
            all_rows = list(csv.DictReader((report / f'{cell}_absolute.csv').open()))
            assert len(all_rows) >= 10
            assert all(float(a['abs_ev']) >= float(b['abs_ev']) for a, b in zip(all_rows, all_rows[1:]))
            selected[cell] = all_rows[:10]
            for rank, row in enumerate(selected[cell], 1):
                assert int(row['rank']) == rank
                assert row['summary'] in MARKERS
                expected = reference[(model, cell, rank)]
                for field in ('feature_id', 'summary', 'ev', 'abs_ev', 'effect', 'null_sd', 'positive_support', 'minimum_support'):
                    assert row[field] == expected[field], (model, cell, rank, field)
                assert int(row['positive_support']) >= int(row['minimum_support'])
        repeated = Counter(r['feature_id'] for group in selected.values() for r in group)
        expected_unique = 38 if model == 'DeepSeek' else 32
        assert len(repeated) == expected_unique
        title = (r'DeepSeek-Coder: 119 focal improvements vs.\ 96 other improvements' if model == 'DeepSeek'
                 else r'CodeLlama: 50 focal regressions vs.\ 241 other regressions')
        if model == 'CodeLlama':
            latex.append(r'\midrule')
        latex += [r'\multicolumn{5}{@{}l}{\textit{' + title + r'}} \\', r'\addlinespace']
        for rank in range(10):
            entries = []
            for cell in CELLS:
                row = selected[cell][rank]
                feature = row['feature_id']
                if repeated[feature] > 1:
                    feature = r'\textbf{' + feature + '}'
                marker = MARKERS[row['summary']]
                entries.append(feature + '$^{' + marker + '}$ ($' + format(float(row['ev']), '+.2f') + '$)')
            latex.append(str(rank + 1) + ' & ' + ' & '.join(entries) + r' \\')
        counts = Counter(r['summary'] for group in selected.values() for r in group)
        top3 = Counter(r['summary'] for group in selected.values() for r in group[:3])
        assert sum(counts.values()) == 40 and sum(top3.values()) == 12
        audit['models'][model] = {'unique_features': len(repeated),
            'top10_summary_counts': {s: counts[s] for s in MARKERS},
            'top3_summary_counts': {s: top3[s] for s in MARKERS},
            'by_cell': {cell: {'summary_counts': dict(Counter(r['summary'] for r in group)),
                'nominations': [{'rank': int(r['rank']), 'feature_id': int(r['feature_id']),
                                'summary': r['summary'], 'ev': float(r['ev']),
                                'repeated_across_cells': repeated[r['feature_id']] > 1} for r in group]}
                        for cell, group in selected.items()}}
    assert audit['models']['DeepSeek']['top10_summary_counts'] == {'max': 35, 'mean': 1, 'active_fraction': 4}
    assert audit['models']['CodeLlama']['top10_summary_counts'] == {'max': 0, 'mean': 16, 'active_fraction': 24}
    latex += [r'\bottomrule', r'\end{tabular}', r'\end{table*}']
    table = package / 'tables/screening_top10_annotated.tex'
    audit_path = package / 'tables/screening_summary_audit.json'
    table.write_text('\n'.join(latex) + '\n')
    audit_path.write_text(json.dumps(audit, indent=2) + '\n')
    return table, audit_path


def refresh_checksums(root, additions):
    path = root / 'reproducibility/dstk100_119_v1/checksums.json'
    existing = json.loads(path.read_text())
    for relative in {*existing, *(str(p.relative_to(root)) for p in additions)}:
        digest = hashlib.sha256()
        with (root / relative).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        existing[relative] = digest.hexdigest()
    path.write_text(json.dumps(dict(sorted(existing.items())), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-checksums', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = generate(root)
    if args.refresh_checksums:
        refresh_checksums(root, [*files, Path(__file__).resolve()])
    print('Validated all 80 nominations and exported the annotated LaTeX table.')


if __name__ == '__main__':
    main()
