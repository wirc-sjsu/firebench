import time
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from ..widgets import StationListPanes
from ..dialogs import AddSkipDialog, AddRemovalDialog
from ..data import _segment_by_gap, _haversine_km
from ..theme import PLOT_BG, ERROR_FG, WARN_FG, ERROR_BG, WARN_BG, ACCENT, MUTED, OUTAGE_SHADE, FIG_DPI, PAD


class DetailTabMixin:
    def _build_detail_tab(self):
        """Build Station Detail tab with station list, time series, and stats views."""
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Station Detail")
        pw = ttk.PanedWindow(f, orient="horizontal")
        pw.pack(fill="both", expand=True)

        lf = ttk.Frame(pw, width=185)
        pw.add(lf, weight=0)
        ttk.Label(lf, text="Stations", style="Section.TLabel").pack()
        self.detail_panes = StationListPanes(
            lf,
            on_click=self._refresh_detail_view,
            on_select_change=self._refresh_detail_view,
            header_bg=self._pane_header_bg,
        )
        bsf = tk.Frame(lf)
        bsf.pack(fill="x")
        ttk.Button(
            bsf, text="Mark Greenlit (batch)", command=self._detail_add_greenlit, style="Small.TButton"
        ).pack(side="left", padx=PAD, pady=PAD)
        ttk.Button(
            bsf, text="Un-greenlit (batch)", command=self._station_list_ungreenlit, style="Small.TButton"
        ).pack(side="left", padx=PAD, pady=PAD)
        ttk.Button(
            bsf,
            text="Add to Skip List (batch)...",
            command=self._detail_add_skip_batch,
            style="Small.TButton",
        ).pack(side="left", padx=PAD, pady=PAD)

        rf = ttk.Frame(pw)
        pw.add(rf, weight=1)
        self.detail_nb = ttk.Notebook(rf)
        self.detail_nb.pack(fill="both", expand=True)
        self._build_ts_subtab()
        self._build_varstats_subtab()
        self._build_assert_subtab()

    def _build_ts_subtab(self):
        """Build Time Series subtab with plot canvas, wind controls, and range-selection tools."""
        f = ttk.Frame(self.detail_nb)
        self.detail_nb.add(f, text="Time Series")
        self.var_ts_var = tk.StringVar()

        varstrip_row = tk.Frame(f)
        varstrip_row.pack(fill="x", padx=4, pady=(4, 2))
        # btn_ts_compare sits outside frm_var_btns so it survives
        # _rebuild_var_tabs which destroys/recreates all children of frm_var_btns.
        self.btn_ts_compare = ttk.Button(
            varstrip_row, text="Compare...", command=self._ts_compare_nearest, state="disabled"
        )
        self.btn_ts_compare.pack(side="right", padx=(8, 2))
        self.frm_var_btns = tk.Frame(varstrip_row)
        self.frm_var_btns.pack(side="left", fill="x", expand=True)
        self._ts_var_btns: dict = {}
        self._ts_var_order: list = []

        # plot_row created before canvas (but not packed) so canvas can be a true
        # child of plot_row. Packing order still puts tb_row above visually.
        plot_row = tk.Frame(f)

        fig = Figure(figsize=(8, 3.6), dpi=FIG_DPI)
        self.ax_ts = fig.add_subplot(111)
        self.canvas_ts = FigureCanvasTkAgg(fig, master=plot_row)

        tb_row = tk.Frame(f)
        tb_row.pack(fill="x")
        NavigationToolbar2Tk(self.canvas_ts, tb_row).pack(side="left", fill="x", expand=True)
        # Collapsible legend panel for multi-station overlay (collapsed by default).
        # Holds station names with line colors instead of cluttering plot with legend.
        self._ts_legend_open = False
        self.btn_ts_legend = ttk.Button(tb_row, text="Legend ▸", width=10, command=self._toggle_ts_legend)
        self.btn_ts_legend.pack(side="right", padx=4)
        # Wind plot controls: aggregation bin width picker + Auto toggle.
        # Auto = dt adjusts with on-screen arrow density; off = user-fixed dt.
        self.frm_wind_dt = ttk.Frame(tb_row)
        self.var_wind_auto = tk.BooleanVar(value=True)
        ttk.Label(self.frm_wind_dt, text="Arrow dt:").pack(side="left")
        self.cmb_wind_dt = ttk.Combobox(
            self.frm_wind_dt, width=7, values=list(self._WIND_DT_CHOICES), state="disabled"
        )
        self.cmb_wind_dt.pack(side="left", padx=(2, 4))
        self.cmb_wind_dt.bind("<<ComboboxSelected>>", self._on_wind_dt_pick)
        ttk.Checkbutton(
            self.frm_wind_dt, text="Auto", variable=self.var_wind_auto, command=self._on_wind_auto_toggle
        ).pack(side="left")
        # Below calm threshold, wind direction is noise—exclude from arrow direction.
        self.var_wind_calm = tk.BooleanVar(value=True)
        self.var_wind_calm_thresh = tk.StringVar(value="1.5")
        ttk.Checkbutton(
            self.frm_wind_dt, text="Calm <", variable=self.var_wind_calm, command=self._on_wind_dt_pick
        ).pack(side="left", padx=(6, 0))
        ent_wind_calm = ttk.Entry(self.frm_wind_dt, width=4, textvariable=self.var_wind_calm_thresh)
        ent_wind_calm.pack(side="left")
        ent_wind_calm.bind("<Return>", self._on_wind_dt_pick)
        ent_wind_calm.bind("<FocusOut>", self._on_wind_dt_pick)
        ttk.Label(self.frm_wind_dt, text="m/s").pack(side="left")

        plot_row.pack(fill="both", expand=True)
        self.canvas_ts.get_tk_widget().pack(side="left", fill="both", expand=True)
        self._add_var_cycle_arrows(self.canvas_ts.get_tk_widget(), self._ts_prev_var, self._ts_next_var)

        self.frm_ts_legend = tk.Frame(plot_row, width=150)
        self.tv_ts_legend = ttk.Treeview(
            self.frm_ts_legend, show="tree", selectmode="none", style="Pane.Treeview"
        )
        self.tv_ts_legend.column("#0", width=140, anchor="w")
        legend_sb = ttk.Scrollbar(self.frm_ts_legend, orient="vertical", command=self.tv_ts_legend.yview)
        self.tv_ts_legend.configure(yscrollcommand=legend_sb.set)
        legend_sb.pack(side="right", fill="y")
        self.tv_ts_legend.pack(fill="both", expand=True)

        _zoom_apply = self._add_zoom_controls(f, lambda: self.ax_ts, lambda: self.canvas_ts)

        def _apply_and_sync(*a, _f=_zoom_apply):
            # New station selection resets view to global range (one-shot flag).
            # Variable-only switch keeps current window. Syncs navigator after apply.
            reset = getattr(self, "_ts_reset_view", False)
            self._ts_reset_view = False
            _f(*a, reset_full=reset)
            self._sync_ts_nav()

        self._ts_zoom_apply = _apply_and_sync
        self.canvas_ts.mpl_connect("button_press_event", self._on_ts_press)
        self.canvas_ts.mpl_connect("motion_notify_event", self._on_ts_motion)
        self.canvas_ts.mpl_connect("button_release_event", self._on_ts_release)

        skip_row = tk.Frame(f)
        skip_row.pack(fill="x", padx=4, pady=(2, 4))
        tk.Label(skip_row, text="Reason:").pack(side="left")
        self.var_ts_reason = tk.StringVar()
        ttk.Entry(skip_row, textvariable=self.var_ts_reason, width=44).pack(side="left", padx=4)
        ttk.Button(skip_row, text="Add to Skip List", command=self._ts_add_skip).pack(side="left")
        # Remove records (marked non-destructive manifest): point or range selection.
        self.btn_ts_remove = ttk.Button(
            skip_row, text="Remove records...", command=self._ts_remove_records, state="disabled"
        )
        self.btn_ts_remove.pack(side="left", padx=(12, 0))

    def _build_varstats_subtab(self):
        """Build Variable Stats subtab with statistics table for single-station mode."""
        f = ttk.Frame(self.detail_nb)
        self.detail_nb.add(f, text="Variable Stats")
        cols = (
            "Variable",
            "NaN%",
            "Avg Freq (min)",
            "Longest Gap (hr)",
            "Longest Frozen (pts)",
            "Min",
            "Max",
            "Mean",
        )
        self.tv_vs = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        widths = (170, 60, 110, 120, 145, 80, 80, 80)
        for c, w in zip(cols, widths):
            self.tv_vs.heading(c, text=c)
            self.tv_vs.column(c, width=w, anchor="center")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tv_vs.yview)
        self.tv_vs.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tv_vs.pack(fill="both", expand=True)
        self.tv_vs.tag_configure("warn", background=WARN_BG, foreground="black")
        self.tv_vs.tag_configure("error", background=ERROR_BG, foreground="black")
        bf = tk.Frame(f)
        bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="Flag selected variable -> Skip List", command=self._vs_add_skip).pack(
            side="left"
        )

    def _build_assert_subtab(self):
        """Build Assertions subtab with QC issue tree for single-station mode."""
        f = ttk.Frame(self.detail_nb)
        self.detail_nb.add(f, text="Assertions")
        self.tv_assert = ttk.Treeview(f, show="tree", selectmode="browse", style="Mono.Treeview")
        self.tv_assert.column("#0", anchor="w")
        self.tv_assert.tag_configure("error", foreground=ERROR_FG)
        self.tv_assert.tag_configure("warn", foreground=WARN_FG)
        sb = ttk.Scrollbar(f, command=self.tv_assert.yview)
        self.tv_assert.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tv_assert.pack(fill="both", expand=True)
        bf = tk.Frame(f)
        bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="Add to Skip List (selected reason)", command=self._assert_add_skip).pack(
            side="left"
        )

    def _refresh_station_list(self):
        """Refresh station list panel with current skip/greenlit status and QC issue icons.

        Updates status prefixes: [!] for ERROR, [~] for WARN, [ ] for clear.
        """

        def _status(stid):
            issues = self.all_issues.get(stid, [])
            has_err = any(s == "ERROR" for s, _, _ in issues)
            has_warn = any(s == "WARN" for s, _, _ in issues)
            return "[!] " if has_err else ("[~] " if has_warn else "[ ] ")

        self.detail_panes.refresh(self.stids, self.skip_list, self.green_list, status_fn=_status)

    def _detail_add_greenlit(self):
        """Mark selected stations as greenlit (auto-approval, excluded from QC review).

        Updates self.green_list and refreshes overview/station list. Requires
        at least one selected station.
        """
        sel = self.detail_panes.get_selected()
        if not sel:
            messagebox.showinfo("Select", "Click a station first (Ctrl/Cmd-click for more)")
            return
        self.green_list.update(sel)
        self._refresh_station_list()
        self._refresh_overview(dirty=set(sel))
        self.lbl_status.config(text=f"Greenlit {len(sel)} station{'s' if len(sel) != 1 else ''}")

    def _station_list_ungreenlit(self):
        """Remove greenlit status from selected stations.

        Requires selection to include at least one currently greenlit station.
        """
        sel = self.detail_panes.get_selected() & self.green_list
        if not sel:
            messagebox.showinfo("Select", "Select greenlit station(s) first")
            return
        self.green_list -= sel
        self._refresh_station_list()
        self._refresh_overview(dirty=set(sel))
        self.lbl_status.config(text=f"Removed {len(sel)} from greenlit")

    def _detail_add_skip_batch(self):
        """Batch add selected stations to skip list with user-provided reason.

        For single selection: suggests top 3 issue reasons. For multi-selection:
        opens generic dialog. Updates skip_list and refreshes all views.
        """
        sel = self.detail_panes.get_selected()
        if not sel:
            messagebox.showinfo("Select", "Click a station first (Ctrl/Cmd-click for more)")
            return
        if len(sel) == 1:
            stid = next(iter(sel))
            shorts = [self._short_reason(k, m) for _, k, m in self.all_issues.get(stid, [])]
            self._prompt_add_skip(stid, "; ".join(dict.fromkeys(shorts[:3])))
        else:
            dlg = AddSkipDialog(self, None, "", label=f"{len(sel)} stations selected")
            self.wait_window(dlg)
            if dlg.result is not None:
                for stid in sel:
                    self.skip_list[stid] = dlg.result
                self._refresh_skiplist()
                self._refresh_overview(dirty=set(sel))
                self._refresh_station_list()
                self.nb.select(3)
                self.lbl_status.config(text=f"Added {len(sel)} stations to skip list")

    def _navigate_to_station(self, stid):
        """Switch to Detail tab and select single station.

        Used by map and overview tabs to navigate to a specific station's
        time series view.

        Args:
            stid (str): Station ID to select.
        """
        self.nb.select(1)
        self.detail_panes.select_only(stid)
        self._refresh_detail_view()

    def _set_single_station_tabs_enabled(self, enabled):
        """Enable/disable Variable Stats and Assertions tabs (single-station only).

        Time Series tab (0) always remains enabled. Multi-station overlay hides
        tabs 1-2 and switches to Time Series if currently viewing those tabs.
        Also controls Compare and Remove buttons.

        Args:
            enabled (bool): True for single-station, False for multi-station.
        """
        # Variable Stats / Assertions only make sense for single-station.
        # Tabs 1 and 2 greyed/disabled for multi-station; tab 0 (Time Series) always enabled.
        state = "normal" if enabled else "disabled"
        for idx in (1, 2):
            self.detail_nb.tab(idx, state=state)
        if not enabled and self.detail_nb.index("current") != 0:
            self.detail_nb.select(0)
        self.btn_ts_compare.config(state=("normal" if enabled else "disabled"))
        self.btn_ts_remove.config(state=("normal" if enabled else "disabled"))

    def _rebuild_var_tabs(self, avail_vars):
        """Build or update variable tab-strip with available variables for current selection.

        Reuses Radiobutton widgets (avoid destroy/recreate churn) but reconfigures
        text and enabled state. Only destroys/creates if variable count changes.
        Greys out unavailable variables. Updates self._ts_var_btns dict and
        self._ts_var_order list for navigation cycling.

        Args:
            avail_vars (list): Available variable names for current station(s).
        """
        # (Re)build variable tab-strip against full dataset-wide variable set.
        # Grey unavailable vars; reuse Radiobuttons by reconfig instead of destroy/recreate.
        # Only destroy/create if variable count changes.
        avail_set = set(avail_vars)
        all_vars = self._all_vars_global if getattr(self, "_all_vars_global", None) else avail_vars
        all_vars = list(all_vars)
        self._ts_var_order = all_vars
        btns = list(self.frm_var_btns.winfo_children())
        for w in btns[len(all_vars) :]:
            w.destroy()
        btns = btns[: len(all_vars)]
        while len(btns) < len(all_vars):
            rb = ttk.Radiobutton(
                self.frm_var_btns,
                style="VarTab.Toolbutton",
                variable=self.var_ts_var,
                command=self._plot_timeseries,
            )
            rb.pack(side="left", padx=1, pady=1)
            btns.append(rb)
        self._ts_var_btns = {}
        for rb, v in zip(btns, all_vars):
            rb.configure(text=v, value=v)
            rb.state(["disabled"] if v not in avail_set else ["!disabled"])
            self._ts_var_btns[v] = rb

    def _refresh_detail_view(self, _stid=None):
        """Refresh detail tabs based on current station selection (single vs. multi-station).

        Populates Variable Stats and Assertions tables in single-station mode,
        disables them in multi-station overlay mode. Rebuilds variable tab-strip
        and triggers initial plot. Includes synthetic "wind" tab if both wind_speed
        and wind_direction are available.

        Args:
            _stid: Unused; provided by station list callback protocol.
        """
        # Single-station (rich view) vs multi-station (overlay) based on selection.
        sel = sorted(self.detail_panes.get_selected())
        if not sel:
            self._current_stid = None
            self._set_single_station_tabs_enabled(False)
            self._rebuild_var_tabs([])
            self.var_ts_var.set("")
            self.ax_ts.cla()
            self.canvas_ts.draw()
            return

        if len(sel) == 1:
            stid = sel[0]
            self._current_stid = stid
            st, stats, issues = self.stations[stid], self.all_stats[stid], self.all_issues[stid]
            avail_vars = sorted(st["variables"].keys())
            self._set_single_station_tabs_enabled(True)

            self.tv_vs.delete(*self.tv_vs.get_children())
            avg_freq = stats["_time"]["avg_freq_min"]
            flagged_keys = {key for _, key, _ in issues}
            for vname in avail_vars:
                vs = stats[vname]
                tag = ""
                if any(
                    f"nan:{vname}" in flagged_keys
                    or f"frozen:{vname}" in flagged_keys
                    or f"lo:{vname}" in flagged_keys
                    or f"hi:{vname}" in flagged_keys
                    for _ in [1]
                ):
                    tag = "warn"
                if any(k in flagged_keys for k in (f"lo:{vname}", f"hi:{vname}")):
                    err_sev = next(
                        (s for s, k, _ in issues if k in (f"lo:{vname}", f"hi:{vname}") and s == "ERROR"),
                        None,
                    )
                    if err_sev:
                        tag = "error"
                gap_hr = f"{vs['longest_gap_hr']:.1f}" if vs["longest_gap_hr"] is not None else "--"
                self.tv_vs.insert(
                    "",
                    "end",
                    iid=vname,
                    tags=(tag,),
                    values=(
                        vname,
                        f"{vs['nan_pct']:.1f}%",
                        f"{avg_freq:.0f}" if avg_freq else "--",
                        gap_hr,
                        str(vs["longest_frozen"]),
                        f"{vs['min']:.3f}" if vs["min"] is not None else "--",
                        f"{vs['max']:.3f}" if vs["max"] is not None else "--",
                        f"{vs['mean']:.3f}" if vs["mean"] is not None else "--",
                    ),
                )

            # Populate assertions; iid = row index for _assert_add_skip to map back.
            self.tv_assert.delete(*self.tv_assert.get_children())
            for i, (sev, key, msg) in enumerate(issues):
                tag = "error" if sev == "ERROR" else "warn"
                self.tv_assert.insert("", "end", iid=str(i), text=f"[{sev}]  {msg}", tags=(tag,))
        else:
            self._current_stid = None
            avail_vars = sorted({v for s in sel for v in self.stations[s]["variables"]})
            self._set_single_station_tabs_enabled(False)

        # Synthetic "wind" tab only in single-station with both wind_speed and wind_direction.
        # Appended after var-stats/assertions loops to avoid KeyError on missing sensor.
        if (
            self._current_stid is not None
            and "wind_speed" in self.stations[self._current_stid]["variables"]
            and "wind_direction" in self.stations[self._current_stid]["variables"]
        ):
            avail_vars = list(avail_vars) + ["wind"]
        self._ts_avail_vars = avail_vars
        self._rebuild_var_tabs(avail_vars)
        if avail_vars and self.var_ts_var.get() not in avail_vars:
            self.var_ts_var.set(avail_vars[0])
        elif not avail_vars:
            self.var_ts_var.set("")
        self.var_ts_reason.set("")
        self._plot_timeseries()

    def _ts_compare_nearest(self):
        """Select source station and N nearest geographic neighbors with current variable.

        Finds up to N stations (from config "compare_n_neighbors", default 4) with
        lowest haversine distance that also have the selected variable available.
        Optionally includes skip-listed/greenlit stations (from config
        "compare_include_skip_greenlit"). Overlays all stations and pins
        sparkline to source station. Enables "Compare..." button only in
        single-station mode.
        """
        # Source station + N nearest geographic neighbors with current variable.
        # N and pool eligibility configurable via Settings.
        stid = self._current_stid
        if not stid:
            return
        vname = self.var_ts_var.get()
        if not vname:
            messagebox.showinfo("No variable", "Select a variable first")
            return
        src = self.stations[stid]
        n = int(self.cfg.get("compare_n_neighbors", 4))
        include_pool = self.cfg.get("compare_include_skip_greenlit", False)
        candidates = []
        for other in self.stids:
            if other == stid:
                continue
            if not include_pool and (other in self.skip_list or other in self.green_list):
                continue
            st = self.stations[other]
            if vname not in st["variables"]:
                continue
            dist = _haversine_km(src["lat"], src["lon"], st["lat"], st["lon"])
            candidates.append((dist, other))
        if not candidates:
            hint = "" if include_pool else " (skip-listed/greenlit excluded — see Settings)"
            messagebox.showinfo("No neighbors", f"No other stations have '{vname}' available{hint}")
            return
        candidates.sort(key=lambda x: x[0])
        nearest = {s for _, s in candidates[:n]}
        # Nav sparkline pinned to source station (the one Compare was pressed from).
        self._ts_compare_source = stid
        self.detail_panes.select_many({stid} | nearest)
        self._refresh_detail_view()

    _ARROW_FAINT = "#c9c9c9"
    _ARROW_HOVER = ACCENT

    def _add_var_cycle_arrows(self, canvas_widget, on_prev, on_next):
        """Add hover-reveal variable-cycle chevrons to left/right of plot canvas.

        Netflix-banner-style: chevrons hidden by default (faint), highlight on
        hover. Drawn on tk.Canvas for precise control over angle and roundness.
        Placed at canvas edges (relx/rely anchoring).

        Args:
            canvas_widget: tk.Widget to overlay chevrons on.
            on_prev: Callback for left-side click (previous variable).
            on_next: Callback for right-side click (next variable).
        """
        # Faint hover-reveal chevrons on plot edges (Netflix-banner-style).
        # Drawn on tk.Canvas for precise angle/roundness control.
        w, h = 22, 40
        cy = h / 2
        # Obtuse apex (~103°): wide, not pointy.
        run, arm = 8, 10
        cx = w / 2

        def _make(side, cmd):
            cv = tk.Canvas(canvas_widget, width=w, height=h, bg=PLOT_BG, highlightthickness=0, bd=0)
            if side == "right":
                apex_x, base_x = cx + run / 2, cx - run / 2
            else:
                apex_x, base_x = cx - run / 2, cx + run / 2
            line = cv.create_line(
                base_x,
                cy - arm,
                apex_x,
                cy,
                base_x,
                cy + arm,
                fill=self._ARROW_FAINT,
                width=4,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            relx = 0.0 if side == "left" else 1.0
            anchor = "w" if side == "left" else "e"
            cv.place(relx=relx, rely=0.5, anchor=anchor)
            cv.bind("<Enter>", lambda _e: cv.itemconfig(line, fill=self._ARROW_HOVER))
            cv.bind("<Leave>", lambda _e: cv.itemconfig(line, fill=self._ARROW_FAINT))
            cv.bind("<Button-1>", lambda _e: cmd())
            return cv

        _make("left", on_prev)
        _make("right", on_next)

    def _ts_prev_var(self):
        """Cycle to previous available variable in tab strip.

        Wraps around at start. Triggered by left-side chevron hover-click.
        """
        vals = [v for v in self._ts_var_order if v in getattr(self, "_ts_avail_vars", [])]
        if not vals:
            return
        cur = self.var_ts_var.get()
        idx = vals.index(cur) if cur in vals else 0
        self.var_ts_var.set(vals[(idx - 1) % len(vals)])
        self._plot_timeseries()

    def _ts_next_var(self):
        """Cycle to next available variable in tab strip.

        Wraps around at end. Triggered by right-side chevron hover-click.
        """
        vals = [v for v in self._ts_var_order if v in getattr(self, "_ts_avail_vars", [])]
        if not vals:
            return
        cur = self.var_ts_var.get()
        idx = vals.index(cur) if cur in vals else -1
        self.var_ts_var.set(vals[(idx + 1) % len(vals)])
        self._plot_timeseries()

    _MULTI_PLOT_CHUNK_THRESHOLD = 15

    def _plot_timeseries(self):
        """Dispatch to single-station or multi-station plotting based on current selection.

        Increments plot generation counter to abort in-flight chunked renders
        if a new selection supersedes them. Resets view to full range on new
        station selection (but preserves window on variable-only switches).
        Clears stale Compare source and range selections.
        """
        # Dispatcher: single-station rich view vs multi-station overlay.
        # Plot generation bumped on every call; in-flight chunked renders check
        # generation to abort if superseded by a new selection.
        self._ts_plot_gen += 1
        # Any replot invalidates shift-drag range selection (indices tied to old _ts_times).
        self._ts_clear_range_sel(redraw=False)
        # Clear stale nav sparkline from previous overlay mode.
        self._ts_nav_series = None
        sel = self.detail_panes.get_selected()
        # New station selection resets view to full range (one-shot flag).
        # Variable-only switch keeps current window.
        sel_key = frozenset(sel)
        if sel_key != getattr(self, "_ts_last_sel", None):
            self._ts_reset_view = True
            # Drop stale Compare source unless still part of new selection.
            if getattr(self, "_ts_compare_source", None) not in sel:
                self._ts_compare_source = None
        self._ts_last_sel = sel_key
        if len(sel) > 1:
            self._plot_timeseries_multi(sorted(sel), self._ts_plot_gen)
        else:
            self._plot_timeseries_single()

    def _plot_timeseries_multi(self, stids, gen):
        """Initialize multi-station overlay plot with gap-segmented LineCollections per station.

        Sets up chunked rendering (if >15 stations) with progress bar. Configures
        a sparkline from Compare source or first station for time-navigator. Initializes
        color tracking and missing-data lists for legend building.

        Args:
            stids (list): Selected station IDs to overlay.
            gen (int): Plot generation counter; used to abort if superseded.
        """
        vname = self.var_ts_var.get()
        ax = self.ax_ts
        ax.cla()
        self._ts_sel_artist = None
        self._ts_sel_annot = None
        self._ts_sel_idx = None
        self._ts_times = self._ts_data = self._ts_xnum = None
        self._ts_wd = None
        self._ts_quiver = None
        self.frm_wind_dt.pack_forget()
        if not vname:
            self.canvas_ts.draw()
            return
        # Nav sparkline: Compare-sourced overlay pins to source station only.
        # Plain multi-select falls back to first selected station (sort order).
        compare_src = getattr(self, "_ts_compare_source", None)
        candidates = [compare_src] if compare_src in stids else stids
        for stid in candidates:
            st = self.stations[stid]
            data = st["variables"].get(vname)
            times = st["times"]
            if (
                data is not None
                and isinstance(times, np.ndarray)
                and np.issubdtype(times.dtype, np.datetime64)
            ):
                self._ts_nav_series = (mdates.date2num(times), data)
                break
        ax.set_ylabel(vname)
        ax.grid(True, alpha=0.3)
        self._ts_multi_stids = stids
        self._ts_multi_idx = 0
        self._ts_multi_units = ""
        self._ts_multi_missing = []
        self._ts_multi_colors = {}
        chunked = len(stids) > self._MULTI_PLOT_CHUNK_THRESHOLD
        if chunked:
            self.pb_load["maximum"] = len(stids)
            self.pb_load["value"] = 0
            self.pb_load.pack(side="right", padx=(0, 4))
        self._plot_timeseries_multi_chunk(gen)

    def _plot_timeseries_multi_chunk(self, gen, time_budget=0.05):
        """Render multi-station overlay in time-budgeted chunks (non-blocking UI).

        Processes stations incrementally within a time budget; reschedules
        itself if more remain. Updates progress bar and status label for large
        datasets. Aborts if generation counter changes (newer plot requested).

        Args:
            gen (int): Plot generation counter; current chunk aborts if gen != self._ts_plot_gen.
            time_budget (float): Maximum seconds to spend per chunk (default 0.05).
        """
        # Abort if superseded by newer plot.
        if gen != self._ts_plot_gen:
            return
        ax = self.ax_ts
        vname = self.var_ts_var.get()
        stids = self._ts_multi_stids
        chunked = len(stids) > self._MULTI_PLOT_CHUNK_THRESHOLD
        deadline = time.perf_counter() + time_budget
        while self._ts_multi_idx < len(stids) and time.perf_counter() < deadline:
            stid = stids[self._ts_multi_idx]
            self._ts_multi_idx += 1
            st = self.stations[stid]
            if vname not in st["variables"]:
                self._ts_multi_missing.append(stid)
                continue
            if not self._ts_multi_units:
                self._ts_multi_units = st["var_units"].get(vname, "")
            avg_freq = self.all_stats[stid]["_time"].get("avg_freq_min")
            segments = _segment_by_gap(st["times"], st["variables"][vname], avg_freq)
            # Batch gap-segments into one LineCollection per station (not one Line2D per segment).
            # Keeps per-station color and legend mapping. Collections bypass units framework,
            # so datetime x needs explicit date2num conversion.
            segs = [
                np.column_stack([mdates.date2num(t_seg), d_seg]) for t_seg, d_seg in segments if len(t_seg)
            ]
            if segs:
                if not self._ts_multi_colors:
                    ax.xaxis_date()
                color = ax._get_lines.get_next_color()
                ax.add_collection(LineCollection(segs, colors=color, linewidths=0.8, alpha=0.8, label=stid))
                self._ts_multi_colors[stid] = color
        done = self._ts_multi_idx >= len(stids)
        if chunked:
            self.pb_load["value"] = self._ts_multi_idx
            self.lbl_status.config(text=f"Plotting {self._ts_multi_idx}/{len(stids)} stations...")
        # add_collection(autolim=True) grows dataLim but doesn't autoscale view.
        if self._ts_multi_colors:
            ax.autoscale_view()
        if not done:
            self.canvas_ts.draw_idle()
            self.after(1, lambda: self._plot_timeseries_multi_chunk(gen))
            return
        units = self._ts_multi_units
        ax.set_ylabel(f"{vname} [{units}]" if units else vname)
        ax.set_title(f"Overlay: {vname}  ({len(stids)} stations)")
        ax.figure.autofmt_xdate()
        self.canvas_ts.draw()
        self._ts_zoom_apply()
        self._rebuild_ts_legend_panel()
        if chunked:
            self.pb_load.pack_forget()
            self.lbl_status.config(text=f"Plotted {len(stids)} stations")

    def _toggle_ts_legend(self):
        """Toggle collapsible legend panel open/closed (multi-station overlay mode).

        Shows/hides Treeview listing station names with line colors.
        Updates button text to ▸ (closed) or ◂ (open).
        """
        self._ts_legend_open = not self._ts_legend_open
        if self._ts_legend_open:
            self.frm_ts_legend.pack(side="right", fill="y", padx=(4, 0))
            self.btn_ts_legend.config(text="Legend ◂")
        else:
            self.frm_ts_legend.pack_forget()
            self.btn_ts_legend.config(text="Legend ▸")

    def _rebuild_ts_legend_panel(self):
        """Populate legend Treeview from last completed multi-station overlay render.

        Lists plotted stations (colored text matching line color) and missing-data
        stations (grey 'x' prefix). Called after chunked render completes.
        """
        # Populate legend from last completed multi-station render.
        # Plotted stations: line color as text color. Missing: grey 'x' prefix.
        tv = self.tv_ts_legend
        tv.delete(*tv.get_children())
        for stid in self._ts_multi_stids:
            if stid in self._ts_multi_colors:
                color = self._ts_multi_colors[stid]
                tv.insert("", "end", iid=stid, text=stid, tags=(stid,))
                tv.tag_configure(stid, foreground=color)
            elif stid in self._ts_multi_missing:
                tv.insert("", "end", iid=f"{stid}__nodata", text=f"x  {stid}", tags=("nodata",))
        tv.tag_configure("nodata", foreground=MUTED)

    def _plot_timeseries_single(self):
        """Plot single-station time series or synthetic wind quiver for current variable.

        For "wind" variable: calls _plot_wind_single. For other variables: plots
        line segments with NaN-run shading (outage spans). Stores snapshots in
        self._ts_times, self._ts_data, self._ts_xnum for point-selection machinery.
        Overlays removal-record spans. Updates time-navigator and zoom controls.
        """
        # Clear legend panel (no content in single-station mode).
        self.tv_ts_legend.delete(*self.tv_ts_legend.get_children())
        if not self._current_stid:
            self.ax_ts.cla()
            self.canvas_ts.draw_idle()
            return
        vname = self.var_ts_var.get()
        if not vname:
            return
        st = self.stations[self._current_stid]
        # Synthetic "wind" var -> quiver. Degrade gracefully if missing either sensor.
        if vname == "wind":
            if "wind_speed" in st["variables"] and "wind_direction" in st["variables"]:
                self._plot_wind_single(st)
            else:
                self.frm_wind_dt.pack_forget()
                self._ts_times = self._ts_data = self._ts_xnum = None
                self._ts_wd = None
                self._ts_quiver = None
                self._ts_sel_artist = self._ts_sel_annot = self._ts_sel_idx = None
                self.ax_ts.cla()
                self.canvas_ts.draw_idle()
                self._ts_zoom_apply()
            return
        # Non-wind var: clear lingering wind-mode state.
        self.frm_wind_dt.pack_forget()
        self._ts_wd = None
        self._ts_quiver = None
        data = st["variables"].get(vname)
        times = st["times"]
        units = st["var_units"].get(vname, "")
        ax = self.ax_ts
        ax.cla()
        # ax.cla() drops selection marker/annotation; reset handles.
        self._ts_sel_artist = None
        self._ts_sel_annot = None
        self._ts_sel_idx = None
        if data is not None and isinstance(times, np.ndarray) and np.issubdtype(times.dtype, np.datetime64):
            self._ts_times, self._ts_data = times, data
            self._ts_xnum = mdates.date2num(times)
            self._ts_vname, self._ts_units = vname, units
        else:
            self._ts_times = self._ts_data = self._ts_xnum = None
        if data is not None:
            nan_mask = np.isnan(data)
            # Outage shading: wind_direction/wind_gust NaN expected when wind_speed=0.
            # Skip shading NaN run unless WS>0 somewhere in it (real outage).
            # All other vars shade any NaN run.
            ws_data = (
                st["variables"].get("wind_speed") if vname in ("wind_direction", "wind_gust") else None
            )
            if nan_mask.any():
                n = len(nan_mask)
                i = 0
                while i < n:
                    if nan_mask[i]:
                        j = i
                        while j < n and nan_mask[j]:
                            j += 1
                        if ws_data is not None and not np.any(ws_data[i:j] > 0):
                            i = j
                            continue
                        t_left = times[i - 1] if i > 0 else times[0]
                        t_right = times[j] if j < n else times[n - 1]
                        ax.axvspan(t_left, t_right, color=OUTAGE_SHADE, alpha=0.55, linewidth=0, zorder=0)
                        i = j
                    else:
                        i += 1
            avg_freq = self.all_stats[self._current_stid]["_time"].get("avg_freq_min")
            for t_seg, d_seg in _segment_by_gap(times, data, avg_freq):
                ax.plot(t_seg, d_seg, ".-", markersize=2, linewidth=0.8, color=ACCENT, zorder=2)
            ax.relim()
            ax.autoscale_view()
            ax.set_ylabel(f"{vname} [{units}]")
            ax.set_title(f"{self._current_stid}  —  {st['name']}")
            ax.grid(True, alpha=0.3)
            ax.figure.autofmt_xdate()
        self._draw_removal_overlays(ax, (vname,))
        self.canvas_ts.draw_idle()
        self._ts_zoom_apply()

    _TS_WIND_ARROW_CAP = 400
    # Manual aggregation-dt picks: label -> bin width in days (matplotlib date units).
    _WIND_DT_CHOICES = {
        "10 min": 10 / 1440,
        "30 min": 30 / 1440,
        "1 h": 1 / 24,
        "3 h": 3 / 24,
        "6 h": 6 / 24,
        "12 h": 12 / 24,
        "1 d": 1.0,
        "3 d": 3.0,
    }

    @staticmethod
    def _fmt_wind_dt(days):
        """Format matplotlib date-num bin width as human-readable interval string.

        Args:
            days (float): Bin width in matplotlib date-num units (days).

        Returns:
            str: Formatted interval ("10 min", "1.5 h", "3.0 d", etc.).
        """
        # Format bin width for Auto readout.
        mins = days * 1440.0
        if mins < 90:
            return f"{mins:.0f} min"
        if mins < 2880:
            return f"{mins / 60:.1f} h"
        return f"{days:.1f} d"

    def _on_wind_auto_toggle(self):
        """Handle wind binning Auto toggle: enable/disable manual bin-width picker.

        In auto mode, density-adapts arrow count to screen width. Manual mode
        respects user-selected bin width from combobox.
        """
        auto = self.var_wind_auto.get()
        self.cmb_wind_dt.configure(state="disabled" if auto else "readonly")
        if not auto and self.cmb_wind_dt.get() not in self._WIND_DT_CHOICES:
            self.cmb_wind_dt.set("1 h")
        if self._ts_wd is not None and self.var_ts_var.get() == "wind":
            self._draw_wind_quiver()

    def _on_wind_dt_pick(self, _evt=None):
        """Handle wind binning combobox change or calm threshold edit: redraw quiver.

        Triggered by combobox selection, calm-threshold checkbox, or entry focus-out.
        Redraws quiver with new parameters if wind plot is active.
        """
        if self._ts_wd is not None and self.var_ts_var.get() == "wind":
            self._draw_wind_quiver()

    def _plot_wind_single(self, st):
        """Plot synthetic wind plot: quiver arrows colored by wind_speed, rotated by direction.

        Displays viridis-colored arrows at (time, wind_speed) positions, rotated
        by wind_direction bearing (FROM compass, negated for downwind). Underlays
        faint wind_speed trend line. Configures wind controls (bin width picker,
        auto/manual toggle, calm-wind filter). Re-samples arrows on zoom/pan via
        debounced xlim_changed callback. Stores wind_direction snapshot for
        point-selection annotations.

        Args:
            st (dict): Station dict with "times" (np.datetime64[us]), "variables"
                (dict with "wind_speed" and "wind_direction" arrays), "var_units".
        """
        # Synthetic wind plot: quiver arrows (time, wind_speed) rotated by wind_direction,
        # viridis-colored by wind_speed, over faint ws trend line.
        # Arrows re-sampled to current x-view on zoom/pan (debounced xlim_changed).
        ax = self.ax_ts
        ax.cla()
        # ax.cla() drops selection artists, quiver, and xlim callbacks; clear and reconnect.
        self._ts_sel_artist = None
        self._ts_sel_annot = None
        self._ts_sel_idx = None
        self._ts_quiver = None
        self.frm_wind_dt.pack(side="right", padx=4)
        times = st["times"]
        ws = st["variables"].get("wind_speed")
        wd = st["variables"].get("wind_direction")
        units = st["var_units"].get("wind_speed", "")
        if (
            ws is None
            or wd is None
            or not isinstance(times, np.ndarray)
            or not np.issubdtype(times.dtype, np.datetime64)
        ):
            self._ts_times = self._ts_data = self._ts_xnum = None
            self._ts_wd = None
            self.canvas_ts.draw_idle()
            self._ts_zoom_apply()
            return
        # Snapshots: _ts_data = ws drives point selection; _ts_wd flags wind mode + annotation.
        self._ts_times = times
        self._ts_data = ws
        self._ts_xnum = mdates.date2num(times)
        self._ts_wd = wd
        self._ts_vname = "wind"
        self._ts_units = units
        # Outage shading: same NaN-run logic as normal plot, on ws.
        nan_mask = np.isnan(ws)
        if nan_mask.any():
            n = len(nan_mask)
            i = 0
            while i < n:
                if nan_mask[i]:
                    j = i
                    while j < n and nan_mask[j]:
                        j += 1
                    t_left = times[i - 1] if i > 0 else times[0]
                    t_right = times[j] if j < n else times[n - 1]
                    ax.axvspan(t_left, t_right, color=OUTAGE_SHADE, alpha=0.55, linewidth=0, zorder=0)
                    i = j
                else:
                    i += 1
        # Faint ws trend beneath arrows for readability where arrows thin.
        ax.plot(times, ws, "-", linewidth=0.8, alpha=0.3, color=MUTED, zorder=1)
        ax.set_ylabel(f"wind_speed [{units}]" if units else "wind_speed")
        ax.set_title(f"{self._current_stid}  —  {st['name']}  (wind)")
        ax.grid(True, alpha=0.3)
        ax.relim()
        ax.autoscale_view()
        # Freeze autoscale to prevent arrow re-quiver from recursing via xlim_changed.
        ax.set_autoscale_on(False)
        ax.figure.autofmt_xdate()
        # Re-sample arrows on x-view change (trailing-debounced).
        ax.callbacks.connect("xlim_changed", self._on_ts_wind_xlim)
        # Removal overlays: show removals for either underlying sensor or "*".
        self._draw_removal_overlays(ax, ("wind_speed", "wind_direction"))
        self._draw_wind_quiver()
        self.canvas_ts.draw_idle()
        self._ts_zoom_apply()

    def _draw_wind_quiver(self):
        """Draw or redraw wind quiver for current x-axis view with adaptive binning.

        Under arrow cap (default 400): plots raw samples. Over cap: aggregates into
        user-fixed or auto-density bins; per-bin direction computed as vector mean
        (circular mean of unit vectors). Y-values and colors snap to nearest raw
        sample time (rides actual trace, not smoothed mean). Filters calm-wind
        samples (< threshold) from direction computation to reduce noise. Normalizes
        vector magnitudes to uniform arrow size.

        Wind_direction convention: FROM-bearing (degrees, compass 0°=N clockwise).
        Negates bearing to get downwind arrow vector (airflow direction).
        """
        # (Re)draw wind quiver for current x-view. Under cap: raw samples.
        # Over cap: split into cap-many bins; direction = per-bin vector mean (circular mean);
        # y/color = raw sample nearest bin's mean time (rides trace, not smoothed mean).
        ax = self.ax_ts
        if self._ts_wd is None or self._ts_xnum is None:
            return
        if self._ts_quiver is not None:
            try:
                self._ts_quiver.remove()
            except (ValueError, AttributeError):
                pass
            self._ts_quiver = None
        xnum, ws, wd = self._ts_xnum, self._ts_data, self._ts_wd
        xmin, xmax = ax.get_xlim()
        if xmax < xmin:
            xmin, xmax = xmax, xmin
        in_view = (xnum >= xmin) & (xnum <= xmax) & ~np.isnan(ws) & ~np.isnan(wd)
        idxs = np.nonzero(in_view)[0]
        if idxs.size == 0:
            self.canvas_ts.draw_idle()
            return
        span = xmax - xmin
        if self.var_wind_auto.get():
            # Auto: ~1 arrow per 7 px on-screen; density tracks window size.
            try:
                width_px = self.ax_ts.get_window_extent().width
            except Exception:
                width_px = 0
            nbins = int(width_px / 7) if width_px > 0 else self._TS_WIND_ARROW_CAP
            nbins = max(40, min(nbins, self._TS_WIND_ARROW_CAP))
            if idxs.size > nbins:
                self.cmb_wind_dt.set(self._fmt_wind_dt(span / nbins))
            else:
                self.cmb_wind_dt.set("raw")
        else:
            # Manual: fixed user-picked bin width; bin count follows view span.
            dt_days = self._WIND_DT_CHOICES.get(self.cmb_wind_dt.get())
            if dt_days is None:
                dt_days = span / max(int(idxs.size), 1)
            nbins = max(1, min(int(np.ceil(span / dt_days)), 1200))
        # Calm-wind filter: below threshold, direction is noise.
        if self.var_wind_calm.get():
            try:
                calm_thresh = float(self.var_wind_calm_thresh.get())
            except (TypeError, ValueError):
                calm_thresh = 1.5
            dir_ok = ws[idxs] >= calm_thresh
        else:
            dir_ok = np.ones(idxs.size, dtype=bool)
        if idxs.size > nbins:
            xs, ys = xnum[idxs], ws[idxs]
            rad = np.radians(wd[idxs])
            bi = np.clip(((xs - xmin) / span * nbins).astype(int), 0, nbins - 1)
            cnt = np.bincount(bi, minlength=nbins)
            cnt_dir = np.bincount(bi, weights=dir_ok.astype(float), minlength=nbins)
            # Arrow only if bin has samples AND at least one usable direction.
            keep = (cnt > 0) & (cnt_dir > 0)
            n = cnt[keep]
            nd = cnt_dir[keep]
            x = np.bincount(bi, weights=xs, minlength=nbins)[keep] / n
            # y/color = nearest raw sample to bin's mean time (not bin-mean ws).
            # Snaps arrows to actual trace, avoiding flattened mean line.
            near = np.searchsorted(xs, x)
            near = np.clip(near, 1, xs.size - 1)
            near = np.where(np.abs(xs[near - 1] - x) <= np.abs(xs[near] - x), near - 1, near)
            y = ys[near]
            su = np.bincount(bi, weights=np.where(dir_ok, np.sin(rad), 0.0), minlength=nbins)[keep] / nd
            sv = np.bincount(bi, weights=np.where(dir_ok, np.cos(rad), 0.0), minlength=nbins)[keep] / nd
            # Normalize mean vector to unit length (uniform arrow size).
            mag = np.hypot(su, sv)
            mag[mag < 1e-12] = 1.0
            # Synoptic wind_direction = FROM-bearing. Negate to get airflow (downwind).
            u, v = -su / mag, -sv / mag
        else:
            idxs_r = idxs[dir_ok]
            x = xnum[idxs_r]
            y = ws[idxs_r]
            rad = np.radians(wd[idxs_r])
            # Wind_direction = bearing FROM (0°=N, 90°=E). Negate for downwind arrows.
            u = -np.sin(rad)
            v = -np.cos(rad)
        vis = ws[in_view]  # color norm over the full visible range, not just the capped/binned arrows
        vmin, vmax = float(np.min(vis)), float(np.max(vis))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            vmax = vmin + 1.0
        # scale=10 (1/10 inch ≈ 10 px): density up, size down vs original 1/8 inch @ 10 px.
        self._ts_quiver = ax.quiver(
            x,
            y,
            u,
            v,
            y,
            cmap="viridis",
            norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
            angles="uv",
            scale_units="inches",
            scale=10.0,
            pivot="mid",
            width=0.0045,
            headwidth=4.0,
            headlength=5.0,
            headaxislength=4.5,
            zorder=3,
        )
        self.canvas_ts.draw_idle()

    def _on_ts_wind_xlim(self, _ax):
        """Handle xlim change in wind mode: queue debounced quiver re-sample.

        Cancels pending debounced redraw and schedules new one (100 ms delay)
        to avoid excessive redraws during rapid zoom/pan. Only active when
        wind_direction snapshot is loaded.
        """
        # xlim_changed hook (wind mode): trailing-debounced quiver re-sample.
        if self._ts_wd is None:
            return
        if self._ts_wind_after_id is not None:
            self.after_cancel(self._ts_wind_after_id)
        self._ts_wind_after_id = self.after(100, self._ts_wind_xlim_fire)

    def _ts_wind_xlim_fire(self):
        """Execute debounced wind quiver redraw (called after 100 ms quiet).

        Safety checks: aborts if wind_direction cleared or plot switched away
        from wind variable.
        """
        self._ts_wind_after_id = None
        if self._ts_wd is None or self.var_ts_var.get() != "wind":
            return
        self._draw_wind_quiver()

    def _sync_ts_nav(self):
        """Synchronize time-series plot extent and sparkline to TimeNavigator widget.

        Sets Navigator domain to global data extent (or falls back to current station
        extent). Pushes current station's time series as sparkline preview. Wires
        xlim_changed callback to keep Navigator window in sync with toolbar zoom/pan.

        Navigator is optional; skips silently if not initialized.
        """
        # Push plot extent + sparkline to TimeNavigator and wire toolbar-zoom follow.
        nav = getattr(self, "_ts_nav", None)
        if nav is None:
            return
        ax = self.ax_ts
        xmin, xmax = ax.dataLim.intervalx
        station_ok = np.isfinite(xmin) and np.isfinite(xmax) and xmax > xmin
        # Domain: global time extent if available (short-record station spans whole H5 period);
        # valid range = station's own extent. Fallback: station extent as both domain/valid.
        gext = getattr(self, "_time_extent_global", None)
        glo = ghi = None
        if gext is not None:
            try:
                glo, ghi = mdates.date2num(gext[0]), mdates.date2num(gext[1])
            except (TypeError, ValueError):
                glo = ghi = None
        if glo is not None and np.isfinite(glo) and np.isfinite(ghi) and ghi > glo:
            nav.set_domain(glo, ghi)
            if station_ok:
                nav.set_valid_range(xmin, xmax)
            else:
                nav.set_valid_range(None, None)
        elif station_ok:
            nav.set_domain(xmin, xmax)
            nav.set_valid_range(None, None)
        if self._ts_xnum is not None and self._ts_data is not None:
            nav.set_series(self._ts_xnum, self._ts_data)
        elif getattr(self, "_ts_nav_series", None) is not None:
            # Overlay mode: first selected station's series.
            nav.set_series(*self._ts_nav_series)
        else:
            nav.set_series(None, None)
        x0, x1 = ax.get_xlim()
        if x1 > x0:
            nav.set_window(x0, x1 - x0)
        # set_window is silent; xlim_changed can follow without feedback loop.
        # ax.cla() drops connection on replot, so reconnecting here every time is correct.
        ax.callbacks.connect("xlim_changed", self._on_ts_nav_xlim)

    def _on_ts_nav_xlim(self, ax):
        """Handle plot xlim change: sync Navigator window and width preset combobox.

        Called by ax.callbacks.connect("xlim_changed", ...) whenever toolbar zoom/pan
        changes axes limits. Updates Navigator's visible window and syncs width
        preset combobox to current zoom level (or blanks it for custom ranges).

        Args:
            ax: Matplotlib axes with new xlim.
        """
        nav = getattr(self, "_ts_nav", None)
        if nav is None:
            return
        x0, x1 = ax.get_xlim()
        if x1 > x0:
            nav.set_window(x0, x1 - x0)
            # Toolbar zoom/pan drives xlim directly, never through the width
            # combobox — keep it in sync (blank = custom) so a later var
            # switch on this same selection doesn't read stale "Full" text
            # and re-snap to the global range.
            self._sync_width_var(self._ts_width_var, x1 - x0)

    def _ts_nearest_idx(self, xdata):
        """Find nearest time-series data index for given matplotlib date-num x-position.

        Args:
            xdata (float): x-axis position in matplotlib date-num units (days).

        Returns:
            int or None: Index into self._ts_times, or None if no data loaded.
        """
        if self._ts_xnum is None or xdata is None or not len(self._ts_xnum):
            return None
        pos = np.searchsorted(self._ts_xnum, xdata)
        pos = int(np.clip(pos, 1, len(self._ts_xnum) - 1))
        left, right = pos - 1, pos
        if abs(self._ts_xnum[left] - xdata) <= abs(self._ts_xnum[right] - xdata):
            return left
        return right

    def _ts_update_selection(self):
        """Redraw point-selection marker and annotation for current self._ts_sel_idx.

        Renders circle marker at (time, value) and popup label with timestamp,
        value, and (if wind mode) compass bearing. For NaN values, marker sits
        at top of y-axis with "NaN" label. Clears previous markers/annotations.
        Preserves y-axis limits (avoids auto-expansion on NaN at extreme).
        """
        if self._ts_sel_artist is not None:
            self._ts_sel_artist.remove()
            self._ts_sel_artist = None
        if self._ts_sel_annot is not None:
            self._ts_sel_annot.remove()
            self._ts_sel_annot = None
        if self._ts_sel_idx is None or self._ts_data is None:
            self.canvas_ts.draw_idle()
            return
        idx = self._ts_sel_idx
        x = self._ts_xnum[idx]
        y = self._ts_data[idx]
        ax = self.ax_ts
        orig_ylim = ax.get_ylim()
        if np.isnan(y):
            # NaN: show timestamp at top of view instead of hiding selection.
            y_disp, val_str = orig_ylim[1], "NaN"
        else:
            y_disp, val_str = y, f"{y:.3f}"
        self._ts_sel_artist = ax.scatter(
            [x], [y_disp], s=60, facecolors="none", edgecolors="black", linewidths=1.6, zorder=6
        )
        t = self._ts_times[idx]
        tstr = str(np.datetime_as_string(t, unit="m")).replace("T", " ")
        # Wind mode: append compass direction to label.
        label = f"{self._ts_vname}: {val_str} {self._ts_units}"
        if self._ts_wd is not None and idx < len(self._ts_wd) and not np.isnan(self._ts_wd[idx]):
            label += f" @ {self._ts_wd[idx]:.0f}°"
        self._ts_sel_annot = ax.annotate(
            f"{label}\n{tstr}",
            xy=(x, y_disp),
            xytext=(14, 14),
            textcoords="offset points",
            fontsize=8,
            zorder=7,
            bbox=dict(boxstyle="round", fc="white", ec="black", alpha=0.95),
            arrowprops=dict(arrowstyle="->", color="black"),
        )
        # Markers/annotation don't grow y-range (important for NaN case at old top).
        ax.set_ylim(orig_ylim)
        self.canvas_ts.draw_idle()

    @staticmethod
    def _ts_event_shift(event):
        """Check if Shift key is held during matplotlib event.

        TkAgg backend: event.key unreliable on mouse events. Falls back to
        guiEvent.state bitmask (& 0x0001 = Shift).

        Args:
            event: matplotlib event with .key and optional .guiEvent.

        Returns:
            bool: True if Shift is held.
        """
        # Check if Shift held (TkAgg: event.key unreliable; use guiEvent.state & 0x0001).
        if event.key == "shift":
            return True
        state = getattr(getattr(event, "guiEvent", None), "state", 0)
        return isinstance(state, int) and bool(state & 0x0001)

    def _ts_clear_range_sel(self, redraw=True):
        """Clear Shift-drag range selection and axvspan indicator.

        Args:
            redraw (bool): If True, redraw canvas; if False, caller handles redraw.
        """
        # Drop shift-drag range selection + axvspan indicator.
        if self._ts_range_artist is not None:
            try:
                self._ts_range_artist.remove()
            except (ValueError, AttributeError):
                pass
            self._ts_range_artist = None
        self._ts_range_sel = None
        self._ts_range_anchor = None
        self._ts_range_dragging = False
        if redraw:
            self.canvas_ts.draw_idle()

    def _ts_draw_range_span(self, i0, i1):
        """Draw or redraw range-selection axvspan between two time-series indices.

        Used for live preview during Shift-drag and persistent selection display.
        For single-sample ranges (x0 == x1), pads span by half-median sample
        spacing for visibility. Replaces previous axvspan artist.

        Args:
            i0 (int): Start index (inclusive).
            i1 (int): End index (inclusive); should satisfy i0 <= i1.
        """
        # (Re)draw range-selection axvspan between indices i0<=i1 (live preview + persistent).
        if self._ts_range_artist is not None:
            try:
                self._ts_range_artist.remove()
            except (ValueError, AttributeError):
                pass
            self._ts_range_artist = None
        if self._ts_xnum is None:
            return
        x0, x1 = self._ts_xnum[i0], self._ts_xnum[i1]
        if x0 == x1 and len(self._ts_xnum) > 1:
            # Zero-width span invisible; pad single-sample by half median spacing.
            half = float(np.median(np.diff(self._ts_xnum))) / 2.0
            x0, x1 = x0 - half, x1 + half
        self._ts_range_artist = self.ax_ts.axvspan(
            x0, x1, color=ACCENT, alpha=0.15, linewidth=0, zorder=0.6
        )

    def _on_ts_press(self, event):
        """Handle mouse button press on time series plot: point or range-selection anchor.

        Left-click without Shift: clears range selection and starts point drag.
        Left-click with Shift: clears point selection and anchors range drag.
        Other buttons/axes: no-op.

        Args:
            event: matplotlib MouseEvent with .xdata, .button, .inaxes, .x, .y.
        """
        if event.inaxes != self.ax_ts or event.button != 1:
            return
        idx = self._ts_nearest_idx(event.xdata)
        if idx is None:
            return
        if self._ts_event_shift(event):
            # Shift+drag: range selection. Anchor snaps; motion extends live preview.
            self._ts_shift_press = (idx, event.x, event.y, self._ts_sel_idx, self._ts_range_sel)
            self._ts_clear_range_sel(redraw=False)
            self._ts_range_dragging = True
            self._ts_range_anchor = idx
            self._ts_range_sel = (idx, idx)
            self._ts_draw_range_span(idx, idx)
            self.canvas_ts.draw_idle()
            return
        self._ts_shift_press = None
        # Plain click: clear range selection, then point-selection.
        self._ts_clear_range_sel(redraw=False)
        self._ts_dragging = True
        self._ts_sel_idx = idx
        self._ts_update_selection()

    def _on_ts_motion(self, event):
        """Handle mouse motion on time series plot: live preview during drag.

        In range-drag mode: extends selection endpoints (live axvspan preview).
        In point-drag mode: updates selected point if x-position changed.
        Outside axes or without valid xdata: no-op.

        Args:
            event: matplotlib MouseEvent with .xdata, .inaxes, .x, .y.
        """
        if self._ts_range_dragging:
            if event.inaxes != self.ax_ts or event.xdata is None:
                return
            idx = self._ts_nearest_idx(event.xdata)
            if idx is None:
                return
            rng = (min(self._ts_range_anchor, idx), max(self._ts_range_anchor, idx))
            if rng != self._ts_range_sel:
                self._ts_range_sel = rng
                self._ts_draw_range_span(*rng)
                self.canvas_ts.draw_idle()
            return
        if not self._ts_dragging or event.inaxes != self.ax_ts or event.xdata is None:
            return
        idx = self._ts_nearest_idx(event.xdata)
        if idx is not None and idx != self._ts_sel_idx:
            self._ts_sel_idx = idx
            self._ts_update_selection()

    def _on_ts_release(self, event):
        """Handle mouse button release on time series plot: finalize or cancel drag.

        Distinguishes clicks (<3 px motion) from intentional drags. In range-drag
        with significant motion: stores final range. For small motion: reverts to
        point selection (current or previous). Point-drag always finalizes selection.

        Args:
            event: matplotlib MouseEvent with .xdata, .inaxes, .x, .y.
        """
        # Shift-drag: endpoints snapped during motion; release ends drag.
        press = self._ts_shift_press
        self._ts_shift_press = None
        self._ts_range_dragging = False
        self._ts_dragging = False
        if press is None:
            return
        anchor_idx, press_x, press_y, prev_sel_idx, prev_range_sel = press
        release_idx = self._ts_nearest_idx(event.xdata) if event.inaxes == self.ax_ts else None
        if None in (press_x, press_y, event.x, event.y):
            moved_px = 0.0 if release_idx == anchor_idx else 999.0
        else:
            moved_px = ((event.x - press_x) ** 2 + (event.y - press_y) ** 2) ** 0.5
        if moved_px >= 3 and release_idx is not None and release_idx != anchor_idx:
            return
        click_idx = release_idx if release_idx is not None else anchor_idx
        if prev_sel_idx is not None:
            self._ts_range_sel = tuple(sorted((prev_sel_idx, click_idx)))
            self._ts_draw_range_span(*self._ts_range_sel)
            self.canvas_ts.draw_idle()
        elif prev_range_sel is not None:
            lo, hi = prev_range_sel
            if abs(click_idx - lo) <= abs(click_idx - hi):
                self._ts_range_sel = tuple(sorted((click_idx, hi)))
            else:
                self._ts_range_sel = tuple(sorted((lo, click_idx)))
            self._ts_draw_range_span(*self._ts_range_sel)
            self.canvas_ts.draw_idle()
        else:
            self._ts_clear_range_sel(redraw=False)
            self._ts_sel_idx = click_idx
            self._ts_update_selection()

    def _add_removal(self, stid, var, t0_iso, t1_iso, reason):
        """Append non-destructive removal-record to manifest; deduplicate exact matches.

        Adds entry to self.removal_list[stid]. If currently viewing this station,
        retriggers plot (which re-overlays removal spans). Does nothing if identical
        entry already exists (deduplication).

        Args:
            stid (str): Station ID.
            var (str): Variable name or "*" for all variables at time range.
            t0_iso (str): ISO timestamp string (start of removal range).
            t1_iso (str): ISO timestamp string (end of removal range).
            reason (str): User-provided reason for removal.
        """
        # Append removal-manifest entry (dedups exact duplicates); refresh if showing.
        entry = {"var": var, "t0": str(t0_iso), "t1": str(t1_iso), "reason": reason}
        lst = self.removal_list.setdefault(stid, [])
        if entry in lst:
            return
        lst.append(entry)
        self._refresh_removals()
        if stid == self._current_stid:
            self._plot_timeseries()

    def _draw_removal_overlays(self, ax, match_vars):
        """Draw removal-record axvspans on plot for matching variables.

        Overlays striped semi-transparent spans for each removal-list entry where
        var == "*" (all vars) or var in match_vars. Single-record entries (t0==t1)
        padded by half-median sample spacing for visibility. Used to visualize
        non-destructive removals on active plots.

        Args:
            ax: Matplotlib axes to draw on.
            match_vars (tuple): Variable names to match; var="*" always matches.
        """
        # Overlay removal-manifest ranges where var="*" or in match_vars.
        stid = self._current_stid
        if not stid:
            return
        entries = self.removal_list.get(stid, [])
        if not entries:
            return
        # Single-record entries (t0 == t1): pad to half-median-dt span for visibility.
        if self._ts_xnum is not None and len(self._ts_xnum) > 1:
            half = float(np.median(np.diff(self._ts_xnum))) / 2.0
        else:
            half = 5.0 / 1440.0
        for e in entries:
            if e["var"] != "*" and e["var"] not in match_vars:
                continue
            x0 = mdates.date2num(np.datetime64(e["t0"]))
            x1 = mdates.date2num(np.datetime64(e["t1"]))
            if x1 < x0:
                x0, x1 = x1, x0
            if x0 == x1:
                x0, x1 = x0 - half, x1 + half
            ax.axvspan(x0, x1, color="0.35", alpha=0.22, hatch="///", linewidth=0, zorder=0.5)

    def _ts_remove_records(self):
        """Prompt user to remove selected time-series records (point or range).

        Opens AddRemovalDialog to configure removal scope (current var or all vars)
        and reason. Updates removal_list and redraws plot with removal overlays.
        Validates that a point or Shift-drag range is selected before allowing.
        """
        stid = self._current_stid
        if not stid or self._ts_times is None:
            messagebox.showinfo("Select records", "Select a point or shift-drag a range first")
            return
        if self._ts_range_sel is not None:
            i0, i1 = self._ts_range_sel
        elif self._ts_sel_idx is not None:
            i0 = i1 = self._ts_sel_idx
        else:
            messagebox.showinfo("Select records", "Select a point or shift-drag a range first")
            return
        t0 = np.datetime_as_string(self._ts_times[i0], unit="m")
        t1 = np.datetime_as_string(self._ts_times[i1], unit="m")
        vname = self.var_ts_var.get()
        dlg = AddRemovalDialog(self, stid, vname, t0, t1, i1 - i0 + 1)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        scope, reason = dlg.result
        if scope == "*":
            self._add_removal(stid, "*", t0, t1, reason)
        elif vname == "wind":
            # synthetic wind plot: one entry per underlying sensor variable
            self._add_removal(stid, "wind_speed", t0, t1, reason)
            self._add_removal(stid, "wind_direction", t0, t1, reason)
        else:
            self._add_removal(stid, vname, t0, t1, reason)
        n = i1 - i0 + 1
        self.lbl_status.config(text=f"Marked {n} record{'s' if n != 1 else ''} for removal ({stid})")

    _VAR_SHORT = {
        "wind_direction": "WD",
        "wind_speed": "WS",
        "wind_gust": "WG",
        "air_temperature": "AT",
        "relative_humidity": "RH",
        "solar_radiation": "SR",
        "fuel_moisture_content_10h": "FM10",
    }

    @staticmethod
    def _short_reason(key: str, _msg: str = "") -> str:
        """Compact skip-list label derived from assertion key.

        Maps assertion keys (e.g., "frozen:wind_speed", "hi:temperature")
        to short labels for UI display (e.g., "WS frozen", "AT range").

        Args:
            key (str): Assertion key from QC checker.
            _msg (str): Unused; provided for compatibility with issue tuple protocol.

        Returns:
            str: Abbreviated label (3-20 chars).
        """
        # Compact skip-list label derived from assertion key.
        if key == "dropout":
            return "WD dropout"
        if key == "dup_ts":
            return "Dup timestamps"
        if key == "time_neg":
            return "Timestamp jump"
        if key == "gap_dt":
            return "Big time gap"
        if key == "max_var_outage":
            return "Var outage"
        if key == "full_outage":
            return "Full outage"
        for prefix in ("frozen:", "lo:", "hi:"):
            if key.startswith(prefix):
                vname = key[len(prefix) :]
                short = DetailTabMixin._VAR_SHORT.get(vname, vname)
                label = {"frozen": "frozen", "lo": "range", "hi": "range"}[prefix.rstrip(":")]
                return f"{short} {label}"
        return key

    def _ts_add_skip(self):
        """Add current station to skip list with reason from text entry.

        Validates non-empty reason before adding. Single-station mode only.
        """
        if not self._current_stid:
            return
        reason = self.var_ts_reason.get().strip()
        if not reason:
            messagebox.showinfo("Reason required", "Enter a reason before adding")
            return
        self._add_to_skip(self._current_stid, reason, switch_tab=False)

    def _vs_add_skip(self):
        """Add current station to skip list with reason from Variable Stats row.

        Uses variable short-name (e.g., "AT QC"). Requires row selection.
        Single-station mode only.
        """
        if not self._current_stid:
            return
        sel = self.tv_vs.selection()
        if not sel:
            messagebox.showinfo("Select variable", "Click a variable row first")
            return
        vname = sel[0]
        short = self._VAR_SHORT.get(vname, vname)
        self._prompt_add_skip(self._current_stid, f"{short} QC", switch_tab=False)

    def _assert_add_skip(self):
        """Add current station to skip list with reason from Assertions row.

        Derives compact reason from assertion key (e.g., "WS frozen").
        Requires row selection. Single-station mode only.
        """
        if not self._current_stid:
            return
        sel = self.tv_assert.selection()
        if not sel:
            messagebox.showinfo("Select", "Click an assertion first")
            return
        _, key, msg = self.all_issues[self._current_stid][int(sel[0])]
        self._prompt_add_skip(self._current_stid, self._short_reason(key, msg), switch_tab=False)
