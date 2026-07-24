import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from .constants import (
    ASSERTION_CATS,
    ASSERTION_DEFAULT_SEVERITY,
    DEFAULT_MAX_VAR_OUTAGE_MIN,
    DEFAULT_FULL_OUTAGE_MIN,
    validate_gui_config,
)
from .theme import PAD, PAD_LG

# Map variables with a colorbar-driven marker/heatmap style on the map tab
# (mirrors map_tab.py's _VAR_CMAP keys).
CBAR_VARS = (
    "air_temperature",
    "relative_humidity",
    "solar_radiation",
    "fuel_moisture_content_10h",
    "wind_speed",
    "wind_gust",
    "wind_direction",
)


class AddSkipDialog(tk.Toplevel):
    """Prompt user to add station to skip list.

    Result holds reason string on OK (stripped), or None on cancel.
    """

    def __init__(self, parent, stid, default_reason="", label=None):
        """Build skip-list reason dialog."""
        super().__init__(parent)
        self.title("Add to Skip List")
        self.resizable(False, False)
        self.result = None
        display = label if label is not None else f"Station:  {stid}"
        ttk.Label(self, text=display, style="Section.TLabel").pack(padx=14, pady=(10, 2))
        ttk.Label(self, text="Reason:").pack(anchor="w", padx=14)
        self.entry = ttk.Entry(self, width=50)
        self.entry.insert(0, default_reason)
        self.entry.pack(padx=14, pady=4)
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        bf = ttk.Frame(self)
        bf.pack(pady=(4, 12))
        ttk.Button(bf, text="Add", command=self._ok, width=8).pack(side="left", padx=4)
        ttk.Button(bf, text="Cancel", command=self.destroy, width=8).pack(side="left", padx=4)
        self.bind("<Return>", lambda _: self._ok())
        self.grab_set()

    def _ok(self):
        """Set result to entry text (stripped) and close."""
        self.result = self.entry.get().strip()
        self.destroy()


class AddRemovalDialog(tk.Toplevel):
    """Confirm record removal. Returns (scope, reason) tuple where scope is
    "var" (current variable; for synthetic "wind" plot, caller expands to
    wind_speed + wind_direction) or "*" (all variables)."""

    def __init__(self, parent, stid, vname, t0_str, t1_str, n_samples):
        """Build removal confirmation dialog."""
        super().__init__(parent)
        self.title("Remove Records")
        self.resizable(False, False)
        self.result = None
        plural = "s" if n_samples != 1 else ""
        summary = f"{stid}:  {t0_str} -> {t1_str}   ({n_samples} sample{plural})"
        ttk.Label(self, text=summary, style="Section.TLabel").pack(anchor="w", padx=14, pady=(10, 4))
        # For synthetic "wind" plot, "current variable" removes both wind_speed and wind_direction.
        cur_label = "wind_speed + wind_direction" if vname == "wind" else f"current variable ({vname})"
        self.var_scope = tk.StringVar(value="var")
        sf = ttk.Frame(self)
        sf.pack(anchor="w", padx=14)
        ttk.Radiobutton(sf, text=cur_label, value="var", variable=self.var_scope).pack(anchor="w", pady=1)
        ttk.Radiobutton(sf, text="all variables (*)", value="*", variable=self.var_scope).pack(
            anchor="w", pady=1
        )
        ttk.Label(self, text="Reason:").pack(anchor="w", padx=14, pady=(6, 0))
        self.entry = ttk.Entry(self, width=50)
        self.entry.pack(padx=14, pady=4)
        self.entry.focus_set()
        bf = ttk.Frame(self)
        bf.pack(pady=(4, 12))
        ttk.Button(bf, text="OK", command=self._ok, width=8).pack(side="left", padx=4)
        ttk.Button(bf, text="Cancel", command=self.destroy, width=8).pack(side="left", padx=4)
        self.bind("<Return>", lambda _: self._ok())
        self.grab_set()

    def _ok(self):
        """Set result to (scope, reason) tuple and close."""
        self.result = (self.var_scope.get(), self.entry.get().strip())
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Edit application configuration (bounds, thresholds, assertions, columns, fire perimeter, colorbars).

    Result holds validated physical bounds, thresholds, assertion visibility
    and severities, column visibility, perimeter settings, station-comparison
    settings, and map marker/colorbar overrides on OK, or None on cancel.
    """

    def __init__(self, parent, cfg, bounds, base_cols, var_col_map, col_visibility, var_short):
        """Build settings notebook dialog with Bounds, Thresholds, Assertions, Columns, Fire Perimeter, Colorbars tabs."""
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.result = None

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        bt = ttk.Frame(nb)
        nb.add(bt, text="Bounds")
        for c, txt in enumerate(("Variable", "Min", "Max", "Unit")):
            ttk.Label(bt, text=txt, style="Section.TLabel").grid(row=0, column=c, padx=PAD_LG, pady=PAD)
        self._bound_entries = {}
        for r, (vname, (lo, hi, unit)) in enumerate(bounds.items(), 1):
            tk.Label(bt, text=vname, anchor="w").grid(row=r, column=0, sticky="w", padx=PAD_LG, pady=PAD)
            e_lo = ttk.Entry(bt, width=9)
            e_lo.insert(0, str(lo))
            e_lo.grid(row=r, column=1, padx=PAD_LG, pady=PAD)
            e_hi = ttk.Entry(bt, width=9)
            e_hi.insert(0, str(hi))
            e_hi.grid(row=r, column=2, padx=PAD_LG, pady=PAD)
            tk.Label(bt, text=unit).grid(row=r, column=3, padx=PAD_LG, pady=PAD)
            self._bound_entries[vname] = (e_lo, e_hi, unit)

        tf = ttk.Frame(nb)
        nb.add(tf, text="Thresholds")
        tk.Label(tf, text="Frozen run >=:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_frz = ttk.Entry(tf, width=10)
        self.e_frz.insert(0, str(cfg["frozen_min_run"]))
        self.e_frz.grid(row=0, column=1, padx=PAD_LG, pady=PAD)
        self.v_frz_exempt_calm = tk.BooleanVar(value=cfg.get("frozen_exempt_calm_wind", False))
        ttk.Checkbutton(
            tf,
            text="Exempt wind direction (calm-wind repetition)",
            variable=self.v_frz_exempt_calm,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD)
        self.v_frz_exempt_rh = tk.BooleanVar(value=cfg.get("frozen_exempt_rh", False))
        ttk.Checkbutton(tf, text="Exempt relative humidity", variable=self.v_frz_exempt_rh).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD
        )
        tk.Label(tf, text="Duplicate-timestamp threshold:", anchor="w").grid(
            row=3, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_dup_max = ttk.Entry(tf, width=10)
        self.e_dup_max.insert(0, str(cfg.get("dup_max", 2)))
        self.e_dup_max.grid(row=3, column=1, padx=PAD_LG, pady=PAD)
        tk.Label(tf, text="Longest variable outage warning (min):", anchor="w").grid(
            row=4, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_max_var_outage = ttk.Entry(tf, width=10)
        self.e_max_var_outage.insert(0, str(cfg.get("max_var_outage_min", DEFAULT_MAX_VAR_OUTAGE_MIN)))
        self.e_max_var_outage.grid(row=4, column=1, padx=PAD_LG, pady=PAD)
        tk.Label(tf, text="Longest full-station outage warning (min):", anchor="w").grid(
            row=5, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_full_outage = ttk.Entry(tf, width=10)
        self.e_full_outage.insert(0, str(cfg.get("full_outage_min", DEFAULT_FULL_OUTAGE_MIN)))
        self.e_full_outage.grid(row=5, column=1, padx=PAD_LG, pady=PAD)

        ttk.Separator(tf, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=PAD_LG, pady=PAD
        )
        tk.Label(tf, text="Compare -> nearest neighbors N:", anchor="w").grid(
            row=7, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_compare_n = ttk.Entry(tf, width=10)
        self.e_compare_n.insert(0, str(cfg.get("compare_n_neighbors", 4)))
        self.e_compare_n.grid(row=7, column=1, padx=PAD_LG, pady=PAD)
        self.v_compare_pool = tk.BooleanVar(value=cfg.get("compare_include_skip_greenlit", False))
        ttk.Checkbutton(
            tf,
            text="Include skip-listed/greenlit stations as neighbor candidates",
            variable=self.v_compare_pool,
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD)

        af = ttk.Frame(nb)
        nb.add(af, text="Assertions")
        ttk.Label(af, text="Assertion categories:", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD
        )
        ttk.Label(af, text="Severity", style="Section.TLabel").grid(
            row=1, column=1, sticky="w", padx=PAD_LG, pady=(0, PAD)
        )
        hidden = cfg.get("hidden_assertions", set())
        severity_overrides = cfg.get("assertion_severity_override", {})
        self._acat_vars = {}
        self._acat_severity_vars = {}
        for i, (key, label) in enumerate(ASSERTION_CATS):
            row = 2 + i
            v = tk.BooleanVar(value=(key not in hidden))
            self._acat_vars[key] = v
            ttk.Checkbutton(af, text=label, variable=v).grid(
                row=row, column=0, sticky="w", padx=PAD_LG, pady=PAD
            )
            sv = tk.StringVar(
                value=severity_overrides.get(key, ASSERTION_DEFAULT_SEVERITY.get(key, "WARN"))
            )
            self._acat_severity_vars[key] = sv
            ttk.Combobox(af, textvariable=sv, values=["WARN", "ERROR"], state="readonly", width=6).grid(
                row=row, column=1, sticky="w", padx=PAD_LG, pady=PAD
            )

        cf = ttk.Frame(nb)
        nb.add(cf, text="Columns")
        self._col_vars = {}
        ttk.Label(cf, text="Base columns:", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=PAD_LG, pady=PAD
        )
        for i, c in enumerate(base_cols):
            v = tk.BooleanVar(value=col_visibility.get(c, True))
            self._col_vars[c] = v
            ttk.Checkbutton(cf, text=c, variable=v).grid(
                row=1 + i // 2, column=(i % 2) * 2, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD
            )

        var_rows = {}
        for col, (vname, key) in var_col_map.items():
            var_rows.setdefault(vname, {})[key] = col
        if var_rows:
            row0 = 1 + (len(base_cols) + 1) // 2
            ttk.Separator(cf, orient="horizontal").grid(
                row=row0, column=0, columnspan=4, sticky="ew", padx=PAD_LG, pady=PAD
            )
            ttk.Label(cf, text="Per-variable stat columns:", style="Section.TLabel").grid(
                row=row0 + 1, column=0, columnspan=4, sticky="w", padx=PAD_LG, pady=PAD
            )
            for c, stat in enumerate(("Max", "Min", "Std", "Cumulative Outage %"), start=1):
                ttk.Label(cf, text=stat, style="Section.TLabel").grid(
                    row=row0 + 2, column=c, padx=PAD_LG, pady=PAD
                )
            for r, vname in enumerate(sorted(var_rows), start=row0 + 3):
                short = var_short.get(vname, vname[:6])
                tk.Label(cf, text=short, anchor="w").grid(
                    row=r, column=0, sticky="w", padx=PAD_LG, pady=PAD
                )
                for c, (stat, key) in enumerate(
                    (
                        ("Max", "max"),
                        ("Min", "min"),
                        ("Std", "std"),
                        ("Cumulative Outage %", "outage_pct"),
                    ),
                    start=1,
                ):
                    col = var_rows[vname].get(key)
                    if col is None:
                        continue
                    v = tk.BooleanVar(value=col_visibility.get(col, stat == "Max"))
                    self._col_vars[col] = v
                    ttk.Checkbutton(cf, variable=v).grid(row=r, column=c, padx=PAD_LG, pady=PAD)

        pf = ttk.Frame(nb)
        nb.add(pf, text="Fire Perimeter")
        ttk.Label(pf, text="Perimeter H5:", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.var_perim_path = tk.StringVar(value=cfg.get("perim_h5_path") or "(none)")
        ttk.Label(pf, textvariable=self.var_perim_path, anchor="w", width=42, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        ttk.Button(pf, text="Choose", command=self._choose_perim_file).grid(
            row=1, column=1, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.v_perim_all = tk.BooleanVar(value=cfg.get("perim_show_all", True))
        ttk.Checkbutton(pf, text="Show all perimeters", variable=self.v_perim_all).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.v_map_fire_deriv = tk.BooleanVar(value=cfg.get("map_nav_fire_area_deriv", False))
        ttk.Checkbutton(
            pf, text="Map sparkline: show growth rate instead of area", variable=self.v_map_fire_deriv
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD)
        self.v_ts_nav_fire_area = tk.BooleanVar(value=cfg.get("ts_nav_fire_area", False))
        ttk.Checkbutton(
            pf,
            text="Station detail sparkline: show fire area when perimeter overlaps",
            variable=self.v_ts_nav_fire_area,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=PAD_LG, pady=PAD)

        cbf = ttk.Frame(nb)
        nb.add(cbf, text="Colorbars")
        tk.Label(cbf, text="Map marker/arrow size (x):", anchor="w").grid(
            row=0, column=0, sticky="w", padx=PAD_LG, pady=PAD
        )
        self.e_marker_size = ttk.Entry(cbf, width=10)
        self.e_marker_size.insert(0, str(cfg.get("map_marker_size", 1.0)))
        self.e_marker_size.grid(row=0, column=1, padx=PAD_LG, pady=PAD)

        ttk.Separator(cbf, orient="horizontal").grid(
            row=1, column=0, columnspan=6, sticky="ew", padx=PAD_LG, pady=PAD
        )
        ttk.Label(cbf, text="Per-variable colorbar overrides:", style="Section.TLabel").grid(
            row=2, column=0, columnspan=6, sticky="w", padx=PAD_LG, pady=PAD
        )
        for c, txt in enumerate(("Variable", "Colormap", "Reversed", "Min", "Max"), start=0):
            ttk.Label(cbf, text=txt, style="Section.TLabel").grid(
                row=3, column=c, padx=PAD_LG, pady=(0, PAD)
            )
        cbar_overrides = cfg.get("cbar_overrides", {})
        self._cbar_vars = {}
        for r, vname in enumerate(CBAR_VARS, start=4):
            override = cbar_overrides.get(vname, {})
            tk.Label(cbf, text=vname, anchor="w").grid(row=r, column=0, sticky="w", padx=PAD_LG, pady=PAD)
            e_cmap = ttk.Entry(cbf, width=12)
            e_cmap.insert(0, override.get("cmap") or "")
            e_cmap.grid(row=r, column=1, padx=PAD_LG, pady=PAD)
            v_rev = tk.BooleanVar(value=override.get("reversed", False))
            ttk.Checkbutton(cbf, variable=v_rev).grid(row=r, column=2, padx=PAD_LG, pady=PAD)
            e_vmin = ttk.Entry(cbf, width=8)
            e_vmin.insert(0, "" if override.get("vmin") is None else str(override.get("vmin")))
            e_vmin.grid(row=r, column=3, padx=PAD_LG, pady=PAD)
            e_vmax = ttk.Entry(cbf, width=8)
            e_vmax.insert(0, "" if override.get("vmax") is None else str(override.get("vmax")))
            e_vmax.grid(row=r, column=4, padx=PAD_LG, pady=PAD)
            self._cbar_vars[vname] = {
                "cmap": e_cmap,
                "reversed": v_rev,
                "vmin": e_vmin,
                "vmax": e_vmax,
            }

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=PAD_LG, pady=PAD)
        ttk.Button(bf, text="OK", command=self._ok, width=8).pack(side="right", padx=PAD)
        ttk.Button(bf, text="Cancel", command=self.destroy, width=8).pack(side="right", padx=PAD)
        self.bind("<Return>", lambda _: self._ok())
        self.grab_set()

    def _choose_perim_file(self):
        """Open file dialog to select fire perimeter H5 file."""
        path = filedialog.askopenfilename(
            title="Open fire perimeter H5", filetypes=[("HDF5 files", "*.h5 *.hdf5"), ("All files", "*.*")]
        )
        if path:
            self.var_perim_path.set(path)

    def _ok(self):
        """Validate all entries and set result dict with parsed config, or show error."""
        try:
            bounds_r = {
                v: (float(lo.get()), float(hi.get()), u) for v, (lo, hi, u) in self._bound_entries.items()
            }
            perim_path = self.var_perim_path.get()
            cbar_overrides = {}
            for vname, entries in self._cbar_vars.items():
                cmap_str = entries["cmap"].get().strip()
                reversed_flag = entries["reversed"].get()
                vmin_str = entries["vmin"].get().strip()
                vmax_str = entries["vmax"].get().strip()
                if not cmap_str and not reversed_flag and not vmin_str and not vmax_str:
                    continue
                cbar_overrides[vname] = {
                    "cmap": cmap_str or None,
                    "reversed": reversed_flag,
                    "vmin": float(vmin_str) if vmin_str else None,
                    "vmax": float(vmax_str) if vmax_str else None,
                }
            result = {
                "frozen_min_run": int(self.e_frz.get()),
                "frozen_exempt_calm_wind": self.v_frz_exempt_calm.get(),
                "frozen_exempt_rh": self.v_frz_exempt_rh.get(),
                "dup_max": int(self.e_dup_max.get()),
                "max_var_outage_min": float(self.e_max_var_outage.get()),
                "full_outage_min": float(self.e_full_outage.get()),
                "hidden_assertions": {k for k, v in self._acat_vars.items() if not v.get()},
                "assertion_severity_override": {k: v.get() for k, v in self._acat_severity_vars.items()},
                "bounds": bounds_r,
                "col_visibility": {c: v.get() for c, v in self._col_vars.items()},
                "perim_h5_path": perim_path if perim_path and perim_path != "(none)" else None,
                "perim_show_all": self.v_perim_all.get(),
                "map_nav_fire_area_deriv": self.v_map_fire_deriv.get(),
                "ts_nav_fire_area": self.v_ts_nav_fire_area.get(),
                "compare_n_neighbors": int(self.e_compare_n.get()),
                "compare_include_skip_greenlit": self.v_compare_pool.get(),
                "map_marker_size": float(self.e_marker_size.get()),
                "cbar_overrides": cbar_overrides,
            }
            validate_gui_config(result)
        except ValueError as exc:
            messagebox.showerror("Bad value", str(exc), parent=self)
            return
        self.result = result
        self.destroy()


class ExportScriptDialog(tk.Toplevel):
    """Export processing script with current skip/removal lists.

    Result holds dict with export parameters (fire_name, json_filename, output_h5_filename,
    description, contributors, compression_lvl, logging_lvl, dest_dir, script_filename) on
    OK after validation, or None on cancel.
    """

    def __init__(self, parent, h5_path=None):
        """Build export script dialog with fire metadata and destination fields."""
        super().__init__(parent)
        self.title("Export Processing Script")
        self.resizable(False, False)
        self.result = None

        # Compute fire name guess from h5_path
        if h5_path is not None:
            fire_name_guess = h5_path.parent.name.replace("_", " ")
        else:
            fire_name_guess = ""

        # Compute slug for defaults
        slug = fire_name_guess.lower().replace(" ", "_") if fire_name_guess else ""

        ttk.Label(self, text="Fire name:", style="Section.TLabel").pack(anchor="w", padx=14, pady=(10, 2))
        self.e_fire_name = ttk.Entry(self, width=50)
        self.e_fire_name.insert(0, fire_name_guess)
        self.e_fire_name.pack(padx=14, pady=4)

        ttk.Label(self, text="JSON source filename:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_json_filename = ttk.Entry(self, width=50)
        default_json = f"wx_{slug}.json" if slug else ""
        self.e_json_filename.insert(0, default_json)
        self.e_json_filename.pack(padx=14, pady=4)

        ttk.Label(self, text="Output H5 filename:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_output_h5 = ttk.Entry(self, width=50)
        default_h5 = h5_path.name if h5_path is not None else ""
        self.e_output_h5.insert(0, default_h5)
        self.e_output_h5.pack(padx=14, pady=4)

        ttk.Label(self, text="Description:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_description = ttk.Entry(self, width=60)
        default_desc = (
            f"FireBench data for {fire_name_guess} fire. Contains: Weather station datasets, "
            f"fire perimeters from NIFC, burn severity from MTBS."
            if fire_name_guess
            else "FireBench data for  fire. Contains: Weather station datasets, fire perimeters from NIFC, burn severity from MTBS."
        )
        self.e_description.insert(0, default_desc)
        self.e_description.pack(padx=14, pady=4)

        ttk.Label(self, text="Contributors:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_contributors = ttk.Entry(self, width=60)
        default_contributors = (
            "Aurelien Costes, SJSU; Angel F. Caus, SJSU; Muthu K. Selvaraj, WPI; "
            "Adam Kochanski, SJSU; Isaac Forrest, SJSU;"
        )
        self.e_contributors.insert(0, default_contributors)
        self.e_contributors.pack(padx=14, pady=4)

        ttk.Label(self, text="Compression level:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_compression = ttk.Entry(self, width=6)
        self.e_compression.insert(0, "1")
        self.e_compression.pack(padx=14, pady=4)

        ttk.Label(self, text="Logging level:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_logging = ttk.Entry(self, width=6)
        self.e_logging.insert(0, "10")
        self.e_logging.pack(padx=14, pady=4)

        ttk.Label(self, text="Destination directory:").pack(anchor="w", padx=14, pady=(10, 0))
        df = ttk.Frame(self)
        df.pack(padx=14, pady=4, fill="x")
        self.var_dest_dir = tk.StringVar(
            value=str(h5_path.parent) if h5_path is not None else str(Path.cwd())
        )
        ttk.Label(df, textvariable=self.var_dest_dir, anchor="w", style="Muted.TLabel").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(df, text="Browse", command=self._choose_dest_dir).pack(side="right", padx=(4, 0))

        ttk.Label(self, text="Output script filename:").pack(anchor="w", padx=14, pady=(10, 0))
        self.e_script_filename = ttk.Entry(self, width=40)
        default_script = f"process_weather_data_{slug}.py" if slug else "process_weather_data.py"
        self.e_script_filename.insert(0, default_script)
        self.e_script_filename.pack(padx=14, pady=4)

        bf = ttk.Frame(self)
        bf.pack(pady=(12, 12))
        ttk.Button(bf, text="Generate", command=self._ok, width=10).pack(side="left", padx=4)
        ttk.Button(bf, text="Cancel", command=self.destroy, width=10).pack(side="left", padx=4)

        self.bind("<Return>", lambda _: self._ok())
        self.grab_set()

    def _choose_dest_dir(self):
        """Open directory dialog to select export destination."""
        path = filedialog.askdirectory(title="Choose destination directory")
        if path:
            self.var_dest_dir.set(path)

    def _ok(self):
        """Validate compression and logging level integers, dest dir/filename, set result dict."""
        try:
            compression_lvl = int(self.e_compression.get().strip())
        except ValueError:
            messagebox.showerror(
                "Bad value",
                "Compression level / logging level must be integers",
                parent=self,
            )
            return

        try:
            logging_lvl = int(self.e_logging.get().strip())
        except ValueError:
            messagebox.showerror(
                "Bad value",
                "Compression level / logging level must be integers",
                parent=self,
            )
            return

        dest_dir = self.var_dest_dir.get().strip()
        script_filename = self.e_script_filename.get().strip()
        if not dest_dir or not script_filename:
            messagebox.showerror(
                "Missing field",
                "Dest dir and script filename are required",
                parent=self,
            )
            return

        self.result = {
            "fire_name": self.e_fire_name.get().strip(),
            "json_filename": self.e_json_filename.get().strip(),
            "output_h5_filename": self.e_output_h5.get().strip(),
            "description": self.e_description.get().strip(),
            "contributors": self.e_contributors.get().strip(),
            "compression_lvl": compression_lvl,
            "logging_lvl": logging_lvl,
            "dest_dir": dest_dir,
            "script_filename": script_filename,
        }
        self.destroy()
