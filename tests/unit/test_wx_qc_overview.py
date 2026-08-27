"""Headless behavioral tests for the weather-QC overview tab."""

from types import SimpleNamespace

from firebench.tools.wx_qc.constants import default_config
from firebench.tools.wx_qc.tabs.overview import OverviewTabMixin


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.options = {}

    def config(self, **kwargs):
        self.options.update(kwargs)


class FakeNotebook:
    def __init__(self):
        self.selected = "overview"

    def select(self, value=None):
        if value is not None:
            self.selected = value
        return self.selected


class FakeDetailPanes:
    def __init__(self):
        self.only = None
        self.many = None

    def select_only(self, stid):
        self.only = stid

    def select_many(self, stids):
        self.many = tuple(stids)


class FakeTree:
    def __init__(self, columns):
        self.columns = columns
        self.rows = {}
        self.order = []
        self.selected = ()
        self.options = {}
        self.tag_calls = []
        self.updates = 0

    def __setitem__(self, key, value):
        self.options[key] = value

    def get_children(self):
        return tuple(self.order)

    def delete(self, *iids):
        for iid in iids:
            self.rows.pop(iid, None)
            if iid in self.order:
                self.order.remove(iid)

    def insert(self, _parent, index, iid, tags, values):
        self.rows[iid] = {"tags": tags, "values": tuple(values)}
        if index == "end":
            self.order.append(iid)
        else:
            self.order.insert(index, iid)

    def exists(self, iid):
        return iid in self.rows

    def item(self, iid, **kwargs):
        self.rows[iid].update(kwargs)

    def set(self, iid, column):
        return str(self.rows[iid]["values"][self.columns.index(column)])

    def move(self, iid, _parent, index):
        self.order.remove(iid)
        self.order.insert(index, iid)

    def selection(self):
        return self.selected

    def tag_configure(self, tag, **kwargs):
        self.tag_calls.append((tag, kwargs))

    def update(self):
        self.updates += 1


class OverviewApp(OverviewTabMixin):
    def __init__(self):
        self.cfg = default_config()
        self.skip_list = {}
        self.green_list = set()
        self._ov_show_greenlit = FakeVariable(False)
        self.stations = {
            "ERR": {
                "name": "Error station",
                "state": "CA",
                "variables": {"air_temperature": [1], "wind_direction": [2]},
            },
            "OK": {"name": "Okay station", "state": "NV", "variables": {"air_temperature": [1]}},
        }
        base_time = {
            "n_pts": 3,
            "avg_freq_min": 5.0,
            "max_var_outage_min": 30.0,
            "full_outage_min": None,
        }
        self.all_stats = {
            "ERR": {
                "_time": dict(base_time),
                "air_temperature": {
                    "max": 30.0,
                    "min": 10.0,
                    "mean": 20.0,
                    "std": 2.5,
                    "nan_pct": 1.0,
                    "outage_pct": 12.5,
                    "longest_gap_hr": 2.0,
                },
                "wind_direction": {
                    "max": 350.0,
                    "min": 5.0,
                    "mean": 180.0,
                    "std": 20.0,
                    "nan_pct": 4.0,
                    "wd_nan_ws_pos_pct": 3.0,
                    "outage_pct": None,
                    "longest_gap_hr": None,
                },
            },
            "OK": {
                "_time": {**base_time, "avg_freq_min": None, "max_var_outage_min": None},
                "air_temperature": {
                    "max": None,
                    "min": None,
                    "mean": None,
                    "std": None,
                    "nan_pct": 0.0,
                    "outage_pct": None,
                    "longest_gap_hr": None,
                },
            },
        }
        self.all_issues = {"ERR": [("ERROR", "physical_bounds", "too hot")], "OK": []}
        self._all_ov_cols = self._OV_BASE_COLS + ("AirT Max", "AirT Std", "AirT Cumulative Outage %")
        self._ov_var_col_map = {
            "AirT Max": ("air_temperature", "max"),
            "AirT Std": ("air_temperature", "std"),
            "AirT Cumulative Outage %": ("air_temperature", "outage_pct"),
        }
        self._ov_row_cache = {}
        self._ov_rendered = set()
        self.stids = ["ERR", "OK"]
        self.tv_ov = FakeTree(self._all_ov_cols)
        self._ov_sort_col = "STID"
        self._ov_sort_rev = False
        self._ov_col_vars = {c: FakeVariable(True) for c in self._all_ov_cols if c != "STID"}
        self.nb = FakeNotebook()
        self._ov_tab_frame = "overview"
        self.detail_panes = FakeDetailPanes()
        self.lbl_status = FakeLabel()
        self.refreshes = []
        self.after_callbacks = []

    def after_idle(self, callback):
        self.after_callbacks.append(callback)
        callback()

    def _refresh_skiplist(self):
        self.refreshes.append("skiplist")

    def _refresh_station_list(self):
        self.refreshes.append("station_list")

    def _refresh_map(self):
        self.refreshes.append("map")

    def _refresh_detail_view(self):
        self.refreshes.append("detail")

    def _short_reason(self, key, _message):
        return key


def test_overview_rows_format_issues_statistics_and_missing_values():
    app = OverviewApp()

    tag, values = app._ov_row_values("ERR")
    by_column = dict(zip(app._all_ov_cols, values))
    assert tag == "error"
    assert by_column["WD NaN%"] == "4.0%"
    assert by_column["Max Cumulative Outage %"] == "12.5%"
    assert by_column["Issues"] == "1E 0W"
    assert by_column["AirT Std"] == "2.50"
    assert by_column["AirT Cumulative Outage %"] == "12.5%"

    tag, values = app._ov_row_values("OK")
    by_column = dict(zip(app._all_ov_cols, values))
    assert tag == "ok"
    assert by_column["WD NaN%"] == "--"
    assert by_column["Avg dt"] == "--"
    assert by_column["AirT Max"] == "--"


def test_overview_full_incremental_append_and_visibility_refreshes():
    app = OverviewApp()
    app.green_list.add("OK")
    app._refresh_overview()
    assert app.tv_ov.order == ["ERR"]
    assert app._ov_rendered == {"ERR", "OK"}

    app._ov_show_greenlit.set(True)
    app._refresh_overview_dirty({"OK"})
    assert app.tv_ov.order == ["ERR", "OK"]

    app.skip_list["ERR"] = "bad"
    app._refresh_overview_dirty({"ERR"})
    assert app.tv_ov.order == ["OK"]

    del app.stations["OK"]
    app._refresh_overview_dirty({"OK"})
    assert app.tv_ov.order == []
    assert "OK" not in app._ov_rendered

    app = OverviewApp()
    app._refresh_overview_append(["ERR", "ERR", "OK"])
    assert app.tv_ov.order == ["ERR", "OK"]
    assert app.tv_ov.updates == 1


def test_overview_sorting_insertion_and_column_visibility():
    app = OverviewApp()
    app._refresh_overview()

    app._sort_overview("Name")
    assert app.tv_ov.order == ["ERR", "OK"]
    app._sort_overview("AirT Max")
    assert app.tv_ov.order == ["OK", "ERR"]
    app._sort_overview("AirT Max")
    assert app.tv_ov.order == ["ERR", "OK"]

    err_values = app.tv_ov.rows["ERR"]["values"]
    app.tv_ov.delete("ERR")
    app._ov_sort_col = "AirT Max"
    app._ov_sort_rev = False
    assert app._ov_sorted_index(err_values) == "end"
    app._ov_sort_col = "missing"
    assert app._ov_sorted_index(err_values) == "end"

    app._ov_col_vars["Name"].set(False)
    app._apply_col_visibility()
    assert "STID" in app.tv_ov.options["displaycolumns"]
    assert "Name" not in app.tv_ov.options["displaycolumns"]


def test_overview_navigation_and_station_decisions(monkeypatch):
    app = OverviewApp()
    app._refresh_overview()
    app.tv_ov.selected = ("ERR",)
    app._ov_to_detail()
    assert app.nb.selected == 1
    assert app.detail_panes.only == "ERR"

    app.tv_ov.selected = ("ERR", "OK")
    app._ov_to_detail()
    assert app.detail_panes.many == ("ERR", "OK")

    app._ov_add_greenlit()
    assert app.green_list == {"ERR", "OK"}
    assert app.skip_list == {}
    assert app.lbl_status.options["text"] == "Greenlit 2 stations"

    class FakeDialog:
        def __init__(self, *_args, **_kwargs):
            self.result = "batch reason"

    monkeypatch.setattr("firebench.tools.wx_qc.tabs.overview.AddSkipDialog", FakeDialog)
    app.wait_window = lambda _dialog: None
    app._ov_add_skip()
    assert app.skip_list == {"ERR": "batch reason", "OK": "batch reason"}
    assert app.green_list == set()
    assert app.nb.selected == 3


def test_overview_empty_selection_and_inactive_repaint(monkeypatch):
    app = OverviewApp()
    notices = []
    monkeypatch.setattr(
        "firebench.tools.wx_qc.tabs.overview.messagebox.showinfo",
        lambda *args: notices.append(args),
    )

    app._ov_to_detail()
    app._ov_add_skip()
    app._ov_add_greenlit()
    assert len(notices) == 2

    app.nb.selected = "detail"
    app._nudge_ov_repaint()
    assert app.after_callbacks == []
    del app.nb
    assert app._ov_tab_active() is False
