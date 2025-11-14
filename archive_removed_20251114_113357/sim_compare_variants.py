#!/usr/bin/env python3
import os, math, csv
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
import evacuate, importlib

OUT_DIR = 'out'
N = 7000
SPEED = 0.2
SCALE = 1
SEED = 8675309

os.makedirs(OUT_DIR, exist_ok=True)

try:
    streams = [Generator(PCG64(SEED, i)) for i in range(5)]
except TypeError:
    try:
        from numpy.random import SeedSequence
        sseq = SeedSequence(SEED).spawn(5)
        streams = [Generator(PCG64(s)) for s in sseq]
    except Exception:
        streams = [Generator(PCG64(SEED + i)) for i in range(5)]
loc_strm, strat_strm, rate_strm, pax_strm, fire_strm = streams

location_sampler = loc_strm.choice
strategy_generator = lambda: float(strat_strm.uniform(.5, 1))
rate_generator = lambda: float(max(.1, abs(rate_strm.normal(1, .1))) * SPEED)
person_mover = lambda: float(pax_strm.uniform())
fire_mover = lambda a: fire_strm.choice(a)

cases = [
    dict(name='b02', in_path=os.path.join('in','arena_cshape_120x75_4x4.txt'), bdelay=0.2),
    dict(name='wide3', in_path=os.path.join('in','arena_cshape_120x75_wide3.txt'), bdelay=1.0),
    dict(name='wide3_b02', in_path=os.path.join('in','arena_cshape_120x75_wide3.txt'), bdelay=0.2),
]

curves = []
for case in cases:
    importlib.reload(evacuate); FireSim = evacuate.FireSim; sim = FireSim(case['in_path'], N, location_sampler, strategy_generator,
                  rate_generator, person_mover, fire_mover,
                  fire_rate=2, bottleneck_delay=case['bdelay'],
                  animation_delay=0.0, verbose=False, scale_factor=SCALE,
                  sample_k=0, sample_seed=123, seconds_per_unit=1.0)
    sim.simulate(maxtime=None, spread_fire=False, gui=False)
    et = np.array(sim.exit_times, dtype=float)
    ut, counts = np.unique(et, return_counts=True)
    cum = counts.cumsum()
    avg_exit = float(et.mean())
    last_exit = float(et.max())

    # save per-case figures
    fig, ax = plt.subplots(figsize=(8,4.5), dpi=140)
    ax.step(ut, cum, where='post', linewidth=1.8)
    ax.set_title(f'Evacuation Curve N={N} ({case["name"]})')
    ax.set_xlabel('time (s)'); ax.set_ylabel('# evacuated'); ax.grid(True, alpha=.3)
    ax.set_xlim(0, last_exit*1.02); ax.set_ylim(0, N)
    fig.tight_layout(); fig.savefig(os.path.join(OUT_DIR, f'evac_curve_7000_{case["name"]}.png'))
    plt.close(fig)

    # save heatmap as before
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
    ax.set_title(f'Heatmap N={N} ({case["name"]})')
    ax.set_xlabel('x (col)'); ax.set_ylabel('y (row)')
    fig.tight_layout(); fig.savefig(os.path.join(OUT_DIR, f'heatmap_exit_time_7000_{case["name"]}.png'))
    plt.close(fig)

    # write stats
    with open(os.path.join(OUT_DIR, f'evac_7000_stats_{case["name"]}.txt'), 'w', encoding='ascii') as f:
        f.write(f'Case: {case["name"]}\n')
        f.write(f'Input: {case["in_path"]}\n')
        f.write(f'Bottleneck delay: {case["bdelay"]} s\n')
        f.write(f'Average time to safe: {avg_exit:.3f} s\n')
        f.write(f'Total evacuation time: {last_exit:.3f} s\n')

    curves.append((case['name'], ut, cum))

# overlay comparison
fig, ax = plt.subplots(figsize=(9,5), dpi=150)
colors = dict(b02='#2c7fb8', wide3='#d95f0e')
for name, ut, cum in curves:
    ax.step(ut, cum, where='post', label=name, linewidth=2.0, color=colors.get(name))
ax.set_title(f'Evacuation Curves Comparison N={N}')
ax.set_xlabel('time (s)'); ax.set_ylabel('# evacuated'); ax.grid(True, alpha=.3)
ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(OUT_DIR, 'evac_curve_compare_7000.png'))
print('DONE: wrote compare figure to out/evac_curve_compare_7000.png')




