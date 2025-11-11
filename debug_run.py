import random
from evacuate import FireSim

fs = FireSim('in/twoexitbottleneck.txt', 10, location_sampler=random.choice, verbose=True)

# schedule like simulate() but don't run yet
for i, p in enumerate(fs.people):
    fs.sim.sched(fs.update_person, i, offset=1/p.rate)
fs.sim.sched(fs.update_bottlenecks, offset=fs.bottleneck_delay)

print('Before run:')
fs.sim.show_calendar()

fs.sim.run()

print('After run: now', fs.sim.now)
print('numsafe', fs.numsafe, 'nummoving', fs.nummoving, 'numdead', fs.numdead)