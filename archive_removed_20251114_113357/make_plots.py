#!/usr/bin/env python3
import os, csv, argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from numpy.random import Generator
try:
    from randomgen import PCG64
except Exception:
    from numpy.random import PCG64

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from evacuate import FireSim

def run_case(in_path, N, speed, bdelay, scale, seed, tag, start_delay_dist='none', start_delay=0.0, start_delay_std=0.0):
    try:
        streams = [Generator(PCG64(seed, i)) for i in range(5)]
    except TypeError:
        try:
            from numpy.random import SeedSequence
            sseq = SeedSequence(seed).spawn(5)
            streams = [Generator(PCG64(s)) for s in sseq]
        except Exception:
            streams = [Generator(PCG64(seed + i)) for i in range(5)]
    loc_strm, strat_strm, rate_strm, pax_strm, fire_strm = streams[:5]

    location_sampler = loc_strm.choice
    strategy_generator = lambda: float(strat_strm.uniform(.5, 1))
    rate_generator = lambda: float(max(.1, abs(rate_strm.normal(1, .1))) * speed)
    person_mover = lambda: float(pax_strm.uniform())
    fire_mover = lambda a: fire_strm.choice(a)
    delay_strm = streams[0]  # reuse a stream for delays

    # start delay generator
    if start_delay_dist == 'exp' and start_delay > 0:
        sdg = lambda: float(max(0.0, delay_strm.exponential(start_delay)))
    elif start_delay_dist == 'normal' and start_delay > 0:
        sd = max(start_delay_std, 1e-6)
        sdg = lambda: float(max(0.0, delay_strm.normal(start_delay, sd)))
    else:
        sdg = lambda: 0.0

    sim = FireSim(in_path, N, location_sampler, strategy_generator, rate_generator,
                  person_mover, fire_mover, fire_rate=2, bottleneck_delay=bdelay,
                  animation_delay=0.0, verbose=False, scale_factor=scale,
                  sample_k=0, sample_seed=123, seconds_per_unit=1.0, start_delay_generator=sdg)
    sim.simulate(maxtime=None, spread_fire=False, gui=False)

    out_dir = 'out'
    os.makedirs(out_dir, exist_ok=True)

    exit_times = np.array(sim.exit_times, dtype=float)
    avg_exit = float(exit_times.mean())
    last_exit = float(exit_times.max())

    ut, counts = np.unique(exit_times, return_counts=True)
    cum = counts.cumsum()
    fig, ax = plt.subplots(figsize=(8,4.5), dpi=140)
    ax.step(ut, cum, where='post', color='#2c7fb8', linewidth=1.9)
    ax.set_title(f'Evacuation Curve (N={N}, tag={tag})')
    ax.set_xlabel('time (s)'); ax.set_ylabel('# evacuated'); ax.grid(True, alpha=.3)
    ax.set_xlim(0, last_exit*1.02); ax.set_ylim(0, N)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, f'evac_curve_{tag}.png'))
    plt.close(fig)

    H, W = int(sim.r), int(sim.c)
    sum_grid = np.zeros((H,W), float); count_grid = np.zeros((H,W), int)
    for p in sim.people:
        if getattr(p, 'safe', False):
            i,j = map(int, p.start_loc)
            if 0 <= i < H and 0 <= j < W:
                sum_grid[i,j] += float(p.exit_time); count_grid[i,j] += 1
    with np.errstate(invalid='ignore', divide='ignore'):
        avg_grid = np.where(count_grid>0, sum_grid/np.maximum(count_grid,1), np.nan)
    fig, ax = plt.subplots(figsize=(7.5,4.7), dpi=150)
    cmap = plt.cm.inferno; cmap.set_bad(color='white')
    im = ax.imshow(avg_grid, origin='upper', cmap=cmap)
    fig.colorbar(im, ax=ax).set_label('avg exit time (s)')
    ax.set_title(f'Exit Time Heatmap (N={N}, tag={tag})')
    ax.set_xlabel('x (col)'); ax.set_ylabel('y (row)')
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, f'heatmap_exit_time_{tag}.png'))
    plt.close(fig)

    with open(os.path.join(out_dir, f'evac_stats_{tag}.txt'), 'w', encoding='ascii') as f:
        f.write(f'Input: {in_path}\n')
        f.write(f'N: {N}\n')
        f.write(f'speed: {speed}\n')
        f.write(f'bottleneck_delay: {bdelay}\n')
        f.write(f'Average time to safe: {avg_exit:.3f} s\n')
        f.write(f'Total evacuation time: {last_exit:.3f} s\n')

    with open(os.path.join(out_dir, f'evac_times_{tag}.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['id','start_i','start_j','exit_time_s'])
        for p in sim.people:
            if getattr(p, 'safe', False):
                i, j = map(int, p.start_loc)
                w.writerow([p.id, i, j, float(p.exit_time)])

    print(f'DONE tag={tag}: avg={avg_exit:.3f}s last={last_exit:.3f}s')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('-i','--input', default=os.path.join('in','arena_cshape_120x75_wide3.txt'))
    ap.add_argument('-n','--num', type=int, default=7000)
    ap.add_argument('--speed', type=float, default=0.2)
    ap.add_argument('-b','--bdelay', type=float, default=0.2)
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--seed', type=int, default=8675309)
    ap.add_argument('--tag', default=None)
    ap.add_argument('--start-delay-dist', choices=['none','exp','normal'], default='none')
    ap.add_argument('--start-delay', type=float, default=0.0)
    ap.add_argument('--start-delay-std', type=float, default=0.0)
    args = ap.parse_args()
    tag = args.tag or f"n{args.num}_b{args.bdelay}_s{args.speed}"
    run_case(args.input, args.num, args.speed, args.bdelay, args.scale, args.seed, tag, args.start_delay_dist, args.start_delay, args.start_delay_std)



