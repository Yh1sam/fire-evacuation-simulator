#!/usr/bin/env python3
import os, math, csv
import numpy as np
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
from numpy.random import Generator
try:
    from randomgen import PCG64  # if available
except Exception:
    from numpy.random import PCG64

import sys, os
# add project root to path so 'evacuate.py' is importable when running from scripts dir
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from evacuate import FireSim

IN_PATH = os.path.join('in', 'arena_cshape_120x75_wide3.txt')
OUT_DIR = 'out'
N = 7000
SCALE = 1
SPEED = 0.2
SEED = 8675309
BDELAY = 0.2

os.makedirs(OUT_DIR, exist_ok=True)

# Set up RNG streams like evacuate.main does
# We generate 5 independent streams derived from a base seed for reproducibility
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

# Run the simulation
sim = FireSim(IN_PATH, N, location_sampler, strategy_generator, rate_generator,
              person_mover, fire_mover, fire_rate=2, bottleneck_delay=BDELAY,
              animation_delay=0.0, verbose=False, scale_factor=SCALE,
              sample_k=0, sample_seed=123, seconds_per_unit=1.0)

# No GUI, fire disabled as walls inside simulate()
sim.simulate(maxtime=None, spread_fire=False, gui=False)

# Collect results
exit_times = np.array(sim.exit_times, dtype=float)
if exit_times.size == 0:
    raise SystemExit('No exit_times recorded; simulation may have failed')

avg_exit = float(exit_times.mean())
last_exit = float(exit_times.max())

# 1) Evacuation curve: #evacuated vs time (step function)
# Aggregate by unique time points
ut, counts = np.unique(exit_times, return_counts=True)
cum = counts.cumsum()
fig, ax = plt.subplots(figsize=(8,4.5), dpi=140)
ax.step(ut, cum, where='post', color='#2c7fb8', linewidth=1.8)
ax.set_title(f'Evacuation Curve (N={N})')
ax.set_xlabel('time (s)')
ax.set_ylabel('# evacuated')
ax.grid(True, alpha=.3)
ax.set_xlim(0, last_exit*1.02)
ax.set_ylim(0, N)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'evac_curve_7000.png'))
plt.close(fig)

# 2) Heatmap: average exit time by starting cell
H, W = int(sim.r), int(sim.c)
sum_grid = np.zeros((H, W), dtype=float)
count_grid = np.zeros((H, W), dtype=int)
for p in sim.people:
    if getattr(p, 'safe', False):
        i, j = map(int, p.start_loc)
        if 0 <= i < H and 0 <= j < W:
            sum_grid[i, j] += float(p.exit_time)
            count_grid[i, j] += 1

with np.errstate(invalid='ignore', divide='ignore'):
    avg_grid = np.where(count_grid>0, sum_grid/np.maximum(count_grid,1), np.nan)

fig, ax = plt.subplots(figsize=(7.5,4.7), dpi=150)
# mask NaNs to white
cmap = plt.cm.inferno
cmap.set_bad(color='white')
im = ax.imshow(avg_grid, origin='upper', cmap=cmap)
cb = fig.colorbar(im, ax=ax)
cb.set_label('avg exit time (s)')
ax.set_title(f'Exit Time Heatmap (start cell, N={N})')
ax.set_xlabel('x (col)')
ax.set_ylabel('y (row)')
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'heatmap_exit_time_7000.png'))
plt.close(fig)

# 3) Write logs and CSV
with open(os.path.join(OUT_DIR, 'evac_7000_stats.txt'), 'w', encoding='ascii') as f:
    f.write(f'Total people: {N}\n')
    f.write(f'# safe: {sim.numsafe}\n')
    f.write(f'# dead: {sim.numpeople - sim.numsafe - sim.nummoving}\n')
    f.write(f'Average time to safe: {avg_exit:.3f} s\n')
    f.write(f'Total evacuation time (last exit): {last_exit:.3f} s\n')

with open(os.path.join(OUT_DIR, 'evac_7000_times.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['id','start_i','start_j','exit_time_s'])
    for p in sim.people:
        if getattr(p, 'safe', False):
            i, j = map(int, p.start_loc)
            w.writerow([p.id, i, j, float(p.exit_time)])

print(f'Average exit time: {avg_exit:.3f} s')
print(f'Total evacuation time: {last_exit:.3f} s')
print('DONE')
print('Curve  :', os.path.join(OUT_DIR, 'evac_curve_7000.png'))
print('Heatmap:', os.path.join(OUT_DIR, 'heatmap_exit_time_7000.png'))
print('Stats  :', os.path.join(OUT_DIR, 'evac_7000_stats.txt'))
print('CSV    :', os.path.join(OUT_DIR, 'evac_7000_times.csv'))










