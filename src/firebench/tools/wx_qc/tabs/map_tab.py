import time
import warnings
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import matplotlib.cm as mcm
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import h5py
import geopandas as gpd
from datetime import datetime

from ..state import visible_issues
from ..theme import ACCENT, MISSING_MARKER, MUTED, SKIP_RED, GREEN_OK, UNDECIDED, FONT_MONO, FIG_DPI, PAD
from ..widgets import TimeNavigator
from ..constants import MAP_COLOR_MODES, parse_nonnegative_finite


class MapTabMixin:
    """Render spatial QC/data views from App-owned station and map state.

    App state:
        Expects station/statistics/issues and decision collections, ``cfg``,
        current-station/global-time state, map/perimeter caches initialized by
        App, shared notebook/status widgets, and station navigation and refresh
        helpers supplied by the other mixins.
    """

    def _build_map_tab(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Map")
        ctrl = ttk.Frame(f)
        ctrl.pack(fill="x", padx=4, pady=4)
        ttk.Label(ctrl, text="Color by:").pack(side="left")
        self.var_map_color = tk.StringVar(value="issues")
        cb_mode = ttk.Combobox(
            ctrl,
            textvariable=self.var_map_color,
            state="readonly",
            width=16,
            values=MAP_COLOR_MODES,
        )
        cb_mode.pack(side="left", padx=PAD)
        # write-trace ensures both interactive picks and programmatic set() calls
        # (e.g. session restore) route through _on_map_mode_change; <<ComboboxSelected>>
        # binding alone would miss the latter, breaking contextual control gating.
        self.var_map_color.trace_add("write", self._on_map_mode_change)
        ttk.Label(ctrl, text="Click station point to open detail", style="Muted.TLabel").pack(
            side="left", padx=PAD
        )

        # ── variable_value mode: which variable ─────────────────────────────
        self._map_value_ctrl = ttk.Frame(f)
        ttk.Label(self._map_value_ctrl, text="Variable:").pack(side="left")
        self.cb_map_value = ttk.Combobox(
            self._map_value_ctrl, textvariable=self.var_map_value, state="readonly", width=24
        )
        self.cb_map_value.pack(side="left", padx=4)
        self.cb_map_value.bind("<<ComboboxSelected>>", lambda e: self._on_map_value_change())

        # ── variable_value / wind_combo modes: agg fn + time window ─────────
        self._map_window_ctrl = ttk.Frame(f)
        ttk.Label(self._map_window_ctrl, text="Agg:").pack(side="left")
        cb_agg = ttk.Combobox(
            self._map_window_ctrl,
            textvariable=self._map_agg_var,
            state="readonly",
            width=8,
            values=["mean", "median", "max", "min", "last"],
        )
        cb_agg.pack(side="left", padx=(2, 10))
        cb_agg.bind("<<ComboboxSelected>>", lambda e: self._map_windowed_recompute())
        ttk.Label(self._map_window_ctrl, text="Window:").pack(side="left")
        cb_dt = ttk.Combobox(
            self._map_window_ctrl,
            textvariable=self._map_dt_var,
            state="readonly",
            width=6,
            values=["1h", "6h", "1d", "7d", "full"],
        )
        cb_dt.pack(side="left", padx=(2, 10))
        cb_dt.bind("<<ComboboxSelected>>", self._on_map_dt_change)
        self.nav_map_window = TimeNavigator(self._map_window_ctrl, on_change=self._on_map_window_nav)
        self.nav_map_window.pack(side="left", padx=(2, 10), fill="x", expand=True)
        self.lbl_map_window = ttk.Label(
            self._map_window_ctrl, text="—", font=FONT_MONO, style="Muted.TLabel"
        )
        self.lbl_map_window.pack(side="left", padx=4)
        # Calm-wind filter: shared tk vars with TS wind tab for sync.
        # In wind_combo: excludes below-threshold samples from circular mean (drawn muted).
        # In variable_value on wind vars: masks calm samples before aggregation.
        self._map_calm_ctrl = ttk.Frame(self._map_window_ctrl)
        ttk.Checkbutton(
            self._map_calm_ctrl,
            text="Calm <",
            variable=self.var_wind_calm,
            command=self._on_map_calm_change,
        ).pack(side="left")
        ent_calm = ttk.Entry(self._map_calm_ctrl, width=4, textvariable=self.var_wind_calm_thresh)
        ent_calm.pack(side="left")
        ent_calm.bind("<Return>", self._on_map_calm_change)
        ent_calm.bind("<FocusOut>", self._on_map_calm_change)
        ttk.Label(self._map_calm_ctrl, text="m/s").pack(side="left")

        fig_map = Figure(figsize=(8, 5), dpi=FIG_DPI)
        self.ax_map = fig_map.add_subplot(111)
        self.canvas_map = FigureCanvasTkAgg(fig_map, master=f)
        self._map_toolbar = NavigationToolbar2Tk(self.canvas_map, f)
        self._map_toolbar.pack(fill="x")
        self.canvas_map.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_map.mpl_connect("motion_notify_event", self._on_map_motion)
        self.canvas_map.mpl_connect("button_press_event", self._on_map_click)
        self._on_map_mode_change()

    _MAP_CLABELS = {
        "issues": "# Issues",
        "wd_nan_pct": "WD NaN %",
        "n_variables": "# Variables",
    }

    # QC Status mode: categorical (not numeric) — uses discrete legend instead of colorbar.
    _QC_STATUS_COLORS = {
        "skip": (SKIP_RED, "Skip-listed"),
        "green": (GREEN_OK, "Greenlit"),
        "undecided": (UNDECIDED, "Undecided"),
    }

    # Diverging for temperature (coolwarm), sequential for most, circular for WD.
    _VAR_CMAP = {
        "air_temperature": "coolwarm",
        "relative_humidity": "YlGnBu",
        "solar_radiation": "inferno",
        "fuel_moisture_content_10h": "YlOrBr_r",
        "wind_speed": "viridis",
        "wind_gust": "viridis",
        "wind_direction": "twilight",
    }

    _MAP_DT_MINUTES = {"1h": 60, "6h": 360, "1d": 1440, "7d": 10080}  # "full" -> None

    def _map_cval(self, stid, cb):
        """Get numeric color value for station in current color mode.

        Args:
            stid (str): station identifier.
            cb (str): color mode ('issues', 'wd_nan_pct', 'n_variables', 'n_pts').

        Returns:
            float: color value for the station in the given mode.
        """
        if cb == "issues":
            return len(visible_issues(self.all_issues.get(stid, []), self.cfg))
        elif cb == "wd_nan_pct":
            return self.all_stats[stid].get("wind_direction", {}).get("nan_pct", 0.0)
        elif cb == "n_variables":
            return len(self.stations[stid]["variables"])
        else:
            return self.all_stats[stid]["_time"]["n_pts"]

    def _map_qc_status(self, stid):
        """Determine QC status category for station.

        Args:
            stid (str): station identifier.

        Returns:
            str: QC status ('skip', 'green', or 'undecided').
        """
        if stid in self.skip_list:
            return "skip"
        if stid in self.green_list:
            return "green"
        return "undecided"

    def _on_map_mode_change(self, *_a):
        """Handle color mode combobox change; rebuild UI and redraw.

        Triggered by var_map_color write-trace, routing both interactive and
        programmatic changes (e.g., session restore) through this callback.
        Packs/unpacks mode-specific controls and refreshes the map display.
        """
        self._map_close_popup()
        self._map_clear_hover()
        cb = self.var_map_color.get()
        windowed = cb in ("variable_value", "wind_combo")
        if cb == "variable_value":
            all_vars = sorted({v for s in self.stations.values() for v in s["variables"]})
            self.cb_map_value["values"] = all_vars
            if all_vars and not self.var_map_value.get():
                self.var_map_value.set(all_vars[0])
            self._map_value_ctrl.pack(fill="x", padx=4, pady=(0, 4), before=self._map_toolbar)
        else:
            self._map_value_ctrl.pack_forget()
        if windowed:
            self._map_window_ctrl.pack(fill="x", padx=4, pady=(0, 4), before=self._map_toolbar)
            if self.stations:
                self._map_recompute_windows()
                n = len(self._map_window_bounds)
                self._map_window_idx = min(self._map_window_idx, max(n - 1, 0))
                self._sync_map_nav()
                self._update_map_window_label()
        else:
            self._map_window_ctrl.pack_forget()
            # Leaving the windowed modes: drop the sparkline so a later
            # non-windowed view can't show a stale one behind the (hidden) nav.
            self.nav_map_window.set_series(None, None)
        self._map_update_calm_ctrl()
        # Single _refresh_map() call: detects stale aggregate matrix and kicks
        # off chunked recompute; completion re-calls _refresh_map() for the draw.
        # Valid cache (mode round-trip) draws immediately, no recompute.
        self._refresh_map()

    def _map_calm_relevant(self):
        """Check if calm-wind filter applies to current mode and variable.

        Returns:
            bool: True if current mode is wind_combo or variable_value on a wind variable.
        """
        cb = self.var_map_color.get()
        return cb == "wind_combo" or (
            cb == "variable_value" and self.var_map_value.get() in ("wind_speed", "wind_direction")
        )

    def _map_update_calm_ctrl(self):
        """Show or hide calm-wind filter control based on current mode.

        Visibility is determined by _map_calm_relevant; called after mode/variable changes.
        """
        if self._map_calm_relevant():
            if not self._map_calm_ctrl.winfo_manager():
                self._map_calm_ctrl.pack(side="left", padx=(10, 0))
        else:
            self._map_calm_ctrl.pack_forget()

    def _on_map_value_change(self):
        """Handle variable selection combobox change in variable_value mode.

        Updates calm control visibility and triggers windowed aggregation recompute.
        """
        self._map_update_calm_ctrl()
        self._map_windowed_recompute()

    def _map_windowed_recompute(self):
        """Trigger map refresh for windowed aggregation modes.

        Called when inputs affecting aggregate signature change (agg function, dt, etc.).
        Only triggers redraw if in windowed mode (variable_value or wind_combo).
        Staleness check in _refresh_map recomputes only if signature actually changed.
        """
        if self.var_map_color.get() in ("variable_value", "wind_combo"):
            self._refresh_map()

    def _on_map_calm_change(self, *_a):
        """Handle calm-wind filter checkbox/entry change.

        Calm params are part of aggregation signature and affect circular mean
        (wind_combo) and pre-aggregation masking (variable_value). TimeSeriesTab
        shares these variables but manages its own redraw; map does not modify TS.
        """
        try:
            threshold = parse_nonnegative_finite(self.var_wind_calm_thresh.get(), "Calm-wind threshold")
        except ValueError as exc:
            messagebox.showerror("Bad value", str(exc), parent=self)
            self.var_wind_calm_thresh.set(f"{self._last_valid_calm_threshold:g}")
            return
        self._last_valid_calm_threshold = threshold
        self.var_wind_calm_thresh.set(f"{threshold:g}")
        if self._map_calm_relevant():
            self._refresh_map()

    def _map_calm_params(self):
        """Get current calm-wind filter parameters.

        Returns:
            tuple: (on, threshold) — on (bool) = filter enabled, threshold
                (float) = the last accepted finite, non-negative m/s value.
        """
        on = bool(self.var_wind_calm.get())
        try:
            thr = parse_nonnegative_finite(self.var_wind_calm_thresh.get(), "Calm-wind threshold")
        except ValueError:
            thr = self._last_valid_calm_threshold
        return on, thr

    def _on_map_dt_change(self, event=None):
        """Handle time-window combobox selection change.

        Resets custom dt (if nav was previously resized), recomputes window grid,
        clamps current window index, syncs navigator, and updates aggregation.
        """
        self._map_dt_custom_min = None
        self._map_recompute_windows()
        n = len(self._map_window_bounds)
        self._map_window_idx = min(self._map_window_idx, max(n - 1, 0))
        self._sync_map_nav()
        self._update_map_window_label()
        self._map_windowed_recompute()

    def _map_active_dt_min(self):
        """Get current aggregation window width in minutes.

        Returns custom (nav-resized) width if set; otherwise looks up combobox selection.
        Returns None for 'full' mode (entire time range in single window).

        Returns:
            float or None: window width in minutes, or None for full range.
        """
        if self._map_dt_custom_min is not None:
            return self._map_dt_custom_min
        return self._MAP_DT_MINUTES.get(self._map_dt_var.get())

    @staticmethod
    def _fmt_map_dt(dur_min):
        """Format duration in minutes as human-readable label (e.g., '6h', '45m').

        Args:
            dur_min (float): duration in minutes.

        Returns:
            str: formatted label, dropping trailing zeros from hours.
        """
        hours = dur_min / 60.0
        if hours >= 1:
            return f"{hours:.1f}".rstrip("0").rstrip(".") + "h"
        return f"{dur_min:.0f}m"

    def _sync_map_nav(self):
        """Sync current window bounds to the TimeNavigator (silent update).

        Called after window bounds are recomputed or when navigation commits.
        Sets navigator domain to global time extent and current window position.
        Stores synced duration for nav-drag pan/resize discrimination.
        """
        # Push window bounds to navigator (silent sync after recompute).
        if self._map_t_extent is None or not self._map_window_bounds:
            return
        gmin_num, gmax_num = self._map_t_extent
        self.nav_map_window.set_domain(gmin_num, gmax_num)
        self.nav_map_window.set_valid_range(None, None)
        idx = min(self._map_window_idx, len(self._map_window_bounds) - 1)
        t0, t1 = self._map_window_bounds[idx]
        s, e = mdates.date2num(t0), mdates.date2num(t1)
        self.nav_map_window.set_window(s, e - s)
        # Store exact duration pushed: _on_map_window_nav uses this (not recomputed dt)
        # to discriminate pan (dur unchanged) vs resize (dur dragged). Rounding differences
        # between custom whole-second windows and dt_min float values can misclassify.
        self._map_nav_synced_dur = self.nav_map_window.get_window()[1]

    def _on_map_window_nav(self, start, dur, final):
        """Handle navigator drag events (pan or resize).

        Discriminates between pan (constant width, snaps to nearest window) and
        resize (width changed, commits custom dt on release). Debounces scrub
        refresh via a 120ms timer to avoid excessive redraws during drag.

        Args:
            start (float): window start time (matplotlib date-num).
            dur (float): window duration (matplotlib date-num, days).
            final (bool): True when drag is released, False during dragging.
        """
        # Navigator drag: pan (width unchanged) snaps to nearest discrete window;
        # resize (width changed) becomes custom dt (committed only on release).
        if self._map_t_extent is None or not self._map_window_bounds:
            return
        gmin_num, _ = self._map_t_extent
        dt_min = self._map_active_dt_min()
        # Discriminate pan vs resize by comparing dur against last synced value.
        # Tolerance 1e-4 days (~9 s) absorbs date2num/whole-second rounding.
        expected_dur = getattr(self, "_map_nav_synced_dur", None)
        if expected_dur is None:
            expected_dur = (self._map_t_extent[1] - gmin_num) if dt_min is None else dt_min / 1440.0
        if abs(dur - expected_dur) > 1e-4:
            if final:
                self._map_apply_custom_dt(dur, start)
            return
        if dt_min is None or len(self._map_window_bounds) <= 1:
            return
        step_days = (dt_min / 4.0) / 1440.0
        idx = int(round((start - gmin_num) / step_days))
        # Pane pinned at domain end -> snap to last window (trailing windows
        # overlap past gmax, so clamped start alone can't round to them).
        if start + dur >= self._map_t_extent[1] - 1e-9:
            idx = len(self._map_window_bounds) - 1
        self._map_window_idx = max(0, min(idx, len(self._map_window_bounds) - 1))
        self._update_map_window_label()
        if getattr(self, "_map_scrub_after_id", None) is not None:
            self.after_cancel(self._map_scrub_after_id)
        self._map_scrub_after_id = self.after(120, self._map_scrub_fire)
        if final:
            self._sync_map_nav()

    def _map_apply_custom_dt(self, dur, start):
        """Commit navigator resize as custom aggregation window width.

        Updates _map_dt_custom_min, refreshes window bounds, and snaps current
        window index to nearest grid point. Recomputes aggregation.

        Args:
            dur (float): resized window duration (matplotlib date-num, days).
            start (float): window start time (matplotlib date-num).
        """
        # Commit nav resize drag as custom window width.
        dur_min = dur * 1440.0
        self._map_dt_custom_min = dur_min
        # Readonly combobox updates display when var is set (no <<ComboboxSelected>> event).
        self._map_dt_var.set(self._fmt_map_dt(dur_min))
        self._map_recompute_windows()
        if self._map_window_bounds and self._map_t_extent is not None:
            gmin_num = self._map_t_extent[0]
            step_days = (dur_min / 4.0) / 1440.0
            idx = int(round((start - gmin_num) / step_days)) if step_days else 0
            self._map_window_idx = max(0, min(idx, len(self._map_window_bounds) - 1))
        self._sync_map_nav()
        self._update_map_window_label()
        self._map_windowed_recompute()

    def _map_scrub_fire(self):
        """Fire delayed map refresh after navigator scrub (debounced callback)."""
        self._map_scrub_after_id = None
        self._refresh_map()

    def _update_map_window_label(self):
        """Update window date-range display label.

        Shows current window bounds (start -> end) or "—" if no windows.
        Called after window index changes or bounds are recomputed.
        """
        if not self._map_window_bounds:
            self.lbl_map_window.config(text="—")
            return
        idx = min(self._map_window_idx, len(self._map_window_bounds) - 1)
        t0, t1 = self._map_window_bounds[idx]
        fmt = lambda t: str(np.datetime_as_string(t, unit="m")).replace("T", " ")
        self.lbl_map_window.config(text=f"{fmt(t0)}  ->  {fmt(t1)}")

    def _map_recompute_windows(self):
        """Recompute time window grid from aggregation parameters.

        Slices global time span into dt-width windows at dt/4 snap steps
        (yielding 4x overlapping coverage for smooth navigation).
        'full' mode yields single whole-record window.
        Sets _map_window_bounds (list of (t0, t1) tuples) and _map_t_extent
        (global min/max as matplotlib date-nums for navigator domain).
        """
        # Global time span sliced into dt-width windows at dt/4 snap steps
        # (4x the non-overlapping count). 'full' becomes single whole-record window.
        dt_min = self._map_active_dt_min()
        times_list = [
            st["times"]
            for st in self.stations.values()
            if isinstance(st["times"], np.ndarray)
            and np.issubdtype(st["times"].dtype, np.datetime64)
            and len(st["times"])
        ]
        if not times_list:
            self._map_window_bounds = []
            self._map_t_extent = None
            return
        gmin = min(t[0] for t in times_list)
        gmax = max(t[-1] for t in times_list)
        # Global extent (date-nums) the navigator spans — stored for
        # _sync_map_nav / the nav drag callback.
        self._map_t_extent = (mdates.date2num(gmin), mdates.date2num(gmax))
        if dt_min is None:
            self._map_window_bounds = [(gmin, gmax)]
            return
        # timedelta64 rejects floats (custom nav-resize may be fractional minutes).
        # Build in whole seconds to preserve sub-minute precision without crashes.
        dt_span = np.timedelta64(int(round(dt_min * 60)), "s")
        step_span = dt_span / 4
        bounds = []
        t0 = gmin
        while t0 < gmax:
            bounds.append((t0, t0 + dt_span))
            t0 = t0 + step_span
        self._map_window_bounds = bounds or [(gmin, gmax)]

    @staticmethod
    def _map_agg_reduce(vals, agg):
        """Reduce array to single aggregated value.

        Args:
            vals (np.ndarray, dtype=float64): values to aggregate (NaN = missing).
            agg (str): aggregation function ('mean', 'median', 'max', 'min', 'last').

        Returns:
            float: aggregated value, or np.nan if all values are NaN.
        """
        valid = vals[~np.isnan(vals)]
        if valid.size == 0:
            return np.nan
        if agg == "mean":
            return float(valid.mean())
        if agg == "median":
            return float(np.median(valid))
        if agg == "max":
            return float(valid.max())
        if agg == "min":
            return float(valid.min())
        if agg == "last":
            return float(valid[-1])
        return float(valid.mean())

    @staticmethod
    def _map_circular_mean_calm(ws_vals, wd_vals, calm_on, thresh):
        """Compute circular mean of wind directions with optional calm filter.

        Circular (vector) mean accounts for wind direction wraparound at 0/360 degrees.
        If calm_on, excludes samples with speed < thresh or NaN speed (direction unreliable).
        Returns NaN if all samples filtered or result magnitude is zero (true calm).

        Args:
            ws_vals (np.ndarray, dtype=float64): wind speeds (m/s), NaN = missing.
            wd_vals (np.ndarray, dtype=float64): wind directions (degrees, 0-360).
            calm_on (bool): if True, filter by wind speed threshold.
            thresh (float): wind speed threshold (m/s) for calm filtering.

        Returns:
            float: circular mean direction (degrees, 0-360), or np.nan if insufficient data.
        """
        # Circular (vector) mean for wind direction (arithmetic mean wrong across 0/360).
        # With calm filter: excludes below-threshold/NaN speeds (direction untrusted).
        # All-calm window -> NaN (drawn as calm dot, not arrow).
        mask = ~np.isnan(wd_vals)
        if calm_on:
            mask &= ~np.isnan(ws_vals) & (ws_vals >= thresh)
        valid = wd_vals[mask]
        if valid.size == 0:
            return np.nan
        rad = np.deg2rad(valid)
        s, c = np.sin(rad).mean(), np.cos(rad).mean()
        if s == 0.0 and c == 0.0:
            return np.nan
        return float(np.degrees(np.arctan2(s, c)) % 360)

    def _map_agg_signature(self):
        """Return aggregation signature (cache key) for current windowed-mode settings.

        Signature combines mode, variable, agg function, dt, and calm params
        (if applicable). Used to detect when aggregation matrix must be recomputed.
        Returns None for non-windowed modes (qc_status, issues, etc.).

        Returns:
            tuple or None: immutable signature, or None if not in windowed mode.
        """
        cb = self.var_map_color.get()
        if cb == "variable_value":
            sig = (cb, self.var_map_value.get(), self._map_agg_var.get(), self._map_dt_var.get())
            # Wind vars use calm filter as pre-aggregation mask; include params in signature.
            if self.var_map_value.get() in ("wind_speed", "wind_direction"):
                sig += (self._map_calm_params(),)
            return sig
        if cb == "wind_combo":
            # Calm params affect per-window circular mean; must be in signature.
            return (cb, self._map_agg_var.get(), self._map_dt_var.get(), self._map_calm_params())
        return None

    def _map_recompute_agg(self):
        """Initiate chunked precomputation of aggregation matrix.

        Creates (n_stations x n_windows) aggregate matrix for efficient
        window scrubbing (index lookup instead of real-time aggregation).
        Uses generation counter + time-budget pattern to enable user interaction
        while computation runs. Snapshots all params at start so mid-run
        changes (e.g., calm toggle) don't affect result.
        """
        # Chunked precompute of (n_stations x n_windows) aggregate matrix so slider
        # scrubbing is just an index lookup. Generation counter + time-budget loop
        # pattern (like loader._load_chunk). Snapshot params here so mid-run changes
        # don't affect the running computation.
        cb = self.var_map_color.get()
        self._map_recompute_windows()
        self._map_agg_gen = getattr(self, "_map_agg_gen", 0) + 1
        gen = self._map_agg_gen
        stids = self._map_stids[:]
        n_st, n_win = len(stids), len(self._map_window_bounds)
        calm_on, calm_thresh = self._map_calm_params()
        state = {
            "cb": cb,
            "sig": self._map_agg_signature(),
            "stids": stids,
            "bounds": list(self._map_window_bounds),
            "agg": self._map_agg_var.get(),
            "vname": self.var_map_value.get(),
            # Calm params snapshotted to prevent mid-run toggle from skewing matrix.
            "calm_on": calm_on,
            "calm_thresh": calm_thresh,
            # variable_value on wind var: pre-aggregation masking of calm samples.
            "calm_var": (
                cb == "variable_value"
                and calm_on
                and self.var_map_value.get() in ("wind_speed", "wind_direction")
            ),
            "idx": 0,
        }
        if cb == "variable_value":
            state["mat"] = np.full((n_st, n_win), np.nan)
        elif cb == "wind_combo":
            state["mat_ws"] = np.full((n_st, n_win), np.nan)
            state["mat_wd"] = np.full((n_st, n_win), np.nan)
        else:
            self._map_cur_agg = None
            return
        self._map_agg_state = state
        self._map_agg_running = True
        self.pb_load["maximum"] = max(n_st, 1)
        self.pb_load["value"] = 0
        self.pb_load.pack(side="right", padx=(0, 4))
        self.after(1, lambda: self._map_agg_chunk(gen))

    def _map_agg_chunk(self, gen, time_budget=0.05):
        """Process one time-budget chunk of aggregation matrix computation.

        Iterates over stations, computing windowed aggregates (variable_value
        or wind_combo). Uses perf_counter deadline to stay responsive.
        Schedules itself recursively until all stations complete or generation
        is superseded (newer recompute triggered). Updates progress bar and
        status label. On completion, caches result and triggers refresh.

        Args:
            gen (int): generation counter (to detect stale computation).
            time_budget (float, optional): seconds per chunk (default 0.05).
        """
        if gen != self._map_agg_gen:
            return  # superseded by a newer recompute (or cancelled)
        state = self._map_agg_state
        stids, bounds, agg = state["stids"], state["bounds"], state["agg"]
        deadline = time.perf_counter() + time_budget
        if state["cb"] == "variable_value":
            mat, vname = state["mat"], state["vname"]
            calm_var, thr = state["calm_var"], state["calm_thresh"]
            while state["idx"] < len(stids) and time.perf_counter() < deadline:
                i = state["idx"]
                state["idx"] += 1
                st = self.stations.get(stids[i])
                if st is None:
                    continue
                data, times = st["variables"].get(vname), st["times"]
                if (
                    data is None
                    or not isinstance(times, np.ndarray)
                    or not np.issubdtype(times.dtype, np.datetime64)
                ):
                    continue
                # Calm masking requires station's wind_speed; omitted if missing.
                ws = st["variables"].get("wind_speed") if calm_var else None
                for w, (t0, t1) in enumerate(bounds):
                    lo = np.searchsorted(times, t0, side="left")
                    hi = np.searchsorted(times, t1, side="right")
                    if hi > lo:
                        seg = data[lo:hi]
                        if ws is not None:
                            wseg = ws[lo:hi]
                            seg = seg[~np.isnan(wseg) & (wseg >= thr)]
                        mat[i, w] = self._map_agg_reduce(seg, agg)
        else:  # wind_combo
            mat_ws, mat_wd = state["mat_ws"], state["mat_wd"]
            calm_on, calm_thresh = state["calm_on"], state["calm_thresh"]
            while state["idx"] < len(stids) and time.perf_counter() < deadline:
                i = state["idx"]
                state["idx"] += 1
                st = self.stations.get(stids[i])
                if st is None:
                    continue
                ws, wd = st["variables"].get("wind_speed"), st["variables"].get("wind_direction")
                times = st["times"]
                if (
                    ws is None
                    or wd is None
                    or not isinstance(times, np.ndarray)
                    or not np.issubdtype(times.dtype, np.datetime64)
                ):
                    continue
                for w, (t0, t1) in enumerate(bounds):
                    lo = np.searchsorted(times, t0, side="left")
                    hi = np.searchsorted(times, t1, side="right")
                    if hi > lo:
                        mat_ws[i, w] = self._map_agg_reduce(ws[lo:hi], agg)
                        mat_wd[i, w] = self._map_circular_mean_calm(
                            ws[lo:hi], wd[lo:hi], calm_on, calm_thresh
                        )
        self.pb_load["value"] = state["idx"]
        if state["idx"] < len(stids):
            self.lbl_status.config(text=f"Aggregating {state['idx']}/{len(stids)} stations...")
            self.after(1, lambda: self._map_agg_chunk(gen))
            return
        self._map_cur_agg = (
            state["mat"] if state["cb"] == "variable_value" else (state["mat_ws"], state["mat_wd"])
        )
        self._map_agg_sig = state["sig"]
        self._map_agg_stids = stids
        self._map_agg_running = False
        self.pb_load.pack_forget()
        self.lbl_status.config(text=f"Aggregated {len(stids)} stations")
        self._update_map_nav_series(state)
        self._refresh_map()

    def _update_map_nav_series(self, state):
        """Create and push sparkline to navigator from completed aggregation matrix.

        Computes per-window means across all stations (nanmean ignores NaN cells).
        Caches result keyed by aggregation signature for reuse after mode round-trip.
        Returns (x, y) as matplotlib date-nums and across-station means.

        Args:
            state (dict): aggregation state dict with bounds and matrix.
        """
        # Sparkline from aggregate matrix: per-window centers vs across-station nanmean.
        # Suppress RuntimeWarning for all-NaN windows (simply plot as gaps).
        bounds = state["bounds"]
        mat = state["mat"] if state["cb"] == "variable_value" else state.get("mat_ws")
        if not bounds or mat is None or not mat.size:
            self._map_nav_series, self._map_nav_series_sig = None, state["sig"]
            self.nav_map_window.set_series(None, None)
            return
        centers = np.array([t0 + (t1 - t0) / 2 for t0, t1 in bounds])
        x = mdates.date2num(centers)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            y = np.nanmean(mat, axis=0)
        # Cache series keyed by agg signature; mode round-trip clears nav, cache hit
        # skips recompute and restores from here via _refresh_map.
        self._map_nav_series, self._map_nav_series_sig = (x, y), state["sig"]
        self.nav_map_window.set_series(x, y)

    def _map_make_missing_marker(self, ax, lons, lats):
        """Create or reinitialize missing-data markers (circle + cross overlay).

        Markers show stations with no data in current mode. Created even when
        empty arrays passed (for later reuse in fast refresh via set_offsets).

        Args:
            ax (matplotlib.axes.Axes): axes to draw on.
            lons (np.ndarray): longitudes of missing stations.
            lats (np.ndarray): latitudes of missing stations.
        """
        # Open circle + cross for stations with no data (not colored by value).
        # Created even when empty for reuse in fast refresh path (set_offsets only).
        self._map_missing_circ = ax.scatter(
            lons, lats, s=70, facecolors="none", edgecolors=MISSING_MARKER, linewidths=1.1, zorder=3
        )
        self._map_missing_x = ax.scatter(
            lons, lats, s=40, marker="x", color=MISSING_MARKER, linewidths=1.1, zorder=3
        )

    def _map_set_missing_marker(self, lons, lats):
        """Update missing-data marker positions (fast in-place artist update).

        Args:
            lons (np.ndarray): longitudes of missing stations.
            lats (np.ndarray): latitudes of missing stations.
        """
        off = np.column_stack([lons, lats]) if len(lons) else np.empty((0, 2))
        self._map_missing_circ.set_offsets(off)
        self._map_missing_x.set_offsets(off)

    def _map_wind_masks(self, ws, wd):
        """Partition stations into arrow/calm/missing categories for wind display.

        Splits wind direction array into three groups:
        - arrow: both speed and direction valid (speed >= threshold if calm filter on)
        - calm: speed valid but below threshold (or no filter), or direction missing
        - missing: speed missing entirely

        Args:
            ws (np.ndarray, dtype=float64): wind speeds (m/s), NaN = missing.
            wd (np.ndarray, dtype=float64): wind directions (degrees).

        Returns:
            tuple: (arrow, calm, missing) boolean masks.
        """
        # Split into arrow / calm-dot / missing. With calm filter: excludes below-threshold
        # directions (drawn muted); filter off -> arrow / missing only.
        calm_on, thr = self._map_calm_params()
        has_ws = ~np.isnan(ws)
        valid = has_ws & ~np.isnan(wd)
        if calm_on:
            arrow = valid & (ws >= thr)
            calm = has_ws & ~arrow
            missing = ~has_ws
        else:
            arrow = valid
            calm = np.zeros(ws.shape, dtype=bool)
            missing = ~valid
        return arrow, calm, missing

    def _map_draw_wind_layers(self, ax, lons_a, lats_a, ws, wd):
        """Draw wind field as quiver plot + calm-dot scatter + missing markers.

        Removes old quiver and calm-dot artists before creating new ones.
        Synoptic wind direction is FROM-bearing (negates sin/cos to draw
        downwind arrows). Missing-marker positions updated via set_offsets.
        Expensive parts (axes, colorbar, perimeters) are reused across refreshes.

        Args:
            ax (matplotlib.axes.Axes): axes to draw on.
            lons_a (np.ndarray): station longitudes (n_stations,).
            lats_a (np.ndarray): station latitudes (n_stations,).
            ws (np.ndarray, dtype=float64): wind speeds (m/s), NaN = missing.
            wd (np.ndarray, dtype=float64): wind directions (degrees, 0-360).

        Returns:
            matplotlib.colors.Normalize or None: color normalization for quiver speed,
                or None if no arrows (all calm/missing).
        """
        # Recreate quiver + calm dots (cheap artists removed each refresh).
        # Quiver can't change arrow count in place; expensive parts (axes, scatter,
        # colorbar, perimeters) reused. Synoptic WD is FROM-bearing: negate sin/cos
        # for downwind arrows. Returns color norm or None if no arrows.
        for attr in ("_map_quiver", "_map_calm_dots"):
            art = getattr(self, attr, None)
            if art is not None:
                try:
                    art.remove()
                except (ValueError, AttributeError):
                    pass
                setattr(self, attr, None)
        arrow, calm, missing = self._map_wind_masks(ws, wd)
        norm = None
        if arrow.any():
            wsv = ws[arrow]
            vmin, vmax = float(wsv.min()), float(wsv.max())
            if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
                vmax = vmin + 1.0
            norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
            rad = np.deg2rad(wd[arrow])
            self._map_quiver = ax.quiver(
                lons_a[arrow],
                lats_a[arrow],
                -np.sin(rad),
                -np.cos(rad),
                wsv,
                cmap="viridis",
                norm=norm,
                angles="uv",
                scale_units="inches",
                scale=8.0,
                pivot="mid",
                width=0.005,
                headwidth=4.0,
                headlength=5.0,
                headaxislength=4.5,
                zorder=3,
            )
        # Calm dots created even when empty for unconditional filter-on check.
        self._map_calm_dots = ax.scatter(lons_a[calm], lats_a[calm], s=12, color=MUTED, zorder=3)
        self._map_set_missing_marker(lons_a[missing], lats_a[missing])
        return norm

    def _load_perim_h5(self, path):
        """Load fire perimeters from firebench HDF5 file.

        Parses /polygons group where each subgroup is '<FireName>_<ISO_datetime>'.
        Each group's attributes include 'rel_path' (relative path to KML file,
        resolved relative to H5 directory) and optional burnt_area metadata.
        Updates _perim_data, _perim_loaded_path, and session config.

        Args:
            path (Path): file path to HDF5 perimeter file.
        """
        # Parse firebench fire-perimeter H5: polygons/<name> groups hold attrs only;
        # actual geometry in external KML at rel_path (resolved relative to H5 dir).
        # Group name format: '<FireName>_<ISO time>' — split on first '_' only.
        try:
            perims = []
            with h5py.File(path, "r") as f:
                grp = f.get("polygons")
                if grp is None:
                    messagebox.showwarning("No polygons", f"{path.name} has no /polygons group")
                    return
                for gname in grp:
                    if "_" not in gname:
                        continue
                    firename, iso_str = gname.split("_", 1)
                    try:
                        dt = datetime.fromisoformat(iso_str)
                    except ValueError:
                        continue
                    attrs = dict(grp[gname].attrs)
                    rel_path = attrs.get("rel_path")
                    if not rel_path:
                        continue
                    perims.append(
                        {
                            "name": firename,
                            "time": dt,
                            "kml_path": path.parent / rel_path,
                            "burnt_area": attrs.get("burnt_area"),
                            "burnt_area_units": attrs.get("burnt_area_units", ""),
                        }
                    )
            perims.sort(key=lambda p: p["time"])
            self._perim_data = perims
            self._perim_loaded_path = path
            self.cfg["perim_h5_path"] = str(path)
            self.lbl_status.config(text=f"Loaded {len(perims)} perimeter(s) from {path.name}")
        except (OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Perimeter load failed", f"Could not read {path}:\n\n{exc}")

    def _map_draw_perimeters(self, ax):
        """Draw fire perimeter polygons as colored underlays (zorder=1).

        If show_all=False, draws most recent perimeter in black.
        If show_all=True, draws all perimeters with time-based color gradient
        and adds a colorbar. Gracefully skips perimeters with missing/unreadable KML.

        Args:
            ax (matplotlib.axes.Axes): axes to draw on.
        """
        # Drawn as underlay (zorder=1) beneath station scatter.
        show_all = self.cfg.get("perim_show_all", False)
        perims = self._perim_data if show_all else self._perim_data[-1:]
        if not perims:
            return
        if not show_all:
            try:
                gdf = gpd.read_file(str(perims[0]["kml_path"]), engine="pyogrio")
                gdf.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=0.8, zorder=1)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.lbl_status.config(text=f"Perimeter load failed: {exc}")
            return
        date_nums = mdates.date2num([p["time"] for p in perims])
        norm = mcolors.Normalize(vmin=date_nums.min(), vmax=date_nums.max())
        cmap_obj = matplotlib.colormaps["turbo"]
        any_ok = False
        for p, dn in zip(perims, date_nums):
            try:
                gdf = gpd.read_file(str(p["kml_path"]), engine="pyogrio")
                gdf.plot(ax=ax, facecolor="none", edgecolor=cmap_obj(norm(dn)), linewidth=0.8, zorder=1)
                any_ok = True
            except (OSError, RuntimeError, TypeError, ValueError):
                continue
        if not any_ok:
            return
        sm = mcm.ScalarMappable(norm=norm, cmap=cmap_obj)
        sm.set_array([])
        self._map_perim_cbar = ax.figure.colorbar(
            sm, ax=ax, label="Perimeter time", fraction=0.03, pad=0.02
        )
        self._map_perim_cbar.ax.yaxis.set_major_locator(mdates.AutoDateLocator())
        self._map_perim_cbar.ax.yaxis.set_major_formatter(mdates.DateFormatter("%b-%d %Hh"))

    def _refresh_map(self):
        """Refresh map display, handling aggregation cache and fast-path updates.

        Main entry point for map redraws. For windowed modes (variable_value, wind_combo),
        checks if aggregation matrix is stale; if so, kicks off chunked recompute and
        returns early (completion re-calls this method). Otherwise fast-paths artist
        data updates when structural signature is unchanged (e.g., window scrub).
        Rebuilds entire map (ax.cla() + new artists) only when mode/variable/stations change.
        Restores navigator sparkline from cache on mode round-trip.
        """
        if not self.stations:
            return
        self._map_stids = self.stids[:]
        cb = self.var_map_color.get()
        if cb in ("variable_value", "wind_combo"):
            sig = self._map_agg_signature()
            if (
                sig != self._map_agg_sig
                or self._map_cur_agg is None
                or getattr(self, "_map_agg_stids", None) != self._map_stids
            ):
                if (
                    getattr(self, "_map_agg_running", False)
                    and self._map_agg_state.get("sig") == sig
                    and self._map_agg_state.get("stids") == self._map_stids
                ):
                    # Identical recompute in flight; let it finish (its completion
                    # refreshes) instead of gen-bumping and restarting.
                    return
                # Stale aggregate matrix: kick off chunked recompute.
                # Completion calls _refresh_map() again for the actual draw.
                # Old map stays interactive meanwhile.
                self._map_recompute_agg()
                return
            # Cache hit after mode round-trip: restore cached sparkline (guarded
            # so scrub-path refreshes don't unnecessarily repaint).
            stored = getattr(self, "_map_nav_series", None)
            if (
                stored is not None
                and not self.nav_map_window.has_series()
                and getattr(self, "_map_nav_series_sig", None) == sig
            ):
                self.nav_map_window.set_series(*stored)
        elif getattr(self, "_map_agg_running", False):
            # Switched away from windowed mode with precompute in flight; cancel it.
            self._map_agg_gen = getattr(self, "_map_agg_gen", 0) + 1
            self._map_agg_running = False
            self.pb_load.pack_forget()
        ax = self.ax_map
        # Cached lon/lat arrays: rebuilt only when station list changes (perf).
        lonlat = getattr(self, "_map_lonlat", None)
        if lonlat is None or lonlat[0] != self._map_stids:
            lons_a = np.array([self.stations[s]["lon"] for s in self._map_stids], dtype=float)
            lats_a = np.array([self.stations[s]["lat"] for s in self._map_stids], dtype=float)
            self._map_lonlat = (self._map_stids[:], lons_a, lats_a)
        else:
            _, lons_a, lats_a = lonlat
        # Structural signature: when unchanged, reuse existing artists (scatter, colorbar,
        # missing markers, perimeter, axes decor) and update in place. No ax.cla(),
        # no colorbar destroy/recreate (full relayout). Fast path: window scrub or calm
        # toggle is just data swap. Mode/variable/station-set/perimeter change rebuilds.
        perim_key = (
            self._perim_loaded_path,
            len(self._perim_data),
            bool(self.cfg.get("perim_show_all", False)),
        )
        struct_sig = (
            cb,
            self.var_map_value.get() if cb == "variable_value" else None,
            tuple(self._map_stids),
            perim_key,
        )
        agg_lbl = f"{self._map_agg_var.get()}, {self._map_dt_var.get()} window"
        if (
            struct_sig == getattr(self, "_map_draw_sig", None)
            and self._map_sc is not None
            and self._map_fast_update(cb, lons_a, lats_a, agg_lbl)
        ):
            self._map_offsets = np.column_stack([lons_a, lats_a]) if len(lons_a) else None
            self._map_plotted = set(self._map_stids)
            self._map_refresh_overlays()
            self.canvas_map.draw_idle()
            return
        if self._map_cbar is not None:
            self._map_cbar.remove()
            self._map_cbar = None
        if self._map_perim_cbar is not None:
            self._map_perim_cbar.remove()
            self._map_perim_cbar = None

        ax.cla()
        # ax.cla() silently drops hover/selection/popup artists; null out handles
        # to prevent double-remove. Also clear cached mode artists (quiver, calm dots).
        self._map_hover_artist = None
        self._map_sel_artist = None
        self._map_popup_artist = None
        self._map_quiver = None
        self._map_calm_dots = None
        self._map_missing_circ = None
        self._map_missing_x = None
        self._map_cbar_sm = None
        if self._perim_data:
            self._map_draw_perimeters(ax)
        if cb == "qc_status":
            colors = [self._QC_STATUS_COLORS[self._map_qc_status(s)][0] for s in self._map_stids]
            self._map_sc = ax.scatter(lons_a, lats_a, c=colors, s=45, alpha=0.85)
            handles = [
                Line2D([0], [0], marker="o", linestyle="", color=color, label=label)
                for color, label in self._QC_STATUS_COLORS.values()
            ]
            ax.legend(handles=handles, loc="best", fontsize=8, title="QC Status")
            self._map_cvals_arr = None
        elif cb == "variable_value":
            vname = self.var_map_value.get()
            vals, valid_mask = self._map_value_column()
            units = next(
                (
                    self.stations[s]["var_units"].get(vname, "")
                    for s in self._map_stids
                    if vname in self.stations[s]["var_units"]
                ),
                "",
            )
            cmap_obj = matplotlib.colormaps[self._VAR_CMAP.get(vname, "viridis")]
            norm, rgba = self._map_value_colors(vals, valid_mask, cmap_obj)
            # Full station-indexed scatter (incl. NaN points) keeps indices aligned
            # with _map_stids for click-to-navigate; missing marker overlay shows no-data cue.
            self._map_sc = ax.scatter(lons_a, lats_a, c=rgba, s=45)
            if valid_mask.any():
                sm = mcm.ScalarMappable(norm=norm, cmap=cmap_obj)
                sm.set_array([])
                self._map_cbar_sm = sm
                self._map_cbar = ax.figure.colorbar(
                    sm, ax=ax, label=f"{vname} [{units}]  ({agg_lbl})", fraction=0.03, pad=0.02
                )
            self._map_value_units = units
            self._map_make_missing_marker(ax, lons_a[~valid_mask], lats_a[~valid_mask])
            self._map_cvals_arr = None
        elif cb == "wind_combo":
            ws, wd = self._map_wind_columns()
            # Invisible scatter (arrows are visible content); keeps index alignment with
            # _map_stids for consistency; click hit-testing uses _map_offsets directly.
            self._map_sc = ax.scatter(lons_a, lats_a, s=45, alpha=0.0)
            self._map_make_missing_marker(ax, np.array([]), np.array([]))
            norm = self._map_draw_wind_layers(ax, lons_a, lats_a, ws, wd)
            units = next(
                (
                    self.stations[s]["var_units"].get("wind_speed", "")
                    for s in self._map_stids
                    if "wind_speed" in self.stations[s]["var_units"]
                ),
                "m/s",
            )
            self._map_value_units = units
            if norm is not None:
                sm = mcm.ScalarMappable(norm=norm, cmap="viridis")
                sm.set_array([])
                self._map_cbar_sm = sm
                self._map_cbar = ax.figure.colorbar(
                    sm, ax=ax, label=f"wind_speed [{units}]  ({agg_lbl})", fraction=0.03, pad=0.02
                )
            ax.set_title(f"Wind (arrows)  —  {agg_lbl}  (click a point to open detail)")
            self._map_cvals_arr = None
        else:
            clabel = self._MAP_CLABELS.get(cb, "N points")
            cvals = [self._map_cval(s, cb) for s in self._map_stids]
            self._map_sc = ax.scatter(lons_a, lats_a, c=cvals, cmap="RdYlGn_r", s=45, alpha=0.85)
            self._map_cbar = ax.figure.colorbar(self._map_sc, ax=ax, label=clabel, fraction=0.03, pad=0.02)
            self._map_cvals_arr = np.array(cvals, dtype=float) if cvals else None
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        if cb != "wind_combo":
            ax.set_title("Station Map  (click a point to open detail)")
        ax.grid(True, alpha=0.3)
        self._map_color_mode = cb
        self._map_draw_sig = struct_sig
        self._map_offsets = np.column_stack([lons_a, lats_a]) if len(lons_a) else None
        self._map_plotted = set(self._map_stids)
        self._map_refresh_overlays()
        self.canvas_map.draw_idle()

    def _map_refresh_overlays(self):
        """Reapply hover and selection overlays after full map redraw.

        Called at end of _refresh_map after axes or artists recreated.
        Clears hover/selection if station is no longer in current stid list.
        Rebuilds popup content if a station is selected (reflects new window/mode).
        """
        # Re-apply hover/selection/popup after redraw so a mode change or scrub
        # doesn't silently drop open popup. Content also refreshes (new window, new mode).
        if self._map_hover_stid is not None and self._map_hover_stid not in self._map_stids:
            self._map_hover_stid = None
        if self._map_hover_stid is not None:
            self._map_update_hover_overlay()
        if self._map_selected_stid is not None and self._map_selected_stid not in self._map_stids:
            self._map_selected_stid = None
        if self._map_selected_stid is not None:
            self._map_open_popup(self._map_selected_stid)

    def _map_value_column(self):
        """Extract per-station values from current window of aggregation matrix.

        Returns:
            tuple: (vals, valid_mask) — vals (ndarray) per station, valid_mask (bool).
        """
        mat = self._map_cur_agg
        n_win = mat.shape[1] if mat is not None else 0
        idx_w = min(self._map_window_idx, n_win - 1) if n_win else 0
        vals = mat[:, idx_w] if n_win else np.full(len(self._map_stids), np.nan)
        return vals, ~np.isnan(vals)

    def _map_wind_columns(self):
        """Extract wind speed and direction from current window of aggregation matrix.

        Returns:
            tuple: (ws, wd) — per-station wind speed and direction arrays.
        """
        mat_ws, mat_wd = self._map_cur_agg if self._map_cur_agg is not None else (None, None)
        n_win = mat_ws.shape[1] if mat_ws is not None else 0
        idx_w = min(self._map_window_idx, n_win - 1) if n_win else 0
        if n_win:
            return mat_ws[:, idx_w], mat_wd[:, idx_w]
        n = len(self._map_stids)
        return np.full(n, np.nan), np.full(n, np.nan)

    @staticmethod
    def _map_value_colors(vals, valid_mask, cmap_obj):
        """Compute per-station RGBA colors from values and colormap.

        NaN/invalid stations get transparent gray (0.6, 0.6, 0.6, 0.0) for visibility.

        Args:
            vals (np.ndarray, dtype=float64): per-station values, NaN = missing.
            valid_mask (np.ndarray, dtype=bool): True where vals is real.
            cmap_obj (matplotlib.colors.Colormap): colormap to apply.

        Returns:
            tuple: (norm, rgba) — Normalize instance and (n_stations, 4) RGBA array.
        """
        # Vectorized per-station RGBA; NaN stations transparent (visible cue is overlay).
        if valid_mask.any():
            norm = mcolors.Normalize(vmin=float(np.nanmin(vals)), vmax=float(np.nanmax(vals)))
        else:
            norm = mcolors.Normalize(vmin=0, vmax=1)
        rgba = cmap_obj(norm(np.where(valid_mask, vals, 0.0)))
        rgba[~valid_mask] = (0.6, 0.6, 0.6, 0.0)
        return norm, rgba

    def _map_fast_update(self, cb, lons_a, lats_a, agg_lbl):
        """Update scatter/quiver data in-place without rebuilding artists.

        Fast path for window scrub or calm toggle: updates colors/positions
        on existing scatter, quiver, and colorbar without ax.cla() or recreation.
        Returns False if structure requires full rebuild (e.g., colorbar
        must appear or disappear for variable_value mode).

        Args:
            cb (str): current color mode.
            lons_a (np.ndarray): station longitudes.
            lats_a (np.ndarray): station latitudes.
            agg_lbl (str): aggregation description for colorbar label.

        Returns:
            bool: True if fast update succeeded, False if full rebuild required.
        """
        # In-place data swap; reused artists remain unchanged. Returns False if
        # structure requires rebuild (e.g., colorbar must appear/disappear).
        try:
            if cb == "qc_status":
                colors = [self._QC_STATUS_COLORS[self._map_qc_status(s)][0] for s in self._map_stids]
                self._map_sc.set_facecolor(colors)
                return True
            if cb == "variable_value":
                vals, valid_mask = self._map_value_column()
                if bool(valid_mask.any()) != (self._map_cbar is not None):
                    return False
                vname = self.var_map_value.get()
                cmap_obj = matplotlib.colormaps[self._VAR_CMAP.get(vname, "viridis")]
                norm, rgba = self._map_value_colors(vals, valid_mask, cmap_obj)
                self._map_sc.set_facecolor(rgba)
                if self._map_cbar is not None:
                    # set_norm fires mappable's 'changed' callback (colorbar tracks);
                    # no destroy/recreate needed.
                    self._map_cbar_sm.set_norm(norm)
                    self._map_cbar.set_label(f"{vname} [{self._map_value_units}]  ({agg_lbl})")
                self._map_set_missing_marker(lons_a[~valid_mask], lats_a[~valid_mask])
                return True
            if cb == "wind_combo":
                ws, wd = self._map_wind_columns()
                norm = self._map_draw_wind_layers(self.ax_map, lons_a, lats_a, ws, wd)
                if (norm is not None) != (self._map_cbar is not None):
                    return False
                if self._map_cbar is not None:
                    self._map_cbar_sm.set_norm(norm)
                    self._map_cbar.set_label(f"wind_speed [{self._map_value_units}]  ({agg_lbl})")
                self.ax_map.set_title(f"Wind (arrows)  —  {agg_lbl}  (click a point to open detail)")
                return True
            # Numeric colorbar modes (issues / wd_nan_pct / n_variables / n_pts).
            cvals = np.array([self._map_cval(s, cb) for s in self._map_stids], dtype=float)
            self._map_sc.set_array(cvals)
            if cvals.size:
                self._map_sc.set_clim(float(cvals.min()), float(cvals.max()))
            self._map_cvals_arr = cvals if cvals.size else None
            return True
        except (ValueError, AttributeError, KeyError):
            # Unexpected error: fall back to full rebuild.
            return False

    def _refresh_map_append(self, new_stids):
        """Progressively update map with newly-loaded stations (cheap append).

        For non-windowed modes, updates existing scatter artist offsets and
        color values without full rebuild. Falls back to _refresh_map for
        windowed modes or if structure incompatible (scatter missing, mode changed).

        Args:
            new_stids (list): newly-loaded station IDs.
        """
        # Cheap in-place scatter update for newly-loaded stations (progressive load).
        # Updates offsets/colors on existing artist (avoids ax.cla() + full rebuild).
        # Falls back for modes with aggregate matrices (QC Status, variable_value, wind_combo).
        cb = self.var_map_color.get()
        if (
            self._map_sc is None
            or cb != self._map_color_mode
            or cb in ("qc_status", "variable_value", "wind_combo")
        ):
            self._refresh_map()
            return
        fresh = [s for s in new_stids if s not in self._map_plotted]
        if not fresh:
            return
        self._map_plotted.update(fresh)
        self._map_stids.extend(fresh)
        new_off = np.array([[self.stations[s]["lon"], self.stations[s]["lat"]] for s in fresh])
        new_cv = np.array([self._map_cval(s, cb) for s in fresh], dtype=float)
        self._map_offsets = (
            new_off if self._map_offsets is None else np.vstack([self._map_offsets, new_off])
        )
        self._map_cvals_arr = (
            new_cv if self._map_cvals_arr is None else np.concatenate([self._map_cvals_arr, new_cv])
        )
        self._map_sc.set_offsets(self._map_offsets)
        self._map_sc.set_array(self._map_cvals_arr)
        self._map_sc.set_clim(self._map_cvals_arr.min(), self._map_cvals_arr.max())
        self.ax_map.update_datalim(self._map_offsets)
        self.ax_map.autoscale_view()
        self.canvas_map.draw_idle()

    def _map_nearest_station(self, event, threshold_px=15):
        """Find nearest station to mouse event using on-screen pixel distance.

        Uses display coordinates (not lon-lat) to avoid distortion from axes aspect.
        Returns None if event outside axes, no stations, or nearest is beyond threshold.

        Args:
            event (matplotlib.backend_bases.MouseEvent): mouse event.
            threshold_px (float, optional): maximum distance in pixels (default 15).

        Returns:
            str or None: station ID of nearest station within threshold, or None.
        """
        # Nearest station in on-screen pixel distance (not lon-lat, which would be
        # distorted by axes aspect ratio). Used for hover and click hit-testing.
        if event.inaxes != self.ax_map or self._map_offsets is None or not len(self._map_stids):
            return None
        disp = self.ax_map.transData.transform(self._map_offsets)
        d = np.hypot(disp[:, 0] - event.x, disp[:, 1] - event.y)
        idx = int(np.argmin(d))
        return self._map_stids[idx] if d[idx] <= threshold_px else None

    def _map_clear_hover(self):
        """Remove hover halo artist and clear hover state."""
        if self._map_hover_artist is not None:
            self._map_hover_artist.remove()
            self._map_hover_artist = None
        self._map_hover_stid = None

    def _map_update_hover_overlay(self):
        """Create or remove hover halo around currently hovered station.

        Hover is a soft transparent halo (looks like bigger point).
        Distinct from selection ring; both visible simultaneously.
        """
        # Hover = soft halo behind point (reads as 'bigger' regardless of mode's artist type).
        if self._map_hover_artist is not None:
            self._map_hover_artist.remove()
            self._map_hover_artist = None
        if self._map_hover_stid is not None:
            lon = self.stations[self._map_hover_stid]["lon"]
            lat = self.stations[self._map_hover_stid]["lat"]
            self._map_hover_artist = self.ax_map.scatter(
                [lon], [lat], s=170, facecolors=ACCENT, edgecolors="none", alpha=0.35, zorder=2.5
            )
        self.canvas_map.draw_idle()

    def _on_map_motion(self, event):
        """Handle mouse motion over map; update hover halo.

        Called by matplotlib motion_notify_event. Updates hover state if
        nearest station changes.

        Args:
            event (matplotlib.backend_bases.MouseEvent): motion event.
        """
        stid = self._map_nearest_station(event)
        if stid != self._map_hover_stid:
            self._map_hover_stid = stid
            self._map_update_hover_overlay()

    def _map_update_selection_overlay(self):
        """Create or remove selection ring around currently selected station.

        Selection is a thick black ring around a point. Distinct from hover halo;
        both visible simultaneously.
        """
        # Selected = thick black ring (distinct from hover halo; both visible simultaneously).
        if self._map_sel_artist is not None:
            self._map_sel_artist.remove()
            self._map_sel_artist = None
        if self._map_selected_stid is not None:
            lon = self.stations[self._map_selected_stid]["lon"]
            lat = self.stations[self._map_selected_stid]["lat"]
            self._map_sel_artist = self.ax_map.scatter(
                [lon], [lat], s=220, facecolors="none", edgecolors="black", linewidths=2.2, zorder=5
            )

    def _map_popup_lines(self, stid):
        """Generate popup text lines for a station.

        Format is mode-specific: variable_value and wind_combo show aggregated
        values; qc_status shows status label; others show generic label: value.

        Args:
            stid (str): station identifier.

        Returns:
            list[str]: text lines for popup annotation.
        """
        # Mode-specific popup content: variable_value, wind_combo, qc_status show
        # custom formatting; others use generic label: value format.
        lines = [stid]
        cb = self.var_map_color.get()
        i = self._map_stids.index(stid) if stid in self._map_stids else None
        if cb == "variable_value":
            vname = self.var_map_value.get()
            short = self._VAR_SHORT.get(vname, vname)
            mat = self._map_cur_agg
            val = np.nan
            if mat is not None and mat.size and i is not None:
                idx_w = min(self._map_window_idx, mat.shape[1] - 1)
                val = mat[i, idx_w]
            if np.isnan(val):
                lines.append(f"{short}: no data")
            else:
                units = self.stations[stid]["var_units"].get(vname, "")
                lines.append(f"{short}: {val:.1f} {units}")
        elif cb == "wind_combo":
            mat_ws, mat_wd = self._map_cur_agg if self._map_cur_agg is not None else (None, None)
            ws_v = wd_v = np.nan
            if mat_ws is not None and mat_ws.size and i is not None:
                idx_w = min(self._map_window_idx, mat_ws.shape[1] - 1)
                ws_v, wd_v = mat_ws[i, idx_w], mat_wd[i, idx_w]
            if np.isnan(ws_v) or np.isnan(wd_v):
                lines.append("WS/WD: no data")
            else:
                lines.append(f"WS: {ws_v:.1f} m/s   WD: {wd_v:.0f}°")
        elif cb == "qc_status":
            lines.append(self._QC_STATUS_COLORS[self._map_qc_status(stid)][1])
        else:
            lines.append(f"{self._MAP_CLABELS.get(cb, cb)}: {self._map_cval(stid, cb):.3g}")
        return lines

    def _map_open_popup(self, stid):
        """Open an annotation popup with mode-specific station info.

        Sets selected station, updates selection overlay, and creates annotation
        with formatted popup lines (see _map_popup_lines).

        Args:
            stid (str): station identifier.
        """
        self._map_selected_stid = stid
        self._map_update_selection_overlay()
        if self._map_popup_artist is not None:
            self._map_popup_artist.remove()
            self._map_popup_artist = None
        lon, lat = self.stations[stid]["lon"], self.stations[stid]["lat"]
        self._map_popup_artist = self.ax_map.annotate(
            "\n".join(self._map_popup_lines(stid)),
            xy=(lon, lat),
            xytext=(14, 14),
            textcoords="offset points",
            fontsize=8,
            zorder=6,
            bbox=dict(boxstyle="round", fc="white", ec="black", alpha=0.95),
            arrowprops=dict(arrowstyle="->", color="black"),
        )
        self.canvas_map.draw_idle()

    def _map_close_popup(self):
        """Close annotation popup and clear selection state."""
        if self._map_popup_artist is not None:
            self._map_popup_artist.remove()
            self._map_popup_artist = None
        self._map_selected_stid = None
        self._map_update_selection_overlay()
        self.canvas_map.draw_idle()

    def _on_map_click(self, event):
        """Handle mouse click on map.

        Single click opens popup for station at click location (or closes if no station).
        Double click navigates to detail tab for that station.

        Args:
            event (matplotlib.backend_bases.MouseEvent): click event.
        """
        stid = self._map_nearest_station(event)
        if stid is None:
            self._map_close_popup()
            return
        if event.dblclick:
            self._navigate_to_station(stid)
            return
        self._map_open_popup(stid)
