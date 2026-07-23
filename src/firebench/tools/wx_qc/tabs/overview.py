import tkinter as tk
from tkinter import ttk, messagebox

from ..dialogs import AddSkipDialog
from ..theme import ERROR_BG, WARN_BG, OK_BG, PAD


class OverviewTabMixin:
    # eNaN% = effective max NaN% (excludes NaN the outage policy treats as
    # benign, e.g. wind_direction/wind_gust filtered to WS>0 periods).
    # Max Var Outage / Full Outage = outage-aware replacements for raw obs gap,
    # computed by data.compute_outage_stats.
    _OV_BASE_COLS = (
        "STID",
        "Name",
        "State",
        "N pts",
        "Variables",
        "WD NaN%",
        "WD NaN@WS>0",
        "eNaN%",
        "Avg dt",
        "Max Var Outage (min)",
        "Full Outage (min)",
        "Max NaN Streak (hr)",
        "Issues",
    )
    _OV_BASE_WIDTHS = {
        "STID": 75,
        "Name": 170,
        "State": 45,
        "N pts": 60,
        "Variables": 190,
        "WD NaN%": 70,
        "WD NaN@WS>0": 80,
        "eNaN%": 65,
        "Avg dt": 55,
        "Max Var Outage (min)": 120,
        "Full Outage (min)": 105,
        "Max NaN Streak (hr)": 105,
        "Issues": 55,
    }

    def _build_overview_tab(self):
        """Build and configure the Overview tab with Treeview, sorting, and action buttons."""
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Overview")
        self._ov_tab_frame = f
        cols = self._OV_BASE_COLS
        self._all_ov_cols = cols
        self.tv_ov = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c in cols:
            self.tv_ov.heading(c, text=c, command=lambda cc=c: self._sort_overview(cc))
            anchor = "w" if c in ("Name", "Variables") else "center"
            self.tv_ov.column(c, width=self._OV_BASE_WIDTHS.get(c, 65), anchor=anchor)
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tv_ov.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=self.tv_ov.xview)
        self.tv_ov.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tv_ov.pack(fill="both", expand=True)
        self.tv_ov.tag_configure("error", background=ERROR_BG, foreground="black")
        self.tv_ov.tag_configure("warn", background=WARN_BG, foreground="black")
        self.tv_ov.tag_configure("ok", background=OK_BG, foreground="black")
        bf = tk.Frame(f)
        bf.pack(fill="x")
        ttk.Button(bf, text="Go to Detail ->", command=self._ov_to_detail).pack(
            side="left", padx=PAD, pady=PAD
        )
        ttk.Button(bf, text="Add to Skip List", command=self._ov_add_skip).pack(
            side="left", padx=PAD, pady=PAD
        )
        ttk.Button(bf, text="Mark Greenlit", command=self._ov_add_greenlit).pack(
            side="left", padx=PAD, pady=PAD
        )
        # Toggle to show/hide greenlit stations; off by default.
        self._ov_show_greenlit = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bf, text="Show Greenlit", variable=self._ov_show_greenlit, command=self._refresh_overview
        ).pack(side="left", padx=(12, 4))
        self._ov_col_vars = {}
        for c in cols:
            if c == "STID":
                continue
            self._ov_col_vars[c] = tk.BooleanVar(value=True)
        self.tv_ov.bind("<Double-1>", lambda _: self._ov_to_detail())
        self._ov_sort_col = "STID"
        self._ov_sort_rev = False

    def _rebuild_ov_columns(self):
        """Add per-variable stat columns (Max/Min/Avg/Std) after data load.

        Constructs new Treeview columns from all variables found across stations.
        Preserves user's prior column visibility settings across schema changes.
        Defaults to showing Max stat for new variables, hides others.
        """
        all_vars = sorted({v for s in self.stations.values() for v in s["variables"]})
        old_col_vars = dict(self._ov_col_vars)

        new_var_cols = []
        new_var_col_map = {}
        for v in all_vars:
            short = self._VAR_SHORT.get(v, v[:6])
            for stat, key in (
                ("Max", "max"),
                ("Min", "min"),
                ("Avg", "mean"),
                ("Std", "std"),
                ("Outage", "outage_min"),
            ):
                col = f"{short} {stat}"
                new_var_cols.append(col)
                new_var_col_map[col] = (v, key)

        all_cols = self._OV_BASE_COLS + tuple(new_var_cols)
        self._all_ov_cols = all_cols
        self._ov_var_col_map = new_var_col_map

        self.tv_ov["columns"] = all_cols
        for c in all_cols:
            self.tv_ov.heading(c, text=c, command=lambda cc=c: self._sort_overview(cc))
            anchor = "w" if c in ("Name", "Variables") else "center"
            self.tv_ov.column(c, width=self._OV_BASE_WIDTHS.get(c, 65), anchor=anchor)

        # Preserve user's prior visibility settings across column schema changes.
        self._ov_col_vars = {}
        for c in self._OV_BASE_COLS:
            if c == "STID":
                continue
            old = old_col_vars.get(c)
            self._ov_col_vars[c] = tk.BooleanVar(value=old.get() if old is not None else True)

        for vname in all_vars:
            short = self._VAR_SHORT.get(vname, vname[:6])
            for stat in ("Max", "Min", "Avg", "Std", "Outage"):
                col = f"{short} {stat}"
                old = old_col_vars.get(col)
                self._ov_col_vars[col] = tk.BooleanVar(
                    value=old.get() if old is not None else (stat == "Max")
                )

        self._apply_col_visibility()

    def _ov_visible(self, stid):
        """Decide if a station should appear in Overview rows.

        Args:
            stid (str): Station identifier.

        Returns:
            bool: True if station should be displayed, False if skipped or greenlit
                (when show_greenlit is off).
        """
        if stid in self.skip_list:
            return False
        if stid in self.green_list and not self._ov_show_greenlit.get():
            return False
        return True

    def _ov_row(self, stid):
        """Return (tag, values) row for stid, or None if it's excluded.

        Args:
            stid (str): Station identifier.

        Returns:
            tuple or None: (tag_str, values_tuple) where tag_str is "ok"/"warn"/"error"
                for Treeview styling, or None if station is not visible.
        """
        if not self._ov_visible(stid):
            return None
        return self._ov_row_values(stid)

    def _ov_row_values(self, stid):
        """Compute row values; cached to avoid recomputation on membership changes.

        Args:
            stid (str): Station identifier.

        Returns:
            tuple: (tag_str, values_tuple) where tag_str is "ok"/"warn"/"error" based on
                issues present, and values_tuple contains formatted display strings
                (e.g., "12.3%", "45 min", "--") for all columns in _all_ov_cols.
        """
        hidden_a = self.cfg.get("hidden_assertions", set())
        show_errs = self.cfg.get("show_errors", True)
        show_wrns = self.cfg.get("show_warns", True)

        def _issue_visible(sev, key):
            if sev == "ERROR" and not show_errs:
                return False
            if sev == "WARN" and not show_wrns:
                return False
            for prefix in hidden_a:
                if key == prefix or key.startswith(prefix):
                    return False
            return True

        st = self.stations[stid]
        stats = self.all_stats[stid]
        issues = [i for i in self.all_issues[stid] if _issue_visible(*i[:2])]
        var_stats = {k: v for k, v in stats.items() if k != "_time"}

        wd_pct = f"{stats['wind_direction']['nan_pct']:.1f}%" if "wind_direction" in stats else "--"
        wd_nan_ws_pos = (
            f"{stats['wind_direction'].get('wd_nan_ws_pos_pct', 0.0):.1f}%"
            if "wind_direction" in stats
            else "--"
        )
        _ws_gated_field = {"wind_direction": "wd_nan_ws_pos_pct", "wind_gust": "gust_nan_ws_pos_pct"}
        eff_nans = []
        for vname, vs in var_stats.items():
            field = _ws_gated_field.get(vname)
            eff_nans.append(vs[field] if field and field in vs else vs["nan_pct"])
        max_nan_s = f"{max(eff_nans):.0f}%" if eff_nans else "--"
        avg_dt = stats["_time"]["avg_freq_min"]
        avg_dt_s = f"{avg_dt:.0f}" if avg_dt is not None else "--"
        mvo = stats["_time"].get("max_var_outage_min")
        fo = stats["_time"].get("full_outage_min")
        max_var_outage_s = f"{mvo:.0f}" if mvo is not None else "--"
        full_outage_s = f"{fo:.0f}" if fo is not None else "--"
        gap_hrs = [v["longest_gap_hr"] for v in var_stats.values() if v["longest_gap_hr"] is not None]
        max_gap_s = f"{max(gap_hrs):.1f}" if gap_hrs else "--"
        n_err = sum(1 for s, _, _ in issues if s == "ERROR")
        n_warn = sum(1 for s, _, _ in issues if s == "WARN")
        tag = "ok" if not issues else ("error" if n_err else "warn")
        issues_s = f"{n_err}E {n_warn}W" if issues else "--"

        base_lookup = {
            "STID": stid,
            "Name": st["name"],
            "State": st["state"],
            "N pts": stats["_time"]["n_pts"],
            "Variables": " ".join(st["variables"].keys()),
            "WD NaN%": wd_pct,
            "WD NaN@WS>0": wd_nan_ws_pos,
            "eNaN%": max_nan_s,
            "Avg dt": avg_dt_s,
            "Max Var Outage (min)": max_var_outage_s,
            "Full Outage (min)": full_outage_s,
            "Max NaN Streak (hr)": max_gap_s,
            "Issues": issues_s,
        }
        vals = []
        for c in self._all_ov_cols:
            if c in base_lookup:
                vals.append(base_lookup[c])
            elif c in self._ov_var_col_map:
                vname, key = self._ov_var_col_map[c]
                vst = stats.get(vname)
                if vst is None:
                    vals.append("--")
                else:
                    val = vst.get(key)
                    if val is None:
                        vals.append("--")
                    elif key == "std":
                        vals.append(f"{val:.2f}")
                    else:
                        vals.append(f"{val:.1f}")
            else:
                vals.append("--")
        row = (tag, tuple(vals))
        self._ov_row_cache[stid] = row
        return row

    def _refresh_overview(self, dirty=None):
        """Full rebuild if dirty=None; incremental update on dirty stids.

        Args:
            dirty (set or None): Set of stid strings to update. If None, perform
                complete rebuild of the entire Treeview.
        """
        if not self._all_ov_cols:
            return
        if dirty is not None:
            self._refresh_overview_dirty(dirty)
            return
        self._ov_row_cache = {}
        self.tv_ov.delete(*self.tv_ov.get_children())
        self._ov_rendered = set()
        for stid in self.stids:
            row = self._ov_row(stid)
            self._ov_rendered.add(stid)
            if row is None:
                continue
            tag, vals = row
            self.tv_ov.insert("", "end", iid=stid, tags=(tag,), values=vals)
        self._nudge_ov_repaint()

    def _refresh_overview_dirty(self, dirty):
        """Update only dirty stids; delete if hidden, insert if visible, else update in place.

        Args:
            dirty (set): Set of stid strings needing update/refresh.
        """
        for stid in dirty:
            present = self.tv_ov.exists(stid)
            if stid not in self.stations:
                if present:
                    self.tv_ov.delete(stid)
                self._ov_row_cache.pop(stid, None)
                self._ov_rendered.discard(stid)
                continue
            self._ov_rendered.add(stid)
            if not self._ov_visible(stid):
                if present:
                    self.tv_ov.delete(stid)
                continue
            row = self._ov_row_cache.get(stid)
            if row is None:
                row = self._ov_row_values(stid)
            tag, vals = row
            if present:
                self.tv_ov.item(stid, tags=(tag,), values=vals)
            else:
                self.tv_ov.insert("", self._ov_sorted_index(vals), iid=stid, tags=(tag,), values=vals)
        self._nudge_ov_repaint()

    def _ov_sorted_index(self, vals):
        """Find insertion index that respects current sort order.

        Args:
            vals (tuple): Row values tuple from _ov_row_values; indexed by column position.

        Returns:
            str: Treeview insertion index (integer as string or "end") respecting
                current _ov_sort_col and _ov_sort_rev settings.
        """
        col = self._ov_sort_col
        try:
            ci = self._all_ov_cols.index(col)
        except ValueError:
            return "end"
        new_raw = str(vals[ci])
        children = self.tv_ov.get_children()
        if not children:
            return "end"

        def _num(s):
            s = s.replace("%", "").strip()
            return float("-inf") if s == "--" else float(s)

        try:
            new_key = _num(new_raw)
            keys = [_num(self.tv_ov.set(iid, col)) for iid in children]
        except ValueError:
            new_key = new_raw
            keys = [self.tv_ov.set(iid, col) for iid in children]
        if self._ov_sort_rev:
            for i, k in enumerate(keys):
                if k < new_key:
                    return i
        else:
            for i, k in enumerate(keys):
                if k > new_key:
                    return i
        return "end"

    def _ov_tab_active(self):
        """Check if Overview tab is currently selected in the notebook.

        Returns:
            bool: True if Overview tab is active, False otherwise.
        """
        try:
            return self.nb.select() == str(self._ov_tab_frame)
        except (AttributeError, tk.TclError):
            return False

    def _nudge_ov_repaint(self, event=None):
        """Work around macOS ttk.Treeview: tag colors don't render until focus.

        Use focus_force() (not focus_set()) to grab immediately, deferred by
        one idle tick to ensure widget is mapped.

        Args:
            event (tk.Event or None): Event that triggered the repaint (unused).
        """
        if not self._ov_tab_active():
            return

        def _do_nudge():
            if not self._ov_tab_active():
                return
            self.tv_ov.tag_configure("error", background=ERROR_BG, foreground="black")
            self.tv_ov.tag_configure("warn", background=WARN_BG, foreground="black")
            self.tv_ov.tag_configure("ok", background=OK_BG, foreground="black")
            self.tv_ov.focus_force()
            self.tv_ov.update()

        self.after_idle(_do_nudge)

    def _refresh_overview_append(self, new_stids):
        """Append new stations without disrupting user's scroll during progressive load.

        Args:
            new_stids (iterable): Station identifiers to append to Treeview.
        """
        if not self._all_ov_cols:
            return
        for stid in new_stids:
            if stid in self._ov_rendered:
                continue
            row = self._ov_row(stid)
            self._ov_rendered.add(stid)
            if row is None:
                continue
            tag, vals = row
            self.tv_ov.insert("", "end", iid=stid, tags=(tag,), values=vals)
        self._nudge_ov_repaint()

    def _ov_to_detail(self):
        """Switch to Detail tab and select stations chosen in Overview.

        Switches notebook selection to Detail tab (index 1) and syncs the
        Detail view to match Overview selection (single or multi-select).
        """
        sel = self.tv_ov.selection()
        if not sel:
            return
        self.nb.select(1)
        if len(sel) == 1:
            self.detail_panes.select_only(sel[0])
        else:
            self.detail_panes.select_many(sel)
        self._refresh_detail_view()

    def _ov_add_skip(self):
        """Add selected stations to skip list via dialog prompt.

        Single-select prompts with pre-filled issue summaries; multi-select
        shows reason input dialog. Updates Overview, station list, and skip list UI.
        """
        sel = self.tv_ov.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first")
            return
        if len(sel) == 1:
            stid = sel[0]
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

    def _ov_add_greenlit(self):
        """Mark selected stations as greenlit (approved QC).

        Adds stations to green_list and refreshes Overview/station list display.
        Updates status bar with count of marked stations.
        """
        sel = self.tv_ov.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first")
            return
        for stid in sel:
            self.green_list.add(stid)
        self._refresh_overview(dirty=set(sel))
        self._refresh_station_list()
        n = len(sel)
        self.lbl_status.config(text=f"Greenlit {n} station{'s' if n != 1 else ''}")

    def _sort_overview(self, col):
        """Sort Treeview rows by column; toggle reverse on same-column re-click.

        Parses numeric values (ignores '%', treats '--' as -inf); falls back to
        string comparison if any value is non-numeric. Reorders rows in-place
        via Treeview.move().

        Args:
            col (str): Column name to sort by.
        """
        self._ov_sort_rev = (not self._ov_sort_rev) if col == self._ov_sort_col else False
        self._ov_sort_col = col
        raw = [(self.tv_ov.set(iid, col), iid) for iid in self.tv_ov.get_children()]

        # Parse numeric keys once and cache alongside iid; fall back to string sort if any value isn't numeric.
        numeric_items = []
        for val, iid in raw:
            s = val.replace("%", "").strip()
            if s == "--":
                numeric_items.append((float("-inf"), iid))
                continue
            try:
                numeric_items.append((float(s), iid))
            except ValueError:
                numeric_items = None
                break

        if numeric_items is not None:
            numeric_items.sort(key=lambda x: x[0], reverse=self._ov_sort_rev)
            items = numeric_items
        else:
            items = sorted(raw, key=lambda x: x[0], reverse=self._ov_sort_rev)

        for i, (_, iid) in enumerate(items):
            self.tv_ov.move(iid, "", i)

    def _apply_col_visibility(self):
        """Update Treeview displaycolumns based on _ov_col_vars BooleanVar states.

        Always ensures STID column is visible as fallback if no columns selected.
        """
        vis = [
            c
            for c in self._all_ov_cols
            if c == "STID" or self._ov_col_vars.get(c) is None or self._ov_col_vars[c].get()
        ]
        self.tv_ov["displaycolumns"] = vis if vis else ("STID",)
