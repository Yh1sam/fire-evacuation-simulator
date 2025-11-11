import random
from evacuate import FireSim
from person import Person

fs = FireSim('in/twoexitbottleneck.txt', 0, location_sampler=random.choice, verbose=True)
# Build a person at a P cell
p_locs = [loc for loc, a in fs.graph.items() if a.get('P')]
loc = p_locs[0]
print('Using loc', loc)
px = Person(0, rate=1.0, strategy=0.9, loc=loc)

def step_once(px):
    loc = px.loc
    square = fs.graph[loc]
    nbrs = [(coords, fs.graph[coords]) for coords in square['nbrs']]
    # apply same filter as in Person.move
    filtered = [(l,a) for (l,a) in nbrs if not (a.get('W') or a.get('F'))]
    print('nbrs total', len(nbrs), 'passable', len(filtered))
    t = px.move(nbrs)
    print('move returned', t)
    return t

step_once(px)