"""Empirical token-distance distribution, with explicit out-of-view counts."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'
OUT = REPORTS / 'overleaf_sections67_68_20261022_v1/crosscoder_case_studies/figures'
ds = json.loads((REPORTS / 'deepseek4810_marker_followup_20261022_v1/natural_task_positions.json').read_text())
cl = json.loads((REPORTS / 'codellama4309_same_text_tables_20261022_v2/task_temporal_relations.json').read_text())
d = np.array([r['activation_minus_marker_tokens'] for r in ds])
assert len(d) == 119 and d.max() == 1
plt.rcParams.update({'font.size': 9, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
fig, (ax, bx) = plt.subplots(1, 2, figsize=(9, 3.6))
edges = np.arange(-25.5, 26.5, 1)
counts, _ = np.histogram(d, bins=edges)
centers = (edges[1:] + edges[:-1]) / 2
ax.fill_between(centers, 100 * counts / len(d), color='#7654cf', alpha=.22, step='mid')
ax.plot(centers, 100 * counts / len(d), color='#7654cf', lw=1.7, drawstyle='steps-mid')
ax.axvline(0, color='#333333', ls='--', lw=1, label='Behavioral marker (0)')
ax.set(xlim=(-25.5, 25.5), xticks=np.arange(-25, 26, 5), ylabel='Tasks (%)', xlabel='First activation minus marker (tokens)')
ax.set_title('DeepSeek 4810: empirical distribution', color='#7654cf', fontsize=10)
ax.text(.03, .95, f'Median: {np.median(d):.0f} tokens\nMean: {d.mean():.1f} tokens\n27/119 tasks below −25\nFull range: −268 to +1', transform=ax.transAxes, va='top', fontsize=8)
ax.text(.98, .95, 'n = 119\n1-token bins', transform=ax.transAxes, va='top', ha='right', fontsize=8)
ax.grid(axis='y', alpha=.15)
keys = ['before', 'same_token_or_within_region', 'after', 'not_observed_or_unmapped']
cc = [sum(r['relation'] == k for r in cl) for k in keys]
assert cc == [14, 27, 3, 6]
bx.bar(range(4), cc, color=['#a84608', '#d67a16', '#efa454', '#f7cf9c'])
bx.set_xticks(range(4), ['Before', 'Within', 'After', 'Unavailable'])
bx.set_ylabel('Tasks')
bx.set_title('CodeLlama 4309: localized failure region', color='#d67a16', fontsize=10)
for i, v in enumerate(cc):
    bx.text(i, v + .5, str(v), ha='center', fontsize=9)
bx.set_ylim(0, max(cc) + 6)
bx.grid(axis='y', alpha=.15)
fig.tight_layout(pad=1.3)
OUT.mkdir(parents=True, exist_ok=True)
for ext in ['png', 'pdf', 'svg']:
    fig.savefig(OUT / f'temporal_relation_to_behavior_v3.{ext}', dpi=300, bbox_inches='tight', facecolor='white')
print('Exported temporal_relation_to_behavior_v3: PNG, PDF, SVG')
