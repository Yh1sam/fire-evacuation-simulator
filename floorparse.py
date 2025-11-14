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
    def parse_image(self, path, palette=None):
        '''
        Parse a PNG/JPG image as a single-layer grid.
        Each pixel is treated as one cell (0.5m x 0.5m in your physical model).
        Colors are mapped to tokens W/N/S/B/F/P/Z by nearest color distance.
        If PNG has a 'map_meta' text chunk with cell_px>1, we average blocks of
        that many pixels per cell instead.
        '''
        try:
            from PIL import Image
        except Exception as e:
            raise RuntimeError('Pillow is required to read PNG maps: '+str(e))
        DEFAULT_PAL = {

            'W': (0, 0, 0),
            'N': (191, 227, 240),
            'S': (92, 184, 92),
            'B': (33, 59, 143),
            'F': (217, 83, 79),
            'P': (91, 192, 222),
            'Z': (153, 0, 153),
        }
        if palette:
            pal.update(palette)
        img = Image.open(path).convert('RGB')
        W, H = img.size
        cell_px = 1
        # optional metadata
        meta = getattr(img, "text", {}) or getattr(img, "info", {})
        if 'map_meta' in meta:
            try:
                import json as _json
                m = _json.loads(meta['map_meta'])
                if 'cell_px' in m:
                    cell_px = max(1, int(m['cell_px']))
                elif 'tile_px' in m:
                    cell_px = max(1, int(m['tile_px']))
            except Exception:
                cell_px = 1
        from math import gcd
        if (W % cell_px != 0) or (H % cell_px != 0):
            g = gcd(W, H) or 1
            cell_px = g
        R, C = H//cell_px, W//cell_px
        px = img.load()
        def block_avg(i,j):
            rs=gs=bs=0; cnt=0
            for di in range(cell_px):
                for dj in range(cell_px):
                    r,g,b = px[j*cell_px+dj, i*cell_px+di]
                    rs+=r; gs+=g; bs+=b; cnt+=1
            return (rs//cnt, gs//cnt, bs//cnt)
        def nearest_token(rgb):
            r,g,b = rgb; best="N"; bestd=10**12
            for t,(Rr,Gg,Bb) in pal.items():
                d=(r-Rr)*(r-Rr)+(g-Gg)*(g-Gg)+(b-Bb)*(b-Bb)
                if d<bestd: bestd=d; best=t
            return best
        from collections import defaultdict
        graph = defaultdict(lambda: {'nbrs': set()})
        for i in range(R):
            for j in range(C):
                tok = nearest_token(block_avg(i,j))
                for att in "WSBFNPZ":
                    graph[(i,j)][att] = int(att == tok)
        for i in range(R):
            for j in range(C):
                for di,dj in ((-1,0),(1,0),(0,-1),(0,1)):
                    i2, j2 = i+di, j+dj
                    if 0 <= i2 < R and 0 <= j2 < C:
                        graph[(i,j)]['nbrs'].add((i2,j2))
        self.graph = dict(graph.items())
        return self.graph
