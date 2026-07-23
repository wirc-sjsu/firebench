import time
from pathlib import Path
from tkinter import filedialog, messagebox
import numpy as np
import h5py

from .data import (
    iter_h5_stations,
    compute_stats,
    run_assertions,
    _var_stat_block,
    compute_outage_stats,
    run_outage_assertions,
    _ws_gated_nan_pct,
    _deltas_minutes,
)


class LoaderMixin:
    """Load station data and populate App-owned data/QC collections incrementally.

    App state:
        Expects ``h5_path``, ``cfg``, station/statistics/issues collections,
        Overview/map render caches, loading widgets, Tk scheduling methods, and
        the refresh helpers supplied by the tab mixins.
    """

    def _open_file(self):
        """Open a file dialog to select an H5 file and load its data.

        Prompts user to choose an HDF5 file, sets self.h5_path, updates UI labels,
        and calls _load_data() to begin loading. If user cancels the dialog, does nothing.
        """
        path = filedialog.askopenfilename(
            title="Open firebench H5",
            filetypes=[("HDF5 files", "*.h5 *.hdf5"), ("All files", "*.*")],
            initialdir=str(self.h5_path.parent) if self.h5_path else ".",
        )
        if not path:
            return
        self.h5_path = Path(path)
        self.lbl_file.config(text=str(self.h5_path))
        self.lbl_status.config(text="Loading...")
        self.update()
        self._load_data()

    def _stats_for_station(self, stid, st, cached_stats):
        """Compute or reuse cached stats for a station, merging any new variables.

        If cached stats exist for this station, reuses them and computes stats only
        for newly-added variables. If wind_speed changed or wind_direction/wind_gust
        are new, recomputes their gated NaN percentages. If no cache, computes all stats.

        Args:
            stid (str): Station ID.
            st (dict): Station dict (keys: stid, name, lat, lon, alt, state, timezone,
                provider, times, rel_min, variables, var_units).
            cached_stats (dict or None): Dict mapping stid to stats dict, or None.

        Returns:
            tuple: (stats_dict, was_fresh) where stats_dict is the stats dict for the
                station and was_fresh (bool) is True if any new stats were computed.
        """
        cached = cached_stats.get(stid) if cached_stats else None
        if cached is None or "time_axis_valid" not in cached.get("_time", {}):
            return compute_stats(st), True
        new_vars = [v for v in st["variables"] if v not in cached]
        if not new_vars:
            return cached, False
        avg_freq = cached["_time"]["avg_freq_min"]
        deltas = (
            _deltas_minutes(st["times"])
            if cached["_time"].get("time_axis_valid") and len(st["times"]) > 1
            else None
        )
        merged = dict(cached)
        for v in new_vars:
            merged[v] = _var_stat_block(st["variables"][v], avg_freq, deltas)
        # recompute cross-var derived stat if wind vars changed
        vd = st["variables"]
        ws = vd.get("wind_speed")
        if ws is not None:
            for gated_var, field in (
                ("wind_direction", "wd_nan_ws_pos_pct"),
                ("wind_gust", "gust_nan_ws_pos_pct"),
            ):
                if gated_var in vd and (gated_var in new_vars or "wind_speed" in new_vars):
                    merged[gated_var][field] = _ws_gated_nan_pct(vd[gated_var], ws)
        return merged, True

    def _compute_global_time_extent(self):
        """Compute global time extent across all stations and derive outage stats.

        Finds the earliest first timestamp (gmin) and latest last timestamp
        (gmax) across stations with valid, ordered time axes. For each station,
        passes separate leading/trailing gaps and the global duration to
        compute_outage_stats(), then appends threshold warnings.
        """
        firsts, lasts = [], []
        for stid, st in self.stations.items():
            t = st["times"]
            time_valid = self.all_stats[stid]["_time"].get("time_axis_valid")
            if (
                time_valid
                and isinstance(t, np.ndarray)
                and len(t)
                and np.issubdtype(t.dtype, np.datetime64)
            ):
                firsts.append(t[0])
                lasts.append(t[-1])
        if not firsts:
            self._time_extent_global = None
            for stid, st in self.stations.items():
                stats = self.all_stats[stid]
                compute_outage_stats(st, stats)
                self.all_issues[stid] = self.all_issues.get(stid, []) + run_outage_assertions(
                    stats, self.cfg
                )
            return
        gmin = min(firsts)
        gmax = max(lasts)
        self._time_extent_global = (gmin, gmax)
        one_min = np.timedelta64(1, "m")
        global_duration = float((gmax - gmin) / one_min)
        for stid, st in self.stations.items():
            stats = self.all_stats[stid]
            t = st["times"]
            if (
                stats["_time"].get("time_axis_valid")
                and isinstance(t, np.ndarray)
                and len(t)
                and np.issubdtype(t.dtype, np.datetime64)
            ):
                head = float((t[0] - gmin) / one_min)
                tail = float((gmax - t[-1]) / one_min)
            else:
                head = 0.0
                tail = 0.0
            compute_outage_stats(
                st,
                stats,
                leading_gap_min=head,
                trailing_gap_min=tail,
                global_duration_min=global_duration,
            )
            self.all_issues[stid] = self.all_issues.get(stid, []) + run_outage_assertions(stats, self.cfg)

    def _load_data(self, cached_stats=None, on_complete=None):
        """Start an incremental, non-blocking load of stations from the H5 file.

        Stations stream in via _load_chunk() on self.after() ticks so the UI stays
        responsive. Overview and map refresh after each chunk with pending new
        stations. Global time extent and outage stats are computed only when load
        finishes. Optional cached statistics remain an internal loading
        optimization; persisted sessions never supply them.

        Args:
            cached_stats (dict, optional): Dict mapping stid to precomputed
                statistics for an internal caller. JSON session restoration
                always leaves this as None. Defaults to None.
            on_complete (callable, optional): Callback with no arguments, invoked
                after all stations are loaded and UI is fully refreshed. Defaults to None.
        """
        self._load_gen_id = getattr(self, "_load_gen_id", 0) + 1
        gen_id = self._load_gen_id
        self.stations = {}
        self.all_stats = {}
        self.all_issues = {}
        self.stids = []
        self._time_extent_global = None  # (gmin, gmax) once the load finishes
        self._load_iter = iter_h5_stations(self.h5_path)
        self._load_cached = cached_stats
        self._load_on_complete = on_complete
        self._load_n_fresh = 0
        self._load_n_total = 0
        self._load_last_ui_t = 0.0
        self._load_pending_new = []
        self._load_error = None
        self._map_sc = None  # force a full (re)creation on first tick of this load
        self._map_offsets = None
        self._map_cvals_arr = None
        self._map_plotted = set()
        self._map_lonlat = None
        self._map_tile_pending_extent = None
        self._map_tile_view_extent = None
        self._map_tile_cached_result = None
        self._ov_rendered = set()
        # Upfront group-name scan (no dataset reads) so progress bar has
        # real denominator instead of undefined count.
        try:
            with h5py.File(self.h5_path, "r") as f:
                ts_grp = f.get("time_series")
                self._load_total = len(ts_grp) if ts_grp is not None else 0
        except (OSError, ValueError) as exc:
            self._load_iter = None
            self.lbl_status.config(text=f"H5 load failed: {exc}")
            messagebox.showerror(
                "H5 load failed",
                f"Could not inspect {self.h5_path} as a FireBench HDF5 file:\n\n{exc}",
            )
            return
        self.pb_load["maximum"] = max(self._load_total, 1)
        self.pb_load["value"] = 0
        self.pb_load.pack(side="right", padx=(0, 4))
        self.after(1, lambda: self._load_chunk(gen_id))

    def _load_chunk(self, gen_id, time_budget=0.05, ui_refresh_interval=1.0, min_first_refresh=25):
        """Load a time-budgeted chunk of stations and selectively refresh UI.

        Pulls stations from self._load_iter until time_budget expires, computes stats
        and assertions for each via _stats_for_station(), and accumulates them in
        self.stations/all_stats/all_issues. UI refreshes throttled to ~1 per sec
        (append-only until done). On completion, computes global time extent, does
        final full refresh, and invokes on_complete callback. Reschedules via
        self.after(1) if more stations remain.

        Args:
            gen_id (int): Generation ID to detect if this load was superseded by
                a newer one (user opened a different file/session mid-load).
            time_budget (float): Seconds allowed per chunk (default 0.05).
            ui_refresh_interval (float): Minimum seconds between UI refreshes
                (default 1.0).
            min_first_refresh (int): Do not refresh UI until at least this many
                stations loaded (default 25).
        """
        if gen_id != self._load_gen_id:
            return  # superseded by a newer load (new file/session opened mid-load)
        deadline = time.perf_counter() + time_budget
        done = False
        while time.perf_counter() < deadline:
            try:
                stid, st = next(self._load_iter)
            except StopIteration:
                done = True
                break
            except (OSError, KeyError, TypeError, ValueError) as exc:
                self._load_error = exc
                done = True
                break
            stats, fresh = self._stats_for_station(stid, st, self._load_cached)
            self.stations[stid] = st
            self.all_stats[stid] = stats
            self.all_issues[stid] = run_assertions(st, stats, self.cfg)
            self._load_n_total += 1
            self._load_n_fresh += 1 if fresh else 0
            self._load_pending_new.append(stid)
        self.stids = sorted(self.stations.keys())
        self.pb_load["value"] = self._load_n_total
        if self._load_total:
            pct = 100 * self._load_n_total // self._load_total
            self.lbl_status.config(text=f"Loaded {self._load_n_total}/{self._load_total} stations ({pct}%)")
        else:
            self.lbl_status.config(text=f"Loaded {self._load_n_total} stations")
        # Full rebuild on every chunk was 2x+ slower; instead throttle to
        # ~1 refresh/sec with append-only updates (no teardown). Prevents
        # disruption to scrolling and avoids lonely single-row flashes.
        # Always do full rebuild at end for correct sort order.
        now = time.perf_counter()
        ready = done or (
            self._load_n_total >= min_first_refresh and (now - self._load_last_ui_t) >= ui_refresh_interval
        )
        if done:
            # Global extent and separate edge gaps must exist before final refresh
            # (_refresh_all reads both from Overview and detail nav).
            self._compute_global_time_extent()
        if ready:
            if done:
                self._refresh_all()
            else:
                self._refresh_overview_append(self._load_pending_new)
                self._refresh_map_append(self._load_pending_new)
                self._refresh_station_list()
                self._refresh_skiplist()
            self._load_pending_new = []
            self._load_last_ui_t = now
        if done:
            self.pb_load.pack_forget()
            cached_ct = self._load_n_total - self._load_n_fresh
            if self._load_error is not None:
                self.lbl_status.config(text=f"H5 load stopped after {self._load_n_total} stations")
                messagebox.showerror(
                    "H5 load failed",
                    f"Could not finish reading {self.h5_path} after "
                    f"{self._load_n_total} station(s):\n\n{self._load_error}",
                )
            else:
                self.lbl_status.config(
                    text=(
                        f"Loaded {self._load_n_total} stations "
                        f"({cached_ct} cached, {self._load_n_fresh} new)"
                        if self._load_cached
                        else f"Loaded {self._load_n_total} stations"
                    )
                )
            on_complete = self._load_on_complete
            self._load_iter = None
            if on_complete is not None and self._load_error is None:
                on_complete()
        else:
            self.after(1, lambda: self._load_chunk(gen_id))
