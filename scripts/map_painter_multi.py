#!/usr/bin/env python3
"""
map_painter_multi.py
Multi-floor, cell-based map editor for the evacuation simulator.

- Logical grid: each cell represents 0.5 m x 0.5 m.
- Resolution is fixed in cells; display size is controlled by a zoom factor
  (pixels per cell) so you can freely zoom the canvas without changing
  the underlying map.
- Tokens (per cell):
    W = wall
    N = walkable (normal)
    S = safe / exit
    B = bottleneck / door
    F = fire
    P = spawn point
    Z = stairs / vertical connector between floors
- Tools:
    Brush, Line, Rect, Eraser ? all operate at cell granularity. A cell is
    either filled with a token or set to N; no half-cells.
- Multi-floor:
    Add / delete floors; spinbox and external label show "Floor X".
- Export:
    Prompt for a map name and write PNGs to maps/{name}/floor1.png,
    maps/{name}/floor2.png, ...
    Each PNG is (#cols x #rows) pixels, one pixel per cell, with a map_meta
    JSON chunk containing cell_px=1 and meters_per_cell=0.5.

Run:
    python scripts/map_painter_multi.py
"""
import os
import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox
from dataclasses import dataclass, field
from typing import List
from PIL import Image, ImageTk
from PIL.PngImagePlugin import PngInfo

CELL_METERS = 0.5  # each cell is 0.5m x 0.5m
TOKENS = ['W','N','S','B','F','P','Z']
PALETTE = {
    'W': '#000000',     # wall
    'N': '#BFE3F0',     # walkable
    'S': '#5CB85C',     # safe
    'B': '#213B8F',     # bottleneck / door
    'F': '#D9534F',     # fire
    'P': '#5BC0DE',     # spawn
    'Z': '#990099',     # stairs / connector
}

@dataclass
class FloorGrid:
    rows: int
    cols: int
    cells: List[List[str]] = field(init=False)
    undo: List[List[tuple]] = field(default_factory=list)  # list of ops; op = [(r,c,old,new)]
    redo: List[List[tuple]] = field(default_factory=list)

    def __post_init__(self):
        self.cells = [['N' for _ in range(self.cols)] for _ in range(self.rows)]

class MapPainter(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title('Multi-Floor Cell Map Painter (0.5m per cell)')
        self.geometry('1280x840')

        # parameters
        self.width_m = tk.IntVar(value=28)
        self.height_m = tk.IntVar(value=15)
        self.zoom = tk.IntVar(value=24)  # pixels per cell for display
        self.tool = tk.StringVar(value='Brush')
        self.token = tk.StringVar(value='W')
        self.current_floor = tk.IntVar(value=1)
        self.show_grid = tk.BooleanVar(value=True)

        # model
        self.floors: List[FloorGrid] = []

        # ui state
        self.canvas: tk.Canvas | None = None
        self.canvas_img = None
        self.dragging = False
        self.start_cell: tuple[int,int] | None = None
        self.ruler_start: tuple[int,int] | None = None  # last mousedown cell

        self._build_ui()
        self.new_document()

    # ---- UI ----
    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text='Width (m)').pack(side=tk.LEFT)
        ttk.Entry(top, width=6, textvariable=self.width_m).pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(top, text='Height (m)').pack(side=tk.LEFT)
        ttk.Entry(top, width=6, textvariable=self.height_m).pack(side=tk.LEFT, padx=(2,8))
        ttk.Button(top, text='New', command=self.new_document).pack(side=tk.LEFT, padx=(4,8))
        ttk.Button(top, text='Save Map?', command=self.save_map).pack(side=tk.LEFT, padx=(4,8))

        ttk.Label(top, text='Zoom (px/cell)').pack(side=tk.LEFT, padx=(12,2))
        ttk.Spinbox(top, from_=8, to=64, increment=2, textvariable=self.zoom,
                    command=self.redraw, width=5).pack(side=tk.LEFT)
        ttk.Checkbutton(top, text='Grid', variable=self.show_grid,
                        command=self.redraw).pack(side=tk.LEFT, padx=(8,2))

        # floor controls
        fl = ttk.Frame(self)
        fl.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)
        ttk.Button(fl, text='Prev', command=lambda: self.step_floor(-1)).pack(side=tk.LEFT)
        ttk.Button(fl, text='Next', command=lambda: self.step_floor(+1)).pack(side=tk.LEFT, padx=(2,8))
        ttk.Button(fl, text='Add Floor', command=self.add_floor).pack(side=tk.LEFT)
        ttk.Button(fl, text='Delete Floor', command=self.delete_floor).pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(fl, text='Floor').pack(side=tk.LEFT)
        ttk.Spinbox(fl, from_=1, to=99, width=4, textvariable=self.current_floor,
                    command=self.redraw).pack(side=tk.LEFT)

        titlebar = ttk.Frame(self)
        titlebar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0,4))
        self.floor_label = ttk.Label(titlebar, text='Floor 1', font=('Arial',14,'bold'))
        self.floor_label.pack(side=tk.LEFT)
        # ruler feedback (distance between last mousedown cell and current cursor cell)
        self.ruler_label = ttk.Label(titlebar, text='Ruler: -', font=('Arial',10))
        self.ruler_label.pack(side=tk.LEFT, padx=(16,0))

        tools = ttk.Frame(self)
        tools.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)
        # tools: Brush, Line, Rect (filled), RectO (outline), Eraser
        for t in ['Brush', 'Line', 'Rect', 'RectO', 'Eraser']:
            ttk.Radiobutton(tools, text=t, value=t,
                            variable=self.tool).pack(side=tk.LEFT)

        pal = ttk.Frame(self)
        pal.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)
        ttk.Label(pal, text='Token').pack(side=tk.LEFT)
        for k in TOKENS:
            ttk.Radiobutton(pal, text=k, value=k, variable=self.token).pack(side=tk.LEFT)
            sw = tk.Canvas(pal, width=22, height=14, highlightthickness=1,
                           highlightbackground='#888')
            sw.pack(side=tk.LEFT, padx=(0,8))
            sw.create_rectangle(0,0,22,14, fill=PALETTE[k], outline='')

        wrap = ttk.Frame(self)
        wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(wrap, bg='white')
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sx = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self.canvas.xview)
        sy = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        sx.pack(side=tk.BOTTOM, fill=tk.X)
        sy.pack(side=tk.RIGHT, fill=tk.Y)

        # events
        self.canvas.bind('<Button-1>', self.on_down)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_up)
        self.bind('<Key>', self.on_key)
        self.bind_all('<Control-z>', lambda e: self.undo())
        self.bind_all('<Control-y>', lambda e: self.redo())

    # ---- floor management ----
    def _cells_dims(self) -> tuple[int,int]:
        cols = max(1, int(self.width_m.get()/CELL_METERS))
        rows = max(1, int(self.height_m.get()/CELL_METERS))
        return rows, cols

    def new_document(self) -> None:
        rows, cols = self._cells_dims()
        self.floors = [FloorGrid(rows, cols)]
        self.current_floor.set(1)
        self._update_scroll_region()
        self.redraw()

    def add_floor(self) -> None:
        if not self.floors:
            self.new_document(); return
        rows, cols = self.floors[0].rows, self.floors[0].cols
        self.floors.append(FloorGrid(rows, cols))
        self.current_floor.set(len(self.floors))
        self.redraw()

    def delete_floor(self) -> None:
        if len(self.floors) <= 1:
            messagebox.showinfo('Info', 'At least one floor is required.')
            return
        idx = self._current_index()
        self.floors.pop(idx)
        self.current_floor.set(min(len(self.floors), idx+1))
        self._update_scroll_region()
        self.redraw()

    def step_floor(self, d:int) -> None:
        if not self.floors: return
        n = len(self.floors)
        i = ((self._current_index() + d) % n) + 1
        self.current_floor.set(i)
        self.redraw()

    def _current_index(self) -> int:
        if not self.floors:
            return 0
        try:
            i = int(self.current_floor.get())
        except Exception:
            i = 1
        i = max(1, min(len(self.floors), i))
        if i != self.current_floor.get():
            self.current_floor.set(i)
        return i-1

    # ---- canvas helpers ----
    def _update_scroll_region(self) -> None:
        if not self.floors or not self.canvas:
            return
        rows, cols = self.floors[0].rows, self.floors[0].cols
        s = max(1, int(self.zoom.get()))
        self.canvas.config(scrollregion=(0,0, cols*s, rows*s))

    def cell_from_xy(self, x:float, y:float):
        s = max(1, int(self.zoom.get()))
        col = int(x//s)
        row = int(y//s)
        if not self.floors:
            return None
        rows, cols = self.floors[0].rows, self.floors[0].cols
        if 0 <= row < rows and 0 <= col < cols:
            return row, col
        return None

    # ---- mouse / drawing ----
    def on_down(self, e):
        if not self.floors: return
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)
        cell = self.cell_from_xy(x,y)
        if cell is None: return
        self.dragging = True
        self.start_cell = cell
        # update ruler origin to this cell
        self.ruler_start = cell
        self._begin_op()
        if self.tool.get() in ('Brush','Eraser'):
            self._apply_to_cell(cell)

    def on_drag(self, e):
        if not self.dragging: return
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)
        cell = self.cell_from_xy(x,y)
        if cell is None: return
        if self.tool.get() in ('Brush','Eraser'):
            self._line_cells(self.start_cell, cell)
            self.start_cell = cell
        # while dragging, also update ruler display
        if self.ruler_start is not None and cell is not None:
            self._update_ruler(cell)

    def on_up(self, e):
        if not self.dragging: return
        x = self.canvas.canvasx(e.x); y = self.canvas.canvasy(e.y)
        end = self.cell_from_xy(x,y)
        if end is not None:
            tool = self.tool.get()
            if tool == 'Line':
                self._line_cells(self.start_cell, end)
            elif tool == 'Rect':
                self._rect_cells(self.start_cell, end)
            elif tool == 'RectO':
                self._rect_outline_cells(self.start_cell, end)
        self.dragging = False
        self.start_cell = None
        self._end_op()
        self.redraw()

    def _begin_op(self):
        self._op: List[tuple] = []  # (floor_idx, r, c, old, new)

    def _record(self, r:int, c:int, old:str, new:str):
        self._op.append((self._current_index(), r, c, old, new))

    def _end_op(self):
        if not self._op:
            return
        fl = self.floors[self._current_index()]
        fl.undo.append(self._op)
        fl.redo.clear()
        self._op = []

    def _set_cell(self, cell, tok:str):
        fi = self._current_index()
        fl = self.floors[fi]
        r,c = cell
        old = fl.cells[r][c]
        if old == tok:
            return
        fl.cells[r][c] = tok
        self._record(r,c,old,tok)

    def _apply_to_cell(self, cell):
        tok = 'N' if self.tool.get() == 'Eraser' else self.token.get()
        self._set_cell(cell, tok)

    def _line_cells(self, a, b):
        ar,ac = a; br,bc = b
        dr = br-ar; dc = bc-ac
        steps = max(abs(dr), abs(dc)) or 1
        for k in range(steps+1):
            r = ar + int(round(dr*k/steps))
            c = ac + int(round(dc*k/steps))
            self._apply_to_cell((r,c))

    def _rect_cells(self, a, b):
        ar,ac = a; br,bc = b
        r0,r1 = sorted((ar,br)); c0,c1 = sorted((ac,bc))
        for r in range(r0, r1+1):
            for c in range(c0, c1+1):
                self._apply_to_cell((r,c))

    def _rect_outline_cells(self, a, b):
        """Draw hollow rectangle: only border cells."""
        ar,ac = a; br,bc = b
        r0,r1 = sorted((ar,br)); c0,c1 = sorted((ac,bc))
        for r in range(r0, r1+1):
            for c in range(c0, c1+1):
                if r in (r0, r1) or c in (c0, c1):
                    self._apply_to_cell((r, c))

    def _update_ruler(self, current_cell):
        """Update ruler label based on last mousedown cell and current cell."""
        if self.ruler_start is None or current_cell is None:
            self.ruler_label.config(text='Ruler: -')
            return
        r0,c0 = self.ruler_start
        r1,c1 = current_cell
        dr_cells = abs(r1 - r0)
        dc_cells = abs(c1 - c0)
        # convert to meters (each cell is 0.5m x 0.5m)
        dy = dr_cells * CELL_METERS
        dx = dc_cells * CELL_METERS
        dist = (dx*dx + dy*dy) ** 0.5
        self.ruler_label.config(
            text=f'Ruler: start ({c0},{r0})  dx={dx:.2f}m dy={dy:.2f}m d={dist:.2f}m'
        )

    # ---- undo/redo ----
    def undo(self):
        if not self.floors: return
        fl = self.floors[self._current_index()]
        if not fl.undo: return
        op = fl.undo.pop()
        for _, r,c,old,new in op:
            fl.cells[r][c] = old
        fl.redo.append(op)
        self.redraw()

    def redo(self):
        if not self.floors: return
        fl = self.floors[self._current_index()]
        if not fl.redo: return
        op = fl.redo.pop()
        for _, r,c,old,new in op:
            fl.cells[r][c] = new
        fl.undo.append(op)
        self.redraw()

    # ---- redraw ----
    def redraw(self):
        if not self.floors or not self.canvas:
            return
        fi = self._current_index()
        fl = self.floors[fi]
        rows, cols = fl.rows, fl.cols
        s = max(1, int(self.zoom.get()))
        self._update_scroll_region()
        # draw into a PIL image for smooth zoom
        img = Image.new('RGB', (cols*s, rows*s), (255,255,255))
        for r in range(rows):
            for c in range(cols):
                tok = fl.cells[r][c]
                color = PALETTE.get(tok,'#FFFFFF')
                rgb = tuple(int(color[i:i+2],16) for i in (1,3,5))
                x0,y0 = c*s, r*s
                for yy in range(y0, y0+s):
                    for xx in range(x0, x0+s):
                        img.putpixel((xx,yy), rgb)
        if self.show_grid.get() and s >= 4:
            from PIL import ImageDraw as ImageDrawMod
            d = ImageDrawMod.Draw(img)
            line_color = (0,0,0)
            for r in range(rows+1):
                y = r*s
                d.line([(0,y),(cols*s-1,y)], fill=line_color)
            for c in range(cols+1):
                x = c*s
                d.line([(x,0),(x,rows*s-1)], fill=line_color)
        self.canvas_img = ImageTk.PhotoImage(img)
        self.canvas.delete('all')
        self.canvas.create_image(0,0, image=self.canvas_img, anchor='nw')
        self.floor_label.config(text=f'Floor {fi+1}')
        # update ruler text (keep previous measurement if no ruler_start)
        if self.ruler_start is not None:
            # use last start and current cursor cell if inside grid
            # here we just show origin; live distance is updated on mouse events
            r0,c0 = self.ruler_start
            self.ruler_label.config(text=f'Ruler: start ({c0},{r0})')
        else:
            self.ruler_label.config(text='Ruler: -')

    # ---- save ----
    def save_map(self):
        if not self.floors:
            messagebox.showwarning('No floors', 'Nothing to save.')
            return
        name = simpledialog.askstring('Save Map', 'Map name (folder under maps/):',
                                      initialvalue='my_building')
        if not name:
            return
        outdir = os.path.join('maps', name)
        os.makedirs(outdir, exist_ok=True)
        for idx, fl in enumerate(self.floors, start=1):
            rows, cols = fl.rows, fl.cols
            img = Image.new('RGB', (cols, rows), (255,255,255))
            for r in range(rows):
                for c in range(cols):
                    tok = fl.cells[r][c]
                    color = PALETTE.get(tok,'#FFFFFF')
                    rgb = tuple(int(color[i:i+2],16) for i in (1,3,5))
                    img.putpixel((c,r), rgb)
            meta = PngInfo()
            meta.add_text('map_meta',
                          f"{{\"cell_px\": 1, \"meters_per_cell\": {CELL_METERS}, \"width_m\": {self.width_m.get()}, \"height_m\": {self.height_m.get()}, \"floor_index\": {idx}, \"floors_total\": {len(self.floors)} }}")
            path = os.path.join(outdir, f'floor{idx}.png')
            img.save(path, pnginfo=meta)
        messagebox.showinfo('Saved', f'Saved {len(self.floors)} floor image(s) under\n{outdir}')

    # ---- keys ----
    def on_key(self, e):
        ch = e.keysym.lower()
        if ch == 'g':
            self.show_grid.set(not self.show_grid.get()); self.redraw()
        elif ch == 'b':
            self.tool.set('Brush')
        elif ch == 'l':
            self.tool.set('Line')
        elif ch == 'r':
            self.tool.set('Rect')
        elif ch == 'o':
            self.tool.set('RectO')

        elif ch in ('plus','equal'):
            self.zoom.set(min(64, self.zoom.get()+2)); self.redraw()
        elif ch in ('minus','underscore'):
            self.zoom.set(max(4, self.zoom.get()-2)); self.redraw()
        elif ch in ('1','2','3','4','5','6','7'):
            self.token.set(TOKENS[int(ch)-1])
        elif ch == 'n': self.add
        elif ch == 'r': self.tool.set('Rect')
        elif ch in ('plus','equal'):
            self.zoom.set(min(64, self.zoom.get()+2)); self.redraw()
        elif ch in ('minus','underscore'):
            self.zoom.set(max(4, self.zoom.get()-2)); self.redraw()
        elif ch in ('1','2','3','4','5','6','7'):
            self.token.set(TOKENS[int(ch)-1])
        elif ch == 'n': self.add_floor()
        elif ch == 'delete': self.delete_floor()

if __name__ == '__main__':
    MapPainter().mainloop()
