#!/usr/bin/env python3
"""
image_map_io.py
- Render grid maps to an image (PNG) using a fixed palette
- Scan an image (with solid-colored tiles) back into the simulator text format

Usage examples
  Render: python scripts/image_map_io.py render -i in/basic_six_offices_hallway.txt -o out/map.png -t 16
  Scan  : python scripts/image_map_io.py scan   -i out/map.png -o in/from_img.txt -t 16 --spawn keep

Notes
- The scanner expects each tile to be uniformly filled with one palette color.
- If --tile is omitted, the script tries to auto-detect a tile size that evenly
  divides the image and yields nearly-uniform blocks (tries 1..64).
- Palette can be overridden via --palette JSON (keys: W,S,B,F,P,N -> hex colors).
"""
import os, sys, json, math, argparse
from typing import Tuple, Dict, List
from PIL import Image

# Default color palette (RGB)
DEFAULT_PALETTE = {
    'W': (0, 0, 0),           # wall black
    'N': (191, 227, 240),     # walkable light-blue
    'S': (92, 184, 92),       # safe green
    'B': (33, 59, 143),       # bottleneck navy
    'F': (217, 83, 79),       # fire red
    'P': (91, 192, 222),      # spawn cyan
}
TOKEN_ORDER = ['W','S','B','F','P','N']

# Helpers

def hex_to_rgb(h: str) -> Tuple[int,int,int]:
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0,2,4))

def load_palette(path: str=None) -> Dict[str,Tuple[int,int,int]]:
    pal = dict(DEFAULT_PALETTE)
    if path:
        with open(path,'r',encoding='utf-8') as f:
            data = json.load(f)
        for k,v in data.items():
            if isinstance(v, str): v = hex_to_rgb(v)
            pal[k] = tuple(map(int, v))
    return pal

def nearest_token(rgb: Tuple[int,int,int], pal: Dict[str,Tuple[int,int,int]]) -> str:
    r,g,b = rgb
    best = None; bestd = 1e18
    for t, (R,G,B) in pal.items():
        d = (r-R)*(r-R) + (g-G)*(g-G) + (b-B)*(b-B)
        if d < bestd:
            bestd, best = d, t
    return best

# Render: text -> image

def read_text_grid(path: str) -> List[List[List[str]]]:
    grid: List[List[List[str]]] = []
    with open(path, 'r', encoding='utf-8') as f:
        for raw in f.read().replace('\r\n','\n').split('\n'):
            row = [tok.strip() for tok in raw.split(';') if tok.strip()]
            if not row: continue
            grid.append([cell.split(',') for cell in row])
    return grid

def grid_dims(G) -> Tuple[int,int]:
    r = len(G); c = max((len(row) for row in G), default=0)
    return r, c

def render_text_to_image(in_txt: str, out_png: str, tile: int, palette: Dict[str,Tuple[int,int,int]], draw_grid: bool=False):
    G = read_text_grid(in_txt)
    R,C = grid_dims(G)
    if R==0 or C==0:
        raise SystemExit('Empty grid: '+in_txt)
    W,H = C*tile, R*tile
    img = Image.new('RGB', (W,H), (255,255,255))
    px = img.load()
    # main cells
    for i in range(R):
        for j in range(C):
            toks = set(x for x in G[i][j] if x)
            t = 'N'
            for k in TOKEN_ORDER:
                if k in toks: t = k; break
            color = palette.get(t, palette['N'])
            for di in range(tile):
                for dj in range(tile):
                    px[j*tile+dj, i*tile+di] = color
    # \n# optional grid lines
    if draw_grid and tile >= 3:
        gcol = (0,0,0)
        # horizontal lines
        for i in range(R+1):
            y = i*tile
            if y >= H: y = H-1
            for x in range(W):
                px[x, y] = gcol
        # vertical lines
        for j in range(C+1):
            x = j*tile
            if x >= W: x = W-1
            for y in range(H):
                px[x, y] = gcol
    os.makedirs(os.path.dirname(out_png) or '.', exist_ok=True)
    img.save(out_png)
    return out_png

# Scan: image -> text

def autodetect_tile(img: Image.Image, max_tile: int=64, tol: float=4.0) -> int:
    W,H = img.size
    # try divisors up to max_tile (prefer larger tiles but minimal size that passes)
    candidates = [s for s in range(1, max_tile+1) if W % s == 0 and H % s == 0]
    if not candidates: return 1
    px = img.load()
    for s in sorted(candidates):
        R, C = H//s, W//s
        ok = True
        # sample a few random blocks and check near-uniformity
        step_r = max(1, R//8); step_c = max(1, C//8)
        for i in range(0, R, step_r):
            for j in range(0, C, step_c):
                # center color
                ci, cj = i*s + s//2, j*s + s//2
                r0,g0,b0 = px[cj, ci]
                # compare 8 points around center
                for di in (-s//2, 0, s//2):
                    for dj in (-s//2, 0, s//2):
                        ii = min(H-1, max(0, i*s + s//2 + di))
                        jj = min(W-1, max(0, j*s + s//2 + dj))
                        r,g,b = px[jj, ii]
                        if (r-r0)**2 + (g-g0)**2 + (b-b0)**2 > tol*tol:
                            ok = False; break
                    if not ok: break
            if not ok: break
        if ok:
            return s
    return 1

def scan_image_to_text(in_png: str, out_txt: str, tile: int=None, palette: Dict[str,Tuple[int,int,int]]=None, spawn: str='keep'):
    palette = palette or DEFAULT_PALETTE
    img = Image.open(in_png).convert('RGB')
    W,H = img.size
    if tile is None:
        tile = autodetect_tile(img)
    R, C = H//tile, W//tile
    px = img.load()

    def block_color(i,j):
        # average color of the block
        rs=gs=bs=0; cnt=0
        for di in range(tile):
            for dj in range(tile):
                r,g,b = px[j*tile+dj, i*tile+di]
                rs+=r; gs+=g; bs+=b; cnt+=1
        return (rs//cnt, gs//cnt, bs//cnt)

    rows: List[str] = []
    has_p = False
    for i in range(R):
        toks_row: List[str] = []
        for j in range(C):
            rgb = block_color(i,j)
            t = nearest_token(rgb, palette)
            if spawn == 'all' and t in ('N','S'):
                t = f'{t},P'
                has_p = True
            elif 'P' in t:
                has_p = True
            toks_row.append(t)
        rows.append(';'.join(toks_row))
    if spawn == 'keep' and not has_p:
        print('WARN: no P (spawn) tiles detected. Use --spawn all if desired.', file=sys.stderr)
    os.makedirs(os.path.dirname(out_txt) or '.', exist_ok=True)
    with open(out_txt, 'w', encoding='ascii') as f:
        f.write('\n'.join(rows))
    return out_txt

# CLI

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    ap_pal = lambda p: p.add_argument('--palette', type=str, default=None, help='path to JSON palette (keys W,S,B,F,P,N -> hex)')

    p1 = sub.add_parser('render', help='text -> image')
    p1.add_argument('-i','--in', dest='in_path', required=True)
    p1.add_argument('-o','--out', dest='out_path', required=True)
    p1.add_argument('-t','--tile', type=int, default=16)
    p1.add_argument('--grid', action='store_true')
    ap_pal(p1)

    p2 = sub.add_parser('scan', help='image -> text')
    p2.add_argument('-i','--in', dest='in_path', required=True)
    p2.add_argument('-o','--out', dest='out_path', required=True)
    p2.add_argument('-t','--tile', type=int, default=None, help='tile size (auto if omitted)')
    p2.add_argument('--spawn', choices=['keep','all','none'], default='keep', help='add P to walkable tiles (all/keep/none)')
    ap_pal(p2)

    args = ap.parse_args()
    pal = load_palette(args.palette)

    if args.cmd == 'render':
        out = render_text_to_image(args.in_path, args.out_path, args.tile, pal, draw_grid=args.grid)
        print('WROTE', out)
    elif args.cmd == 'scan':
        out = scan_image_to_text(args.in_path, args.out_path, args.tile, pal, spawn=args.spawn)
        print('WROTE', out)

if __name__ == '__main__':
    main()
