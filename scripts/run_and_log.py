#!/usr/bin/env python3
"""
scripts/run_and_log.py
Run evacuate.py with given args and write full stdout to a single text file.
Also forces SAMPLE to include all safe agents by setting --sample-k to a large number unless overridden.

Usage:
  python scripts/run_and_log.py -i in_or_png -n 90 --scale 6 --speed 6 -a 0.03 -o out\run.txt
"""
import argparse, shlex, subprocess, sys, os, datetime

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-i','--input', required=True)
    ap.add_argument('-n','--numpeople', type=int, required=True)
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--speed', type=float, default=1.0)
    ap.add_argument('-a','--animation-delay', type=float, default=0.05)
    ap.add_argument('--extra', type=str, default='', help='extra args to pass to evacuate.py as raw string')
    ap.add_argument('-o','--out', required=True, help='path to txt to write full output')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)

    cmd = [sys.executable, 'evacuate.py', '-i', args.input, '-n', str(args.numpeople),
           '--scale', str(args.scale), '--speed', str(args.speed), '-a', str(args.animation_delay),
           '--sample-k', '100000']
    if args.extra:
        cmd += shlex.split(args.extra)
    print('Running:', ' '.join(shlex.quote(c) for c in cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(proc.stdout)
    print('WROTE', args.out)

if __name__ == '__main__':
    main()