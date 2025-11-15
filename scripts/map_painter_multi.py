#!/usr/bin/env python3
"""
Multi-floor, cell-based map editor for the evacuation simulator.

- Each cell = 0.5m x 0.5m (logical解析時使用，不影響這裡的畫圖）。
- 底層是固定 rows x cols 的格子；畫布顯示大小透過 zoom (px/cell) 動態縮放。
- 每個 cell 只能是一個 token（牆 / 走道 / 安全區 / 火等），沒有半格。
- 支援多樓層：Floor spinbox + "Floor X" label。
- 支援 Room 模式：在地圖上拉一個白色半透明矩形，定義房間區域，並且為每個房間命名。
  存檔時會產生 floor{n}_rooms.txt。
- 存檔：
    maps/{map_name}/floor1.png, floor2.png, ...
    maps/{map_name}/floor1_rooms.txt, floor2_rooms.txt, ...

Run:
    python scripts/map_painter_multi.py
"""
import os
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

from PIL import Image
from PIL.PngImagePlugin import PngInfo


CELL_METERS = 0.5  # 0.5m x 0.5m per cell

TOKENS = ['W', 'N', 'S', 'B', 'F', 'P', 'SD', 'SU', 'TD', 'TU']

# human-readable names for UI
TOKEN_NAMES = {
    'W':  'Wall',
    'N':  'Walkable',
    'S':  'Safe / Exit',
    'B':  'Bottleneck / Door',
    'F':  'Fire',
    'P':  'Spawn',
    'SD': 'Stairs Down Area',
    'SU': 'Stairs Up Area',
    'TD': 'Teleport Down',
    'TU': 'Teleport Up',
}

PALETTE = {
    'W':  '#000000',   # wall
    'N':  '#BFE3F0',   # walkable
    'S':  '#5CB85C',   # safe / exit
    'B':  '#213B8F',   # bottleneck / door
    'F':  '#D9534F',   # fire
    'P':  '#5BC0DE',   # spawn
    'SD': '#7f3b08',   # stairs down area
    'SU': '#b35806',   # stairs up area
    'TD': '#01665e',   # teleport down
    'TU': '#35978f',   # teleport up
}


@dataclass
class FloorGrid:
    rows: int
    cols: int
    cells: List[List[str]] = field(default_factory=list)

    def __post_init__(self):
        if not self.cells:
            self.cells = [['N' for _ in range(self.cols)] for _ in range(self.rows)]

    def clone(self) -> "FloorGrid":
        return FloorGrid(self.rows, self.cols, [row[:] for row in self.cells])


class MapPainterApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Multi-floor map painter")

        # --- state --------------------------------------------------------
        # map physical size (meters); 1 cell = CELL_METERS
        self.map_width_m = 20.0
        self.map_height_m = 20.0
        rows, cols = self._ask_initial_grid_size()
        self.floors: List[FloorGrid] = [FloorGrid(rows, cols)]
        self.current_floor = tk.IntVar(value=1)  # 1-based for UI

        # map drawing state
        self.tool = tk.StringVar(value='Brush')  # Brush / Line / Rect / RectO / Eraser / Ruler
        self.current_token = tk.StringVar(value='W')  # internal short token code
        self.brush_size = tk.IntVar(value=1)  # in cells (square)
        self.zoom = tk.IntVar(value=16)       # px per cell
        self.mode = tk.StringVar(value='map')  # 'map' or 'room'

        self.start_cell: Optional[Tuple[int, int]] = None
        self.temp_shape = None
        self.ruler_start: Optional[Tuple[int, int]] = None

        # Room 定義：floor_index -> list of rooms
        # room: {'id': int, 'name': str, 'bbox': (r0,c0,r1,c1)}
        self.rooms: Dict[int, List[Dict]] = {}
        self.next_room_id = 1
        self.room_start_cell: Optional[Tuple[int, int]] = None
        self.temp_room_rect = None
        self.selected_room_index: Optional[int] = None
        self.editing_room_index: Optional[int] = None

        # undo stack: list of (floors_snapshot, rooms_snapshot)
        self.undo_stack: List[Tuple[List[FloorGrid], Dict[int, List[Dict]]]] = []

        # floor copy/paste buffer: (FloorGrid, rooms_for_that_floor)
        self.copied_floor: Optional[Tuple[FloorGrid, List[Dict]]] = None

        # --- UI -----------------------------------------------------------
        self._build_ui()
        self.redraw()

    # ---------------- UI building ----------------------------------------
    def _build_ui(self):
        top = self.master

        toolbar = ttk.Frame(top)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # Floor controls
        ttk.Label(toolbar, text="Floor:").grid(row=0, column=0, sticky='w')
        self.floor_spin = ttk.Spinbox(
            toolbar, from_=1, to=999, width=4,
            textvariable=self.current_floor, command=self.on_floor_change
        )
        self.floor_spin.grid(row=0, column=1, sticky='w')
        ttk.Button(toolbar, text="+", width=2, command=self.add_floor).grid(row=0, column=2)
        ttk.Button(toolbar, text="-", width=2, command=self.del_floor).grid(row=0, column=3)

        self.floor_label = ttk.Label(toolbar, text="Floor 1")
        self.floor_label.grid(row=0, column=4, padx=10)

        # Mode (map / room)
        ttk.Label(toolbar, text="Mode:").grid(row=0, column=5, sticky='w')
        ttk.Radiobutton(toolbar, text="Map", variable=self.mode, value='map').grid(row=0, column=6)
        ttk.Radiobutton(toolbar, text="Room", variable=self.mode, value='room').grid(row=0, column=7)

        # Tools
        ttk.Label(toolbar, text="Tool:").grid(row=1, column=0, sticky='w')
        col = 1
        for name in ('Brush', 'Line', 'Rect', 'RectO', 'Eraser', 'Ruler'):
            ttk.Radiobutton(toolbar, text=name, variable=self.tool, value=name).grid(row=1, column=col)
            col += 1

        # Token
        ttk.Label(toolbar, text="Token:").grid(row=2, column=0, sticky='w')
        # show full name + short code, e.g. "Wall (W)"
        self.token_display = tk.StringVar()
        display_values = [f"{TOKEN_NAMES[t]} ({t})" for t in TOKENS]
        self.token_display.set(f"{TOKEN_NAMES['W']} (W)")
        self.token_combo = ttk.Combobox(
            toolbar,
            values=display_values,
            width=18,
            textvariable=self.token_display,
            state='readonly'
        )
        self.token_combo.grid(row=2, column=1, sticky='w', columnspan=2)
        self.token_combo.bind("<<ComboboxSelected>>", self.on_token_change)

        # Brush size
        ttk.Label(toolbar, text="Brush size (cells):").grid(row=2, column=2, sticky='w')
        ttk.Spinbox(toolbar, from_=1, to=10, width=4, textvariable=self.brush_size).grid(row=2, column=3)

        # Zoom
        ttk.Label(toolbar, text="Zoom (px/cell):").grid(row=2, column=4, sticky='w')
        ttk.Spinbox(toolbar, from_=4, to=64, width=4, textvariable=self.zoom, command=self.on_zoom_change).grid(row=2, column=5)

        # Ruler label
        self.ruler_label = ttk.Label(toolbar, text="Ruler: -")
        self.ruler_label.grid(row=2, column=6, columnspan=3, sticky='w', padx=10)

        # Buttons
        ttk.Button(toolbar, text="Undo (Ctrl+Z)", command=self.undo).grid(row=3, column=0, padx=4, pady=4)
        ttk.Button(toolbar, text="Save Map...", command=self.save_map).grid(row=3, column=1, padx=4, pady=4)

        # Map size controls (meters)
        ttk.Label(toolbar, text="Size (m):").grid(row=3, column=2, sticky='w')
        self.width_m_var = tk.DoubleVar(value=self.map_width_m)
        self.height_m_var = tk.DoubleVar(value=self.map_height_m)
        ttk.Entry(toolbar, width=6, textvariable=self.width_m_var).grid(row=3, column=3, sticky='w')
        ttk.Entry(toolbar, width=6, textvariable=self.height_m_var).grid(row=3, column=4, sticky='w')
        ttk.Button(toolbar, text="Apply size", command=self.apply_size).grid(row=3, column=5, padx=4, pady=4)

        # Floor copy/paste
        ttk.Button(toolbar, text="Copy Floor", command=self.copy_floor).grid(row=3, column=6, padx=4, pady=4)
        ttk.Button(toolbar, text="Paste Floor", command=self.paste_floor).grid(row=3, column=7, padx=4, pady=4)

        # Center area: canvas (left) + room list (right)
        center = ttk.Frame(top)
        center.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Canvas
        self.canvas = tk.Canvas(center, bg='white')
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)

        # Room list panel
        room_frame = ttk.Frame(center, width=220)
        room_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.room_list_label = ttk.Label(room_frame, text="Rooms (Floor 1)")
        self.room_list_label.pack(anchor='nw', padx=4, pady=(4, 2))

        list_container = ttk.Frame(room_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=4)

        self.room_list = tk.Listbox(list_container, height=20)
        self.room_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.room_list.bind("<<ListboxSelect>>", self.on_room_select)

        room_scroll = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.room_list.yview)
        room_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.room_list.configure(yscrollcommand=room_scroll.set)

        btn_frame = ttk.Frame(room_frame)
        btn_frame.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(btn_frame, text="Rename", command=self.rename_room).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Delete", command=self.delete_room).pack(fill=tk.X, pady=1)
        ttk.Button(btn_frame, text="Edit Region", command=self.edit_room_region).pack(fill=tk.X, pady=1)

        top.bind("<Control-z>", lambda e: self.undo())

    # ----------------- helpers -------------------------------------------
    def current_grid(self) -> FloorGrid:
        idx = max(1, min(self.current_floor.get(), len(self.floors))) - 1
        return self.floors[idx]

    def push_undo(self):
        # deep copy floors and rooms
        floors_snapshot = [fl.clone() for fl in self.floors]
        rooms_snapshot = {
            k: [dict(id=r['id'], name=r['name'], bbox=r['bbox']) for r in v]
            for k, v in self.rooms.items()
        }
        self.undo_stack.append((floors_snapshot, rooms_snapshot))
        # limit size
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        floors_snapshot, rooms_snapshot = self.undo_stack.pop()
        self.floors = [fl.clone() for fl in floors_snapshot]
        self.rooms = {
            k: [dict(id=r['id'], name=r['name'], bbox=r['bbox']) for r in v]
            for k, v in rooms_snapshot.items()
        }
        self.redraw()

    def on_floor_change(self):
        # clamp
        v = self.current_floor.get()
        if v < 1:
            self.current_floor.set(1)
        if v > len(self.floors):
            self.current_floor.set(len(self.floors))
        self.floor_label.config(text=f"Floor {self.current_floor.get()}")
        # reset room selection when floor changes
        self.selected_room_index = None
        self.editing_room_index = None
        self.refresh_room_list()
        self.redraw()

    def add_floor(self):
        fl0 = self.current_grid()
        self.floors.append(FloorGrid(fl0.rows, fl0.cols))
        self.current_floor.set(len(self.floors))
        self.on_floor_change()

    def del_floor(self):
        if len(self.floors) <= 1:
            messagebox.showinfo("Info", "At least one floor is required.")
            return
        idx = self.current_floor.get() - 1
        del self.floors[idx]
        # shift room definitions
        new_rooms = {}
        for z, lst in self.rooms.items():
            if z == idx:
                continue
            nz = z if z < idx else z - 1
            new_rooms[nz] = lst
        self.rooms = new_rooms
        if self.current_floor.get() > len(self.floors):
            self.current_floor.set(len(self.floors))
        self.on_floor_change()

    def on_zoom_change(self):
        self.redraw()

    def on_token_change(self, event=None):
        """Update internal token code when user changes token combo selection."""
        disp = self.token_display.get()
        for t in TOKENS:
            if disp == f"{TOKEN_NAMES[t]} ({t})":
                self.current_token.set(t)
                break

    def _ask_initial_grid_size(self) -> Tuple[int, int]:
        """Ask user for initial map size in meters and convert to rows/cols."""
        try:
            w = simpledialog.askfloat(
                "Map width (m)", "Width (meters):",
                initialvalue=self.map_width_m, minvalue=1.0
            )
            h = simpledialog.askfloat(
                "Map height (m)", "Height (meters):",
                initialvalue=self.map_height_m, minvalue=1.0
            )
        except Exception:
            w = self.map_width_m
            h = self.map_height_m
        if not w or not h:
            w = self.map_width_m
            h = self.map_height_m
        self.map_width_m = float(w)
        self.map_height_m = float(h)
        cols = max(1, int(round(self.map_width_m / CELL_METERS)))
        rows = max(1, int(round(self.map_height_m / CELL_METERS)))
        return rows, cols

    def apply_size(self):
        """Resize all floors based on width/height in meters."""
        try:
            w = float(self.width_m_var.get())
            h = float(self.height_m_var.get())
        except Exception:
            messagebox.showerror("Error", "Size must be numeric (meters).")
            return
        if w <= 0 or h <= 0:
            messagebox.showerror("Error", "Size must be positive.")
            return
        self.map_width_m = w
        self.map_height_m = h
        cols = max(1, int(round(self.map_width_m / CELL_METERS)))
        rows = max(1, int(round(self.map_height_m / CELL_METERS)))
        self.push_undo()
        new_floors: List[FloorGrid] = []
        for fl in self.floors:
            new_grid = FloorGrid(rows, cols)
            for i in range(min(rows, fl.rows)):
                for j in range(min(cols, fl.cols)):
                    new_grid.cells[i][j] = fl.cells[i][j]
            new_floors.append(new_grid)
        self.floors = new_floors
        # clip room bboxes to new size
        for z, rooms in self.rooms.items():
            clipped = []
            for r in rooms:
                r0, c0, r1, c1 = r['bbox']
                r0 = max(0, min(rows - 1, r0))
                r1 = max(0, min(rows - 1, r1))
                c0 = max(0, min(cols - 1, c0))
                c1 = max(0, min(cols - 1, c1))
                if r0 > r1 or c0 > c1:
                    continue
                clipped.append(dict(id=r['id'], name=r['name'], bbox=(r0, c0, r1, c1)))
            self.rooms[z] = clipped
        self.refresh_room_list()
        self.redraw()

    def copy_floor(self):
        """Copy current floor grid and its rooms into buffer."""
        idx = self.current_floor.get() - 1
        if idx < 0 or idx >= len(self.floors):
            return
        fl_copy = self.floors[idx].clone()
        rooms_copy = [
            dict(id=r['id'], name=r['name'], bbox=r['bbox'])
            for r in self.rooms.get(idx, [])
        ]
        self.copied_floor = (fl_copy, rooms_copy)
        messagebox.showinfo("Copy Floor", f"Copied Floor {idx+1}")

    def paste_floor(self):
        """Paste previously copied floor into current floor (grid + rooms)."""
        if self.copied_floor is None:
            messagebox.showinfo("Paste Floor", "No floor copied yet.")
            return
        idx = self.current_floor.get() - 1
        if idx < 0 or idx >= len(self.floors):
            return
        self.push_undo()
        fl_copy, rooms_copy = self.copied_floor
        target = self.floors[idx]
        rows, cols = target.rows, target.cols
        new_grid = FloorGrid(rows, cols)
        for i in range(min(rows, fl_copy.rows)):
            for j in range(min(cols, fl_copy.cols)):
                new_grid.cells[i][j] = fl_copy.cells[i][j]
        self.floors[idx] = new_grid
        # copy and clip rooms
        clipped_rooms: List[Dict] = []
        for r in rooms_copy:
            r0, c0, r1, c1 = r['bbox']
            r0 = max(0, min(rows - 1, r0))
            r1 = max(0, min(rows - 1, r1))
            c0 = max(0, min(cols - 1, c0))
            c1 = max(0, min(cols - 1, c1))
            if r0 > r1 or c0 > c1:
                continue
            clipped_rooms.append(
                dict(id=r['id'], name=r['name'], bbox=(r0, c0, r1, c1))
            )
        self.rooms[idx] = clipped_rooms
        self.refresh_room_list()
        self.redraw()

    def cell_from_xy(self, x: int, y: int) -> Tuple[int, int]:
        cs = max(1, self.zoom.get())
        r = max(0, y // cs)
        c = max(0, x // cs)
        fl = self.current_grid()
        r = min(fl.rows - 1, r)
        c = min(fl.cols - 1, c)
        return int(r), int(c)

    # --------------- drawing primitives ----------------------------------
    def set_cell(self, r: int, c: int, tok: str):
        fl = self.current_grid()
        if 0 <= r < fl.rows and 0 <= c < fl.cols:
            fl.cells[r][c] = tok

    def apply_brush(self, r: int, c: int, tok: str):
        size = max(1, self.brush_size.get())
        half = size // 2
        for dr in range(-half, -half + size):
            for dc in range(-half, -half + size):
                self.set_cell(r + dr, c + dc, tok)

    def draw_line_cells(self, r0, c0, r1, c1, tok):
        # Bresenham
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)
        sr = 1 if r1 >= r0 else -1
        sc = 1 if c1 >= c0 else -1
        if dc > dr:
            err = dc // 2
            r = r0
            for c in range(c0, c1 + sc, sc):
                self.set_cell(r, c, tok)
                err -= dr
                if err < 0:
                    r += sr
                    err += dc
        else:
            err = dr // 2
            c = c0
            for r in range(r0, r1 + sr, sr):
                self.set_cell(r, c, tok)
                err -= dc
                if err < 0:
                    c += sc
                    err += dr

    def draw_rect_cells(self, r0, c0, r1, c1, tok, hollow=False):
        rr0, rr1 = sorted((r0, r1))
        cc0, cc1 = sorted((c0, c1))
        for r in range(rr0, rr1 + 1):
            for c in range(cc0, cc1 + 1):
                if hollow and not (r == rr0 or r == rr1 or c == cc0 or c == cc1):
                    continue
                self.set_cell(r, c, tok)

    # --------------- mouse handlers --------------------------------------
    def on_down(self, event):
        r, c = self.cell_from_xy(event.x, event.y)

        # ruler start
        if self.tool.get() == 'Ruler':
            self.ruler_start = (r, c)
            self.update_ruler(r, c)
            return

        # Room 定義模式
        if self.mode.get() == 'room':
            self.room_start_cell = (r, c)
            cs = self.zoom.get()
            x0, y0 = c * cs, r * cs
            self.temp_room_rect = self.canvas.create_rectangle(
                x0, y0, x0 + cs, y0 + cs,
                fill='white', outline='gray40', stipple='gray25'
            )
            return

        # Map 繪圖模式
        self.push_undo()
        self.start_cell = (r, c)
        tok = self.current_token.get()
        if self.tool.get() == 'Brush':
            self.apply_brush(r, c, tok)
        elif self.tool.get() == 'Eraser':
            self.apply_brush(r, c, 'N')
        # Line / Rect / RectO 在 drag/up 時處理
        self.redraw()

    def on_drag(self, event):
        r, c = self.cell_from_xy(event.x, event.y)

        if self.tool.get() == 'Ruler' and self.ruler_start:
            self.update_ruler(r, c)
            return

        # continuous brush / eraser while dragging in map mode
        if self.mode.get() == 'map' and self.tool.get() in ('Brush', 'Eraser'):
            tok = self.current_token.get() if self.tool.get() == 'Brush' else 'N'
            self.apply_brush(r, c, tok)
            self.redraw()
            return

        if self.mode.get() == 'room':
            if self.room_start_cell is None or self.temp_room_rect is None:
                return
            r0, c0 = self.room_start_cell
            cs = self.zoom.get()
            x0, y0 = min(c0, c) * cs, min(r0, r) * cs
            x1, y1 = (max(c0, c) + 1) * cs, (max(r0, r) + 1) * cs
            self.canvas.coords(self.temp_room_rect, x0, y0, x1, y1)
            return

        if self.start_cell is None:
            return

        # show preview for Line/Rect/RectO using a temp rectangle/line
        cs = self.zoom.get()
        r0, c0 = self.start_cell
        if self.temp_shape:
            self.canvas.delete(self.temp_shape)
            self.temp_shape = None
        if self.tool.get() in ('Line', 'Rect', 'RectO'):
            x0, y0 = c0 * cs, r0 * cs
            x1, y1 = (c + 1) * cs, (r + 1) * cs
            if self.tool.get() == 'Line':
                self.temp_shape = self.canvas.create_line(
                    x0 + cs / 2, y0 + cs / 2, x1 - cs / 2, y1 - cs / 2,
                    fill='black'
                )
            else:
                self.temp_shape = self.canvas.create_rectangle(
                    x0, y0, x1, y1,
                    outline='black',
                    dash=(3, 3)
                )

    def on_up(self, event):
        r, c = self.cell_from_xy(event.x, event.y)

        if self.tool.get() == 'Ruler' and self.ruler_start:
            # mouse up 不重置，仍然保持 ruler_start
            return

        if self.mode.get() == 'room':
            # finalize room rectangle
            if self.room_start_cell is None or self.temp_room_rect is None:
                return
            r0, c0 = self.room_start_cell
            rr0, rr1 = sorted((r0, r))
            cc0, cc1 = sorted((c0, c))
            fl_index = self.current_floor.get() - 1
            # 編輯既有房間：更新 bbox，不改名稱
            if self.editing_room_index is not None:
                rooms = self.rooms.get(fl_index, [])
                if 0 <= self.editing_room_index < len(rooms):
                    rooms[self.editing_room_index]['bbox'] = (rr0, cc0, rr1, cc1)
                    self.rooms[fl_index] = rooms
                self.editing_room_index = None
            else:
                # 新增房間：詢問房間名稱
                default_name = f"room{self.next_room_id}"
                name = simpledialog.askstring("Room name", "Room name (no spaces):",
                                              initialvalue=default_name)
                if not name:
                    # 取消：刪除暫時矩形
                    self.canvas.delete(self.temp_room_rect)
                    self.temp_room_rect = None
                    self.room_start_cell = None
                    return
                name = name.strip().replace(" ", "_")
                rid = str(self.next_room_id)
                self.next_room_id += 1
                self.rooms.setdefault(fl_index, []).append(
                    {'id': rid, 'name': name, 'bbox': (rr0, cc0, rr1, cc1)}
                )
            # 清掉暫時矩形，由 redraw 畫正式的 overlay
            self.canvas.delete(self.temp_room_rect)
            self.temp_room_rect = None
            self.room_start_cell = None
            self.refresh_room_list()
            self.redraw()
            return

        if self.start_cell is None:
            return

        r0, c0 = self.start_cell
        tok = self.current_token.get()
        if self.tool.get() == 'Line':
            self.draw_line_cells(r0, c0, r, c, tok)
        elif self.tool.get() == 'Rect':
            self.draw_rect_cells(r0, c0, r, c, tok, hollow=False)
        elif self.tool.get() == 'RectO':
            self.draw_rect_cells(r0, c0, r, c, tok, hollow=True)
        # Brush/Eraser 已經在 on_down 做一次即可；如果你希望拖曳連續刷，可以在 on_drag 裡同樣呼叫 apply_brush。

        if self.temp_shape:
            self.canvas.delete(self.temp_shape)
            self.temp_shape = None
        self.start_cell = None
        self.redraw()

    # ---------------- ruler ----------------------------------------------
    def update_ruler(self, r: int, c: int):
        if not self.ruler_start:
            self.ruler_label.config(text="Ruler: -")
            return
        r0, c0 = self.ruler_start
        dr = r - r0
        dc = c - c0
        dist = ((dr * CELL_METERS) ** 2 + (dc * CELL_METERS) ** 2) ** 0.5
        self.ruler_label.config(
            text=f"Ruler: from ({r0},{c0}) to ({r},{c})  "
                 f"Δr={dr}, Δc={dc}, d={dist:.2f} m"
        )

    # ---------------- redraw ---------------------------------------------
    def redraw(self):
        self.canvas.delete("all")
        fl = self.current_grid()
        cs = self.zoom.get()
        width = fl.cols * cs
        height = fl.rows * cs
        self.canvas.config(scrollregion=(0, 0, width, height), width=width, height=height)

        # draw grid cells
        for r in range(fl.rows):
            for c in range(fl.cols):
                tok = fl.cells[r][c]
                color = PALETTE.get(tok, "#FFFFFF")
                x0, y0 = c * cs, r * cs
                x1, y1 = x0 + cs, y0 + cs
                self.canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=color,
                    outline="#DDDDDD"
                )

        # draw room overlays for current floor
        self._draw_rooms_overlay()

    def _draw_rooms_overlay(self):
        cs = self.zoom.get()
        fl_index = self.current_floor.get() - 1
        rooms = self.rooms.get(fl_index, [])
        for idx, room in enumerate(rooms):
            r0, c0, r1, c1 = room['bbox']
            x0, y0 = c0 * cs, r0 * cs
            x1, y1 = (c1 + 1) * cs, (r1 + 1) * cs
            outline = 'red' if idx == self.selected_room_index else 'gray25'
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                fill='white',
                outline=outline,
                stipple='gray25'
            )
            self.canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=room['name'],
                fill='black'
            )

    # ---------------- rooms list / editing -------------------------------
    def refresh_room_list(self):
        """Refresh room list UI for current floor."""
        if not hasattr(self, "room_list"):
            return
        fl_index = self.current_floor.get() - 1
        rooms = self.rooms.get(fl_index, [])
        self.room_list_label.config(text=f"Rooms (Floor {self.current_floor.get()})")
        self.room_list.delete(0, tk.END)
        for r in rooms:
            self.room_list.insert(tk.END, f"{r['name']} [{r['id']}]")
        # reset selection index to stay within bounds
        if rooms and self.selected_room_index is not None and self.selected_room_index < len(rooms):
            self.room_list.select_set(self.selected_room_index)
        else:
            self.selected_room_index = None

    def on_room_select(self, event):
        sel = self.room_list.curselection()
        if not sel:
            self.selected_room_index = None
        else:
            self.selected_room_index = sel[0]
        self.editing_room_index = None
        self.redraw()

    def _get_selected_room(self):
        fl_index = self.current_floor.get() - 1
        rooms = self.rooms.get(fl_index, [])
        idx = self.selected_room_index
        if idx is None or idx < 0 or idx >= len(rooms):
            return fl_index, rooms, None
        return fl_index, rooms, idx

    def rename_room(self):
        fl_index, rooms, idx = self._get_selected_room()
        if idx is None:
            messagebox.showinfo("Rename Room", "Select a room in the list first.")
            return
        room = rooms[idx]
        new_name = simpledialog.askstring(
            "Rename room",
            "New name (no spaces):",
            initialvalue=room['name']
        )
        if not new_name:
            return
        room['name'] = new_name.strip().replace(" ", "_")
        rooms[idx] = room
        self.rooms[fl_index] = rooms
        self.refresh_room_list()
        self.redraw()

    def delete_room(self):
        fl_index, rooms, idx = self._get_selected_room()
        if idx is None:
            messagebox.showinfo("Delete Room", "Select a room in the list first.")
            return
        if not messagebox.askyesno("Delete Room", "Delete selected room?"):
            return
        self.push_undo()
        rooms.pop(idx)
        self.rooms[fl_index] = rooms
        self.selected_room_index = None
        self.editing_room_index = None
        self.refresh_room_list()
        self.redraw()

    def edit_room_region(self):
        fl_index, rooms, idx = self._get_selected_room()
        if idx is None:
            messagebox.showinfo("Edit Room", "Select a room in the list first.")
            return
        self.mode.set('room')
        self.editing_room_index = idx
        self.selected_room_index = idx
        messagebox.showinfo(
            "Edit Room Region",
            "在畫布上用滑鼠左鍵拖出新的矩形區域，放開後會更新該房間的範圍（名稱不變）。"
        )
        self.redraw()

    # ---------------- save -----------------------------------------------
    def save_map(self):
        # ask for map name
        name = simpledialog.askstring("Map name", "Map folder name under maps/:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        base_dir = os.path.join("maps", name)
        os.makedirs(base_dir, exist_ok=True)

        # export each floor as PNG
        for idx, fl in enumerate(self.floors, start=1):
            img = Image.new("RGB", (fl.cols, fl.rows))
            px = img.load()
            for i in range(fl.rows):
                for j in range(fl.cols):
                    tok = fl.cells[i][j]
                    hexcol = PALETTE.get(tok, "#FFFFFF")
                    r = int(hexcol[1:3], 16)
                    g = int(hexcol[3:5], 16)
                    b = int(hexcol[5:7], 16)
                    px[j, i] = (r, g, b)

            meta = PngInfo()
            import json as _json
            meta.add_text(
                "map_meta",
                _json.dumps(
                    {
                        "cell_px": 1,
                        "meters_per_cell": CELL_METERS,
                        "width_m": fl.cols * CELL_METERS,
                        "height_m": fl.rows * CELL_METERS,
                        "floor_index": idx - 1,
                        "floors_total": len(self.floors),
                    }
                )
            )

            out_path = os.path.join(base_dir, f"floor{idx}.png")
            img.save(out_path, pnginfo=meta)

        # export rooms per floor
        for z, rooms in self.rooms.items():
            if not rooms:
                continue
            path = os.path.join(base_dir, f"floor{z+1}_rooms.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# room_id name r0 c0 r1 c1\n")
                for room in rooms:
                    rid = room['id']
                    name = room['name']
                    r0, c0, r1, c1 = room['bbox']
                    f.write(f"{rid} {name} {r0} {c0} {r1} {c1}\n")

        messagebox.showinfo("Saved", f"Saved to {base_dir}")


def main():
    root = tk.Tk()
    app = MapPainterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
