#!/usr/bin/env python3
"""
Simple grid map editor for the fire-evacuation-simulator.
- Paint on a canvas with tile types: N (empty), W (wall), S (safe), B (bottleneck), F (fire), P (spawn area)
- Optional vertical connectors (portals): Z#, E#, U# (e.g., Z1, E2). These are exported alongside the cell.
- Exports text files in the expected format: rows separated by newlines; cells separated by ';'; tokens in a cell separated by ','.

Notes
- The simulator samples initial person locations from cells that contain 'P'. Use at least one P somewhere.
- Empty cells will be saved as 'N' so the grid remains rectangular.
- Multi-layer is not supported here; this creates a single-layer map.

Run
    python scripts/map_editor.py

"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Tuple, Set

# Colors for the main attribute displayed per cell. Order defines priority when multiple exist.
ATTR_ORDER = ['W', 'S', 'B', 'F', 'P', 'N']
ATTR_COLORS = {
    'N': '#ffffff',  # white
    'W': '#333333',  # dark gray
    'S': '#5cb85c',  # green
    'B': '#f0ad4e',  # orange
    'F': '#d9534f',  # red
    'P': '#5bc0de',  # light blue
}
# Portal text color overlay
PORTAL_COLOR = '#3f51b5'  # indigo-ish
GRID_COLOR = '#cccccc'
SELECT_COLOR = '#ffcc00'

class Cell:
    """Represents one grid cell with a set of tokens.
    tokens contains 0..1 of the main attrs in {'W','S','B','F','P','N'} and optional portal tokens like 'Z1','E2','U3'.
    """
    __slots__ = ('tokens',)
    def __init__(self):
        self.tokens: Set[str] = set(['N'])

    def set_attr(self, attr: str):
        # remove any existing main attribute, then set new
        self.tokens.difference_update({'W','S','B','F','P','N'})
        self.tokens.add(attr)

    def get_attr(self) -> str:
        for a in ATTR_ORDER:
            if a in self.tokens:
                return a
        # default fallback
        return 'N'

    def toggle_portal(self, letter: str, idx: int):
        tok = f"{letter}{idx}"
        if tok in self.tokens:
            self.tokens.remove(tok)
        else:
            # remove any existing portal with the same letter to keep 1 portal per letter
            to_remove = [t for t in self.tokens if (len(t) >= 2 and t[0] in 'ZEUP' and t[0] == letter)]
            for t in to_remove:
                self.tokens.remove(t)
            self.tokens.add(tok)

    def clear_portals(self):
        self.tokens.difference_update({t for t in self.tokens if (len(t) >= 2 and t[0] in 'ZEUP' and t[1:].isdigit())})

    def list_tokens_for_export(self) -> List[str]:
        # Ensure there is at least one of the main attrs; default to N if none.
        main_present = any(a in self.tokens for a in {'W','S','B','F','P','N'})
        toks = list(sorted([t for t in self.tokens if not (len(t) >= 2 and t[0] in 'ZEUP' and t[1:].isdigit())]))
        if not main_present:
            toks.append('N')
        # Append portals at the end (no sort to keep stable order per letter)
        for letter in 'ZEU':  # avoid 'P#' to not conflict with spawn 'P'
            for t in sorted(self.tokens):
                if t.startswith(letter) and t[1:].isdigit():
                    toks.append(t)
        return toks

class MapEditor(tk.Tk):
    def __init__(self, rows=30, cols=50, cell_px=20):
        super().__init__()
        self.title('Fire Evacuation Map Editor')
        self.rows = rows
        self.cols = cols
        self.cell_px = cell_px
        self.brush = tk.StringVar(value='W')
        self.portal_letter = tk.StringVar(value='Z')
        self.portal_id = tk.IntVar(value=1)
        self.show_grid = tk.BooleanVar(value=True)

        self.cells: List[List[Cell]] = [[Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        # default fill to N
        for r in range(self.rows):
            for c in range(self.cols):
                self.cells[r][c].set_attr('N')

        self._build_ui()
        self._redraw_all()

    def _build_ui(self):
        # Top controls
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        # Grid size controls
        ttk.Label(top, text='Rows').pack(side=tk.LEFT)
        self.rows_entry = ttk.Entry(top, width=5)
        self.rows_entry.insert(0, str(self.rows))
        self.rows_entry.pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(top, text='Cols').pack(side=tk.LEFT)
        self.cols_entry = ttk.Entry(top, width=5)
        self.cols_entry.insert(0, str(self.cols))
        self.cols_entry.pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(top, text='Cell px').pack(side=tk.LEFT)
        self.cell_entry = ttk.Entry(top, width=5)
        self.cell_entry.insert(0, str(self.cell_px))
        self.cell_entry.pack(side=tk.LEFT, padx=(2,8))
        ttk.Button(top, text='New Grid', command=self._apply_new_grid).pack(side=tk.LEFT, padx=(0,10))
        ttk.Checkbutton(top, text='Gridlines', variable=self.show_grid, command=self._redraw_all).pack(side=tk.LEFT)

        # Brush controls
        palette = ttk.Frame(self)
        palette.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        ttk.Label(palette, text='Brush:').pack(side=tk.LEFT)
        for ch in ['N','W','S','B','F','P']:
            ttk.Radiobutton(palette, text=ch, value=ch, variable=self.brush).pack(side=tk.LEFT)
        ttk.Separator(palette, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(palette, text='Portal').pack(side=tk.LEFT)
        portal_combo = ttk.Combobox(palette, values=['Z','E','U'], textvariable=self.portal_letter, width=3, state='readonly')
        portal_combo.pack(side=tk.LEFT)
        ttk.Label(palette, text='#').pack(side=tk.LEFT)
        portal_spin = ttk.Spinbox(palette, from_=1, to=999, width=5, textvariable=self.portal_id)
        portal_spin.pack(side=tk.LEFT)
        ttk.Button(palette, text='Apply Portal', command=self._apply_portal_brush).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(palette, text='Clear Portals', command=self._clear_portal_brush).pack(side=tk.LEFT)

        # File controls
        files = ttk.Frame(self)
        files.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        ttk.Button(files, text='New', command=self._new_blank).pack(side=tk.LEFT)
        ttk.Button(files, text='Open...', command=self._open_file).pack(side=tk.LEFT, padx=(4,0))
        ttk.Button(files, text='Save...', command=self._save_file).pack(side=tk.LEFT, padx=(4,0))
        ttk.Button(files, text='Export Preview', command=self._preview_text).pack(side=tk.LEFT, padx=(4,0))
        ttk.Label(files, text='Tip: Left-click to paint, right-click to set N').pack(side=tk.LEFT, padx=12)

        # Canvas
        self.canvas = tk.Canvas(self, width=self.cols*self.cell_px, height=self.rows*self.cell_px, bg='#ffffff')
        self.canvas.pack(side=tk.TOP, padx=8, pady=8)
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<Button-3>', self._on_right_click)

        # Status bar
        self.status = ttk.Label(self, text='Ready', anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _apply_new_grid(self):
        try:
            rows = max(1, int(self.rows_entry.get()))
            cols = max(1, int(self.cols_entry.get()))
            cell_px = max(4, int(self.cell_entry.get()))
        except ValueError:
            messagebox.showerror('Invalid Size', 'Rows/Cols/Cell px must be integers')
            return
        self.rows, self.cols, self.cell_px = rows, cols, cell_px
        self.cells = [[Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                self.cells[r][c].set_attr('N')
        self.canvas.config(width=self.cols*self.cell_px, height=self.rows*self.cell_px)
        self._redraw_all()

    def _new_blank(self):
        if not messagebox.askyesno('New', 'Clear the current map?'):
            return
        for r in range(self.rows):
            for c in range(self.cols):
                self.cells[r][c] = Cell()
                self.cells[r][c].set_attr('N')
        self._redraw_all()

    def _open_file(self):
        path = filedialog.askopenfilename(title='Open Map', filetypes=[('Text', '*.txt'), ('All', '*.*')])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read().replace('\r\n', '\n')
            rows = []
            for line in text.split('\n'):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(';')]
                if parts and (parts[-1] == '' or parts[-1] == ','):
                    parts = parts[:-1]
                rows.append(parts)
            if not rows:
                raise ValueError('Empty file')
            R = len(rows)
            C = max(len(r) for r in rows)
            self.rows, self.cols = R, C
            self.rows_entry.delete(0, tk.END)
            self.rows_entry.insert(0, str(R))
            self.cols_entry.delete(0, tk.END)
            self.cols_entry.insert(0, str(C))
            self.cells = [[Cell() for _ in range(C)] for _ in range(R)]
            for i, line in enumerate(rows):
                for j, cell_str in enumerate(line):
                    toks = [t.strip() for t in cell_str.split(',') if t.strip()]
                    if not toks:
                        toks = ['N']
                    # main attr: take the first of known ones, else default N
                    main = None
                    portals = []
                    for t in toks:
                        if t in {'W','S','B','F','P','N'} and main is None:
                            main = t
                        elif len(t) >= 2 and t[0] in 'ZEU' and t[1:].isdigit():
                            portals.append(t)
                    if main is None:
                        main = 'N'
                    self.cells[i][j].set_attr(main)
                    for p in portals:
                        self.cells[i][j].tokens.add(p)
            self.canvas.config(width=self.cols*self.cell_px, height=self.rows*self.cell_px)
            self._redraw_all()
            self.status.config(text=f'Opened {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('Open Failed', f'Could not open file:\n{e}')

    def _save_file(self):
        path = filedialog.asksaveasfilename(title='Save Map As', defaultextension='.txt', filetypes=[('Text', '*.txt')])
        if not path:
            return
        try:
            text = self._export_text()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            self.status.config(text=f'Saved {os.path.basename(path)}')
            messagebox.showinfo('Saved', f'Saved to:\n{path}')
        except Exception as e:
            messagebox.showerror('Save Failed', f'Could not save file:\n{e}')

    def _preview_text(self):
        text = self._export_text()
        top = tk.Toplevel(self)
        top.title('Export Preview')
        txt = tk.Text(top, width=120, height=30)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert('1.0', text)
        txt.configure(state='disabled')

    def _export_text(self) -> str:
        lines = []
        for r in range(self.rows):
            cells = []
            for c in range(self.cols):
                toks = self.cells[r][c].list_tokens_for_export()
                cells.append(', '.join(toks))
            lines.append(' ; '.join(cells))
        return '\n'.join(lines) + '\n'

    def _coord_from_event(self, event) -> Tuple[int,int]:
        j = int(event.x // self.cell_px)
        i = int(event.y // self.cell_px)
        if i < 0 or j < 0 or i >= self.rows or j >= self.cols:
            return None
        return i, j

    def _on_click(self, event):
        ij = self._coord_from_event(event)
        if not ij:
            return
        i, j = ij
        self.cells[i][j].set_attr(self.brush.get())
        self._draw_cell(i, j)

    def _on_drag(self, event):
        ij = self._coord_from_event(event)
        if not ij:
            return
        i, j = ij
        self.cells[i][j].set_attr(self.brush.get())
        self._draw_cell(i, j)

    def _on_right_click(self, event):
        ij = self._coord_from_event(event)
        if not ij:
            return
        i, j = ij
        self.cells[i][j].set_attr('N')
        self._draw_cell(i, j)

    def _apply_portal_brush(self):
        # Clicking Apply Portal enters a temporary mode for one click
        self.status.config(text=f'Click a cell to toggle portal {self.portal_letter.get()}{self.portal_id.get()}')
        self.canvas.config(cursor='tcross')
        self.canvas.bind('<Button-1>', self._on_portal_click, add='+')

    def _on_portal_click(self, event):
        ij = self._coord_from_event(event)
        if not ij:
            return
        i, j = ij
        self.cells[i][j].toggle_portal(self.portal_letter.get(), int(self.portal_id.get()))
        self._draw_cell(i, j)
        self.status.config(text='Portal toggled')
        self.canvas.config(cursor='')
        # unbind this temporary handler
        self.canvas.unbind('<Button-1>', funcid=None)
        self.canvas.bind('<Button-1>', self._on_click)

    def _clear_portal_brush(self):
        self.status.config(text='Click a cell to clear all portals')
        self.canvas.config(cursor='tcross')
        def handler(event):
            ij = self._coord_from_event(event)
            if not ij:
                return
            i, j = ij
            self.cells[i][j].clear_portals()
            self._draw_cell(i, j)
            self.status.config(text='Portals cleared')
            self.canvas.config(cursor='')
            self.canvas.unbind('<Button-1>', funcid=None)
            self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Button-1>', handler, add='+')

    def _redraw_all(self):
        self.canvas.delete('all')
        for i in range(self.rows):
            for j in range(self.cols):
                self._draw_cell(i, j)
        if self.show_grid.get():
            for i in range(self.rows+1):
                y = i*self.cell_px
                self.canvas.create_line(0, y, self.cols*self.cell_px, y, fill=GRID_COLOR)
            for j in range(self.cols+1):
                x = j*self.cell_px
                self.canvas.create_line(x, 0, x, self.rows*self.cell_px, fill=GRID_COLOR)

    def _draw_cell(self, i: int, j: int):
        x0 = j*self.cell_px
        y0 = i*self.cell_px
        x1 = x0 + self.cell_px
        y1 = y0 + self.cell_px
        attr = self.cells[i][j].get_attr()
        color = ATTR_COLORS.get(attr, '#ffffff')
        self.canvas.create_rectangle(x0, y0, x1, y1, outline='', fill=color)
        # Small text overlay for main attr (except N)
        if attr != 'N' and self.cell_px >= 14:
            self.canvas.create_text((x0+x1)//2, (y0+y1)//2, text=attr, fill='#000000')
        # Show portals text overlay
        portals = [t for t in sorted(self.cells[i][j].tokens) if len(t) >= 2 and t[0] in 'ZEU' and t[1:].isdigit()]
        if portals and self.cell_px >= 14:
            txt = '\n'.join(portals[:2]) if self.cell_px < 28 else ','.join(portals)
            self.canvas.create_text(x0+4, y0+4, text=txt, anchor='nw', fill=PORTAL_COLOR, font=('TkDefaultFont', 8))


def main():
    rows = 30
    cols = 50
    if len(sys.argv) >= 3:
        try:
            rows = int(sys.argv[1])
            cols = int(sys.argv[2])
        except ValueError:
            pass
    app = MapEditor(rows=rows, cols=cols, cell_px=20)
    app.mainloop()

if __name__ == '__main__':
    main()
