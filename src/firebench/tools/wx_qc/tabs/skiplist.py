import copy
import pickle
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import h5py
import hdf5plugin  # noqa: F401  (registers HDF5 compression filters on import)

from ..dialogs import AddSkipDialog, ExportScriptDialog
from ..theme import PAD


def _format_skip_stations_block(skip_list: dict) -> str:
    """Render skip_list as a Python source literal for export.

    Used by both _skip_export_write and build_processing_script_text.

    Args:
        skip_list (dict[str, str]): station ID -> skip reason.

    Returns:
        str: multi-line ``skip_stations = [...]`` Python source, one
            station ID per line with its reason as a trailing comment.
    """
    lines = ["skip_stations = ["]
    for stid, reason in sorted(skip_list.items()):
        lines.append(f'    "{stid}",  # {reason.replace(chr(34), chr(39))}')
    lines.append("]")
    return "\n".join(lines)


def _format_remove_records_block(removal_list: dict) -> str:
    """Render removal_list as a Python source literal for export.

    Used by both _skip_export_write and build_processing_script_text.

    Args:
        removal_list (dict[str, list[dict]]): station ID -> list of
            removal entries, each a dict with keys "var" (variable name
            or "*" for all variables), "t0"/"t1" (ISO timestamp strings,
            inclusive range), and "reason" (str).

    Returns:
        str: multi-line ``remove_records = {...}`` Python source, one
            ``(var, t0, t1, reason)`` tuple per removal entry.
    """
    lines = ["remove_records = {"]
    for stid in sorted(removal_list):
        entries = removal_list[stid]
        if not entries:
            continue
        lines.append(f'    "{stid}": [')
        for e in sorted(entries, key=lambda e: (e["var"], e["t0"], e["t1"])):
            reason = e["reason"].replace(chr(34), chr(39))
            lines.append(f'        ("{e["var"]}", "{e["t0"]}", "{e["t1"]}", "{reason}"),')
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines)


def build_processing_script_text(skip_list: dict, removal_list: dict, fields: dict) -> str:
    """Build a complete processing script with the given configuration.

    Args:
        skip_list: dict[str, str] (stid -> reason)
        removal_list: dict[str, list[dict]] (stid -> list of removal entries)
        fields: dict with keys: fire_name, json_filename, output_h5_filename, description,
                contributors, compression_lvl (int), logging_lvl (int), dest_dir, script_filename

    Returns:
        Full script text as a string.
    """
    skip_block = _format_skip_stations_block(skip_list)
    remove_block = _format_remove_records_block(removal_list)

    script = f'''import firebench.standardize as fs
from pathlib import Path
import firebench.tools as ft
import json
import tempfile
import pytz
import numpy as np
from datetime import datetime, timezone

def _dedup_obs(obs: dict) -> None:
    """Drop rows where timestamp AND all variable values are identical to a prior row.
    Rows with the same timestamp but different data are kept (genuine conflict)."""
    times = obs.get("date_time", [])
    if not times:
        return
    var_keys = [k for k, v in obs.items()
                if k != "date_time" and isinstance(v, list) and len(v) == len(times)]
    seen: dict = {{}}  # ts -> first index
    drop: set = set()
    for i, t in enumerate(times):
        if t not in seen:
            seen[t] = i
        else:
            first = seen[t]
            if all(obs[k][first] == obs[k][i] for k in var_keys):
                drop.add(i)
    if not drop:
        return
    keep = [i for i in range(len(times)) if i not in drop]
    obs["date_time"] = [times[i] for i in keep]
    for k in var_keys:
        obs[k] = [obs[k][i] for i in keep]


def preprocess_timestamps(json_path: Path) -> Path:
    """Normalise timestamps to UTC naive format expected by firebench.
    UTC avoids DST fall-back ambiguity where two distinct UTC instants
    map to the same local naive string."""
    with open(json_path, "r") as f:
        data = json.load(f)
    for station in data["STATION"]:
        station["TIMEZONE"] = "UTC"  # timestamps stored as UTC; tell firebench
        obs = station.get("OBSERVATIONS", {{}})
        if "date_time" in obs:
            converted = []
            for t in obs["date_time"]:
                if "T" in t:
                    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    converted.append(dt.strftime("%Y%m%d%H%M%S"))
                else:
                    converted.append(t)
            obs["date_time"] = converted
        _dedup_obs(obs)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


def apply_record_removals(h5file, remove_records: dict) -> None:
    """NaN out per-station/variable time ranges flagged in the wx_qc GUI's
    skip-list export (`remove_records`: {{stid: [(var_or_*, t0_iso, t1_iso,
    reason), ...]}}). Runs directly against the just-built standardized H5,
    after `standardize_synoptic_raws_from_json` has created the station
    groups (time_series/station_<stid>/{{time, <var>...}})."""
    ts_grp = h5file.get("time_series")
    if ts_grp is None:
        return
    for stid, entries in remove_records.items():
        if not entries:
            continue
        grp = ts_grp.get(f"station_{{stid}}")
        if grp is None or "time" not in grp:
            continue
        t0_str  = grp["time"].attrs.get("time_origin", "")
        rel_min = grp["time"][:]
        try:
            t0 = datetime.fromisoformat(t0_str)
            if np.isnan(rel_min).any():
                raise ValueError("NaN in time dataset")
            if t0.tzinfo is not None:
                t0 = t0.astimezone(timezone.utc).replace(tzinfo=None)
            us = np.rint(rel_min.astype(np.float64) * 60_000_000.0).astype(np.int64)
            times = np.datetime64(t0, "us") + us.astype("timedelta64[us]")
        except Exception:
            continue  # can't parse a time axis -> can't build a mask

        for var, t0_iso, t1_iso, reason in entries:
            try:
                t0m, t1m = np.datetime64(t0_iso), np.datetime64(t1_iso)
            except Exception:
                continue
            if t1m < t0m:
                t0m, t1m = t1m, t0m
            mask = (times >= t0m) & (times <= t1m)
            if not mask.any():
                continue
            if var == "*":
                targets = [ds for ds in grp if ds != "time"]
            else:
                targets = [var] if var in grp else []
            for vname in targets:
                ds = grp[vname]
                if not np.issubdtype(ds.dtype, np.floating):
                    continue  # non-float dataset: NaN isn't representable, skip
                arr = ds[:]
                arr[mask] = np.nan
                ds[...] = arr


data_source_path = Path("{fields["json_filename"]}")
output_file = "{fields["output_h5_filename"]}"
compression_lvl = {fields["compression_lvl"]}  # 1 = no compression, 22 = max compression
logging_lvl = {fields["logging_lvl"]}  # 0 NOTSET, 10 DEBUG, 20 INFO, 30 WARNING, 40 ERROR, 50 CRITICAL
{skip_block}

# Per-station/variable time ranges to NaN out (not whole-station skips).
# Paste the `remove_records` dict from a wx_qc GUI skip-list export here —
# same shape: {{stid: [(var_or_"*", t0_iso, t1_iso, reason), ...]}}.
{remove_block}

ft.set_logging_level(logging_lvl)
data_source_path = preprocess_timestamps(data_source_path)

h5 = fs.new_std_file(
    output_file,
    "{fields["contributors"]}",
    overwrite=True,
)

h5.attrs["description"] = (
    "{fields["description"]}"
)

# See firebench.standardize for the full list of variables this converts.
fs.standardize_synoptic_raws_from_json(
    data_source_path, h5, skip_stations=skip_stations, overwrite=True, compression_lvl=compression_lvl, export_trusted_history=True
)

apply_record_removals(h5, remove_records)

h5.close()
'''
    return script


class SkiplistTabMixin:
    """Skip List tab: manual station skip/greenlit list plus the
    record-removal manifest, and the export actions (skip-list script,
    processing script, cleaned H5) that consume both."""

    def _build_skiplist_tab(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="Skip List")
        cols = ("STID", "Reason")
        self.tv_skip = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        self.tv_skip.heading("STID",   text="STID")
        self.tv_skip.heading("Reason", text="Reason")
        self.tv_skip.column("STID",   width=110, anchor="w")
        self.tv_skip.column("Reason", width=700, anchor="w")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tv_skip.yview)
        self.tv_skip.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tv_skip.pack(fill="both", expand=True)
        self.tv_skip.bind("<Double-1>", lambda _: self._skip_goto_detail())

        bf = ttk.Frame(f)
        bf.pack(fill="x", padx=4, pady=6)
        ttk.Label(bf, text="STID:").pack(side="left")
        self.var_skip_stid   = tk.StringVar()
        self.var_skip_reason = tk.StringVar()
        ttk.Entry(bf, textvariable=self.var_skip_stid,   width=10).pack(side="left", padx=2)
        ttk.Label(bf, text="Reason:").pack(side="left", padx=(6, 1))
        ttk.Entry(bf, textvariable=self.var_skip_reason, width=44).pack(side="left", padx=2)
        ttk.Button(bf, text="Add",         command=self._skip_manual_add).pack(side="left", padx=PAD)
        ttk.Button(bf, text="Remove",      command=self._skip_remove).pack(side="left", padx=PAD)
        ttk.Button(bf, text="Edit Reason", command=self._skip_edit_reason).pack(side="left", padx=PAD)
        ttk.Button(bf, text="Go to Detail ->", command=self._skip_goto_detail).pack(side="left", padx=PAD)
        ttk.Button(bf, text="Export Script...", command=self._export_script).pack(side="right", padx=PAD)
        ttk.Button(bf, text="Export Python...", command=self._skip_export).pack(side="right", padx=PAD)

        self.lbl_skip_count = ttk.Label(f, text="", anchor="w", style="Muted.TLabel")
        self.lbl_skip_count.pack(anchor="w", padx=4, pady=(0, 4))

        ttk.Label(f, text="Record removals", style="Section.TLabel").pack(
            anchor="w", padx=4, pady=(8, 2))
        rcols = ("STID", "Variable", "From", "To", "Reason")
        self.tv_removals = ttk.Treeview(f, columns=rcols, show="headings",
                                         selectmode="browse", height=7)
        widths = (90, 130, 140, 140, 400)
        for c, w in zip(rcols, widths):
            self.tv_removals.heading(c, text=c)
            self.tv_removals.column(c, width=w, anchor="w")
        rvsb = ttk.Scrollbar(f, orient="vertical", command=self.tv_removals.yview)
        self.tv_removals.configure(yscrollcommand=rvsb.set)
        rvsb.pack(side="right", fill="y")
        self.tv_removals.pack(fill="both", expand=True)
        self.tv_removals.bind("<Double-1>", lambda _: self._removal_goto_detail())

        rbf = ttk.Frame(f); rbf.pack(fill="x", padx=4, pady=6)
        ttk.Button(rbf, text="Remove Entry",     command=self._removal_remove_entry).pack(side="left", padx=PAD)
        ttk.Button(rbf, text="Edit Reason",      command=self._removal_edit_reason).pack(side="left", padx=PAD)
        ttk.Button(rbf, text="Go to Detail ->",  command=self._removal_goto_detail).pack(side="left", padx=PAD)
        ttk.Button(rbf, text="Export cleaned H5...", command=self._export_cleaned_h5).pack(side="right", padx=PAD)

        self.lbl_removal_count = ttk.Label(f, text="", anchor="w", style="Muted.TLabel")
        self.lbl_removal_count.pack(anchor="w", padx=4, pady=(0, 4))

    def _refresh_skiplist(self):
        """Repopulate the skip-list treeview and count label from self.skip_list."""
        self.tv_skip.delete(*self.tv_skip.get_children())
        for stid, reason in sorted(self.skip_list.items()):
            self.tv_skip.insert("", "end", iid=stid, values=(stid, reason))
        n = len(self.skip_list)
        self.lbl_skip_count.config(text=f"{n} station{'s' if n != 1 else ''} in skip list")
        self._refresh_removals()

    @staticmethod
    def _removal_iid(stid, idx):
        """Build the tv_removals row iid for one removal entry.

        Args:
            stid (str): station identifier.
            idx (int): index into self.removal_list[stid].

        Returns:
            str: "{stid}::{idx}".
        """
        return f"{stid}::{idx}"

    @staticmethod
    def _removal_iid_parts(iid):
        """Inverse of _removal_iid.

        Args:
            iid (str): a tv_removals row iid ("{stid}::{idx}").

        Returns:
            tuple[str, int]: (stid, idx).
        """
        stid, idx = iid.rsplit("::", 1)
        return stid, int(idx)

    def _refresh_removals(self):
        """Repopulate the removal-manifest treeview and count label from self.removal_list."""
        self.tv_removals.delete(*self.tv_removals.get_children())
        n_entries = 0
        for stid in sorted(self.removal_list):
            entries = self.removal_list[stid]
            for i, e in enumerate(entries):
                self.tv_removals.insert("", "end", iid=self._removal_iid(stid, i),
                    values=(stid, e["var"], e["t0"], e["t1"], e["reason"]))
                n_entries += 1
        n_stations = sum(1 for v in self.removal_list.values() if v)
        self.lbl_removal_count.config(
            text=f"{n_entries} removal entr{'y' if n_entries == 1 else 'ies'} "
                 f"across {n_stations} station{'s' if n_stations != 1 else ''}")

    def _removal_goto_detail(self):
        sel = self.tv_removals.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first"); return
        stid, idx = self._removal_iid_parts(sel[0])
        if stid not in self.stations:
            messagebox.showwarning("Not loaded", f"{stid} not in current H5"); return
        entries = self.removal_list.get(stid, [])
        entry = entries[idx] if idx < len(entries) else None
        self._navigate_to_station(stid)
        if entry is not None and entry["var"] != "*" and entry["var"] in getattr(self, "_ts_avail_vars", []):
            self.var_ts_var.set(entry["var"])
            self._plot_timeseries()

    def _removal_remove_entry(self):
        sel = self.tv_removals.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first"); return
        stid, idx = self._removal_iid_parts(sel[0])
        lst = self.removal_list.get(stid, [])
        if idx >= len(lst):
            return
        if not messagebox.askyesno("Remove", f"Remove this removal entry for {stid}?"):
            return
        del lst[idx]
        if not lst:
            self.removal_list.pop(stid, None)
        self._refresh_removals()
        if stid == self._current_stid:
            self._plot_timeseries()

    def _removal_edit_reason(self):
        sel = self.tv_removals.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first"); return
        stid, idx = self._removal_iid_parts(sel[0])
        lst = self.removal_list.get(stid, [])
        if idx >= len(lst):
            return
        entry = lst[idx]
        dlg = AddSkipDialog(self, None, entry["reason"],
                             label=f"{stid}  {entry['var']}  {entry['t0']} -> {entry['t1']}")
        self.wait_window(dlg)
        if dlg.result is not None:
            entry["reason"] = dlg.result
            self._refresh_removals()

    def _skip_manual_add(self):
        stid   = self.var_skip_stid.get().strip().upper()
        reason = self.var_skip_reason.get().strip()
        if not stid:
            messagebox.showinfo("STID required", "Enter a station ID"); return
        self._add_to_skip(stid, reason or "manually added")
        self.var_skip_stid.set(""); self.var_skip_reason.set("")

    def _skip_remove(self):
        sel = self.tv_skip.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first"); return
        stid = sel[0]
        if messagebox.askyesno("Remove", f"Remove {stid} from skip list?"):
            del self.skip_list[stid]
            self._refresh_skiplist()
            self._refresh_overview(dirty={stid})
            self._refresh_station_list()

    def _skip_goto_detail(self):
        sel = self.tv_skip.selection()
        if not sel:
            messagebox.showinfo("Select", "Click a row first"); return
        stid = sel[0]
        if stid not in self.stations:
            messagebox.showwarning("Not loaded", f"{stid} not in current H5"); return
        self._navigate_to_station(stid)

    def _skip_edit_reason(self, event=None):
        sel = self.tv_skip.selection()
        if not sel:
            return
        stid = sel[0]
        dlg = AddSkipDialog(self, stid, self.skip_list.get(stid, ""))
        self.wait_window(dlg)
        if dlg.result is not None:
            self.skip_list[stid] = dlg.result
            self._refresh_skiplist()

    def _skip_export(self):
        if not self.skip_list and not self.removal_list:
            messagebox.showinfo("Empty", "Skip list is empty"); return
        if self.h5_path:
            fire = self.h5_path.stem.removesuffix("_weather_data")
            default = f"{fire}_skiplist.py"
        else:
            default = "skiplist.py"
        path = filedialog.asksaveasfilename(
            title="Export skip list",
            defaultextension=".py",
            filetypes=[("Python file", "*.py"), ("Text file", "*.txt"), ("All", "*.*")],
            initialfile=default,
            initialdir=str(self.h5_path.parent) if self.h5_path else ".",
        )
        if not path:
            return
        _, qc_path = self._skip_export_write(path)
        qc_msg = f"\n{qc_path.name}" if qc_path else ""
        messagebox.showinfo("Exported", f"Saved:\n{path}{qc_msg}")

    def _export_script(self):
        dlg = ExportScriptDialog(self, self.h5_path)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        r = dlg.result
        text = build_processing_script_text(self.skip_list, self.removal_list, r)
        dest = Path(r["dest_dir"]) / r["script_filename"]
        try:
            dest.write_text(text)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc)); return
        messagebox.showinfo("Exported", f"Wrote:\n{dest}")

    def _skip_export_write(self, path):
        """Write the skip-list + removal-manifest export, no dialogs involved.

        Directly callable from tests. Writes `path` (skip_stations +
        remove_records as Python source) and, if an H5 is loaded, a sibling
        <fire>_QC.pkl with the full QC session state.

        Args:
            path (str or Path): destination .py file path.

        Returns:
            tuple[str or Path, Path or None]: (path, qc_path) — qc_path is
                None when no H5 is currently loaded.
        """
        skip_block = _format_skip_stations_block(self.skip_list)
        lines = [skip_block]
        lines.append("")
        lines.append("# Record removals: per-station list of (variable_or_*, t0_iso, t1_iso, reason).")
        lines.append("# Apply in processing scripts, e.g.:")
        lines.append("#   mask = (times >= np.datetime64(t0)) & (times <= np.datetime64(t1))")
        lines.append('#   data[var][mask] = np.nan   # or drop; "*" = every variable')
        remove_block = _format_remove_records_block(self.removal_list)
        lines.append(remove_block)
        Path(path).write_text("\n".join(lines) + "\n")

        qc_path = None
        if self.h5_path:
            fire    = self.h5_path.stem.removesuffix("_weather_data")
            qc_path = self.h5_path.parent / f"{fire}_QC.pkl"
            with open(qc_path, "wb") as qf:
                pickle.dump({
                    "version":      4,
                    "skip_list":    dict(self.skip_list),
                    "green_list":   sorted(self.green_list),
                    "removal_list": {s: [dict(e) for e in v]
                                      for s, v in self.removal_list.items()},
                    "saved_at":     datetime.now().isoformat(timespec="seconds"),
                    "h5_path":      str(self.h5_path),
                    "cfg":          copy.deepcopy(self.cfg),
                    "all_stats":    self.all_stats,
                    "ov_col_vis":   {c: v.get() for c, v in self._ov_col_vars.items()},
                }, qf)
        return path, qc_path

    def _export_cleaned_h5(self):
        if not self.h5_path:
            messagebox.showinfo("No H5", "Load an H5 file first"); return
        if not self.removal_list:
            messagebox.showinfo("Empty", "Removal list is empty — nothing to clean"); return
        fire    = self.h5_path.stem.removesuffix("_weather_data")
        default = f"{fire}_weather_data_cleaned.h5"
        path = filedialog.asksaveasfilename(
            title="Export cleaned H5",
            defaultextension=".h5",
            filetypes=[("HDF5 files", "*.h5 *.hdf5"), ("All", "*.*")],
            initialfile=default,
            initialdir=str(self.h5_path.parent),
        )
        if not path:
            return
        try:
            n_stations, n_nanned, errors = self._export_cleaned_h5_write(path)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc)); return
        msg = (f"Wrote:\n{path}\n\n"
               f"{n_stations} station(s) modified, {n_nanned} value(s) set to NaN.")
        if errors:
            shown = "\n".join(f"  {s}/{v}: {err}" for s, v, err in errors[:10])
            msg += f"\n\n{len(errors)} dataset write(s) failed and were skipped:\n{shown}"
            if len(errors) > 10:
                msg += f"\n  ... and {len(errors) - 10} more"
        messagebox.showinfo("Cleaned H5 exported", msg)

    def _export_cleaned_h5_write(self, dest_path):
        """Write a copy of the loaded H5 with removal-manifest ranges NaN'd out.

        No dialogs involved, directly callable from tests. Copies
        self.h5_path to dest_path (original untouched) then NaNs every
        record-removal manifest range in the copy. Layout mirrors
        data._parse_station_group: time_series/station_<stid>/, a "time"
        dataset (minutes since the time_origin attr) plus one float64
        dataset per variable.

        Args:
            dest_path (str or Path): destination .h5 file path.

        Returns:
            tuple[int, int, list[tuple[str, str, str]]]: (n_stations_modified,
                n_values_nanned, errors), where errors is a list of
                (stid, var, exc_str) for per-dataset write failures that
                were caught and skipped rather than aborting the whole export.
        """
        if not self.h5_path:
            raise ValueError("No H5 loaded")
        dest_path = Path(dest_path)
        shutil.copy2(self.h5_path, dest_path)

        n_stations = 0
        n_nanned   = 0
        errors     = []
        with h5py.File(dest_path, "r+") as f:
            ts_grp = f.get("time_series")
            if ts_grp is None:
                return n_stations, n_nanned, errors
            for stid, entries in self.removal_list.items():
                if not entries:
                    continue
                grp = ts_grp.get(f"station_{stid}")
                if grp is None or "time" not in grp:
                    continue
                t0_str  = grp["time"].attrs.get("time_origin", "")
                rel_min = grp["time"][:]
                try:
                    t0 = datetime.fromisoformat(t0_str)
                    if np.isnan(rel_min).any():
                        raise ValueError("NaN in time dataset")
                    if t0.tzinfo is not None:
                        t0 = t0.astimezone(timezone.utc).replace(tzinfo=None)
                    us = np.rint(rel_min.astype(np.float64) * 60_000_000.0).astype(np.int64)
                    times = np.datetime64(t0, "us") + us.astype("timedelta64[us]")
                except Exception:
                    continue  # can't parse a time axis -> can't build a mask

                station_touched = False
                for e in entries:
                    try:
                        t0m, t1m = np.datetime64(e["t0"]), np.datetime64(e["t1"])
                    except Exception:
                        continue
                    if t1m < t0m:
                        t0m, t1m = t1m, t0m
                    mask = (times >= t0m) & (times <= t1m)
                    if not mask.any():
                        continue
                    if e["var"] == "*":
                        targets = [ds for ds in grp if ds != "time"]
                    else:
                        targets = [e["var"]] if e["var"] in grp else []
                    for vname in targets:
                        ds = grp[vname]
                        if not np.issubdtype(ds.dtype, np.floating):
                            continue  # non-float dataset: NaN isn't representable, skip
                        try:
                            arr = ds[:]
                            arr[mask] = np.nan
                            ds[...] = arr
                            n_nanned += int(mask.sum())
                            station_touched = True
                        except Exception as exc:
                            errors.append((stid, vname, str(exc)))
                if station_touched:
                    n_stations += 1
        return n_stations, n_nanned, errors
