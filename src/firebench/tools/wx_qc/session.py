"""Versioned JSON persistence for weather-station QC sessions."""

import copy
import json
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from .constants import ASSERTION_CATS, MAP_COLOR_MODES, default_config, validate_gui_config
from .file_io import atomic_write_text
from .state import resolve_restored_decisions

# Matches firebench's user-local data convention (see get_local_db_path
# in tools/local_db_management.py) rather than the installed package tree.
SESSION_VERSION = 2
AUTOSAVE_PATH = Path.home() / ".firebench" / "wx_qc_autosave.json"

_SESSION_FIELDS = {
    "version",
    "saved_at",
    "h5_path",
    "skip_list",
    "green_list",
    "removal_list",
    "cfg",
    "current_stid",
    "map_color",
    "map_basemap",
    "ov_col_vis",
}
_SESSION_FIELDS_V1 = _SESSION_FIELDS - {"map_basemap"}
_CONFIG_FIELDS = set(default_config())
_ASSERTION_KEYS = {key for key, _label in ASSERTION_CATS}


class SessionValidationError(ValueError):
    """Raised when a JSON session does not match the supported schema."""


def _field_difference(actual, expected, label):
    """Raise a useful error when a mapping has missing or unexpected fields."""
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    details = []
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected {', '.join(unexpected)}")
    if details:
        raise SessionValidationError(f"{label} fields are invalid ({'; '.join(details)})")


def _validate_string_mapping(value, label):
    """Return a copy of a string-to-string mapping."""
    if not isinstance(value, dict):
        raise SessionValidationError(f"{label} must be an object")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise SessionValidationError(f"{label} must map station ID strings to string values")
        if not key:
            raise SessionValidationError(f"{label} contains an empty station ID")
        result[key] = item
    return result


def _validate_removal_list(value):
    """Return a validated copy of station record-removal decisions."""
    if not isinstance(value, dict):
        raise SessionValidationError("removal_list must be an object")
    result = {}
    required = {"var", "t0", "t1", "reason"}
    for station_id, entries in value.items():
        if not isinstance(station_id, str) or not station_id:
            raise SessionValidationError("removal_list station IDs must be non-empty strings")
        if not isinstance(entries, list):
            raise SessionValidationError(f"removal_list[{station_id!r}] must be an array")
        validated_entries = []
        for index, entry in enumerate(entries):
            label = f"removal_list[{station_id!r}][{index}]"
            if not isinstance(entry, dict):
                raise SessionValidationError(f"{label} must be an object")
            _field_difference(set(entry), required, label)
            if not all(isinstance(entry[field], str) for field in required):
                raise SessionValidationError(f"{label} fields must all be strings")
            if not entry["var"] or not entry["t0"] or not entry["t1"]:
                raise SessionValidationError(f"{label} variable and timestamps must not be empty")
            validated_entries.append(dict(entry))
        result[station_id] = validated_entries
    return result


def _validate_config_scalars(config):
    """Validate scalar configuration fields."""
    for key in ("frozen_min_run", "compare_n_neighbors"):
        if isinstance(config[key], bool) or not isinstance(config[key], int):
            raise SessionValidationError(f"cfg.{key} must be an integer")
    for key in ("max_var_outage_min", "full_outage_min"):
        if isinstance(config[key], bool) or not isinstance(config[key], (int, float)):
            raise SessionValidationError(f"cfg.{key} must be a number")
    for key in (
        "show_errors",
        "show_warns",
        "perim_show_all",
        "compare_include_skip_greenlit",
    ):
        if not isinstance(config[key], bool):
            raise SessionValidationError(f"cfg.{key} must be true or false")
    if config["perim_h5_path"] is not None and not isinstance(config["perim_h5_path"], str):
        raise SessionValidationError("cfg.perim_h5_path must be a string or null")


def _validate_hidden_assertions(config):
    """Normalize the JSON assertion-category array to an App-native set."""
    hidden = config["hidden_assertions"]
    if not isinstance(hidden, list) or not all(isinstance(item, str) for item in hidden):
        raise SessionValidationError("cfg.hidden_assertions must be an array of strings")
    unknown_assertions = sorted(set(hidden) - _ASSERTION_KEYS)
    if unknown_assertions:
        raise SessionValidationError(
            f"cfg.hidden_assertions contains unknown categories: {', '.join(unknown_assertions)}"
        )
    config["hidden_assertions"] = set(hidden)


def _validate_bounds(config):
    """Normalize JSON bounds arrays to App-native tuples."""
    bounds = config["bounds"]
    default_bounds = default_config()["bounds"]
    if not isinstance(bounds, dict):
        raise SessionValidationError("cfg.bounds must be an object")
    _field_difference(set(bounds), set(default_bounds), "cfg.bounds")
    normalized_bounds = {}
    for variable, bound in bounds.items():
        if not isinstance(bound, list) or len(bound) != 3:
            raise SessionValidationError(f"cfg.bounds.{variable} must be a [min, max, unit] array")
        lower, upper, unit = bound
        if (
            isinstance(lower, bool)
            or not isinstance(lower, (int, float))
            or isinstance(upper, bool)
            or not isinstance(upper, (int, float))
            or not isinstance(unit, str)
        ):
            raise SessionValidationError(
                f"cfg.bounds.{variable} must contain two numbers and a unit string"
            )
        normalized_bounds[variable] = (lower, upper, unit)
    config["bounds"] = normalized_bounds


def _validate_config(value):
    """Validate JSON field types and return the App-native configuration."""
    if not isinstance(value, dict):
        raise SessionValidationError("cfg must be an object")
    _field_difference(set(value), _CONFIG_FIELDS, "cfg")

    config = copy.deepcopy(value)
    _validate_config_scalars(config)
    _validate_hidden_assertions(config)
    _validate_bounds(config)
    try:
        validate_gui_config(config)
    except ValueError as exc:
        raise SessionValidationError(f"cfg is invalid: {exc}") from exc
    return config


def validate_session_state(value):
    """Validate a decoded JSON session and return an App-native copy.

    Validation is intentionally complete before callers mutate App state. The
    returned configuration uses sets and tuples expected by the GUI; the input
    remains JSON-compatible.
    """
    if not isinstance(value, dict):
        raise SessionValidationError("session must be a JSON object")

    version = value["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise SessionValidationError("session version must be an integer")
    if version not in (1, SESSION_VERSION):
        raise SessionValidationError(
            f"unsupported session version {version}; expected version 1 or {SESSION_VERSION}"
        )
    _field_difference(set(value), _SESSION_FIELDS_V1 if version == 1 else _SESSION_FIELDS, "session")

    saved_at = value["saved_at"]
    if not isinstance(saved_at, str):
        raise SessionValidationError("saved_at must be an ISO timestamp string")
    try:
        datetime.fromisoformat(saved_at)
    except ValueError as exc:
        raise SessionValidationError("saved_at must be a valid ISO timestamp") from exc

    h5_path = value["h5_path"]
    if h5_path is not None and not isinstance(h5_path, str):
        raise SessionValidationError("h5_path must be a string or null")

    skip_list = _validate_string_mapping(value["skip_list"], "skip_list")
    green_list = value["green_list"]
    if (
        not isinstance(green_list, list)
        or not all(isinstance(station_id, str) and station_id for station_id in green_list)
        or len(green_list) != len(set(green_list))
    ):
        raise SessionValidationError("green_list must be an array of unique, non-empty station IDs")
    skip_list, green_list = resolve_restored_decisions(skip_list, green_list)

    current_stid = value["current_stid"]
    if current_stid is not None and not isinstance(current_stid, str):
        raise SessionValidationError("current_stid must be a string or null")
    map_color = value["map_color"]
    if map_color not in MAP_COLOR_MODES:
        raise SessionValidationError(f"map_color must be one of: {', '.join(MAP_COLOR_MODES)}")
    map_basemap = value.get("map_basemap", True)
    if not isinstance(map_basemap, bool):
        raise SessionValidationError("map_basemap must be true or false")
    ov_col_vis = value["ov_col_vis"]
    if not isinstance(ov_col_vis, dict) or not all(
        isinstance(column, str) and isinstance(visible, bool) for column, visible in ov_col_vis.items()
    ):
        raise SessionValidationError("ov_col_vis must map column names to true or false")

    return {
        "version": version,
        "saved_at": saved_at,
        "h5_path": h5_path,
        "skip_list": skip_list,
        "green_list": green_list,
        "removal_list": _validate_removal_list(value["removal_list"]),
        "cfg": _validate_config(value["cfg"]),
        "current_stid": current_stid,
        "map_color": map_color,
        "map_basemap": map_basemap,
        "ov_col_vis": dict(ov_col_vis),
    }


def _atomic_write_json(destination, value):
    """Atomically replace ``destination`` with UTF-8 JSON."""
    text = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    atomic_write_text(destination, text)


def write_session_file(destination, state):
    """Validate and atomically write a JSON session."""
    validate_session_state(state)
    _atomic_write_json(destination, state)


def read_session_file(path):
    """Read and validate a JSON session, returning its JSON-compatible state."""
    path = Path(path)
    if path.suffix.lower() == ".pkl":
        raise SessionValidationError(
            "legacy pickle sessions are not supported; select a versioned JSON session"
        )
    with path.open("r", encoding="utf-8") as session_file:
        state = json.load(session_file)
    validate_session_state(state)
    return state


class SessionMixin:
    """Persist and restore App-owned QC decisions, configuration, and view state.

    App state:
        Expects ``h5_path``, ``cfg``, station decision collections, current
        station/map/Overview view variables, status widgets, and the loader,
        map, navigation, and tab-refresh helpers supplied by App's other mixins.
    """

    def _session_state(self) -> dict:
        """Return a JSON-compatible snapshot without cached station statistics."""
        config = copy.deepcopy(self.cfg)
        config["hidden_assertions"] = sorted(config["hidden_assertions"])
        config["bounds"] = {
            variable: [lower, upper, unit] for variable, (lower, upper, unit) in config["bounds"].items()
        }
        return {
            "version": SESSION_VERSION,
            "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "h5_path": str(self.h5_path) if self.h5_path else None,
            "skip_list": dict(self.skip_list),
            "removal_list": {
                station_id: [dict(entry) for entry in entries]
                for station_id, entries in self.removal_list.items()
            },
            "green_list": sorted(self.green_list),
            "cfg": config,
            "current_stid": self._current_stid,
            "map_color": self.var_map_color.get(),
            "map_basemap": self.var_map_basemap.get(),
            "ov_col_vis": {column: variable.get() for column, variable in self._ov_col_vars.items()},
        }

    def _save_session(self, path=None):
        """Save current session state to a versioned JSON file."""
        if path is None:
            init_dir = str(self.h5_path.parent) if self.h5_path else "."
            path = filedialog.asksaveasfilename(
                title="Save session",
                defaultextension=".json",
                filetypes=[("QC session JSON", "*.json")],
                initialfile="wx_qc_session.json",
                initialdir=init_dir,
            )
            if not path:
                return
        try:
            write_session_file(path, self._session_state())
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            messagebox.showerror("Save failed", f"Could not save JSON session to {path}:\n\n{exc}")
            return
        self.lbl_status.config(text=f"Saved: {Path(path).name}")

    def _load_session_file(self, path=None):
        """Read, validate, and restore a versioned JSON session."""
        if path is None:
            path = filedialog.askopenfilename(
                title="Load session",
                filetypes=[("QC session JSON", "*.json")],
                initialdir=str(AUTOSAVE_PATH.parent),
            )
            if not path:
                return
        try:
            session = read_session_file(path)
            self._restore_session(session)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            messagebox.showerror(
                "Load failed",
                f"Could not restore JSON session {path}:\n\n{exc}",
            )

    def _apply_restored_view(self, session):
        """Apply validated Overview, station, and map view state."""
        for column, variable in self._ov_col_vars.items():
            if column in session["ov_col_vis"]:
                variable.set(session["ov_col_vis"][column])
        self._apply_col_visibility()
        station_id = session["current_stid"]
        if station_id and station_id in self.stations:
            self._navigate_to_station(station_id)
        self.var_map_basemap.set(session["map_basemap"])
        self.var_map_color.set(session["map_color"])
        self._on_map_basemap_toggle()

    def _restore_session(self, value):
        """Validate state, reload its H5, and recompute every station statistic."""
        session = validate_session_state(value)

        # No App-owned state changes occur before the complete validation above.
        self.cfg = session["cfg"]
        perim_path = self.cfg["perim_h5_path"]
        if perim_path and Path(perim_path).exists():
            self._load_perim_h5(Path(perim_path))
        else:
            self._perim_data = []
            self._perim_loaded_path = None
        self.skip_list = session["skip_list"]
        self.green_list = session["green_list"]
        self.removal_list = session["removal_list"]

        h5_path = session["h5_path"]
        if h5_path and Path(h5_path).is_file():
            self.h5_path = Path(h5_path)
            self.lbl_file.config(text=str(self.h5_path))
            self.lbl_status.config(text="Loading H5 and recomputing statistics...")

            def _on_complete():
                self._apply_restored_view(session)
                self._refresh_skiplist()
                self._refresh_overview()
                self._refresh_station_list()
                saved_at = session["saved_at"][:16]
                self.lbl_status.config(text=f"Session restored  (saved {saved_at})")

            # Session files never contain trusted statistics. The H5 loader must
            # recompute them from source data on every restoration.
            self._load_data(on_complete=_on_complete)
        else:
            if h5_path:
                messagebox.showwarning(
                    "H5 not found",
                    f"Session references:\n{h5_path}\n\nFile not found. Open it manually.",
                )
            self._apply_restored_view(session)
            self._refresh_skiplist()
            self._refresh_overview()
            self._refresh_station_list()

    def _check_autosave(self):
        """Offer to restore the validated JSON autosave, if one exists."""
        if not AUTOSAVE_PATH.exists():
            return
        try:
            session = read_session_file(AUTOSAVE_PATH)
            saved_at = session["saved_at"][:16]
            h5_name = Path(session["h5_path"]).name if session["h5_path"] else "—"
            message = (
                f"Autosave found from {saved_at}\n"
                f"File: {h5_name}\n"
                f"Skip: {len(session['skip_list'])}  |  "
                f"Greenlit: {len(session['green_list'])}\n\n"
                "Reload this session?"
            )
            if messagebox.askyesno("Restore autosave?", message):
                self._restore_session(session)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            tk.TclError,
        ) as exc:
            try:
                self.lbl_status.config(text=f"Autosave check failed for {AUTOSAVE_PATH.name}: {exc}")
            except tk.TclError:
                print(f"Weather QC autosave check failed: {exc}", file=sys.stderr)

    def _on_quit(self):
        """Autosave non-empty work as JSON, report failures, and close the App."""
        if self.h5_path or self.skip_list or self.green_list or self.removal_list:
            try:
                write_session_file(AUTOSAVE_PATH, self._session_state())
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                message = (
                    f"Could not autosave your QC session to {AUTOSAVE_PATH}:\n\n{exc}\n\n"
                    "Use Save Session before closing if you want to preserve this work."
                )
                try:
                    messagebox.showerror("Autosave failed", message)
                except tk.TclError:
                    print(f"Weather QC autosave failed: {exc}", file=sys.stderr)
        self._shutdown_map_tiles()
        self.destroy()
