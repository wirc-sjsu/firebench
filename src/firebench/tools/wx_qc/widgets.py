import tkinter as tk
from tkinter import ttk

import numpy as np
import matplotlib.dates as mdates

from . import theme


class StationListPanes:
    """Cross-pane multi-select station picker: 3 scrollable panes split by
    category (unclassified/skipped/greenlit), each collapsible via its header
    toggle. Ctrl/Cmd-click toggles a station in one selection set spanning all
    3 panes; shift-click range-selects within a single pane only. Plain click
    always narrows to just that station and reports it via on_click."""

    _CATS = (("kept", "Unclassified", ""), ("skipped", "Skipped", "[x] "),
             ("greenlit", "Greenlit", "[ok] "))

    def __init__(self, parent, on_click=None, on_select_change=None, height=8, header_bg=None):
        """Initialize the station list picker widget with three collapsible panes.

        Args:
            parent: Tk parent widget.
            on_click (callable): Optional callback(stid) fired when a station is clicked (narrows selection to that one).
            on_select_change (callable): Optional callback() fired when multi-select changes via Ctrl/Cmd or Shift clicks.
            height (int): Number of rows visible in each pane (default 8).
            header_bg (str): Background color for pane headers; uses theme.ACCENT if None.
        """
        self.on_click = on_click
        self.on_select_change = on_select_change
        header_bg = header_bg if header_bg is not None else theme.ACCENT
        self.selected = set()
        self._order = {cat: [] for cat, _, _ in self._CATS}
        self._last_idx = {cat: None for cat, _, _ in self._CATS}
        self.trees = {}
        self._bodies = {}
        self._labels = {}
        self._toggle_btns = {}
        self._collapsed = {cat: False for cat, _, _ in self._CATS}

        pw = ttk.PanedWindow(parent, orient="vertical")
        pw.pack(fill="both", expand=True)
        for cat, label, _ in self._CATS:
            fr = tk.Frame(pw)
            pw.add(fr, weight=1)

            hdr = tk.Frame(fr, bg=header_bg)
            hdr.pack(fill="x")
            btn = tk.Label(hdr, text="▾", bg=header_bg, fg="white",
                           font=("", 10), cursor="hand2", padx=6)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, c=cat: self._toggle(c))
            lbl = tk.Label(hdr, text=label, bg=header_bg, fg="white",
                           font=theme.FONT_SECTION, anchor="w")
            lbl.pack(side="left", fill="x", expand=True, pady=4)
            lbl.bind("<Button-1>", lambda e, c=cat: self._toggle(c))
            self._toggle_btns[cat] = btn
            self._labels[cat] = lbl

            body = tk.Frame(fr)
            body.pack(fill="both", expand=True)
            self._bodies[cat] = body
            tv = ttk.Treeview(body, show="tree", selectmode="none", height=height,
                               style="Pane.Treeview")
            tv.column("#0", width=150, anchor="w")
            sb = ttk.Scrollbar(body, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            tv.pack(fill="both", expand=True)
            tv.tag_configure("sel", background=theme.ACCENT, foreground="white")
            tv.bind("<Button-1>", lambda e, c=cat: self._on_click(e, c))
            tv.bind("<Shift-Button-1>", lambda e, c=cat: self._on_shift_click(e, c))
            tv.bind("<Control-Button-1>", lambda e, c=cat: self._on_ctrl_click(e, c))
            tv.bind("<Command-Button-1>", lambda e, c=cat: self._on_ctrl_click(e, c))
            self.trees[cat] = tv

    def _toggle(self, cat):
        """Toggle collapse/expand of a pane."""
        self._collapsed[cat] = not self._collapsed[cat]
        if self._collapsed[cat]:
            self._bodies[cat].pack_forget()
            self._toggle_btns[cat].configure(text="▸")
        else:
            self._bodies[cat].pack(fill="both", expand=True)
            self._toggle_btns[cat].configure(text="▾")

    def refresh(self, stids, skip_list, green_list, status_fn=None):
        """Rebuild the three panes with the given station set, bucketed by classification.

        Args:
            stids (list or set): All station IDs to display.
            skip_list (dict): Mapping of skipped station IDs to rejection reasons.
            green_list (set): Set of greenlit station IDs.
            status_fn (callable): Optional callback(stid) -> str that returns a status prefix for each station.

        Returns:
            None. Optimizes single-station moves without full redraw where possible.
        """
        buckets = {
            "kept":     [s for s in stids if s not in skip_list and s not in green_list],
            "skipped":  [s for s in stids if s in skip_list],
            "greenlit": [s for s in stids if s in green_list],
        }
        self.selected &= set(stids)
        if self._apply_single_move(buckets, status_fn):
            return
        for cat, label, fixed_prefix in self._CATS:
            tv = self.trees[cat]
            tv.delete(*tv.get_children())
            ids = buckets[cat]
            self._order[cat] = ids
            self._labels[cat].configure(text=f"{label}  ({len(ids)})")
            for stid in ids:
                prefix = fixed_prefix or (status_fn(stid) if status_fn else "")
                tag = ("sel",) if stid in self.selected else ()
                tv.insert("", "end", iid=stid, text=f"{prefix}{stid}", tags=tag)

    def _apply_single_move(self, buckets, status_fn):
        """Optimize refresh when exactly one station moves between categories."""
        src_cat = dst_cat = moved_out = moved_in = None
        for cat, _, _ in self._CATS:
            old, new = self._order[cat], buckets[cat]
            if old == new:
                continue
            if len(old) - len(new) == 1:
                gone = set(old) - set(new)
                if len(gone) != 1 or src_cat is not None:
                    return False
                (m,) = gone
                if [s for s in old if s != m] != new:
                    return False
                src_cat, moved_out = cat, m
            elif len(new) - len(old) == 1:
                came = set(new) - set(old)
                if len(came) != 1 or dst_cat is not None:
                    return False
                (m,) = came
                if [s for s in new if s != m] != old:
                    return False
                dst_cat, moved_in = cat, m
            else:
                return False
        if src_cat is None or dst_cat is None or moved_out != moved_in:
            return False
        stid = moved_out
        labels = {cat: label for cat, label, _ in self._CATS}
        prefixes = {cat: p for cat, _, p in self._CATS}
        self.trees[src_cat].delete(stid)
        self._order[src_cat] = buckets[src_cat]
        prefix = prefixes[dst_cat] or (status_fn(stid) if status_fn else "")
        tag = ("sel",) if stid in self.selected else ()
        self.trees[dst_cat].insert("", buckets[dst_cat].index(stid), iid=stid,
                                   text=f"{prefix}{stid}", tags=tag)
        self._order[dst_cat] = buckets[dst_cat]
        for cat in (src_cat, dst_cat):
            self._labels[cat].configure(text=f"{labels[cat]}  ({len(buckets[cat])})")
        return True

    def _repaint(self):
        """Update visual selection state (tags) in all panes to match self.selected."""
        for cat, tv in self.trees.items():
            for iid in self._order[cat]:
                tv.item(iid, tags=("sel",) if iid in self.selected else ())

    def select_only(self, stid):
        """Select exactly one station across all panes; scroll to show it.

        Args:
            stid (str): Station ID to select.
        """
        self.selected = {stid}
        self._repaint()
        for cat, ids in self._order.items():
            if stid in ids:
                self.trees[cat].see(stid)

    def select_many(self, stids):
        """Set multi-select to the given set of station IDs; scroll to show the first in each pane.

        Args:
            stids (list or set): Station IDs to select; filtered to only those present in the current data.
        """
        known = set().union(*self._order.values()) if self._order else set()
        self.selected = set(stids) & known
        self._repaint()
        for cat, ids in self._order.items():
            common = [i for i in ids if i in self.selected]
            if common:
                self.trees[cat].see(common[0])

    def _on_click(self, event, cat):
        """Handle plain click: select that station only and fire on_click callback."""
        tv = self.trees[cat]
        iid = tv.identify_row(event.y)
        if not iid:
            return "break"
        self._last_idx[cat] = self._order[cat].index(iid)
        self.select_only(iid)
        if self.on_click:
            self.on_click(iid)
        return "break"

    def _on_ctrl_click(self, event, cat):
        """Handle Ctrl/Cmd-click: toggle station in multi-select set."""
        tv = self.trees[cat]
        iid = tv.identify_row(event.y)
        if not iid:
            return "break"
        self._last_idx[cat] = self._order[cat].index(iid)
        if iid in self.selected:
            self.selected.discard(iid)
        else:
            self.selected.add(iid)
        self._repaint()
        if self.on_select_change:
            self.on_select_change()
        return "break"

    def _on_shift_click(self, event, cat):
        """Handle Shift-click: extend multi-select to a range within the same pane."""
        tv = self.trees[cat]
        iid = tv.identify_row(event.y)
        if not iid:
            return "break"
        order = self._order[cat]
        idx = order.index(iid)
        last = self._last_idx[cat] if self._last_idx[cat] is not None else idx
        lo, hi = sorted((last, idx))
        self.selected.update(order[lo:hi + 1])
        self._last_idx[cat] = idx
        self._repaint()
        if self.on_select_change:
            self.on_select_change()
        return "break"

    def get_selected(self):
        """Get the currently selected station IDs.

        Returns:
            set: Set of selected station IDs.
        """
        return set(self.selected)


class TimeNavigator(tk.Canvas):
    """Time-window scrubber (Google-Finance/d3-brush style): the track shows
    a faint sparkline of the whole record with a shaded pane over the current
    view window. Drag the pane to pan, drag its right edge to resize, click
    outside the pane to jump there. on_change(start, dur, final) fires live
    during a drag and once on release; set_domain/set_valid_range/set_window
    are silent, so callers can push state without a feedback loop."""

    _M = 10
    _TRACK_TOP = 3
    _EDGE_GRAB = 6
    _TICK_STEPS = (1, 2, 7, 14, 30, 90)

    def __init__(self, parent, height=56, min_dur=1 / 24, on_change=None):
        """Initialize the time-window navigator canvas.

        Args:
            parent: Tk parent widget.
            height (int): Canvas height in pixels (default 56).
            min_dur (float): Minimum window duration in date-num units; default 1/24 (1 hour).
            on_change (callable): Optional callback(start, dur, final) fired during drag and on release.
                start and dur are in date-num units (matplotlib dates). final=False during drag, True on release.
        """
        # ttk widgets don't expose per-widget bg; query parent first, fall back to theme
        try:
            bg = parent.cget("bg")
        except tk.TclError:
            bg = ttk.Style().lookup("TFrame", "background") or "#d9d9d9"
        super().__init__(parent, height=height, highlightthickness=0, bg=bg)
        self._height = height
        self._min_dur = min_dur
        self._on_change = on_change
        self._lo = self._hi = None
        self._vlo = self._vhi = None
        self._start = 0.0
        self._dur = 1.0
        self._sx = self._sy = None
        # macOS Tk ignores canvas stipple; precompute tint instead of stippling
        self._pane_fill = self._tint(theme.ACCENT, 0.18)
        self._drag = None
        self._pan_grab = 0.0
        self._hover = False
        self.bind("<Configure>",        lambda e: self._redraw())
        self.bind("<Button-1>",         self._on_press)
        self.bind("<B1-Motion>",        self._on_drag)
        self.bind("<ButtonRelease-1>",  self._on_release)
        self.bind("<Motion>",           self._on_motion)
        self.bind("<Enter>",            self._on_enter)
        self.bind("<Leave>",            self._on_leave)

    def set_domain(self, lo, hi):
        """Set the overall domain (full extent of available data).

        Args:
            lo (float): Low end of domain in date-num units.
            hi (float): High end of domain in date-num units.
        """
        self._lo, self._hi = lo, hi
        self._start, self._dur = self._clamp(self._start, self._dur)
        self._redraw()

    def set_valid_range(self, lo=None, hi=None):
        """Restrict where the window may live. (None, None) means the whole
        domain is valid; a range narrower than min_dur falls back to the full
        domain. Regions outside the valid range render as muted zones."""
        self._vlo, self._vhi = lo, hi
        self._start, self._dur = self._clamp(self._start, self._dur)
        self._redraw()

    def set_window(self, start, dur):
        """Set the current view window silently without firing on_change.

        Args:
            start (float): Window start in date-num units.
            dur (float): Window duration in date-num units.
        """
        self._start, self._dur = self._clamp(start, dur)
        self._redraw()

    def get_window(self):
        """Get the current view window.

        Returns:
            tuple: (start, dur) in date-num units.
        """
        return self._start, self._dur

    def has_series(self):
        """Check whether a sparkline series has been set and is non-empty.

        Returns:
            bool: True if series data is available, False otherwise.
        """
        return self._sx is not None and len(self._sx) > 0

    def set_series(self, x, y):
        """Set the sparkline data (time series to render behind the window).

        Args:
            x (array-like or None): X-values in date-num units; None clears the series.
            y (array-like or None): Y-values (typically measurements); None clears the series.

        Returns:
            None. Pairs are aligned by index, clipped to min(len(x), len(y)), and filtered to remove NaNs.
        """
        if x is None or y is None:
            self._sx = self._sy = None
            self._redraw()
            return
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n = min(len(x), len(y))
        x, y = x[:n], y[:n]
        keep = ~(np.isnan(x) | np.isnan(y))
        self._sx, self._sy = x[keep], y[keep]
        self._redraw()

    def _has_domain(self):
        """Check if domain is set and valid."""
        return (self._lo is not None and self._hi is not None
                and self._hi > self._lo)

    def _plot_w(self):
        """Get plot width in pixels, accounting for margins."""
        return max(self.winfo_width() - 2 * self._M, 1)

    def _track_bottom(self):
        """Get Y-coordinate of track bottom in canvas pixels."""
        return self._height - 21

    def _x_to_data(self, px):
        """Convert canvas X pixel to date-num value in current domain."""
        frac = (px - self._M) / self._plot_w()
        return self._lo + frac * (self._hi - self._lo)

    def _data_to_x(self, v):
        """Convert date-num value in current domain to canvas X pixel."""
        frac = (v - self._lo) / (self._hi - self._lo)
        return self._M + frac * self._plot_w()

    def _valid_range(self):
        """Get the valid range, clamped to domain if narrower than min_dur."""
        vlo = self._lo if self._vlo is None else max(self._vlo, self._lo)
        vhi = self._hi if self._vhi is None else min(self._vhi, self._hi)
        if vhi - vlo < self._min_dur:
            return self._lo, self._hi
        return vlo, vhi

    def _clamp(self, start, dur):
        """Clamp window to domain and valid range, respecting min_dur."""
        if not self._has_domain():
            return start, dur
        vlo, vhi = self._valid_range()
        dur = min(max(dur, self._min_dur), self._hi - self._lo)
        if dur >= vhi - vlo:
            # Full-width window: confine to domain, not valid range, or shrinking
            # the view to the valid range would freeze at station extent
            start = min(max(start, self._lo), self._hi - dur)
        else:
            start = min(max(start, vlo), vhi - dur)
        return start, dur

    @staticmethod
    def _tint(color, frac):
        """Blend color toward white by fraction frac (0=original, 1=white)."""
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        mix = lambda c: int(round(255 - (255 - c) * frac))
        return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"

    @staticmethod
    def _fmt_dur(dur):
        """Format duration in date-num units as a readable string (e.g. '12 h' or '3.5 d')."""
        hours = dur * 24.0
        if hours < 48:
            val, unit = hours, "h"
        else:
            val, unit = dur, "d"
        if abs(val - round(val)) < 1e-9:
            return f"{val:.0f} {unit}"
        return f"{val:.1f} {unit}"

    def _redraw(self):
        """Redraw the entire canvas."""
        self.delete("all")
        w = self.winfo_width()
        tb = self._track_bottom()
        self.create_rectangle(self._M, self._TRACK_TOP, w - self._M, tb,
                              fill="#ffffff", outline="#c2cad1")
        if not self._has_domain():
            return
        # Layering order: tint fill, sparkline, unavailable zones, ticks, frame
        # This fakes transparency; Tk canvas has no alpha
        self._draw_pane_fill(tb)
        self._draw_sparkline(w, tb)
        self._draw_unavailable(tb)
        self._draw_ticks(w, tb)
        self._draw_pane_frame(tb)
        if self._hover or self._drag is not None:
            self._draw_popup(w)

    def _draw_sparkline(self, w, tb):
        """Draw the time series sparkline within the track area."""
        if self._sx is None or len(self._sx) == 0:
            return
        lo, hi = self._lo, self._hi
        sx, sy = self._sx, self._sy
        in_dom = (sx >= lo) & (sx <= hi)
        sx, sy = sx[in_dom], sy[in_dom]
        if len(sx) == 0:
            return
        # Downsample to ~1 point per pixel for performance
        npix = int(self._plot_w())
        if len(sx) > npix > 0:
            idx = np.linspace(0, len(sx) - 1, npix).astype(int)
            sx, sy = sx[idx], sy[idx]
        ymin, ymax = float(np.min(sy)), float(np.max(sy))
        top_in, bot_in = self._TRACK_TOP + 3, tb - 3
        if ymax <= ymin:
            ypix = np.full(len(sy), (top_in + bot_in) / 2.0)
        else:
            ypix = bot_in - (sy - ymin) / (ymax - ymin) * (bot_in - top_in)
        xpix = self._M + (sx - lo) / (hi - lo) * self._plot_w()
        pts = list(zip(xpix, ypix))
        # Draw filled area, then line on top
        poly = [(xpix[0], bot_in)] + pts + [(xpix[-1], bot_in)]
        if len(poly) >= 3:
            self.create_polygon([c for xy in poly for c in xy],
                                fill="#dfe6ee", outline="")
        if len(pts) >= 2:
            self.create_line([c for xy in pts for c in xy],
                            fill="#b9c6d2", width=1)

    def _draw_unavailable(self, tb):
        """Draw muted zones for regions outside the valid range."""
        vlo, vhi = self._valid_range()
        for a, b in ((self._lo, vlo), (vhi, self._hi)):
            if b - a <= 0:
                continue
            x0, x1 = self._data_to_x(a), self._data_to_x(b)
            self.create_rectangle(x0, self._TRACK_TOP, x1, tb,
                                  fill="#e9e9e9", outline="")

    def _draw_ticks(self, w, tb):
        """Draw date ticks and labels along the track."""
        span = self._hi - self._lo
        ppd = self._plot_w() / span      # pixels per day
        step = self._TICK_STEPS[-1]
        for s in self._TICK_STEPS:
            if s * ppd >= 70:
                step = s
                break
        first = np.ceil(self._lo / step) * step
        t = first
        while t <= self._hi + 1e-9:
            x = self._data_to_x(t)
            self.create_line(x, tb, x, tb + 4, fill="#c2cad1")
            label = mdates.num2date(t).strftime("%b %d").replace(" 0", " ")
            self.create_text(x, tb + 5, text=label, anchor="n",
                            fill=theme.MUTED, font=theme.FONT_SMALL)
            t += step

    def _draw_pane_fill(self, tb):
        """Draw the tinted fill for the current window pane."""
        x0 = self._data_to_x(self._start)
        x1 = self._data_to_x(self._start + self._dur)
        self.create_rectangle(x0, self._TRACK_TOP, x1, tb,
                              fill=self._pane_fill, outline="")

    def _draw_pane_frame(self, tb):
        """Draw the border and resize handle for the current window pane."""
        x0 = self._data_to_x(self._start)
        x1 = self._data_to_x(self._start + self._dur)
        self.create_rectangle(x0, self._TRACK_TOP, x1, tb,
                              fill="", outline=theme.ACCENT, width=2)
        cy = (self._TRACK_TOP + tb) / 2.0
        self.create_rectangle(x1 - 2, cy - 9, x1 + 2, cy + 9,
                              fill=theme.ACCENT, outline=theme.ACCENT)

    def _draw_popup(self, w):
        """Draw a tooltip showing window dates and duration; reposition to stay on-screen."""
        start, dur = self._start, self._dur
        d0 = mdates.num2date(start).strftime("%b %d %H:%M")
        d1 = mdates.num2date(start + dur).strftime("%b %d %H:%M")
        text = f"{d0} → {d1} · {self._fmt_dur(dur)}"
        cx = self._data_to_x(start + dur / 2.0)
        cx = min(max(cx, self._M), w - self._M)
        py = self._TRACK_TOP - 6
        t = self.create_text(cx, py, text=text, anchor="s", fill="white",
                            font=theme.FONT_SMALL)
        x0, y0, x1, y1 = self.bbox(t)
        dx = dy = 0
        if x0 < 2:
            dx = 2 - x0
        elif x1 > w - 2:
            dx = w - 2 - x1
        if y0 < 2:
            dy = 2 - y0
        if dx or dy:
            self.move(t, dx, dy)
            x0, y0, x1, y1 = self.bbox(t)
        r = self.create_rectangle(x0 - 4, y0 - 2, x1 + 4, y1 + 2,
                                 fill="#2b3138", outline="")
        self.tag_raise(t, r)

    def _fire(self, final):
        """Fire the on_change callback with current window state."""
        if self._on_change is not None:
            self._on_change(self._start, self._dur, final)

    def _resize_zone(self, x0, x1):
        """Calculate the drag zone for resizing the right edge of the pane."""
        # Asymmetric zone: limit inner reach to 1/3 pane width to avoid
        # swallowing pan grabs when pane is narrower than grab zone
        inner = min(self._EDGE_GRAB, (x1 - x0) / 3.0)
        return x1 - inner, x1 + self._EDGE_GRAB

    def _on_press(self, e):
        """Handle mouse down: detect whether drag is resize, pan, or jump."""
        if not self._has_domain():
            return
        x1 = self._data_to_x(self._start + self._dur)
        x0 = self._data_to_x(self._start)
        rz0, rz1 = self._resize_zone(x0, x1)
        if rz0 <= e.x <= rz1:
            self._drag = "resize"
        elif x0 <= e.x <= x1:
            self._drag = "pan"
            self._pan_grab = self._x_to_data(e.x) - self._start
        else:
            # Click outside pane: center window at click point, then enable panning
            center = self._x_to_data(e.x)
            self._start, self._dur = self._clamp(center - self._dur / 2.0, self._dur)
            self._drag = "pan"
            self._pan_grab = self._x_to_data(e.x) - self._start
            self._redraw()
            self._fire(False)

    def _on_drag(self, e):
        """Handle mouse motion during drag: update window and redraw; fire on_change with final=False."""
        if self._drag is None or not self._has_domain():
            return
        if self._drag == "resize":
            dur = self._x_to_data(e.x) - self._start
            dur = min(dur, self._valid_range()[1] - self._start)
            self._start, self._dur = self._clamp(self._start, dur)
        else:  # pan
            self._start, self._dur = self._clamp(
                self._x_to_data(e.x) - self._pan_grab, self._dur)
        self._redraw()
        self._fire(False)

    def _on_release(self, e):
        """Handle mouse up: clear drag state and fire on_change with final=True."""
        if self._drag is None:
            return
        self._drag = None
        self._redraw()
        self._fire(True)

    def _on_motion(self, e):
        """Handle mouse motion: update cursor to reflect resize/pan/arrow affordance."""
        if not self._has_domain():
            self.configure(cursor="arrow")
            return
        x1 = self._data_to_x(self._start + self._dur)
        x0 = self._data_to_x(self._start)
        rz0, rz1 = self._resize_zone(x0, x1)
        if rz0 <= e.x <= rz1:
            self.configure(cursor="sb_h_double_arrow")
        elif x0 <= e.x <= x1:
            self.configure(cursor="fleur")
        else:
            self.configure(cursor="arrow")

    def _on_enter(self, e):
        """Handle mouse enter: show tooltip if domain is set."""
        self._hover = True
        if self._has_domain():
            self._redraw()

    def _on_leave(self, e):
        """Handle mouse leave: hide tooltip if not dragging."""
        self._hover = False
        if self._drag is None:
            self._redraw()
