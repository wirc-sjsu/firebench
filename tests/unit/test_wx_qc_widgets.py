"""Headless behavioral tests for the reusable weather-QC widgets."""

from types import SimpleNamespace

import numpy as np
import pytest

from firebench.tools.wx_qc.widgets import StationListPanes, TimeNavigator


class FakeLabel:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


class FakeBody:
    def __init__(self):
        self.packed = True

    def pack(self, **_kwargs):
        self.packed = True

    def pack_forget(self):
        self.packed = False


class FakeTree:
    def __init__(self):
        self.rows = {}
        self.order = []
        self.options = {}
        self.headings = {}
        self.seen = []
        self.hit_row = ""
        self.hit_region = "cell"

    def __setitem__(self, key, value):
        self.options[key] = value

    def delete(self, *iids):
        for iid in iids:
            self.rows.pop(iid, None)
            if iid in self.order:
                self.order.remove(iid)

    def insert(self, _parent, index, iid, text, values, tags):
        self.rows[iid] = {"text": text, "values": dict(zip(StationListPanes._COLS, values)), "tags": tags}
        if index == "end":
            self.order.append(iid)
        else:
            self.order.insert(index, iid)

    def get_children(self, _parent=""):
        return tuple(self.order)

    def item(self, iid, option=None, **kwargs):
        if kwargs:
            self.rows[iid].update(kwargs)
        if option is not None:
            return self.rows[iid][option]
        return self.rows[iid]

    def set(self, iid, column):
        return self.rows[iid]["values"].get(column, "")

    def move(self, iid, _parent, index):
        self.order.remove(iid)
        self.order.insert(index, iid)

    def heading(self, column, **kwargs):
        self.headings[column] = kwargs

    def see(self, iid):
        self.seen.append(iid)

    def identify_region(self, _x, _y):
        return self.hit_region

    def identify_row(self, _y):
        return self.hit_row


def _station_panes():
    panes = object.__new__(StationListPanes)
    panes.selected = set()
    panes._order = {cat: [] for cat, _, _ in panes._CATS}
    panes._last_idx = {cat: None for cat, _, _ in panes._CATS}
    panes.trees = {cat: FakeTree() for cat, _, _ in panes._CATS}
    panes._labels = {cat: FakeLabel() for cat, _, _ in panes._CATS}
    panes._bodies = {cat: FakeBody() for cat, _, _ in panes._CATS}
    panes._toggle_btns = {cat: FakeLabel() for cat, _, _ in panes._CATS}
    panes._collapsed = {cat: False for cat, _, _ in panes._CATS}
    panes._col_visible = {c: True for c in panes._COLS}
    panes._sort_state = {cat: (None, False) for cat, _, _ in panes._CATS}
    panes._sort_key_fn = None
    panes._display_fn = None
    panes.on_click = None
    panes.on_select_change = None
    return panes


def test_station_panes_refresh_move_sort_and_visibility():
    panes = _station_panes()
    panes.refresh(
        ["B", "A", "C"],
        {"B": "bad sensor"},
        {"C"},
        status_fn=lambda stid: "[!]" if stid == "A" else "[ ]",
        sort_key_fn=lambda stid: stid,
    )

    assert panes._order == {"kept": ["A"], "skipped": ["B"], "greenlit": ["C"]}
    assert panes.trees["kept"].set("A", "status") == "ERR"
    assert panes.trees["skipped"].set("B", "reason") == "bad sensor"

    panes.selected = {"A"}
    panes.refresh(["B", "A", "C"], {"A": "manual"}, {"C"})
    assert panes._order["kept"] == ["B"]
    assert panes._order["skipped"] == ["A"]
    assert panes.trees["skipped"].item("A", "tags") == ("sel",)

    panes._sort_by("kept", "#0")
    panes._sort_by("kept", "#0")
    assert panes._sort_state["kept"] == ("#0", True)
    assert panes.trees["kept"].headings["#0"]["text"].endswith("▼")

    panes._col_visible["reason"] = False
    panes._apply_col_visibility()
    assert panes.trees["kept"].options["displaycolumns"] == ["status"]
    panes._toggle("kept")
    assert panes._bodies["kept"].packed is False
    panes._toggle("kept")
    assert panes._bodies["kept"].packed is True


def test_station_panes_selection_click_gestures_and_display_override():
    panes = _station_panes()
    changes = []
    clicks = []
    panes.on_click = clicks.append
    panes.on_select_change = lambda: changes.append(set(panes.selected))
    panes.refresh(
        ["A", "B", "C"],
        {},
        set(),
        display_fn=lambda stid: "shown" if stid == "A" else None,
    )
    tree = panes.trees["kept"]
    assert tree.set("A", "reason") == "shown"

    tree.hit_row = "B"
    assert panes._on_click(SimpleNamespace(x=1, y=1), "kept") == "break"
    assert panes.get_selected() == {"B"}
    assert clicks == ["B"]

    tree.hit_row = "C"
    panes._on_ctrl_click(SimpleNamespace(x=1, y=1), "kept")
    assert panes.selected == {"B", "C"}
    tree.hit_row = "A"
    panes._on_shift_click(SimpleNamespace(x=1, y=1), "kept")
    assert panes.selected == {"A", "B", "C"}
    assert len(changes) == 2

    panes.select_many({"A", "missing"})
    assert panes.selected == {"A"}
    panes.select_only("C")
    assert panes.selected == {"C"}
    assert tree.seen[-1] == "C"

    tree.hit_region = "heading"
    assert panes._on_click(SimpleNamespace(x=1, y=1), "kept") is None
    tree.hit_region = "cell"
    tree.hit_row = ""
    assert panes._on_ctrl_click(SimpleNamespace(x=1, y=1), "kept") == "break"


class FakeNavigator(TimeNavigator):
    """TimeNavigator instance that records canvas operations without Tk."""

    def __init__(self):
        self._height = 56
        self._min_dur = 1.0
        self._lo = self._hi = None
        self._vlo = self._vhi = None
        self._start = 0.0
        self._dur = 2.0
        self._sx = self._sy = None
        self._pane_fill = "#eeeeee"
        self._drag = None
        self._pan_grab = 0.0
        self._hover = False
        self._on_change = None
        self.operations = []
        self.cursor = None

    def winfo_width(self):
        return 300

    def delete(self, *args):
        self.operations.append(("delete", args))

    def create_rectangle(self, *args, **kwargs):
        self.operations.append(("rectangle", args, kwargs))
        return len(self.operations)

    def create_polygon(self, *args, **kwargs):
        self.operations.append(("polygon", args, kwargs))
        return len(self.operations)

    def create_line(self, *args, **kwargs):
        self.operations.append(("line", args, kwargs))
        return len(self.operations)

    def create_text(self, *args, **kwargs):
        self.operations.append(("text", args, kwargs))
        return len(self.operations)

    def bbox(self, _item):
        return (0, -4, 320, 10)

    def move(self, *args):
        self.operations.append(("move", args))

    def tag_raise(self, *args):
        self.operations.append(("raise", args))

    def configure(self, **kwargs):
        self.cursor = kwargs.get("cursor")


for _name in (
    "set_domain",
    "set_valid_range",
    "set_window",
    "get_window",
    "nudge",
    "has_series",
    "set_series",
    "_has_domain",
    "_plot_w",
    "_track_bottom",
    "_x_to_data",
    "_data_to_x",
    "_valid_range",
    "_clamp",
    "_redraw",
    "_draw_sparkline",
    "_draw_unavailable",
    "_draw_ticks",
    "_draw_pane_fill",
    "_draw_pane_frame",
    "_nudge_rect",
    "_draw_nudge_buttons",
    "_in_nudge_button",
    "_draw_popup",
    "_fire",
    "_resize_zone",
    "_on_press",
    "_on_drag",
    "_on_release",
    "_on_motion",
    "_on_enter",
    "_on_leave",
):
    setattr(FakeNavigator, _name, getattr(TimeNavigator, _name))


def test_time_navigator_domain_series_and_drawing():
    nav = FakeNavigator()
    fired = []
    nav._on_change = lambda start, dur, final: fired.append((start, dur, final))

    nav.set_domain(10.0, 20.0)
    nav.set_valid_range(12.0, 18.0)
    nav.set_window(0.0, 0.25)
    assert nav.get_window() == (12.0, 1.0)
    nav.nudge(1)
    assert fired[-1] == (12.25, 1.0, True)

    nav.set_series([9, 10, 12, np.nan, 18, 21], [2, 2, 4, 9, 1, 3])
    assert nav.has_series()
    nav._hover = True
    nav._redraw()
    kinds = {op[0] for op in nav.operations}
    assert {"rectangle", "polygon", "line", "text", "move", "raise"} <= kinds
    assert nav._x_to_data(nav._data_to_x(15.0)) == pytest.approx(15.0)
    assert nav._in_nudge_button(3, 5) == -1
    assert nav._in_nudge_button(290, 5) == 1

    nav.set_series(None, None)
    assert not nav.has_series()
    assert TimeNavigator._tint("#000000", 0.5) == "#808080"
    assert TimeNavigator._fmt_dur(0.5) == "12 h"
    assert TimeNavigator._fmt_dur(2.5) == "2.5 d"


def test_time_navigator_mouse_pan_resize_jump_and_cursor():
    nav = FakeNavigator()
    nav.set_domain(0.0, 10.0)
    nav.set_valid_range(1.0, 9.0)
    nav.set_window(2.0, 3.0)
    fired = []
    nav._on_change = lambda start, dur, final: fired.append((start, dur, final))

    inside = SimpleNamespace(x=nav._data_to_x(3.0), y=10)
    nav._on_press(inside)
    assert nav._drag == "pan"
    nav._on_drag(SimpleNamespace(x=nav._data_to_x(4.0), y=10))
    nav._on_release(SimpleNamespace(x=0, y=0))
    assert fired[-1][2] is True

    edge = SimpleNamespace(x=nav._data_to_x(nav._start + nav._dur), y=10)
    nav._on_press(edge)
    assert nav._drag == "resize"
    nav._on_drag(SimpleNamespace(x=nav._data_to_x(8.0), y=10))
    nav._on_release(edge)
    assert nav._dur >= nav._min_dur

    nav._on_press(SimpleNamespace(x=nav._data_to_x(1.0), y=40))
    assert nav._drag == "pan"
    nav._on_release(inside)
    nav._on_press(SimpleNamespace(x=3, y=5))
    assert fired[-1][2] is True

    nav._on_motion(SimpleNamespace(x=3, y=5))
    assert nav.cursor == "hand2"
    nav._on_motion(SimpleNamespace(x=150, y=10))
    assert nav.cursor in {"fleur", "arrow", "sb_h_double_arrow"}
    nav._on_enter(None)
    assert nav._hover is True
    nav._on_leave(None)
    assert nav._hover is False


def test_time_navigator_invalid_domain_and_range_fallbacks():
    nav = FakeNavigator()
    assert nav._clamp(-1.0, 100.0) == (-1.0, 100.0)
    nav.nudge(1)
    nav._on_drag(SimpleNamespace(x=5, y=5))
    nav._on_motion(SimpleNamespace(x=5, y=5))
    assert nav.cursor == "arrow"

    nav.set_domain(0.0, 4.0)
    nav.set_valid_range(2.0, 2.5)
    assert nav._valid_range() == (0.0, 4.0)
    nav.set_window(-10.0, 20.0)
    assert nav.get_window() == (0.0, 4.0)
