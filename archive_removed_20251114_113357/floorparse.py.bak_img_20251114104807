#!/usr/bin/env python3

from collections import defaultdict
import re

class FloorParser:

    def __init__(self):
        pass

    def _parse_single_layer(self, floor, z=0):
        grid = []
        portals = defaultdict(list)  # id -> list of (z,i,j)
        for row in floor.split('\n'):
            if not row.strip():
                continue
            sqs = row.split(';')
            rowattrs = []
            for sq in sqs:
                tok = sq.strip()
                if not tok:
                    continue
                parts = [p.strip() for p in tok.split(',') if p.strip()]
                # collect portal tokens like Z1, E2, U3
                for p in list(parts):
                    if re.match(r'^[ZEUP][0-9]+$', p):
                        portals[p].append((z, len(grid), len(rowattrs)))
                        parts.remove(p)
                rowattrs.append(set(parts))
            if rowattrs:
                # print preview first attribute for this row (optional)
                # print(' '.join([list(row)[0] if row else '-' for row in rowattrs]))
                grid.append(rowattrs)
        return grid, portals

    def parse(self, floor):
        '''
        Parses either a single-layer text grid, or a multi-layer file using
        blocks separated by lines starting with '=== LAYER'.
        Tokens:
         - Standard: W,S,B,F,N,P (as before)
         - Vertical connectors: Z<num> / E<num> / U<num> / P<num>
           Any of these create inter-layer links between cells with the same id
           across different layers.
        Returns a graph mapping (z,i,j) or (i,j) -> attrs with 'nbrs' set.
        '''
        floor = floor.replace('\r\n', '\n')
        m = re.split(r'^===\s*LAYER\s*(.*?)\s*===\s*$', floor, flags=re.M)
        # m will be like [before, name1, block1, name2, block2, ...]
        multilayer = len(m) >= 3

        graphs = []
        all_portals = defaultdict(list)
        if multilayer:
            # ignore m[0] (text before first layer)
            for idx in range(1, len(m), 2):
                name = m[idx].strip() or str((idx-1)//2)
                block = m[idx+1]
                grid, portals = self._parse_single_layer(block, z=(idx-1)//2)
                graphs.append(grid)
                for k,v in portals.items():
                    all_portals[k].extend(v)
        else:
            grid, portals = self._parse_single_layer(floor, z=0)
            graphs.append(grid)
            for k,v in portals.items():
                all_portals[k].extend(v)

        # Build graph dict with 4-neighbor links within each layer
        graph = defaultdict(lambda: {'nbrs': set()})
        for z, grid in enumerate(graphs):
            if not grid:
                continue
            R, C = len(grid), len(grid[0])
            for i in range(R):
                for j in range(C):
                    attrs = grid[i][j]
                    # copy standard flags
                    graph_key = (z,i,j) if multilayer else (i,j)
                    for att in 'WSBFNP':
                        graph[graph_key][att] = int(att in attrs)
                    # neighbors within layer
                    for di,dj in ((-1,0),(1,0),(0,-1),(0,1)):
                        i2, j2 = i+di, j+dj
                        if 0 <= i2 < R and 0 <= j2 < C:
                            nbr_key = (z,i2,j2) if multilayer else (i2,j2)
                            graph[graph_key]['nbrs'].add(nbr_key)

        # Connect portals across layers (link all occurrences with the same id)
        for pid, locs in all_portals.items():
            # connect every pair of locations with same portal id
            for a in locs:
                for b in locs:
                    if a == b:
                        continue
                    graph[a]['nbrs'].add(b)

        self.graph = dict(graph.items())
        return self.graph

    def tostr(self, graph):
        '''
        For single-layer graphs. For multi-layer graphs, only layer 0 is shown.
        '''
        # detect if keys are 3D
        sample_key = next(iter(graph))
        if isinstance(sample_key, tuple) and len(sample_key) == 3:
            # show layer 0 only
            layer = 0
            # derive r,c
            r=c=0
            for (z,i,j), attrs in graph.items():
                if z!=layer: continue
                r=max(r,i)
                c=max(c,j)
            r+=1; c+=1
            s=''
            for i in range(r):
                for j in range(c):
                    sq = graph[(layer,i,j)]
                    att = ','.join([a for a in 'BNSFWP' if sq.get(a)])
                    s += '{:>4}'.format(att)
                s+='\n'
            return s
        else:
            r, c = 0, 0
            for loc, attrs in graph.items():
                r = max(r, loc[0])
                c = max(c, loc[1])
            r, c = r+1, c+1
            s = ''
            for r_ in range(r):
                for c_ in range(c):
                    sq = graph[(r_, c_)]
                    att = ','.join([a for a in 'BNSFWP' if sq[a]])
                    s += '{:>4}'.format(att)
                s += '\n'
            return s