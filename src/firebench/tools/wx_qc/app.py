import time
import tkinter as tk
from tkinter import ttk
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.dates as mdates
import numpy as np
from pathlib import Path

from .constants import default_config
from .data import run_assertions, run_outage_assertions
from .state import mark_stations_skipped
from .theme import setup_style, FONT_MONO
from .widgets import TimeNavigator
from .dialogs import AddSkipDialog, SettingsDialog
from .tabs.overview import OverviewTabMixin
from .tabs.detail import DetailTabMixin
from .tabs.map_tab import MapTabMixin
from .tabs.skiplist import SkiplistTabMixin
from .session import SessionMixin
from .loader import LoaderMixin


class App(
    OverviewTabMixin, DetailTabMixin, MapTabMixin, SkiplistTabMixin, SessionMixin, LoaderMixin, tk.Tk
):
    """Tk root that owns the shared state documented by each GUI mixin."""

    def __init__(self):
        """Initialize the Weather Station QC application.

        Sets up the main window, initializes data storage for stations and QC results,
        configures theme and UI components, and registers event handlers.
        """
        super().__init__()
        self.title("Weather Station QC")
        self.geometry("1440x900")
        self.minsize(1000, 700)

        self.h5_path = None
        self.stations = {}
        self.all_stats = {}
        self.all_issues = {}
        self.skip_list = {}
        self.green_list = set()
        # Record-removal QC: stid -> list of {var, t0, t1, reason}. Non-destructive;
        # original data plotted + visual overlay. t0/t1 inclusive ISO (minute); "*"=all vars.
        self.removal_list = {}
        self.stids = []
        self._map_stids = []
        self._map_cbar = None
        self._map_sc = None
        self._map_color_mode = None
        self._map_offsets = None
        self._map_cvals_arr = None
        self._map_plotted = set()
        # Reusable map artists (quiver, dots, markers, colorbar) + signature.
        # Fast in-place refresh: update artists' data instead of ax.cla() + rebuild.
        self._map_quiver = None
        self._map_calm_dots = None
        self._map_missing_circ = None
        self._map_missing_x = None
        self._map_cbar_sm = None
        self._map_draw_sig = None
        self._map_lonlat = None
        self._map_value_units = ""
        # Online road basemap: tile work happens off the Tk thread and only the
        # newest viewport is applied. The checkbox is persisted in session JSON.
        self.var_map_basemap = tk.BooleanVar(value=True)
        self._map_basemap_artist = None
        self._map_attribution_artist = None
        self._map_tile_executor = None
        self._map_tile_future = None
        self._map_tile_poll_after_id = None
        self._map_tile_debounce_after_id = None
        self._map_tile_pending_extent = None
        self._map_tile_request_extent = None
        self._map_tile_view_extent = None
        self._map_tile_cached_result = None
        self._map_tile_closed = False
        # Time-window aggregation: aggregate matrix precomputed on mode/var/dt change;
        # slider only re-indexes (no recompute-on-drag).
        self._map_dt_var = tk.StringVar(value="6h")
        self._map_agg_var = tk.StringVar(value="mean")
        self.var_map_value = tk.StringVar()
        self._map_window_idx = 0
        self._map_window_bounds = []
        # Global time extent and custom window width (minutes). None = follow preset.
        self._map_t_extent = None
        self._map_dt_custom_min = None
        # Last synced duration; discriminator for pan/resize in _on_map_window_nav.
        self._map_nav_synced_dur = None
        self._map_cur_agg = None
        self._map_agg_sig = None
        # Debounce window-scrub slider: defer heavy _refresh_map, keep label live.
        self._map_scrub_after_id = None
        # Hover/selection state: separate lightweight overlay artists on ax_map,
        # independent of main redraw so hover doesn't trigger full replot.
        self._map_hover_stid = None
        self._map_selected_stid = None
        self._map_hover_artist = None
        self._map_sel_artist = None
        self._map_popup_artist = None
        # Fire perimeter overlay: separate colorbar on same axes;
        # remove-before-redraw pattern to avoid conflicts.
        self._perim_data = []
        self._perim_loaded_path = None
        self._map_perim_cbar = None
        # Time series point selection: snapshot of plotted (times, data) for
        # click/drag snapping without re-deriving from self.stations.
        self._ts_times = None
        self._ts_data = None
        self._ts_xnum = None
        self._ts_vname = None
        self._ts_units = ""
        self._ts_sel_idx = None
        self._ts_sel_artist = None
        self._ts_sel_annot = None
        self._ts_dragging = False
        # Removal QC: Shift+drag range selection (idx0, idx1) on single-station plot.
        # Cleared by plain click or plot refresh (station/var change).
        self._ts_range_sel = None
        self._ts_range_artist = None
        self._ts_range_anchor = None
        self._ts_range_dragging = False
        self._ts_shift_press = None
        # Synthetic "wind" variable: wind_direction snapshot parallel to _ts_data
        # (wind_speed) for annotation. None for non-wind vars (disambiguator).
        # Quiver artist + debounce after-id for re-sampling on zoom/pan.
        self._ts_wd = None
        self._ts_quiver = None
        self._ts_wind_after_id = None
        # Generation counter bumped on each _plot_timeseries() call.
        # Chunked multi-station render bails if stale (selection changed mid-render).
        self._ts_plot_gen = 0
        self._ov_rendered = set()
        self._ov_row_cache = {}  # stid -> (tag, values) memo for Overview rows
        self._current_stid = None
        self._all_ov_cols = ()
        self._ov_var_col_map = {}  # col_name -> (vname, stat_key)

        self.cfg = default_config()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_quit)
        self.bind("<Command-s>", lambda _: self._save_session())
        # macOS Aqua quirk: ttk.Treeview row tag colors unpainted until keyboard focus
        # or tab/window focus change. Nudge on all focus events.
        self.nb.bind("<<NotebookTabChanged>>", self._nudge_ov_repaint)
        self.bind("<FocusIn>", self._nudge_ov_repaint)
        self.bind("<Visibility>", self._nudge_ov_repaint)
        # Tk quirk: finish geometry+paint before window mapped, else alert sheet
        # later causes transparent corners. update_idletasks ensures clean render.
        self.update_idletasks()
        self.after(100, self._check_autosave)

    def _build_ui(self):
        """Construct the main application interface with all notebook tabs."""
        derived = setup_style(self)
        self._pane_header_bg = derived["header_bg"]
        self._build_topbar()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._build_overview_tab()
        self._build_detail_tab()
        self._build_map_tab()
        self._build_skiplist_tab()

    def _build_topbar(self):
        """Build the top navigation bar with file/session controls and status display."""
        bar = ttk.Frame(self, relief="flat")
        bar.pack(fill="x", padx=4, pady=4)
        ttk.Button(bar, text="Open H5", command=self._open_file).pack(side="left", padx=(4, 2))
        # Use ttk.Label so theme respects system dark/light mode (not hardcoded color).
        self.lbl_file = ttk.Label(bar, text="No file loaded", anchor="w")
        self.lbl_file.pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(bar, text="Settings...", command=self._open_thresholds_dialog).pack(
            side="left", padx=(8, 2)
        )
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6, pady=3)
        ttk.Button(bar, text="Save Session", command=self._save_session).pack(side="left", padx=2)
        ttk.Button(bar, text="Load Session", command=self._load_session_file).pack(side="left", padx=2)
        # Fixed width prevents layout jitter from progress text updates.
        self.lbl_status = ttk.Label(bar, text="", anchor="e", width=48, style="Status.TLabel")
        self.lbl_status.pack(side="right", padx=8)
        self.pb_load = ttk.Progressbar(bar, mode="determinate", length=140)

    _ZOOM_WIDTH_HOURS = {
        "14d": 14 * 24,
        "7d": 7 * 24,
        "3d": 3 * 24,
        "1d": 24,
        "12h": 12,
        "6h": 6,
        "3h": 3,
        "1h": 1,
    }

    def _add_zoom_controls(self, parent, get_ax, get_canvas):
        """Build time-window zoom controls and navigator widget.

        Args:
            parent: Parent widget to pack controls into.
            get_ax (callable): Function returning the plot axes for xlim updates.
            get_canvas (callable): Function returning the plot canvas for redraw.

        Returns:
            callable: Apply function to sync view to width preset or custom range.
        """
        f = tk.Frame(parent)
        f.pack(fill="x", padx=4, pady=(0, 2))
        ttk.Label(f, text="Width:", style="Muted.TLabel").pack(side="left")
        width_var = tk.StringVar(value="Full")
        # Exposed so detail.py's xlim_changed hook can blank it when toolbar zoom/pan occurs.
        self._ts_width_var = width_var
        cb_width = ttk.Combobox(
            f,
            textvariable=width_var,
            state="readonly",
            width=6,
            values=["Full", "14d", "7d", "3d", "1d", "12h", "6h", "3h", "1h"],
        )
        cb_width.pack(side="left", padx=(2, 8))
        lbl = ttk.Label(f, text="—", font=FONT_MONO, style="Muted.TLabel")

        def _update_lbl(start, dur):
            end = start + dur
            lbl.config(
                text=f"{mdates.num2date(start):%Y-%m-%d %H:%M} -> " f"{mdates.num2date(end):%Y-%m-%d %H:%M}"
            )

        def _on_nav(start, dur, final):
            ax, canvas = get_ax(), get_canvas()
            ax.set_xlim(start, start + dur)
            _update_lbl(start, dur)
            canvas.draw_idle()
            # On final resize, update width var if it no longer matches a preset.
            if final:
                self._sync_width_var(width_var, dur)

        nav = TimeNavigator(f, on_change=_on_nav)
        self._ts_nav = nav

        def _apply(*_, reset_full=False):
            ax, canvas = get_ax(), get_canvas()
            xmin, xmax = ax.dataLim.intervalx
            if not np.isfinite(xmin) or not np.isfinite(xmax) or xmax <= xmin:
                return
            # Global extent (when loaded) is track domain; station's own dataLim is valid range.
            # Width preset must not shrink nav back to station extent alone.
            gext = getattr(self, "_time_extent_global", None)
            glo = ghi = None
            if gext is not None:
                try:
                    glo, ghi = mdates.date2num(gext[0]), mdates.date2num(gext[1])
                except (TypeError, ValueError):
                    glo = ghi = None
            if glo is not None and np.isfinite(glo) and np.isfinite(ghi) and ghi > glo:
                nav.set_domain(glo, ghi)
                nav.set_valid_range(xmin, xmax)
            else:
                nav.set_domain(xmin, xmax)
                nav.set_valid_range(None, None)
            cur_start, cur_dur = nav.get_window()
            if reset_full:
                width_var.set("Full")
            w = width_var.get()
            if w == "Full":
                # Full = global extent, not station's dataLim. Every station frames the same.
                if glo is not None and np.isfinite(glo) and np.isfinite(ghi) and ghi > glo:
                    start, dur = glo, ghi - glo
                else:
                    start, dur = xmin, xmax - xmin
            elif w in self._ZOOM_WIDTH_HOURS:
                dur = min(self._ZOOM_WIDTH_HOURS[w] / 24.0, xmax - xmin)
                start = cur_start if np.isfinite(cur_start) else xmin
            else:
                # Blank = custom width (nav-resized). Keep window as-is.
                start, dur = cur_start, cur_dur
            nav.set_window(start, dur)
            start, dur = nav.get_window()
            ax.set_xlim(start, start + dur)
            _update_lbl(start, dur)
            canvas.draw_idle()

        cb_width.bind("<<ComboboxSelected>>", _apply)
        nav.pack(side="left", padx=(4, 8), fill="x", expand=True)
        lbl.pack(side="left", padx=4)
        return _apply

    def _sync_width_var(self, width_var, dur):
        """Update width preset combobox to match current window duration.

        Args:
            width_var (tk.StringVar): Combobox variable holding preset name.
            dur (float): Current window duration in matplotlib date-num days.
        """
        hours = dur * 24.0
        for name, ph in self._ZOOM_WIDTH_HOURS.items():
            if abs(ph - hours) < 1e-6:
                width_var.set(name)
                return
        width_var.set("")

    def _prompt_add_skip(self, stid, default_reason="", switch_tab=True):
        """Show dialog to add a station to the skip list.

        Args:
            stid (str): Station identifier.
            default_reason (str): Pre-populated skip reason text.
            switch_tab (bool): If True, switch to skiplist tab after adding.
        """
        dlg = AddSkipDialog(self, stid, default_reason)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._add_to_skip(stid, dlg.result, switch_tab=switch_tab)

    def _add_to_skip(self, stid, reason, switch_tab=True):
        """Add station to skip list and refresh all affected displays.

        Args:
            stid (str): Station identifier.
            reason (str): Reason for skipping this station.
            switch_tab (bool): If True, switch to skiplist tab after adding.
        """
        mark_stations_skipped(self.skip_list, self.green_list, (stid,), reason)
        self._refresh_skiplist()
        self._refresh_overview(dirty={stid})
        self._refresh_station_list()
        self._refresh_map()
        if switch_tab:
            self.nb.select(3)
        self.lbl_status.config(text=f"Added {stid} to skip list")

    def _open_thresholds_dialog(self):
        """Open Settings dialog to adjust QC thresholds and appearance options.

        Handles re-running assertions if thresholds changed, loading fire perimeter data,
        and refreshing all tabs with new settings.
        """
        dlg = SettingsDialog(
            self,
            self.cfg,
            self.cfg["bounds"],
            tuple(c for c in self._OV_BASE_COLS if c != "STID"),
            self._ov_var_col_map,
            {c: v.get() for c, v in self._ov_col_vars.items()},
            self._VAR_SHORT,
        )
        self.wait_window(dlg)
        if dlg.result is not None:
            col_visibility = dlg.result.pop("col_visibility")
            perim_path = dlg.result.pop("perim_h5_path")
            rerun = (
                dlg.result["frozen_min_run"] != self.cfg["frozen_min_run"]
                or dlg.result["max_var_outage_min"] != self.cfg.get("max_var_outage_min")
                or dlg.result["full_outage_min"] != self.cfg.get("full_outage_min")
                or dlg.result["bounds"] != self.cfg["bounds"]
            )
            self.cfg.update(dlg.result)
            self.cfg["perim_h5_path"] = perim_path
            for c, val in col_visibility.items():
                if c in self._ov_col_vars:
                    self._ov_col_vars[c].set(val)
            self._apply_col_visibility()
            if perim_path:
                if self._perim_loaded_path is None or str(self._perim_loaded_path) != perim_path:
                    self._load_perim_h5(Path(perim_path))
            else:
                self._perim_data = []
                self._perim_loaded_path = None
            if self.stations:
                if rerun:
                    # heavy path: chunked re-run; the tab refreshes are
                    # coalesced into one on_complete at the very end.
                    self._rerun_assertions(on_complete=self._settings_refresh)
                else:
                    self._settings_refresh()

    def _settings_refresh(self):
        """Refresh all tabs after settings change.

        Called directly or after chunked re-run as coalesced batch refresh.
        """
        # Coalesced refresh after Settings-OK: called directly or after chunked re-run.
        self._refresh_overview()
        self._refresh_station_list()
        self._refresh_detail_view()
        self._refresh_map()

    def _rerun_assertions(self, on_complete=None):
        """Re-run all QC assertions in time-budgeted chunks to keep UI responsive.

        Uses a generation counter to cancel prior incomplete runs if settings change again.
        New H5 loads also cancel the run.

        Args:
            on_complete (callable, optional): Callback to invoke when all stations checked.
        """
        # Chunked re-run (generation counter + time-budget loop) to keep UI responsive.
        # Newer call bumps generation and cancels prior run. New H5 load cancels too.
        self._rerun_gen = getattr(self, "_rerun_gen", 0) + 1
        gen = self._rerun_gen
        self._rerun_stids = list(self.stations)
        self._rerun_idx = 0
        self._rerun_new_issues = {}
        self._rerun_on_complete = on_complete
        self._rerun_load_gen = getattr(self, "_load_gen_id", 0)
        self.pb_load["maximum"] = max(len(self._rerun_stids), 1)
        self.pb_load["value"] = 0
        self.pb_load.pack(side="right", padx=(0, 4))
        self.after(1, lambda: self._rerun_chunk(gen))

    def _rerun_chunk(self, gen, time_budget=0.05):
        """Process assertions for a batch of stations within time budget.

        Continues in background via after() if more stations remain. Bails if generation
        changed or new H5 load started mid-run. Calls on_complete callback when finished.

        Args:
            gen (int): Generation ID; processing halts if _rerun_gen advances.
            time_budget (float): Time in seconds to process before rescheduling.
        """
        if gen != self._rerun_gen:
            return  # superseded by a newer Settings-OK re-run
        if getattr(self, "_load_gen_id", 0) != self._rerun_load_gen:
            return  # a new H5 load started mid-run; it owns all_issues now
        stids = self._rerun_stids
        deadline = time.perf_counter() + time_budget
        while self._rerun_idx < len(stids) and time.perf_counter() < deadline:
            s = stids[self._rerun_idx]
            self._rerun_idx += 1
            st, stats = self.stations.get(s), self.all_stats.get(s)
            if st is not None and stats is not None:
                # Outage stats independent of cfg thresholds; re-check both families against changes.
                self._rerun_new_issues[s] = run_assertions(st, stats, self.cfg) + run_outage_assertions(
                    stats, self.cfg
                )
        self.pb_load["value"] = self._rerun_idx
        n = len(stids)
        if self._rerun_idx < n:
            self.lbl_status.config(text=f"Re-checking {self._rerun_idx}/{n} stations...")
            self.after(1, lambda: self._rerun_chunk(gen))
            return
        self.all_issues = self._rerun_new_issues
        self.pb_load.pack_forget()
        self.lbl_status.config(text=f"Re-checked {n} stations")
        on_complete = self._rerun_on_complete
        self._rerun_on_complete = None
        if on_complete is not None:
            on_complete()

    def _refresh_all(self):
        """Rebuild variable list and refresh all tabs after data load.

        Synthesizes a composite "wind" variable when both wind_speed and wind_direction
        are present (for display only; not in data or stats).
        """
        all_vars = sorted({v for s in self.stations.values() for v in s["variables"]})
        # Synthetic "wind" display var (tab-strip only, not data/stats/assertions).
        # Injected after wind_direction where both wind_speed and wind_direction exist.
        if "wind_speed" in all_vars and "wind_direction" in all_vars:
            all_vars.insert(all_vars.index("wind_direction") + 1, "wind")
        self._all_vars_global = all_vars
        self._rebuild_ov_columns()
        self._refresh_overview()
        self._refresh_station_list()
        self._refresh_map()
        self._refresh_skiplist()
