"""Headless construction tests for the weather-QC user interface."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

import matplotlib
import pytest

from firebench.tools.wx_qc.constants import default_config
from firebench.tools.wx_qc.pipeline import load_policy

# The application selects TkAgg at import time. A headless CI runner cannot
# activate that interactive backend, so suppress only the selection call while
# importing the classes exercised by these construction tests.
with patch.object(matplotlib, "use"):
    from firebench.tools.wx_qc import app as app_module
    from firebench.tools.wx_qc import dialogs
    from firebench.tools.wx_qc.app import App
    from firebench.tools.wx_qc.tabs import actions as actions_module
    from firebench.tools.wx_qc.tabs.actions import ActionsTabMixin


# Keep the non-interactive backend explicit so this test module cannot affect
# plotting tests collected after it.
matplotlib.use("Agg", force=True)


class FakeVariable:
    def __init__(self, value=None, **_kwargs):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, mode, callback):
        self.traces.append((mode, callback))


class FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.options = dict(kwargs)
        self.children = []
        self.callbacks = {}
        self.text = ""
        self.value = ""

    def __setitem__(self, key, value):
        self.options[key] = value

    def __getitem__(self, key):
        return self.options.get(key)

    def pack(self, **kwargs):
        self.options["pack"] = kwargs
        return self

    def pack_forget(self):
        self.options["packed"] = False

    def grid(self, **kwargs):
        self.options["grid"] = kwargs
        return self

    def add(self, child, **kwargs):
        self.children.append((child, kwargs))

    def bind(self, event, callback):
        self.callbacks[event] = callback

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def heading(self, column, **kwargs):
        self.options.setdefault("headings", {})[column] = kwargs

    def column(self, column, **kwargs):
        self.options.setdefault("column_defs", {})[column] = kwargs

    def tag_configure(self, tag, **kwargs):
        self.options.setdefault("tags", {})[tag] = kwargs

    def insert(self, index, value=None, **_kwargs):
        if isinstance(index, int):
            self.value = str(value)
        return "item"

    def get(self):
        return self.value

    def focus_set(self):
        self.options["focused"] = True

    def select_range(self, *_args):
        self.options["selected"] = True

    def get_tk_widget(self):
        return self

    def mpl_connect(self, event, callback):
        self.callbacks[event] = callback
        return len(self.callbacks)

    def create_line(self, *_args, **_kwargs):
        return "line"

    def place(self, **kwargs):
        self.options["place"] = kwargs

    def itemconfig(self, item, **kwargs):
        self.options.setdefault("items", {})[item] = kwargs

    def yview(self, *_args):
        return None

    def xview(self, *_args):
        return None

    def set(self, *_args):
        return None


class FakeStationPanes(FakeWidget):
    def refresh(self, *_args, **_kwargs):
        return None


def _patch_tk_widgets(monkeypatch):
    for name in ("Frame", "Label", "Canvas", "Menu"):
        monkeypatch.setattr(tk, name, FakeWidget)
    for name in ("StringVar", "BooleanVar", "IntVar", "DoubleVar"):
        monkeypatch.setattr(tk, name, FakeVariable)
    for name in (
        "Frame",
        "LabelFrame",
        "Label",
        "Button",
        "Checkbutton",
        "Radiobutton",
        "Entry",
        "Combobox",
        "Spinbox",
        "Notebook",
        "PanedWindow",
        "Treeview",
        "Scrollbar",
        "Progressbar",
        "Separator",
    ):
        monkeypatch.setattr(ttk, name, FakeWidget)

    monkeypatch.setattr("firebench.tools.wx_qc.tabs.detail.FigureCanvasTkAgg", FakeWidget)
    monkeypatch.setattr("firebench.tools.wx_qc.tabs.detail.NavigationToolbar2Tk", FakeWidget)
    monkeypatch.setattr("firebench.tools.wx_qc.tabs.detail.StationListPanes", FakeStationPanes)
    monkeypatch.setattr("firebench.tools.wx_qc.tabs.map_tab.FigureCanvasTkAgg", FakeWidget)
    monkeypatch.setattr("firebench.tools.wx_qc.tabs.map_tab.NavigationToolbar2Tk", FakeWidget)
    monkeypatch.setattr("firebench.tools.wx_qc.tabs.map_tab.TimeNavigator", FakeWidget)
    monkeypatch.setattr(app_module, "TimeNavigator", FakeWidget)
    monkeypatch.setattr(app_module, "setup_style", lambda _app: {"header_bg": "#123456"})


def test_app_initializes_all_tabs_and_state_without_a_display(monkeypatch):
    _patch_tk_widgets(monkeypatch)
    monkeypatch.setattr(tk.Tk, "__init__", lambda self: None)
    for method in ("title", "geometry", "minsize", "protocol", "bind", "update_idletasks"):
        monkeypatch.setattr(App, method, lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(App, "after", lambda self, _delay, callback: "after-id")
    monkeypatch.setattr(App, "_on_map_mode_change", lambda self, *_args: None)

    application = App()

    assert application.stations == {}
    assert application.skip_list == {}
    assert application.green_list == set()
    assert application._pane_header_bg == "#123456"
    assert len(application.nb.children) == 5
    assert application.nb.children[-1][1]["text"] == "Actions"
    assert application.var_map_basemap.get() is True
    assert application._map_tile_closed is False
    assert application._ts_dragging is False
    assert application.var_qc_comment.get() == ""
    assert "<<TreeviewSelect>>" in application.tree_actions.callbacks


def test_action_decision_uses_inline_optional_comment_without_dialog(monkeypatch):
    recorded = []

    class FakeTree:
        @staticmethod
        def selection():
            return ("WXQC-TEST",)

    class DecisionApp(ActionsTabMixin):
        def __init__(self):
            self.tree_actions = FakeTree()
            self.var_qc_reviewer = FakeVariable("reviewer")
            self.var_qc_comment = FakeVariable("  supporting evidence  ")
            self.qc_manifest_path = Path("qc.json")
            self.qc_manifest = {"summary": {"pending": 1}}
            self.lbl_status = FakeWidget()

        def _refresh_actions(self):
            return None

    def fake_decide(manifest_path, action_id, decision, reviewer, comment):
        recorded.append((manifest_path, action_id, decision, reviewer, comment))
        return {"summary": {"pending": 0}}

    monkeypatch.setattr(actions_module, "decide_action", fake_decide)
    monkeypatch.setattr(
        actions_module.simpledialog,
        "askstring",
        lambda *_args, **_kwargs: pytest.fail("decision should not open a comment dialog"),
    )

    application = DecisionApp()
    application._decide_selected("accepted")

    assert recorded == [(Path("qc.json"), "WXQC-TEST", "accepted", "reviewer", "supporting evidence")]
    assert application.var_qc_comment.get() == ""

    application._decide_selected("rejected")

    assert recorded[-1] == (Path("qc.json"), "WXQC-TEST", "rejected", "reviewer", None)


def test_action_double_click_opens_detail_with_visible_pending_queue_and_audit_mode():
    class FakeTree:
        selected = ("A2",)

        @classmethod
        def selection(cls):
            return cls.selected

        @staticmethod
        def get_children(_parent=""):
            return ("A2", "F1", "A1")

    action_one = {"id": "A1", "decision": {"status": "pending"}}
    action_two = {"id": "A2", "decision": {"status": "pending"}}
    finding = {"id": "F1"}

    class ReviewApp(ActionsTabMixin):
        def __init__(self):
            self.tree_actions = FakeTree()
            self.qc_manifest = {
                "actions": [action_one, action_two],
                "findings": [finding],
            }
            self.opened = []

        def _open_review_item(self, item, queue, read_only=False, switch_to_detail=True):
            self.opened.append((item["id"], queue, read_only))

    application = ReviewApp()
    application._navigate_from_action()
    assert application.opened[-1] == ("A2", ["A2", "A1"], False)

    FakeTree.selected = ("F1",)
    application._navigate_from_action()
    assert application.opened[-1] == ("F1", ["A2", "A1"], True)


def test_action_selection_updates_hidden_detail_and_sort_refreshes_queue():
    class FakeTree:
        selected = ("A2",)
        focused = "A2"
        order = ["A2", "A1"]
        values = {"A1": "Alpha", "A2": "Zulu"}

        @classmethod
        def selection(cls):
            return cls.selected

        @classmethod
        def focus(cls):
            return cls.focused

        @classmethod
        def get_children(cls, _parent=""):
            return tuple(cls.order)

        @classmethod
        def set(cls, item, _column):
            return cls.values[item]

        @classmethod
        def move(cls, item, _parent, index):
            cls.order.remove(item)
            cls.order.insert(index, item)

    action_one = {"id": "A1", "decision": {"status": "pending"}}
    action_two = {"id": "A2", "decision": {"status": "pending"}}

    class ReviewApp(ActionsTabMixin):
        def __init__(self):
            self.tree_actions = FakeTree()
            self.qc_manifest = {"actions": [action_one, action_two], "findings": []}
            self._action_sort_reverse = {}
            self.opened = []

        def _open_review_item(self, item, queue, read_only=False, switch_to_detail=True):
            self._active_review_item = {"item": item, "read_only": read_only}
            self._active_review_queue = list(queue)
            self.opened.append((item["id"], list(queue), switch_to_detail))

        def _configure_review_controls(self):
            self.configured = True

    application = ReviewApp()
    application._select_review_from_action()
    assert application.opened[-1] == ("A2", ["A2", "A1"], False)

    application._sort_action_tree("station")
    assert FakeTree.order == ["A1", "A2"]
    assert application._active_review_queue == ["A1", "A2"]
    assert application.configured is True


def test_actions_table_includes_only_unlinked_findings_as_read_only_audit_rows():
    class FakeTree:
        def __init__(self):
            self.rows = {}

        def get_children(self, _parent=""):
            return tuple(self.rows)

        def delete(self, item):
            self.rows.pop(item)

        def insert(self, _parent, _position, *, iid, text, values):
            self.rows[iid] = {"text": text, "values": values}

    action = {
        "id": "A1",
        "severity": "WARN",
        "target": {"station": "A", "variable": "wind_speed"},
        "selector": {},
        "effect": {"kind": "no_change"},
        "decision": {"status": "pending"},
        "application": {"candidate": "not_applied_pending", "final": "not_built"},
        "message": "review",
        "linked_findings": ["F1"],
    }
    linked = {
        "id": "F1",
        "severity": "WARN",
        "target": {"station": "A", "variable": "wind_speed"},
        "message": "linked",
    }
    audit = {
        "id": "F2",
        "severity": "INFO",
        "target": {"station": "B", "variable": "air_temperature"},
        "selector": {},
        "message": "audit only",
    }

    class RefreshApp(ActionsTabMixin):
        def __init__(self):
            self.tree_actions = FakeTree()
            self.btn_qc_finalize = FakeWidget()
            self.lbl_action_review = FakeWidget()
            self.var_action_status = FakeVariable("all")
            self.var_action_severity = FakeVariable("all")
            self._action_sort_column = None
            self.qc_manifest = {
                "actions": [action],
                "findings": [linked, audit],
                "summary": {
                    "pending": 1,
                    "actions": 1,
                    "review_actions": 1,
                    "pending_fraction": 1.0,
                    "target_pending_fraction": 0.05,
                },
            }

    application = RefreshApp()
    application._refresh_actions()
    assert set(application.tree_actions.rows) == {"A1", "F2"}
    assert application.tree_actions.rows["F2"]["values"][5:7] == ("audit", "read_only")

    application.var_action_status.set("audit")
    application._refresh_actions()
    assert set(application.tree_actions.rows) == {"F2"}


def test_open_manifest_applies_its_normalized_frozen_settings(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.h5"
    candidate.touch()
    policy = load_policy(None)
    policy["frozen"]["minimum_duration_hours"]["air_temperature"] = 12.0
    manifest = {
        "policy": {"normalized": policy},
        "artifacts": {"candidate_h5": str(candidate)},
        "summary": {"pending": 0},
    }

    class ManifestApp(ActionsTabMixin):
        def __init__(self):
            self.cfg = default_config()
            self.lbl_file = FakeWidget()
            self.lbl_status = FakeWidget()
            self.loaded = False

        def _refresh_actions(self):
            return None

        def _load_data(self):
            self.loaded = True

    monkeypatch.setattr(actions_module, "read_manifest", lambda _path: manifest)

    application = ManifestApp()
    application._open_qc_manifest(tmp_path / "manifest.json")

    assert application.cfg["frozen_min_duration_hours"]["air_temperature"] == 12.0
    assert application.h5_path == candidate
    assert application.loaded


def test_small_decision_dialogs_build_and_return_stripped_values(monkeypatch):
    _patch_tk_widgets(monkeypatch)
    monkeypatch.setattr(tk.Toplevel, "__init__", lambda self, _parent=None: None)
    for cls in (dialogs.AddSkipDialog, dialogs.AddRemovalDialog):
        for method in ("title", "resizable", "bind", "grab_set", "destroy"):
            monkeypatch.setattr(cls, method, lambda self, *_args, **_kwargs: None)

    skip = dialogs.AddSkipDialog(None, "ABC", "  default reason  ")
    skip._ok()
    assert skip.result == "default reason"

    removal = dialogs.AddRemovalDialog(None, "ABC", "wind", "start", "end", 2)
    removal.entry.value = "  bad range  "
    removal.var_scope.set("*")
    removal._ok()
    assert removal.result == ("*", "bad range")


def test_settings_and_export_dialogs_construct_from_current_configuration(monkeypatch):
    _patch_tk_widgets(monkeypatch)
    monkeypatch.setattr(tk.Toplevel, "__init__", lambda self, _parent=None: None)
    for cls in (dialogs.SettingsDialog, dialogs.ExportScriptDialog):
        for method in ("title", "resizable", "bind", "grab_set", "destroy", "transient"):
            monkeypatch.setattr(cls, method, lambda self, *_args, **_kwargs: None, raising=False)

    cfg = app_module.default_config()
    settings = dialogs.SettingsDialog(
        None,
        cfg,
        cfg["bounds"],
        ("Name", "Issues"),
        {"AirT Max": ("air_temperature", "max")},
        {"Name": True, "Issues": False, "AirT Max": True},
        {"air_temperature": "AirT"},
    )
    assert set(settings._bound_entries) == set(cfg["bounds"])
    assert settings.result is None

    export = dialogs.ExportScriptDialog(None, Path("/tmp/weather.h5"))
    assert export.result is None
    assert export.e_output_h5.value == "weather.h5"
