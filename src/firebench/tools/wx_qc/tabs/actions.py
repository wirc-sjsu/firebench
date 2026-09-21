"""Review controls for actions in an automated weather-QC manifest."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..pipeline import (
    QCError,
    add_manual_action,
    decide_action,
    edit_action,
    finalize_manifest,
    read_manifest,
)


class ActionsTabMixin:
    """Display and decide durable actions from a weather-QC manifest."""

    def _build_actions_tab(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Actions")
        controls = ttk.Frame(tab)
        controls.pack(fill="x", padx=6, pady=6)
        ttk.Label(controls, text="Reviewer:").pack(side="left")
        self.var_qc_reviewer = tk.StringVar(value=getattr(self, "qc_reviewer", ""))
        ttk.Entry(controls, textvariable=self.var_qc_reviewer, width=24).pack(side="left", padx=(3, 10))
        ttk.Label(controls, text="Status:").pack(side="left")
        self.var_action_status = tk.StringVar(value="all")
        status = ttk.Combobox(
            controls,
            textvariable=self.var_action_status,
            values=(
                "all",
                "pending",
                "auto_accepted",
                "accepted",
                "rejected",
                "acknowledged",
                "superseded",
            ),
            state="readonly",
            width=15,
        )
        status.pack(side="left", padx=3)
        status.bind("<<ComboboxSelected>>", lambda _event: self._refresh_actions())
        ttk.Label(controls, text="Severity:").pack(side="left", padx=(8, 0))
        self.var_action_severity = tk.StringVar(value="all")
        severity = ttk.Combobox(
            controls,
            textvariable=self.var_action_severity,
            values=("all", "ERROR", "WARN", "INFO"),
            state="readonly",
            width=7,
        )
        severity.pack(side="left", padx=3)
        severity.bind("<<ComboboxSelected>>", lambda _event: self._refresh_actions())
        ttk.Button(controls, text="Accept", command=lambda: self._decide_selected("accepted")).pack(
            side="left", padx=2
        )
        ttk.Button(controls, text="Reject", command=lambda: self._decide_selected("rejected")).pack(
            side="left", padx=2
        )
        ttk.Button(
            controls, text="Acknowledge", command=lambda: self._decide_selected("acknowledged")
        ).pack(side="left", padx=2)
        ttk.Button(controls, text="Reset", command=lambda: self._decide_selected("reset")).pack(
            side="left", padx=2
        )
        ttk.Button(controls, text="Edit…", command=self._edit_selected_action).pack(side="left", padx=2)
        self.btn_qc_finalize = ttk.Button(controls, text="Finalize…", command=self._finalize_qc_manifest)
        self.btn_qc_finalize.pack(side="right", padx=2)

        comment_controls = ttk.Frame(tab)
        comment_controls.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(comment_controls, text="Decision comment (optional):").pack(side="left")
        self.var_qc_comment = tk.StringVar(value="")
        ttk.Entry(comment_controls, textvariable=self.var_qc_comment).pack(
            side="left", fill="x", expand=True, padx=(4, 8)
        )
        ttk.Label(comment_controls, text="applies to selected actions").pack(side="left")

        columns = (
            "severity",
            "station",
            "variable",
            "selector",
            "effect",
            "decision",
            "application",
            "message",
        )
        self.tree_actions = ttk.Treeview(tab, columns=columns, show="tree headings", selectmode="extended")
        self.tree_actions.heading("#0", text="Operation ID")
        self.tree_actions.column("#0", width=220, stretch=False)
        self._action_sort_reverse = {}
        widths = (70, 85, 110, 260, 130, 110, 110, 450)
        for column, width in zip(columns, widths):
            self.tree_actions.heading(
                column,
                text=column.title(),
                command=lambda selected_column=column: self._sort_action_tree(selected_column),
            )
            self.tree_actions.column(column, width=width, stretch=column == "message")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.tree_actions.yview)
        self.tree_actions.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_actions.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        self.tree_actions.bind("<Double-1>", self._navigate_from_action)

    def _open_qc_manifest(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Open weather QC manifest",
                filetypes=[("Weather QC manifest", "*.json"), ("All files", "*.*")],
            )
            if not path:
                return
        try:
            manifest = read_manifest(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open failed", f"Could not open QC manifest:\n\n{exc}")
            return
        self.qc_manifest_path = Path(path).resolve()
        self.qc_manifest = manifest
        candidate = Path(manifest["artifacts"]["candidate_h5"])
        self._refresh_actions()
        if candidate.is_file():
            self.h5_path = candidate
            self.lbl_file.config(text=str(candidate))
            self.lbl_status.config(text="Loading QC candidate")
            self._load_data()
        else:
            messagebox.showwarning("Candidate not found", f"Manifest references missing file:\n{candidate}")

    def _refresh_actions(self):
        if not hasattr(self, "tree_actions"):
            return
        for item in self.tree_actions.get_children():
            self.tree_actions.delete(item)
        manifest = getattr(self, "qc_manifest", None)
        if not manifest:
            self.btn_qc_finalize.configure(state="disabled")
            return
        self.btn_qc_finalize.configure(state="disabled" if manifest["summary"]["pending"] else "normal")
        status_filter = self.var_action_status.get()
        severity_filter = self.var_action_severity.get()
        for action in manifest["actions"]:
            decision = action["decision"]["status"]
            if status_filter != "all" and decision != status_filter:
                continue
            if severity_filter != "all" and action["severity"] != severity_filter:
                continue
            target = action["target"]
            application = action["application"].get("final") or action["application"].get("candidate")
            self.tree_actions.insert(
                "",
                "end",
                iid=action["id"],
                text=action["id"],
                values=(
                    action["severity"],
                    target.get("station") or "--",
                    target.get("variable") or "--",
                    self._selector_label(action["selector"]),
                    action["effect"]["kind"],
                    decision,
                    application,
                    action["message"],
                ),
            )

    @staticmethod
    def _selector_label(selector):
        if "predicate" in selector:
            predicate = selector["predicate"]
            return f"{predicate.get('variable')} == {predicate.get('equals')}"
        ranges = selector.get("ranges", [])
        if ranges:
            first = ranges[0]
            suffix = f" (+{len(ranges) - 1} ranges)" if len(ranges) > 1 else ""
            return f"{first.get('start')} → {first.get('end')}{suffix}"
        timestamps = selector.get("timestamps", [])
        if timestamps:
            return f"{len(timestamps)} timestamp(s): {timestamps[0]}"
        return json.dumps(selector, sort_keys=True, separators=(",", ":"))

    def _sort_action_tree(self, column):
        reverse = self._action_sort_reverse.get(column, False)
        rows = [(self.tree_actions.set(item, column), item) for item in self.tree_actions.get_children("")]
        rows.sort(key=lambda pair: pair[0].casefold(), reverse=reverse)
        for index, (_value, item) in enumerate(rows):
            self.tree_actions.move(item, "", index)
        self._action_sort_reverse[column] = not reverse

    def _decide_selected(self, decision):
        selected = list(self.tree_actions.selection())
        if not selected:
            messagebox.showinfo("No actions selected", "Select one or more actions first.")
            return
        reviewer = self.var_qc_reviewer.get().strip()
        if not reviewer:
            reviewer = simpledialog.askstring("Reviewer required", "Reviewer name or identity:") or ""
            reviewer = reviewer.strip()
            if not reviewer:
                return
            self.var_qc_reviewer.set(reviewer)
        comment = self.var_qc_comment.get().strip() or None
        try:
            for action_id in selected:
                self.qc_manifest = decide_action(
                    self.qc_manifest_path, action_id, decision, reviewer, comment
                )
        except (OSError, QCError) as exc:
            messagebox.showerror("Decision failed", str(exc))
            return
        self.qc_reviewer = reviewer
        self.var_qc_comment.set("")
        self._refresh_actions()
        pending = self.qc_manifest["summary"]["pending"]
        self.lbl_status.config(text=f"Saved decisions; {pending} pending")

    def _record_manual_qc_action(self, station, variable, selector, effect, message):
        """Persist a legacy Skip List or range-removal edit in the active manifest."""
        if not getattr(self, "qc_manifest_path", None):
            return True
        reviewer = self.var_qc_reviewer.get().strip()
        if not reviewer:
            reviewer = simpledialog.askstring("Reviewer required", "Reviewer name or identity:") or ""
            reviewer = reviewer.strip()
            if not reviewer:
                return False
            self.var_qc_reviewer.set(reviewer)
        try:
            self.qc_manifest = add_manual_action(
                self.qc_manifest_path,
                station=station,
                variable=variable,
                selector=selector,
                effect=effect,
                message=message,
                reviewer=reviewer,
            )
        except (OSError, QCError) as exc:
            messagebox.showerror("Action could not be recorded", str(exc))
            return False
        self.qc_reviewer = reviewer
        self._refresh_actions()
        return True

    def _edit_selected_action(self):
        selected = list(self.tree_actions.selection())
        if len(selected) != 1:
            messagebox.showinfo("Select one action", "Select exactly one action to edit.")
            return
        reviewer = self.var_qc_reviewer.get().strip()
        if not reviewer:
            messagebox.showerror("Reviewer required", "Enter a reviewer before editing.")
            return
        action = next(item for item in self.qc_manifest["actions"] if item["id"] == selected[0])
        selector_text = simpledialog.askstring(
            "Edit selector", "Selector JSON:", initialvalue=json.dumps(action["selector"], sort_keys=True)
        )
        if selector_text is None:
            return
        effect_text = simpledialog.askstring(
            "Edit effect", "Effect JSON:", initialvalue=json.dumps(action["effect"], sort_keys=True)
        )
        if effect_text is None:
            return
        try:
            selector = json.loads(selector_text)
            effect = json.loads(effect_text)
            self.qc_manifest = edit_action(self.qc_manifest_path, action["id"], selector, effect, reviewer)
        except (json.JSONDecodeError, OSError, QCError) as exc:
            messagebox.showerror("Edit failed", str(exc))
            return
        self._refresh_actions()

    def _navigate_from_action(self, _event=None):
        selected = self.tree_actions.selection()
        if not selected or not getattr(self, "qc_manifest", None):
            return
        action_id = selected[0]
        action = next(item for item in self.qc_manifest["actions"] if item["id"] == action_id)
        station_id = action["target"].get("station")
        if station_id in self.stations:
            self._navigate_to_station(station_id)

    def _finalize_qc_manifest(self):
        if not getattr(self, "qc_manifest_path", None):
            messagebox.showinfo("No manifest", "Open a QC manifest first.")
            return
        reviewer = self.var_qc_reviewer.get().strip()
        if not reviewer:
            messagebox.showerror("Reviewer required", "Enter a reviewer before finalizing.")
            return
        initial = Path(self.qc_manifest["artifacts"]["candidate_h5"])
        path = filedialog.asksaveasfilename(
            title="Write final QC HDF5",
            defaultextension=".h5",
            initialdir=str(initial.parent),
            initialfile=initial.name.replace("candidate", "final"),
            filetypes=[("HDF5", "*.h5")],
        )
        if not path:
            return
        try:
            self.qc_manifest = finalize_manifest(self.qc_manifest_path, path, reviewer)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Finalization blocked", str(exc))
            return
        self._refresh_actions()
        self.lbl_status.config(text=f"Finalized: {Path(path).name}")
        messagebox.showinfo("Finalized", f"Created final weather HDF5:\n{path}")
