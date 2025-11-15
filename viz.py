import math
from random import Random

import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np


class Plotter:
    """
    Simple matplotlib-based grid visualizer.

    - Single-floor: one panel, same behaviour as original project.
    - Multi-floor: multiple panels shown at the same time (one per floor),
      with per-floor stats in the title.
    """

    def __init__(self):
        plt.ion()
        self.fig = None
        self.axes = None

    # ---- low-level drawing helpers -------------------------------------

    def _ensure_figure(self, n_axes):
        """Create or resize the figure to have at least n_axes axes."""
        if self.fig is None or self.axes is None:
            self.fig, self.axes = plt.subplots(1, n_axes, squeeze=False)
        else:
            # flatten existing axes and resize if needed
            flat = self.axes.ravel()
            if flat.size < n_axes:
                plt.close(self.fig)
                self.fig, self.axes = plt.subplots(1, n_axes, squeeze=False)
        return self.axes.ravel()

    def draw_grid(self, ax, gdata):
        """
        Draw the background grid (walls, fire, exits, bottlenecks, stairs).

        Values in gdata:
          0: normal / empty
          1: wall
          2: fire
          3: safe
          4: bottleneck / door
          5: wall + fire
          6: stairs-down area (SD)
          7: stairs-up area (SU)
          8: teleport-down cell (TD)
          9: teleport-up cell (TU)
        """
        cmap = colors.ListedColormap(
            [
                "#BFE3F0",  # 0 normal
                "#000000",  # 1 wall
                "#D9534F",  # 2 fire
                "#5CB85C",  # 3 safe
                "#213B8F",  # 4 bottleneck
                "#800000",  # 5 burning wall
                "#7f3b08",  # 6 stairs down area
                "#b35806",  # 7 stairs up area
                "#01665e",  # 8 teleport down
                "#35978f",  # 9 teleport up
            ]
        )
        bounds = [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
        norm = colors.BoundaryNorm(bounds, cmap.N)

        r, c = gdata.shape
        ax.imshow(
            gdata,
            cmap=cmap,
            norm=norm,
            origin="upper",
            interpolation="nearest",
            extent=(-0.5, c - 0.5, r - 0.5, -0.5),
        )
        ax.set_xticks([])
        ax.set_yticks([])

    def draw_people(self, ax, X, Y, C):
        """
        Draw people on top of the grid.

        C values:
          0: moving / alive
          1: dead
          2: safe
          3: unknown
        """
        if not X:
            return
        cmap = colors.ListedColormap(
            [
                "#377eb8",  # alive
                "#000000",  # dead
                "#4daf4a",  # safe
                "#ff7f00",  # unknown
            ]
        )
        bounds = [-0.5, 0.5, 1.5, 2.5, 3.5]
        norm = colors.BoundaryNorm(bounds, cmap.N)
        ax.scatter(X, Y, c=C, cmap=cmap, norm=norm, s=10)

    def _prepare_grid_data(self, graph):
        """Convert graph dict into a 2D numpy array of attribute codes."""
        r, c = 0, 0
        for loc, attrs in graph.items():
            r = max(r, loc[0] + 1)
            c = max(c, loc[1] + 1)
        if r == 0 or c == 0:
            return np.zeros((1, 1))

        gdata = np.zeros((r, c))
        for loc, attrs in graph.items():
            code = 0
            # wall (possibly burning) has highest priority
            if attrs.get("W"):
                code = 5 if attrs.get("F") else 1
            elif attrs.get("F"):
                code = 2
            elif attrs.get("S"):
                code = 3
            elif attrs.get("B"):
                code = 4
            elif attrs.get("SD"):
                code = 6
            elif attrs.get("SU"):
                code = 7
            elif attrs.get("TD"):
                code = 8
            elif attrs.get("TU"):
                code = 9
            else:
                code = 0
            gdata[loc] = code
        return gdata

    def _prepare_people_data(self, people):
        """Convert people sequence into scatter plot data."""
        X, Y, C = [], [], []
        for p in people:
            loc = getattr(p, "loc", None)
            if not isinstance(loc, tuple) or len(loc) != 2:
                continue
            row, col = loc
            R = Random(getattr(p, "id", 0))
            x = col - 0.5 + R.random()
            y = row - 0.5 + R.random()
            if getattr(p, "safe", False):
                c = 2
            elif not getattr(p, "alive", True):
                c = 1
            elif getattr(p, "alive", True):
                c = 0
            else:
                c = 3
            X.append(x)
            Y.append(y)
            C.append(c)
        return X, Y, C

    def _compute_room_stats(self, graph, people):
        """
        Compute per-room stats for a single 2D graph.
        Returns dict room_id -> {'total':.., 'safe':.., 'dead':..}
        """
        from collections import defaultdict
        stats = defaultdict(lambda: {"total": 0, "safe": 0, "dead": 0})
        for p in people:
            loc = getattr(p, "loc", None)
            if not isinstance(loc, tuple) or len(loc) != 2:
                continue
            key = (loc[0], loc[1])
            attrs = graph.get(key)
            if not attrs:
                continue
            rid = attrs.get("room")
            if rid is None:
                continue
            s = stats[rid]
            s["total"] += 1
            if getattr(p, "safe", False):
                s["safe"] += 1
            if not getattr(p, "alive", True):
                s["dead"] += 1
        return stats

    def _format_room_title(self, room_stats):
        """Format per-room stats into a short title line."""
        if not room_stats:
            return ""
        parts = []
        for rid in sorted(room_stats.keys(), key=lambda x: str(x)):
            s = room_stats[rid]
            parts.append(
                f"{rid}:T={s.get('total',0)}/S={s.get('safe',0)}/D={s.get('dead',0)}"
            )
        return "Rooms: " + "  ".join(parts)

    def _format_stats_title(self, prefix, stats):
        if not stats:
            return prefix or ""
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(f"total={stats.get('total', 0)}")
        parts.append(f"safe={stats.get('safe', 0)}")
        parts.append(f"dead={stats.get('dead', 0)}")
        return "  ".join(parts)

    # ---- public API -----------------------------------------------------

    def visualize(self, graph={(3, 4): {"F": 1}}, people=None, delay=0.01, stats=None, save_path=None):
        """
        Visualize a single-floor map.

        graph: dict[(i,j)] -> attrs
        people: iterable of objects with at least .loc, .safe, .alive, .id
        stats: optional dict with keys total/safe/dead for title annotation
        """
        if people is None:
            people = []

        axes = self._ensure_figure(1)
        ax = axes[0]
        ax.clear()

        gdata = self._prepare_grid_data(graph)
        self.draw_grid(ax, gdata)

        X, Y, C = self._prepare_people_data(people)
        self.draw_people(ax, X, Y, C)

        # floor-level stats line
        title_main = (
            self._format_stats_title("Floor 1", stats) if stats else "Floor 1"
        )
        # per-room stats line (if any rooms are defined)
        room_stats = self._compute_room_stats(graph, people)
        title_rooms = self._format_room_title(room_stats)
        title = title_main if not title_rooms else f"{title_main}\n{title_rooms}"
        ax.set_title(title)

        self.fig.tight_layout()
        self.fig.canvas.draw_idle()
        # interactive view only; saved frames are produced by dedicated
        # off-screen helpers so they are independent of the window size
        plt.pause(delay)

    def visualize_multi(
        self,
        floor_indices,
        floor_graphs,
        floor_people,
        stats_per_floor,
        delay=0.01,
        save_path=None,
    ):
        """
        Visualize multiple floors side-by-side.

        floor_indices: list of floor indices (z)
        floor_graphs:  list of per-floor 2D graphs (same format as visualize)
        floor_people:  list of per-floor people lists (loc is 2D)
        stats_per_floor: dict z -> stats dict (total/safe/dead)
        """
        n = len(floor_indices)
        if n == 0:
            return

        # arrange subplots in roughly square grid
        ncols = int(math.ceil(math.sqrt(n)))
        nrows = int(math.ceil(n / ncols))

        # create figure only once; reuse between frames so we don't keep
        # popping new windows for every animation step
        if self.fig is None or self.axes is None:
            self.fig, self.axes = plt.subplots(nrows, ncols, squeeze=False)
        else:
            # if layout changed (different number of floors), recreate
            existing_nrows, existing_ncols = self.axes.shape
            if existing_nrows != nrows or existing_ncols != ncols:
                plt.close(self.fig)
                self.fig, self.axes = plt.subplots(nrows, ncols, squeeze=False)
        axes = self.axes.ravel()

        for idx, z in enumerate(floor_indices):
            ax = axes[idx]
            ax.clear()

            graph = floor_graphs[idx]
            people = floor_people[idx]
            gdata = self._prepare_grid_data(graph)
            self.draw_grid(ax, gdata)

            X, Y, C = self._prepare_people_data(people)
            self.draw_people(ax, X, Y, C)

            stats = stats_per_floor.get(z, {})
            title_prefix = f"Floor {z + 1}"
            title_main = self._format_stats_title(title_prefix, stats)
            # per-room stats for this floor
            room_stats = self._compute_room_stats(graph, people)
            title_rooms = self._format_room_title(room_stats)
            title = title_main if not title_rooms else f"{title_main}\n{title_rooms}"
            ax.set_title(title)

        # hide any unused axes
        for j in range(n, axes.size):
            axes[j].set_visible(False)

        self.fig.tight_layout()
        self.fig.canvas.draw_idle()
        # interactive view only; saved frames are produced by dedicated
        # off-screen helpers so they are independent of the window size
        plt.pause(delay)

    # ---- off-screen, fixed-size frame saving ---------------------------

    def save_frame_single(self, graph, people, stats, save_path, dpi=150):
        """
        Save a single-floor frame to disk using a fixed figure size,
        independent of the interactive window size.
        """
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

        fig = Figure(figsize=(6, 6), dpi=dpi)
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(1, 1, 1)

        gdata = self._prepare_grid_data(graph)
        self.draw_grid(ax, gdata)

        X, Y, C = self._prepare_people_data(people)
        self.draw_people(ax, X, Y, C)

        title_main = (
            self._format_stats_title("Floor 1", stats) if stats else "Floor 1"
        )
        room_stats = self._compute_room_stats(graph, people)
        title_rooms = self._format_room_title(room_stats)
        title = title_main if not title_rooms else f"{title_main}\n{title_rooms}"
        ax.set_title(title)

        fig.tight_layout()
        fig.savefig(save_path, dpi=dpi)
        plt.close(fig)

    def save_frame_multi(
        self,
        floor_indices,
        floor_graphs,
        floor_people,
        stats_per_floor,
        save_path,
        dpi=150,
    ):
        """
        Save a multi-floor frame to disk using a fixed figure size,
        independent of the interactive window size.
        """
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

        n = len(floor_indices)
        if n == 0:
            return

        # same layout rule as visualize_multi, but on an off-screen figure
        ncols = int(math.ceil(math.sqrt(n)))
        nrows = int(math.ceil(n / ncols))

        # choose a base size per panel to keep scale reasonable
        fig_width = 4 * ncols
        fig_height = 4 * nrows
        fig = Figure(figsize=(fig_width, fig_height), dpi=dpi)
        canvas = FigureCanvas(fig)
        axes = fig.subplots(nrows, ncols).ravel()

        for idx, z in enumerate(floor_indices):
            ax = axes[idx]
            graph = floor_graphs[idx]
            people = floor_people[idx]

            gdata = self._prepare_grid_data(graph)
            self.draw_grid(ax, gdata)

            X, Y, C = self._prepare_people_data(people)
            self.draw_people(ax, X, Y, C)

            stats = stats_per_floor.get(z, {})
            title_prefix = f"Floor {z + 1}"
            title_main = self._format_stats_title(title_prefix, stats)
            room_stats = self._compute_room_stats(graph, people)
            title_rooms = self._format_room_title(room_stats)
            title = title_main if not title_rooms else f"{title_main}\n{title_rooms}"
            ax.set_title(title)

        # hide any unused axes
        for j in range(n, axes.size):
            axes[j].set_visible(False)

        fig.tight_layout()
        fig.savefig(save_path, dpi=dpi)
        plt.close(fig)
