import copy
import pickle
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from .constants import default_config
from .state import resolve_restored_decisions

# Matches firebench's user-local data convention (see get_local_db_path
# in tools/local_db_management.py) rather than a path relative to this
# module, which would land inside the installed package tree.
AUTOSAVE_PATH = Path.home() / ".firebench" / "wx_qc_autosave.pkl"


class SessionMixin:
    """Persist and restore App-owned QC decisions, configuration, and view state.

    App state:
        Expects ``h5_path``, ``cfg``, station decision collections, ``all_stats``,
        current station/map/Overview view variables, status widgets, and the
        loader, map, navigation, and tab-refresh helpers supplied by App's other
        mixins.
    """

    def _session_state(self) -> dict:
        """Return a serializable snapshot of the current session state.

        Returns:
            dict: Session state with keys: version (int), saved_at (str, ISO format),
                h5_path (str or None), skip_list (dict), removal_list (dict),
                green_list (list), cfg (dict), current_stid (str or None),
                map_color (str), all_stats (dict), ov_col_vis (dict).
        """
        return {
            "version": 4,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "h5_path": str(self.h5_path) if self.h5_path else None,
            "skip_list": dict(self.skip_list),
            "removal_list": {s: [dict(e) for e in v] for s, v in self.removal_list.items()},
            "green_list": sorted(self.green_list),
            "cfg": copy.deepcopy(self.cfg),
            "current_stid": self._current_stid,
            "map_color": self.var_map_color.get(),
            "all_stats": self.all_stats,
            "ov_col_vis": {c: v.get() for c, v in self._ov_col_vars.items()},
        }

    def _save_session(self, path=None):
        """Save current session state to a pickle file.

        Args:
            path (str, optional): File path to save to. If None, opens a file dialog
                to prompt the user for a save location. Defaults to None.
        """
        if path is None:
            init_dir = str(self.h5_path.parent) if self.h5_path else "."
            path = filedialog.asksaveasfilename(
                title="Save session",
                defaultextension=".pkl",
                filetypes=[("QC session", "*.pkl"), ("All files", "*.*")],
                initialfile="wx_qc_session.pkl",
                initialdir=init_dir,
            )
            if not path:
                return
        try:
            with open(path, "wb") as session_file:
                pickle.dump(self._session_state(), session_file)
        except (OSError, pickle.PickleError, TypeError, ValueError) as exc:
            messagebox.showerror("Save failed", f"Could not save session to {path}:\n\n{exc}")
            return
        self.lbl_status.config(text=f"Saved: {Path(path).name}")

    def _load_session_file(self, path=None):
        """Load and restore a session from a pickle file.

        Args:
            path (str, optional): File path to load from. If None, opens a file dialog
                to prompt the user for a file. Defaults to None. If file loading fails,
                shows an error message box.
        """
        if path is None:
            path = filedialog.askopenfilename(
                title="Load session",
                filetypes=[("QC session", "*.pkl"), ("All files", "*.*")],
                initialdir=str(AUTOSAVE_PATH.parent),
            )
            if not path:
                return
        try:
            with open(path, "rb") as f:
                sess = pickle.load(f)
            self._restore_session(sess)
        except (OSError, pickle.PickleError, EOFError, AttributeError, TypeError, ValueError) as exc:
            messagebox.showerror("Load failed", f"Could not read session {path}:\n\n{exc}")

    def _restore_session(self, sess):
        """Restore all session state from a saved session dict.

        Restores config, skip/green lists, removal manifest, and H5 data if the
        referenced file exists. If H5 is missing, displays a warning. Calls
        _load_data with cached stats to avoid recomputing; then on completion
        callback refreshes UI (overview, station list, map) and navigates to the
        previously active station.

        Args:
            sess (dict): Session state dict as returned by _session_state() or
                loaded from a pickle file.
        """
        loaded_cfg = dict(sess.get("cfg", {}))
        loaded_cfg.pop("nan_pct", None)
        self.cfg = default_config()
        self.cfg.update(loaded_cfg)
        perim_path = self.cfg.get("perim_h5_path")
        if perim_path and Path(perim_path).exists():
            self._load_perim_h5(Path(perim_path))
        else:
            self._perim_data = []
            self._perim_loaded_path = None
        self.skip_list, self.green_list = resolve_restored_decisions(
            sess.get("skip_list", {}), sess.get("green_list", [])
        )
        # v4: record-removal manifest; older sessions simply have none
        self.removal_list = sess.get("removal_list", {})
        h5 = sess.get("h5_path")
        if h5 and Path(h5).exists():
            self.h5_path = Path(h5)
            self.lbl_file.config(text=str(self.h5_path))
            self.lbl_status.config(text="Loading H5...")

            def _on_complete():
                ov_col_vis = sess.get("ov_col_vis", {})
                if ov_col_vis:
                    for c, var in self._ov_col_vars.items():
                        if c in ov_col_vis:
                            var.set(ov_col_vis[c])
                    self._apply_col_visibility()
                self._refresh_skiplist()
                self._refresh_overview()
                self._refresh_station_list()
                stid = sess.get("current_stid")
                if stid and stid in self.stations:
                    self._navigate_to_station(stid)
                mc = sess.get("map_color")
                if mc:
                    self.var_map_color.set(mc)
                saved_at = sess.get("saved_at", "")[:16]
                self.lbl_status.config(text=f"Session restored  (saved {saved_at})")

            self._load_data(cached_stats=sess.get("all_stats"), on_complete=_on_complete)
        else:
            if h5:
                messagebox.showwarning(
                    "H5 not found", f"Session references:\n{h5}\n\nFile not found. Open it manually."
                )
            self._refresh_skiplist()
            self._refresh_overview()
            self._refresh_station_list()

    def _check_autosave(self):
        """Check for and optionally restore the autosave file on app startup.

        If an autosave exists, displays a dialog with summary info (timestamp, H5
        file name, skip/green counts) and prompts the user to restore it. If the
        user declines or an error occurs, the autosave is left untouched. Errors
        during autosave load/display are logged to the status bar only (not as
        dialog) to avoid crashing on transient Tk/TclErrors.
        """
        if not AUTOSAVE_PATH.exists():
            return
        try:
            with open(AUTOSAVE_PATH, "rb") as f:
                sess = pickle.load(f)
            saved_at = sess.get("saved_at", "unknown")[:16]
            h5_name = Path(sess["h5_path"]).name if sess.get("h5_path") else "—"
            n_skip = len(sess.get("skip_list", {}))
            n_green = len(sess.get("green_list", []))
            msg = (
                f"Autosave found from {saved_at}\n"
                f"File: {h5_name}\n"
                f"Skip: {n_skip}  |  Greenlit: {n_green}\n\n"
                f"Reload this session?"
            )
            if messagebox.askyesno("Restore autosave?", msg):
                self._restore_session(sess)
        except (
            OSError,
            pickle.PickleError,
            EOFError,
            KeyError,
            AttributeError,
            TypeError,
            ValueError,
            tk.TclError,
        ) as exc:
            # Don't re-raise via messagebox — it likely failed the same way
            # (e.g. transient Tk dialog TclError) and would crash as unhandled
            # callback exception. Report to status bar instead.
            try:
                self.lbl_status.config(text=f"Autosave check failed: {exc}")
            except tk.TclError:
                pass

    def _on_quit(self):
        """Handle app quit: save autosave if there is unsaved work, then destroy window.

        Only writes to autosave if at least one of: H5 was loaded, skip_list is
        non-empty, green_list is non-empty, or removal_list is non-empty. This
        avoids overwriting prior autosave with an empty state when closing an
        unused instance. Exceptions during autosave are silently ignored.
        """
        # Only save if there's actual work. Don't overwrite prior autosave
        # with empty state when closing an unused instance.
        if self.h5_path or self.skip_list or self.green_list or self.removal_list:
            try:
                with open(AUTOSAVE_PATH, "wb") as f:
                    pickle.dump(self._session_state(), f)
            except (OSError, pickle.PickleError, TypeError, ValueError):
                pass
        self.destroy()
