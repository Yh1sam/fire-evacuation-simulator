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
        Each pixel is treated as one logical cell (0.5m x 0.5m in our model).
        Colors are mapped to tokens by nearest color distance.

        Supported tokens (by color):
          W,N,S,B,F,P as usual, and stairs-related tokens:
          SD = stairs down area, SU = stairs up area,
          TD = teleport down,  TU = teleport up.

        Stairs tokens are exposed as boolean attributes SD/SU/TD/TU on each
        cell, in addition to the standard WSBFNP flags.
        '''
        try:
            from PIL import Image
        except Exception as e:
            raise RuntimeError('Pillow is required to read PNG maps: '+str(e))

        DEFAULT_PAL = {
            'W':  (0, 0, 0),
            'N':  (191, 227, 240),
            'S':  (92, 184, 92),
            'B':  (33, 59, 143),
            'F':  (217, 83, 79),
            'P':  (91, 192, 222),
            'SD': (127, 59, 8),
            'SU': (179, 88, 6),
            'TD': (1, 102, 94),
            'TU': (53, 151, 143),
        }
        pal = dict(DEFAULT_PAL)
        if palette:
            pal.update(palette)

        img = Image.open(path).convert('RGB')
        W, H = img.size
        cell_px = 1
        # optional metadata (allows grouping pixels into larger cells)
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
                d = (r-Rr)*(r-Rr) + (g-Gg)*(g-Gg) + (b-Bb)*(b-Bb)
                if d < bestd:
                    bestd, best = d, t
            return best

        graph = defaultdict(lambda: {'nbrs': set()})
        for i in range(R):
            for j in range(C):
                tok = nearest_token(block_avg(i,j))
                attrs = graph[(i,j)]
                # standard flags
                for att in "WSBFNP":
                    attrs[att] = int(att == tok)
                # stairs-related flags; keep them as extra booleans
                for att in ("SD","SU","TD","TU"):
                    attrs[att] = int(att == tok)
        # neighbors (4-connected)
        for i in range(R):
            for j in range(C):
                for di,dj in ((-1,0),(1,0),(0,-1),(0,1)):
                    i2, j2 = i+di, j+dj
                    if 0 <= i2 < R and 0 <= j2 < C:
                        graph[(i,j)]['nbrs'].add((i2,j2))
        self.graph = dict(graph.items())
        return self.graph

    def parse_image_folder(self, folder, palette=None):
        '''
        Parse all floor*.png images in a folder as a multi-floor grid.
        Returns a graph with keys (z,i,j):
          z = floor index (0-based, ordered by floor_index metadata or filename)
          i,j = row, col within that floor.

        Stairs-related tokens use the SD/SU/TD/TU attributes per cell.
        Vertical connectivity:
          - TD at floor z connects to cell at same (i,j) on floor z-1 (if exists)
          - TU at floor z connects to cell at same (i,j) on floor z+1 (if exists)
        Edges are undirected (added in both directions).
        '''
        import os
        try:
            from PIL import Image
        except Exception as e:
            raise RuntimeError('Pillow is required to read PNG maps: '+str(e))

        # discover floor images
        files = []
        for name in os.listdir(folder):
            if name.lower().endswith('.png'):
                files.append(os.path.join(folder, name))
        if not files:
            raise FileNotFoundError(f'No PNG floors found in folder: {folder}')

        # helper to extract floor index from metadata / filename
        def floor_index_for(path):
            idx = None
            try:
                img = Image.open(path)
                meta = getattr(img, "text", {}) or getattr(img, "info", {})
                if 'map_meta' in meta:
                    import json as _json
                    m = _json.loads(meta['map_meta'])
                    idx = int(m.get('floor_index', 0))
            except Exception:
                idx = None
            if idx is not None:
                return idx
            # fallback: parse floorN from filename
            base = os.path.basename(path)
            m = re.search(r'floor(\\d+)', base, flags=re.I)
            if m:
                return int(m.group(1))
            return 0

        files_sorted = sorted(files, key=floor_index_for)
        # reindex floors as 0..Z-1
        floor_paths = [(z, p) for z, p in enumerate(files_sorted)]

        # colour palette consistent with parse_image
        DEFAULT_PAL = {
            'W':  (0, 0, 0),
            'N':  (191, 227, 240),
            'S':  (92, 184, 92),
            'B':  (33, 59, 143),
            'F':  (217, 83, 79),
            'P':  (91, 192, 222),
            'SD': (127, 59, 8),
            'SU': (179, 88, 6),
            'TD': (1, 102, 94),
            'TU': (53, 151, 143),
        }
        pal = dict(DEFAULT_PAL)
        if palette:
            pal.update(palette)

        # first pass: read token grids per floor
        floors = {}
        for z, path in floor_paths:
            img = Image.open(path).convert('RGB')
            W, H = img.size
            cell_px = 1
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
                    d = (r-Rr)*(r-Rr) + (g-Gg)*(g-Gg) + (b-Bb)*(b-Bb)
                    if d < bestd:
                        bestd, best = d, t
                return best

            grid = [[nearest_token(block_avg(i,j)) for j in range(C)]
                    for i in range(R)]
            floors[z] = grid

        # helper: load room definitions per floor
        def _load_rooms_for_floor(folder_path, floor_index):
            """
            Expect optional text file floor{floor_index+1}_rooms.txt with lines:
            room_id name r0 c0 r1 c1
            name should be a single token (no spaces); if spaces are needed,
            they can be encoded with underscores.
            """
            import os as _os
            rooms = []
            fname = _os.path.join(folder_path, f"floor{floor_index+1}_rooms.txt")
            if not _os.path.exists(fname):
                return rooms
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) < 6:
                            continue
                        rid = parts[0]
                        name = parts[1]
                        try:
                            r0 = int(parts[2]); c0 = int(parts[3])
                            r1 = int(parts[4]); c1 = int(parts[5])
                        except ValueError:
                            continue
                        rooms.append((rid, name, r0, c0, r1, c1))
            except Exception:
                return rooms
            return rooms

        # second pass: build multi-floor graph
        graph = defaultdict(lambda: {'nbrs': set()})
        Z = len(floors)
        for z, grid in floors.items():
            R, C = len(grid), len(grid[0])
            for i in range(R):
                for j in range(C):
                    tok = grid[i][j]
                    attrs = graph[(z,i,j)]
                    # standard flags
                    for att in "WSBFNP":
                        attrs[att] = int(att == tok)
                    # stairs flags
                    for att in ("SD","SU","TD","TU"):
                        attrs[att] = int(att == tok)
                    # neighbors within same floor
                    for di,dj in ((-1,0),(1,0),(0,-1),(0,1)):
                        i2, j2 = i+di, j+dj
                        if 0 <= i2 < R and 0 <= j2 < C:
                            graph[(z,i,j)]['nbrs'].add((z,i2,j2))

        # vertical connectivity using TD/TU
        for z, grid in floors.items():
            R, C = len(grid), len(grid[0])
            for i in range(R):
                for j in range(C):
                    tok = grid[i][j]
                    key = (z,i,j)
                    # teleport down to floor z-1
                    if tok == 'TD' and z-1 in floors:
                        tgt = (z-1, i, j)
                        graph[key]['nbrs'].add(tgt)
                        graph[tgt]['nbrs'].add(key)
                    # teleport up to floor z+1
                    if tok == 'TU' and z+1 in floors:
                        tgt = (z+1, i, j)
                        graph[key]['nbrs'].add(tgt)
                        graph[tgt]['nbrs'].add(key)

        # third pass: assign room ids/names from optional room definition files
        for z in floors.keys():
            rooms = _load_rooms_for_floor(folder, z)
            if not rooms:
                continue
            for rid, name, r0, c0, r1, c1 in rooms:
                rr0, rr1 = sorted((r0, r1))
                cc0, cc1 = sorted((c0, c1))
                for i in range(rr0, rr1+1):
                    for j in range(cc0, cc1+1):
                        key = (z, i, j)
                        if key not in graph:
                            continue
                        attrs = graph[key]
                        attrs['room'] = rid
                        attrs['room_name'] = name

        self.graph = dict(graph.items())
        return self.graph
