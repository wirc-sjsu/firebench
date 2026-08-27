"""Headless construction tests for the weather-QC user interface."""

import tkinter as tk
from tkinter import ttk
from pathlib import Path

import matplotlib

from firebench.tools.wx_qc import app as app_module
from firebench.tools.wx_qc import dialogs
from firebench.tools.wx_qc.app import App


# Importing the GUI intentionally selects TkAgg. Restore the non-interactive
# backend so this test module cannot affect plotting tests collected after it.
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
    assert len(application.nb.children) == 4
    assert application.var_map_basemap.get() is True
    assert application._map_tile_closed is False
    assert application._ts_dragging is False


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
