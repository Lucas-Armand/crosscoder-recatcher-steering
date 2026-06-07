#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results-dir', required=True)
    ap.add_argument('--backup', action='store_true', default=True)
    args = ap.parse_args()
    root = Path(args.results_dir)
    root.mkdir(parents=True, exist_ok=True)

    for path in sorted(root.glob('*.jsonl')):
        rows = []
        seen = set()
        total = 0
        skipped = 0
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                row = json.loads(line)
                key = row.get('run_id') or (
                    row.get('benchmark'), row.get('model_label'), row.get('task_id'), row.get('gen_idx')
                )
                if key in seen:
                    skipped += 1
                    continue
                seen.add(key)
                rows.append(row)
        if skipped:
            backup = path.with_suffix(path.suffix + '.bak_dedup')
            if args.backup and not backup.exists():
                path.rename(backup)
            with path.open('w') as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(path.name, 'before:', total, 'after:', len(rows), 'removed:', skipped,
              'tokens:', dict(Counter(r.get('generated_tokens') for r in rows).most_common(5)))


if __name__ == '__main__':
    main()
