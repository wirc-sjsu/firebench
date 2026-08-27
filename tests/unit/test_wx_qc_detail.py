"""Headless interaction tests for the weather-QC detail tab."""

from types import SimpleNamespace

import matplotlib
import numpy as np
from matplotlib.figure import Figure

from firebench.tools.wx_qc.constants import default_config
from firebench.tools.wx_qc.tabs.detail import DetailTabMixin


matplotlib.use("Agg", force=True)


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self):
        self.options = {}
        self.selected = ()

    def __setitem__(self, key, value):
        self.options[key] = value

    def config(self, **kwargs):
        self.options.update(kwargs)

    def selection(self):
        return self.selected


class FakeCanvas:
    def __init__(self):
        self.draws = 0

    def draw_idle(self):
        self.draws += 1

    draw = draw_idle


class FakeNotebook:
    def __init__(self):
        self.current = 1
        self.selected = None
        self.states = {}

    def tab(self, idx, **kwargs):
        self.states[idx] = kwargs

    def index(self, _which):
        return self.current

    def select(self, idx):
        self.selected = idx
        self.current = idx


class FakePanes:
    def __init__(self, selected=()):
        self.selected = set(selected)
        self.refresh_args = None

    def get_selected(self):
        return set(self.selected)

    def select_only(self, stid):
        self.selected = {stid}

    def select_many(self, stids):
        self.selected = set(stids)

    def refresh(self, *args, **kwargs):
        self.refresh_args = (args, kwargs)


class DetailApp(DetailTabMixin):
    def __init__(self):
        self.cfg = default_config()
        self.cfg["compare_n_neighbors"] = 2
        self.stids = ["A", "B", "C", "D"]
        variables = {
            "air_temperature": np.array([10.0, 11.0, 12.0]),
            "wind_speed": np.array([1.0, 2.0, 3.0]),
            "wind_direction": np.array([90.0, 100.0, 110.0]),
        }
        self.stations = {
            stid: {
                "lat": float(idx),
                "lon": float(idx),
                "variables": dict(variables if stid != "D" else {"wind_speed": variables["wind_speed"]}),
            }
            for idx, stid in enumerate(self.stids)
        }
        self.all_issues = {
            "A": [("ERROR", "hi:air_temperature", "hot")],
            "B": [("WARN", "frozen:air_temperature", "frozen")],
            "C": [],
            "D": [],
        }
        self.skip_list = {}
        self.green_list = set()
        self.removal_list = {}
        self._all_ov_cols = ("STID", "Score", "Name")
        self._detail_sort_col = FakeVariable("Score")
        self._detail_sort_desc = False
        self._detail_sort_combo = FakeWidget()
        self.btn_detail_sort_dir = FakeWidget()
        self.detail_panes = FakePanes({"A"})
        self.nb = FakeNotebook()
        self.detail_nb = FakeNotebook()
        self.btn_ts_compare = FakeWidget()
        self.btn_ts_remove = FakeWidget()
        self.btn_ts_locate = FakeWidget()
        self.lbl_status = FakeWidget()
        self.var_ts_var = FakeVariable("air_temperature")
        self.var_ts_reason = FakeVariable("")
        self.var_compare_n = FakeVariable(2)
        self._ts_var_order = ["air_temperature", "wind", "relative_humidity"]
        self._ts_avail_vars = ["air_temperature", "wind"]
        self._current_stid = "A"
        self._ts_plot_gen = 0
        self._ts_range_artist = None
        self._ts_range_sel = None
        self._ts_range_anchor = None
        self._ts_range_dragging = False
        self._ts_shift_press = None
        self._ts_dragging = False
        self._ts_sel_idx = None
        self._ts_sel_artist = None
        self._ts_sel_annot = None
        self._ts_times = np.array(
            ["2020-01-01T00:00", "2020-01-01T01:00", "2020-01-01T02:00"], dtype="datetime64[m]"
        )
        self._ts_xnum = np.array([1.0, 2.0, 3.0])
        self._ts_data = np.array([10.0, np.nan, 12.0])
        self._ts_wd = None
        self._ts_vname = "air_temperature"
        self._ts_units = "C"
        self.ax_ts = Figure().subplots()
        self.ax_ts.set_ylim(0, 20)
        self.canvas_ts = FakeCanvas()
        self.refreshes = []
        self.prompts = []

    def _ov_row_values(self, stid):
        values = {
            "A": ("A", "10.0%", "Zulu"),
            "B": ("B", "--", "Alpha"),
            "C": ("C", "2.0%", "Mike"),
            "D": ("D", "5.0%", "Bravo"),
        }
        return "ok", values[stid]

    def _refresh_skiplist(self):
        self.refreshes.append("skiplist")

    def _refresh_overview(self, **_kwargs):
        self.refreshes.append("overview")

    def _refresh_map(self):
        self.refreshes.append("map")

    def _refresh_removals(self):
        self.refreshes.append("removals")

    def _refresh_detail_view(self, *_args):
        self.refreshes.append("detail")

    def _prompt_add_skip(self, stid, reason, switch_tab=True):
        self.prompts.append((stid, reason, switch_tab))

    def _add_to_skip(self, stid, reason, switch_tab=True):
        self.prompts.append((stid, reason, switch_tab))

    def _plot_timeseries(self):
        self.refreshes.append("plot")

    def _map_open_popup(self, stid):
        self.prompts.append(("map", stid))


def test_detail_sorting_status_refresh_and_direction_toggle():
    app = DetailApp()
    key, display = app._detail_sort_maps()
    assert sorted(app.stids, key=key) == ["C", "D", "A", "B"]
    assert display("B") is None

    app._detail_sort_desc = True
    key, _ = app._detail_sort_maps()
    assert sorted(app.stids, key=key) == ["B", "A", "D", "C"]

    app._detail_sort_col.set("Name")
    app._detail_sort_desc = False
    key, _ = app._detail_sort_maps()
    assert sorted(app.stids, key=key) == ["B", "D", "C", "A"]

    app._refresh_station_list()
    _, kwargs = app.detail_panes.refresh_args
    status = kwargs["status_fn"]
    assert status("A") == "[!] "
    assert status("B") == "[~] "
    assert status("C") == "[ ] "

    app._toggle_detail_sort_dir()
    assert app.btn_detail_sort_dir.options["text"] == "▼"


def test_detail_station_decisions_navigation_and_tab_state(monkeypatch):
    app = DetailApp()
    app.detail_panes.selected = {"A", "B"}
    app._detail_add_greenlit()
    assert app.green_list == {"A", "B"}
    app._station_list_ungreenlit()
    assert app.green_list == set()

    class FakeDialog:
        def __init__(self, *_args, **_kwargs):
            self.result = "batch"

    monkeypatch.setattr("firebench.tools.wx_qc.tabs.detail.AddSkipDialog", FakeDialog)
    app.wait_window = lambda _dialog: None
    app._detail_add_skip_batch()
    assert app.skip_list == {"A": "batch", "B": "batch"}
    assert app.nb.selected == 3

    app._navigate_to_station("C")
    assert app.detail_panes.selected == {"C"}
    app._current_stid = "C"
    app._detail_locate_on_map()
    assert app.nb.selected == 2
    assert app.prompts[-1] == ("map", "C")

    app.detail_nb.current = 2
    app._set_single_station_tabs_enabled(False)
    assert app.detail_nb.selected == 0
    assert app.btn_ts_compare.options["state"] == "disabled"
    app._set_single_station_tabs_enabled(True)
    assert app.btn_ts_locate.options["state"] == "normal"


def test_detail_compare_variable_cycles_and_configuration(monkeypatch):
    app = DetailApp()
    app._ts_prev_var()
    assert app.var_ts_var.get() == "wind"
    app._ts_next_var()
    assert app.var_ts_var.get() == "air_temperature"

    app.var_compare_n.set("invalid")
    app._on_compare_n_change()
    assert app.var_compare_n.get() == 2
    app.var_compare_n.set(-3)
    app._on_compare_n_change()
    assert app.cfg["compare_n_neighbors"] == 1

    app._current_stid = "A"
    app.var_ts_var.set("air_temperature")
    app.skip_list["B"] = "skip"
    app._ts_compare_nearest()
    assert app.detail_panes.selected == {"A", "C"}
    assert app._ts_compare_source == "A"

    notices = []
    monkeypatch.setattr(
        "firebench.tools.wx_qc.tabs.detail.messagebox.showinfo",
        lambda *args: notices.append(args),
    )
    app._current_stid = None
    app._ts_compare_nearest()
    app._current_stid = "A"
    app.var_ts_var.set("")
    app._ts_compare_nearest()
    assert notices[-1][0] == "No variable"


def _event(app, xdata, *, shift=False, x=10, y=10, inaxes=True):
    return SimpleNamespace(
        inaxes=app.ax_ts if inaxes else None,
        button=1,
        xdata=xdata,
        x=x,
        y=y,
        key="shift" if shift else None,
        guiEvent=None,
    )


def test_detail_point_and_range_selection_interactions():
    app = DetailApp()
    assert app._ts_nearest_idx(None) is None
    assert app._ts_nearest_idx(1.1) == 0
    assert app._ts_nearest_idx(2.8) == 2

    app._on_ts_press(_event(app, 1.1))
    assert app._ts_sel_idx == 0
    app._on_ts_motion(_event(app, 2.9))
    assert app._ts_sel_idx == 2

    app._on_ts_press(_event(app, 1.0, shift=True, x=0, y=0))
    app._on_ts_motion(_event(app, 3.0, shift=True, x=10, y=0))
    assert app._ts_range_sel == (0, 2)
    app._on_ts_release(_event(app, 3.0, shift=True, x=10, y=0))
    assert app._ts_range_sel == (0, 2)

    app._ts_wd = np.array([90.0, 180.0, 270.0])
    app._ts_sel_idx = 1
    app._ts_update_selection()
    assert app._ts_sel_artist is not None
    assert app.canvas_ts.draws > 0
    app._ts_clear_range_sel()
    assert app._ts_range_sel is None


def test_detail_removal_manifest_overlays_and_dialog_scopes(monkeypatch):
    app = DetailApp()
    app._add_removal("A", "air_temperature", "2020-01-01T00:00", "2020-01-01T00:00", "bad")
    app._add_removal("A", "air_temperature", "2020-01-01T00:00", "2020-01-01T00:00", "bad")
    assert len(app.removal_list["A"]) == 1
    app._draw_removal_overlays(app.ax_ts, ("air_temperature",))
    assert len(app.ax_ts.patches) >= 1

    results = iter([("*", "all bad"), ("var", "wind bad")])

    class FakeRemovalDialog:
        def __init__(self, *_args, **_kwargs):
            self.result = next(results)

    monkeypatch.setattr("firebench.tools.wx_qc.tabs.detail.AddRemovalDialog", FakeRemovalDialog)
    app.wait_window = lambda _dialog: None
    app._ts_range_sel = (0, 1)
    app._ts_remove_records()
    assert app.removal_list["A"][-1]["var"] == "*"

    app.var_ts_var.set("wind")
    app._ts_range_sel = None
    app._ts_sel_idx = 2
    app._ts_remove_records()
    variables = {entry["var"] for entry in app.removal_list["A"]}
    assert {"wind_speed", "wind_direction"} <= variables
    assert app.lbl_status.options["text"].startswith("Marked 1 record")


def test_detail_skip_actions_and_reason_abbreviations(monkeypatch):
    app = DetailApp()
    notices = []
    monkeypatch.setattr(
        "firebench.tools.wx_qc.tabs.detail.messagebox.showinfo",
        lambda *args: notices.append(args),
    )
    app.var_ts_reason.set("  manual reason  ")
    app._ts_add_skip()
    assert app.prompts[-1] == ("A", "manual reason", False)

    app.tv_vs = FakeWidget()
    app.tv_vs.selected = ("air_temperature",)
    app._vs_add_skip()
    assert app.prompts[-1] == ("A", "AT QC", False)

    app.tv_assert = FakeWidget()
    app.tv_assert.selected = ("0",)
    app._assert_add_skip()
    assert app.prompts[-1] == ("A", "AT range", False)

    assert app._short_reason("dropout") == "WD dropout"
    assert app._short_reason("dup_ts") == "Dup timestamps"
    assert app._short_reason("time_neg") == "Timestamp jump"
    assert app._short_reason("gap_dt") == "Big time gap"
    assert app._short_reason("max_var_outage") == "Var outage"
    assert app._short_reason("full_outage") == "Full outage"
    assert app._short_reason("frozen:wind_speed") == "WS frozen"
    assert app._short_reason("custom") == "custom"
