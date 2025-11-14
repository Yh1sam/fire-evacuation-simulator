#!/usr/bin/env python3
"""
map_painter.py
A layer-based map drawing tool for evacuation maps, working directly on images.
- Canvas in meters (W,H); fixed scale = 10 pixels per meter.
- Layers: W,S,B,F,P as separate RGBA overlays; base is N (walkable) color.
- Tools: Brush (size in meters), Line, Rectangle, Eraser.
- Undo/Redo: Ctrl+Z / Ctrl+Y (transaction per mouse drag or shape commit).
- Grid overlay: 1 m grid (10 px) for guidance; optional export with grid.
- Save embeds metadata (tile_px=10, meters_per_tile=1.0, width_m, height_m).

Run: python scripts/map_painter.py
"""
import json, math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, Tuple, List
from PIL import Image, ImageDraw, ImageTk
from PIL.PngImagePlugin import PngInfo

TILE_PX = 10  # 10 px == 1 meter
PALETTE = {
    'W': (0,0,0),           # wall
    'N': (191,227,240),     # walkable (base)
    'S': (92,184,92),       # safe
    'B': (33,59,143),       # bottleneck
    'F': (217,83,79),       # fire
    'P': (91,192,222),      # spawn
}
Z_ORDER = ['W','B','S','F','P']  # top-most last in draw order
TOOLS = ['Brush','Line','Rect','Eraser']

class MapPainter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Map Painter (layers, undo) 10 px = 1 m')
        self.geometry('1200x800')
        # state
        self.width_m = tk.IntVar(value=28)
        self.height_m = tk.IntVar(value=15)
        self.brush_m = tk.DoubleVar(value=1.0)
        self.tool = tk.StringVar(value='Brush')
        self.color_key = tk.StringVar(value='W')  # active token layer; 'N' clears overlays
        self.show_grid = tk.BooleanVar(value=True)
        self.snap = tk.BooleanVar(value=True)
        self.include_grid_on_save = tk.BooleanVar(value=False)
        # layers (RGBA)
        self.base = None  # PIL RGB image filled with N
        self.layers: Dict[str, Image.Image] = {}
        self.layer_vis: Dict[str, tk.BooleanVar] = {k: tk.BooleanVar(value=True) for k in Z_ORDER}
        # drawing state
        self.drawers: Dict[str, ImageDraw.ImageDraw] = {}
        self.canvas = None
        self.tkimg = None
        self.img_id = None
        self.overlay_id = None
        self.dragging = False
        self.start_xy = None
        # undo/redo stacks: each op = list of (layer_key, bbox, before_img)
        self.undo_stack: List[List[Tuple[str, Tuple[int,int,int,int], Image.Image]]] = []
        self.redo_stack: List[List[Tuple[str, Tuple[int,int,int,int], Image.Image]]] = []
        self.current_op: List[Tuple[str, Tuple[int,int,int,int], Image.Image]] = None

        self._build_ui()
        self.new_canvas()

    # UI -----------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self); top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        ttk.Label(top, text='Width (m)').pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.width_m, width=6).pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(top, text='Height (m)').pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.height_m, width=6).pack(side=tk.LEFT, padx=(2,8))
        ttk.Button(top, text='New', command=self.new_canvas).pack(side=tk.LEFT, padx=(4,8))
        ttk.Button(top, text='Open PNG', command=self.open_png).pack(side=tk.LEFT)
        ttk.Button(top, text='Save PNG', command=self.save_png).pack(side=tk.LEFT, padx=(4,8))
        ttk.Checkbutton(top, text='Grid', variable=self.show_grid, command=self.redraw).pack(side=tk.LEFT, padx=(8,4))
        ttk.Checkbutton(top, text='Snap', variable=self.snap).pack(side=tk.LEFT)
        ttk.Checkbutton(top, text='Export grid', variable=self.include_grid_on_save).pack(side=tk.LEFT, padx=(8,0))

        tool = ttk.Frame(self); tool.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)
        for tname in TOOLS:
            ttk.Radiobutton(tool, text=tname, value=tname, variable=self.tool).pack(side=tk.LEFT, padx=2)
        ttk.Label(tool, text='Brush (m)').pack(side=tk.LEFT, padx=(12,2))
        ttk.Spinbox(tool, from_=0.1, to=10.0, increment=0.1, textvariable=self.brush_m, width=6).pack(side=tk.LEFT)
        # token selector
        pal = ttk.Frame(self); pal.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)
        ttk.Label(pal, text='Layer/Token:').pack(side=tk.LEFT)
        for k in ['W','N','S','B','F','P']:
            ttk.Radiobutton(pal, text=k, value=k, variable=self.color_key).pack(side=tk.LEFT)
            sw = tk.Canvas(pal, width=22, height=14, highlightthickness=1, highlightbackground='#888'); sw.pack(side=tk.LEFT, padx=(0,8))
            R,G,B = PALETTE[k]; sw.create_rectangle(0,0,22,14, fill=f'#{R:02x}{G:02x}{B:02x}', outline='')

        # layer visibility
        lay = ttk.Frame(self); lay.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)
        ttk.Label(lay, text='Visible:').pack(side=tk.LEFT)
        for k in Z_ORDER:
            ttk.Checkbutton(lay, text=k, variable=self.layer_vis[k], command=self.redraw).pack(side=tk.LEFT, padx=(2,6))

        # canvas
        wrap = ttk.Frame(self); wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, bg='white')
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sx = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self.canvas.xview)
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        sx.pack(side=tk.BOTTOM, fill=tk.X); sy.pack(side=tk.RIGHT, fill=tk.Y)

        # bindings
        self.canvas.bind('<Button-1>', self.on_down)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_up)
        self.bind('<Key>', self.on_key)
        # Ctrl+Z / Ctrl+Y
        self.bind_all('<Control-z>', lambda e: self.undo())
        self.bind_all('<Control-y>', lambda e: self.redo())

    # Canvas / layers -----------------------------------------------------
    def new_canvas(self):
        W = max(1, int(self.width_m.get())) * TILE_PX
        H = max(1, int(self.height_m.get())) * TILE_PX
        self.base = Image.new('RGB', (W,H), PALETTE['N'])
        self.layers = {k: Image.new('RGBA',(W,H),(0,0,0,0)) for k in Z_ORDER}
        self.drawers = {k: ImageDraw.Draw(self.layers[k]) for k in Z_ORDER}
        self.canvas.config(scrollregion=(0,0,W,H))
        self.redraw()

    def open_png(self):
        path = filedialog.askopenfilename(filetypes=[('PNG','*.png'),('All','*')])
        if not path: return
        img = Image.open(path).convert('RGB')
        W,H = img.size
        self.width_m.set(W//TILE_PX); self.height_m.set(H//TILE_PX)
        self.base = Image.new('RGB', (W,H), PALETTE['N'])
        # treat opened image as flattened; put into base then continue editing using layers
        self.base.paste(img)
        self.layers = {k: Image.new('RGBA',(W,H),(0,0,0,0)) for k in Z_ORDER}
        self.drawers = {k: ImageDraw.Draw(self.layers[k]) for k in Z_ORDER}
        self.canvas.config(scrollregion=(0,0,W,H))
        self.redraw()

    def save_png(self):
        path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG','*.png')])
        if not path: return
        composite = self._composite()
        if self.include_grid_on_save.get():
            self._draw_grid_on_image(composite)
        meta = PngInfo(); meta.add_text('map_meta', json.dumps({'tile_px':TILE_PX,'meters_per_tile':1.0,'width_m':int(self.width_m.get()),'height_m':int(self.height_m.get())}))
        composite.save(path, pnginfo=meta)
        messagebox.showinfo('Saved', path)

    # Draw ops + undo -----------------------------------------------------
    def brush_px(self) -> int:
        return max(1, int(round(self.brush_m.get()*TILE_PX)))

    def _snap_xy(self, x,y):
        if not self.snap.get(): return x,y
        s=TILE_PX; return (x//s)*s + s//2, (y//s)*s + s//2

    def _begin_op(self):
        self.current_op = []

    def _record_snapshot(self, layer_key: str, bbox: Tuple[int,int,int,int]):
        # capture region before modification
        L = self.layers[layer_key]
        x0,y0,x1,y1 = bbox
        x0=max(0,x0); y0=max(0,y0); x1=min(L.width-1,max(x0+1,x1)); y1=min(L.height-1,max(y0+1,y1))
        crop = L.crop((x0,y0,x1,y1))
        self.current_op.append((layer_key,(x0,y0,x1,y1),crop))

    def _apply_draw(self, target_key: str, draw_fn, bbox: Tuple[int,int,int,int], clear_others: bool):
        # snapshot regions first
        if clear_others:
            for k in Z_ORDER:
                self._record_snapshot(k, bbox)
        else:
            self._record_snapshot(target_key, bbox)
        # modify
        if clear_others:
            for k in Z_ORDER:
                if k == target_key: continue
                # erase area on other layers
                er = Image.new('RGBA', (bbox[2]-bbox[0], bbox[3]-bbox[1]), (0,0,0,0))
                self.layers[k].paste(er, (bbox[0],bbox[1]))
        # call drawing function on target layer
        draw_fn(self.drawers[target_key])

    def undo(self):
        if not self.undo_stack:
            return
        op = self.undo_stack.pop()
        for layer_key, bbox, before in op:
            self.layers[layer_key].paste(before, (bbox[0],bbox[1]))
        self.redo_stack.append(op)
        self.redraw()

    def redo(self):
        if not self.redo_stack:
            return
        # cannot replay without storing the after-state; easiest: reapply by swapping with current content
        op = self.redo_stack.pop()
        inverse = []
        for layer_key, bbox, before in op:
            L = self.layers[layer_key]
            # snapshot current
            curr = L.crop((bbox[0],bbox[1],bbox[2],bbox[3]))
            inverse.append((layer_key, bbox, curr))
            L.paste(before, (bbox[0],bbox[1]))
        self.undo_stack.append(inverse)
        self.redraw()

    # Mouse ---------------------------------------------------------------
    def on_down(self, e):
        x = int(self.canvas.canvasx(e.x)); y = int(self.canvas.canvasy(e.y)); x,y=self._snap_xy(x,y)
        self.dragging=True; self.start_xy=(x,y); self._begin_op()
        if self.tool.get() in ('Brush','Eraser'):
            self._stroke_to((x,y))

    def on_drag(self, e):
        if not self.dragging: return
        x = int(self.canvas.canvasx(e.x)); y = int(self.canvas.canvasy(e.y)); x,y=self._snap_xy(x,y)
        if self.tool.get() in ('Brush','Eraser'):
            self._stroke_to((x,y))
            self.start_xy=(x,y)
        else:
            self._preview_shape(self.start_xy,(x,y))

    def on_up(self, e):
        if not self.dragging: return
        x = int(self.canvas.canvasx(e.x)); y = int(self.canvas.canvasy(e.y)); x,y=self._snap_xy(x,y)
        if self.tool.get()=='Line':
            self._draw_line(self.start_xy,(x,y), commit=True)
        elif self.tool.get()=='Rect':
            self._draw_rect(self.start_xy,(x,y), commit=True)
        self.dragging=False; self.start_xy=None
        if self.overlay_id is not None:
            self.canvas.delete(self.overlay_id); self.overlay_id=None
        # push op to undo
        if self.current_op:
            self.undo_stack.append(self.current_op); self.current_op=None; self.redo_stack.clear()
        self.redraw()

    # Drawing primitives --------------------------------------------------
    def _stroke_to(self, pt):
        a = self.start_xy; b = pt
        w = self.brush_px()
        x0=min(a[0],b[0]) - w; y0=min(a[1],b[1]) - w; x1=max(a[0],b[0]) + w; y1=max(a[1],b[1]) + w
        bbox = (x0,y0,x1,y1)
        if self.tool.get()=='Eraser' or self.color_key.get()=='N':
            # erase from all overlays
            self._record_snapshot(Z_ORDER[0], bbox)  # record one layer multiple times is OK but we need all; do all
            for k in Z_ORDER[1:]:
                self._record_snapshot(k, bbox)
            for k in Z_ORDER:
                er = Image.new('RGBA', (x1-x0, y1-y0), (0,0,0,0))
                self.layers[k].paste(er, (x0,y0))
        else:
            key = self.color_key.get(); fill = PALETTE[key] + (255,)
            def draw_fn(d): d.line([a,b], fill=fill, width=w)
            self._apply_draw(key, draw_fn, bbox, clear_others=True)
        # live preview update
        self.redraw(partial=True)

    def _draw_line(self, a, b, commit=False):
        w=self.brush_px(); x0=min(a[0],b[0])-w; y0=min(a[1],b[1])-w; x1=max(a[0],b[0])+w; y1=max(a[1],b[1])+w
        bbox=(x0,y0,x1,y1)
        if self.color_key.get()=='N':
            for k in Z_ORDER:
                self._record_snapshot(k, bbox)
                er = Image.new('RGBA',(x1-x0,y1-y0),(0,0,0,0))
                self.layers[k].paste(er, (x0,y0))
        else:
            key=self.color_key.get(); fill=PALETTE[key]+(255,)
            def draw_fn(d): d.line([a,b], fill=fill, width=w)
            self._apply_draw(key, draw_fn, bbox, clear_others=True)
        if not commit:
            self._preview_shape(a,b)

    def _draw_rect(self, a, b, commit=False):
        x0,y0=a; x1,y1=b; x0,x1=sorted((x0,x1)); y0,y1=sorted((y0,y1))
        bbox=(x0,y0,x1,y1)
        if self.color_key.get()=='N':
            for k in Z_ORDER:
                self._record_snapshot(k, bbox)
                er = Image.new('RGBA',(x1-x0,y1-y0),(0,0,0,0))
                self.layers[k].paste(er, (x0,y0))
        else:
            key=self.color_key.get(); fill=PALETTE[key]+(255,)
            def draw_fn(d): d.rectangle([x0,y0,x1,y1], outline=fill, fill=fill, width=0)
            self._apply_draw(key, draw_fn, bbox, clear_others=True)
        if not commit:
            self._preview_shape(a,b)

    def _preview_shape(self, a,b):
        if self.overlay_id is not None: self.canvas.delete(self.overlay_id)
        color = '#%02x%02x%02x' % PALETTE[self.color_key.get()]
        if self.tool.get()=='Line':
            self.overlay_id = self.canvas.create_line(a[0],a[1],b[0],b[1], fill=color, width=self.brush_px())
        elif self.tool.get()=='Rect':
            self.overlay_id = self.canvas.create_rectangle(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]), outline=color, width=2)

    # Rendering -----------------------------------------------------------
    def _composite(self) -> Image.Image:
        img = self.base.copy()
        for k in Z_ORDER:
            if not self.layer_vis[k].get():
                continue
            img.paste(self.layers[k], (0,0), self.layers[k])
        return img

    def _draw_grid_on_image(self, im):
        W,H = im.size; s=TILE_PX
        draw = ImageDraw.Draw(im); g=(0,0,0)
        for x in range(0,W,s): draw.line([(x,0),(x,H-1)], fill=g)
        for y in range(0,H,s): draw.line([(0,y),(W-1,y)], fill=g)

    def redraw(self, partial: bool=False):
        disp = self._composite()
        if self.show_grid.get(): self._draw_grid_on_image(disp)
        self.tkimg = ImageTk.PhotoImage(disp)
        if self.img_id is None:
            self.img_id = self.canvas.create_image(0,0, image=self.tkimg, anchor='nw')
        else:
            self.canvas.itemconfigure(self.img_id, image=self.tkimg)

    # Shortcuts -----------------------------------------------------------
    def on_key(self, e):
        ch = e.keysym.lower()
        if ch=='g': self.show_grid.set(not self.show_grid.get()); self.redraw()
        elif ch=='b': self.tool.set('Brush')
        elif ch=='l': self.tool.set('Line')
        elif ch=='r': self.tool.set('Rect')
        elif ch=='e': self.tool.set('Eraser')
        elif ch in ('plus','equal'): self.brush_m.set(min(10.0, self.brush_m.get()+0.1))
        elif ch in ('minus','underscore'): self.brush_m.set(max(0.1, self.brush_m.get()-0.1))
        elif ch in ('1','2','3','4','5','6'):
            self.color_key.set(['W','N','S','B','F','P'][int(ch)-1])

if __name__=='__main__':
    MapPainter().mainloop()