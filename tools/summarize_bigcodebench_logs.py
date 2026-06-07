#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log-dir', required=True)
    args = ap.parse_args()
    total_n = 0
    weighted = 0.0
    for p in sorted(Path(args.log_dir).glob('*.log')):
        txt = p.read_text(errors='ignore')
        m = re.search(r'Reading samples\.\.\.\s*(\d+)it', txt)
        if not m:
            m = re.search(r'(\d+)it \[', txt)
        n = int(m.group(1)) if m else None
        m2 = re.search(r'pass@1:\s*([0-9.]+)', txt)
        status_ok = 'Traceback' not in txt
        if n and m2:
            pass1 = float(m2.group(1))
            total_n += n
            weighted += n * pass1
            print(p.name, 'n=', n, 'pass@1=', pass1, 'ok=', status_ok)
        else:
            print(p.name, 'SKIP/INCOMPLETE', 'ok=', status_ok)
    print('total_n=', total_n)
    print('weighted_pass@1=', weighted / total_n if total_n else None)


if __name__ == '__main__':
    main()
