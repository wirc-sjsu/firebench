"""Focused tests for the wx-QC projected map and OSM tile state."""

from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
import pytest
from matplotlib import colormaps
from matplotlib.figure import Figure

from firebench.tools.wx_qc.tabs.map_tab import (
    MapTabMixin,
    fetch_osm_tiles,
    map_extent,
    map_tile_cache_dir,
    project_lonlat,
)


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        self.text = kwargs["text"]


class FakeCanvas:
    def __init__(self):
        self.draws = 0

    def draw_idle(self):
        self.draws += 1


class TileStateApp(MapTabMixin):
    """Small headless app shape for testing completed tile requests."""

    def __init__(self, current_extent):
        self.var_map_basemap = FakeVariable(True)
        self._current_extent = current_extent
        self._map_tile_future = None
        self._map_tile_request_extent = None
        self._map_tile_pending_extent = None
        self._map_tile_poll_after_id = None
        self._map_basemap_artist = None
        self._map_attribution_artist = None
        self.lbl_status = FakeLabel()
        self.canvas_map = FakeCanvas()
        self.rendered = None
        self.restarted = 0

    def _map_current_extent(self):
        return self._current_extent

    def _map_render_basemap(self, image, image_extent, view_extent):
        self.rendered = (image, image_extent, view_extent)

    def _map_start_tile_request(self):
        self.restarted += 1


class ScheduledTileApp(TileStateApp):
    def __init__(self, current_extent):
        super().__init__(current_extent)
        self.stations = {"TEST": {}}
        self._map_tile_closed = False
        self._map_tile_view_extent = None
        self._map_tile_debounce_after_id = None
        self._map_tile_executor = None
        self._map_offsets = np.array([[0.0, 0.0]])
        self.cancelled = []
        self.scheduled = []

    def after(self, delay, callback):
        after_id = len(self.scheduled) + 1
        self.scheduled.append((after_id, delay, callback))
        return after_id

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)


def test_project_lonlat_returns_expected_web_mercator_coordinates():
    xs, ys = project_lonlat(np.array([0.0, -120.0]), np.array([0.0, 40.0]))

    assert xs[0] == pytest.approx(0.0)
    assert ys[0] == pytest.approx(0.0)
    assert xs[1] == pytest.approx(-13_358_338.895, rel=1e-8)
    assert ys[1] == pytest.approx(4_865_942.280, rel=1e-8)


def test_project_lonlat_clips_poles_and_preserves_invalid_values():
    xs, ys = project_lonlat(np.array([0.0, np.nan]), np.array([90.0, 0.0]))

    assert np.isfinite(xs[0])
    assert np.isfinite(ys[0])
    assert np.isnan(xs[1])
    assert np.isnan(ys[1])


def test_map_extent_uses_minimum_span_for_one_station():
    west, east, south, north = map_extent(np.array([100.0]), np.array([200.0]))

    assert (west + east) / 2.0 == pytest.approx(100.0)
    assert (south + north) / 2.0 == pytest.approx(200.0)
    assert east - west == pytest.approx(11_600.0)
    assert north - south == pytest.approx(11_600.0)


def test_map_extent_remains_finite_without_valid_station_coordinates():
    extent = map_extent(np.array([np.nan]), np.array([np.nan]))

    assert extent == pytest.approx((-5_800.0, 5_800.0, -5_800.0, 5_800.0))


def test_fetch_osm_tiles_uses_mapnik_auto_zoom_cache_and_identification(monkeypatch, tmp_path):
    import contextily as cx

    calls = {}
    expected = (np.zeros((2, 2, 4), dtype=np.uint8), (0.0, 1.0, 0.0, 1.0))

    monkeypatch.setattr(cx, "set_cache_dir", lambda path: calls.setdefault("cache_dir", path))

    def fake_bounds2img(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(cx, "bounds2img", fake_bounds2img)

    result = fetch_osm_tiles((1.0, 2.0, 3.0, 4.0), tmp_path)

    assert result is expected
    assert calls["cache_dir"] == str(tmp_path)
    assert calls["args"] == (1.0, 3.0, 2.0, 4.0)
    assert calls["kwargs"]["source"] is cx.providers.OpenStreetMap.Mapnik
    assert calls["kwargs"]["zoom"] == "auto"
    assert calls["kwargs"]["use_cache"] is True
    assert calls["kwargs"]["n_connections"] == 1
    assert calls["kwargs"]["max_retries"] == 0
    assert calls["kwargs"]["timeout"] == (3.05, 10)
    assert calls["kwargs"]["headers"]["User-Agent"].startswith("FireBench/")


def test_fetch_osm_tiles_omits_timeout_for_contextily_1_6_api(monkeypatch, tmp_path):
    import contextily as cx

    calls = {}

    def legacy_bounds2img(
        west,
        south,
        east,
        north,
        zoom="auto",
        source=None,
        headers=None,
        max_retries=2,
        n_connections=1,
        use_cache=True,
    ):
        calls.update(
            {
                "extent": (west, south, east, north),
                "zoom": zoom,
                "source": source,
                "headers": headers,
                "max_retries": max_retries,
                "n_connections": n_connections,
                "use_cache": use_cache,
            }
        )
        return np.zeros((2, 2, 4), dtype=np.uint8), (0.0, 1.0, 0.0, 1.0)

    monkeypatch.setattr(cx, "set_cache_dir", lambda _path: None)
    monkeypatch.setattr(cx, "bounds2img", legacy_bounds2img)

    fetch_osm_tiles((1.0, 2.0, 3.0, 4.0), tmp_path)

    assert calls["extent"] == (1.0, 3.0, 2.0, 4.0)
    assert calls["zoom"] == "auto"
    assert calls["headers"]["User-Agent"].startswith("FireBench/")
    assert calls["max_retries"] == 0
    assert calls["n_connections"] == 1
    assert calls["use_cache"] is True


def test_map_tile_cache_uses_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert map_tile_cache_dir() == tmp_path / "firebench" / "contextily"


def test_map_draw_debounces_extent_changes():
    app = ScheduledTileApp((1.0, 2.0, 3.0, 4.0))

    app._on_map_draw()
    app._current_extent = (10.0, 20.0, 30.0, 40.0)
    app._on_map_draw()

    assert app.cancelled == [1]
    assert app._map_tile_pending_extent == app._current_extent
    assert len(app.scheduled) == 2
    assert app.scheduled[-1][1] == 250


def test_completed_tile_request_applies_only_matching_latest_view():
    extent = (1.0, 2.0, 3.0, 4.0)
    app = TileStateApp(extent)
    future = Future()
    image = np.zeros((2, 2, 4), dtype=np.uint8)
    image_extent = (0.0, 5.0, 0.0, 5.0)
    future.set_result((image, image_extent))
    app._map_tile_future = future
    app._map_tile_request_extent = extent
    app._map_tile_pending_extent = extent

    app._map_poll_tile_request()

    assert app.rendered[0] is image
    assert app.rendered[1:] == (image_extent, extent)
    assert app.restarted == 0


def test_completed_stale_tile_request_starts_only_latest_view():
    old_extent = (1.0, 2.0, 3.0, 4.0)
    new_extent = (10.0, 20.0, 30.0, 40.0)
    app = TileStateApp(new_extent)
    future = Future()
    future.set_result((np.zeros((2, 2, 4), dtype=np.uint8), (0.0, 5.0, 0.0, 5.0)))
    app._map_tile_future = future
    app._map_tile_request_extent = old_extent
    app._map_tile_pending_extent = new_extent

    app._map_poll_tile_request()

    assert app.rendered is None
    assert app.restarted == 1


def test_tile_failure_disables_basemap_and_exposes_retry(caplog):
    app = TileStateApp((1.0, 2.0, 3.0, 4.0))
    app._map_tile_pending_extent = app._current_extent

    with caplog.at_level("ERROR"):
        app._map_tile_failed(OSError("offline"))

    assert app.var_map_basemap.get() is False
    assert app._map_tile_pending_extent is None
    assert app.lbl_status.text == "Road map unavailable; see error details"
    assert app.canvas_map.draws == 1
    assert "OSError: offline" in caplog.text


def test_shutdown_cancels_callbacks_future_and_executor():
    class FakeExecutor:
        def __init__(self):
            self.shutdown_args = None

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    app = ScheduledTileApp((1.0, 2.0, 3.0, 4.0))
    app._map_tile_debounce_after_id = 11
    app._map_tile_poll_after_id = 12
    future = Future()
    app._map_tile_future = future
    executor = FakeExecutor()
    app._map_tile_executor = executor

    app._shutdown_map_tiles()

    assert app._map_tile_closed is True
    assert app.cancelled == [11, 12]
    assert future.cancelled()
    assert executor.shutdown_args == {"wait": False, "cancel_futures": True}


class LogicMapApp(MapTabMixin):
    def __init__(self):
        self.cfg = {"map_marker_size": 1.5, "hidden_assertions": set()}
        self.stations = {
            "A": {
                "lon": -120.0,
                "lat": 38.0,
                "variables": {"wind_speed": [1], "wind_direction": [1]},
                "var_units": {"wind_speed": "m/s"},
                "times": np.array(["2020-01-01T00:00", "2020-01-01T02:00"], dtype="datetime64[m]"),
            },
            "B": {
                "lon": -121.0,
                "lat": 39.0,
                "variables": {"air_temperature": [1]},
                "var_units": {"air_temperature": "C"},
                "times": np.array(["2020-01-01T01:00", "2020-01-01T03:00"], dtype="datetime64[m]"),
            },
        }
        self.all_issues = {"A": [("WARN", "test", "message")], "B": []}
        self.all_stats = {
            "A": {"wind_direction": {"nan_pct": 4.0}, "_time": {"n_pts": 5}},
            "B": {"_time": {"n_pts": 3}},
        }
        self.skip_list = {}
        self.green_list = set()
        self._map_stids = ["A", "B"]
        self._map_dt_var = FakeVariable("1h")
        self._map_dt_custom_min = None
        self._map_window_bounds = []
        self._map_window_idx = 0
        self._map_t_extent = None
        self._map_cur_agg = None
        self._map_agg_sig = "sig"
        self._map_cbar_range = None
        self._map_cbar_range_sig = None
        self.var_map_color = FakeVariable("qc_status")
        self.var_map_value = FakeVariable("air_temperature")
        self.var_wind_calm = FakeVariable(True)
        self.var_wind_calm_thresh = FakeVariable("1.0")
        self._last_valid_calm_threshold = 1.0
        self._map_value_units = "C"
        self.ax_map = Figure().subplots()
        self.canvas_map = FakeCanvas()
        self._map_offsets = None
        self._map_hit_dirty = True
        self._map_hit_tree = None
        self._map_hit_stids = []
        self._map_hover_artist = None
        self._map_hover_dot_artist = None
        self._map_hover_stid = None
        self._map_sel_artist = None
        self._map_selected_stid = None
        self._map_popup_artist = None
        self._map_sc = None
        self.navigated = None

    def _navigate_to_station(self, stid):
        self.navigated = stid


def test_map_reducers_circular_mean_and_formatting():
    vals = np.array([np.nan, 1.0, 3.0, 2.0])
    assert np.isnan(MapTabMixin._map_agg_reduce(np.array([np.nan]), "mean"))
    assert MapTabMixin._map_agg_reduce(vals, "mean") == 2.0
    assert MapTabMixin._map_agg_reduce(vals, "median") == 2.0
    assert MapTabMixin._map_agg_reduce(vals, "max") == 3.0
    assert MapTabMixin._map_agg_reduce(vals, "min") == 1.0
    assert MapTabMixin._map_agg_reduce(vals, "last") == 2.0
    assert MapTabMixin._map_agg_reduce(vals, "unknown") == 2.0

    ws = np.array([2.0, 2.0, 0.1])
    wd = np.array([350.0, 10.0, 180.0])
    assert MapTabMixin._map_circular_mean_calm(ws, wd, True, 1.0) % 360 == pytest.approx(0.0)
    assert np.isnan(MapTabMixin._map_circular_mean_calm(ws, wd, True, 3.0))
    assert MapTabMixin._fmt_map_dt(45) == "45m"
    assert MapTabMixin._fmt_map_dt(360) == "6h"


def test_map_window_grid_columns_color_ranges_and_status_values():
    app = LogicMapApp()
    app._map_recompute_windows()
    assert len(app._map_window_bounds) > 1
    assert app._map_t_extent[1] > app._map_t_extent[0]
    assert app._map_active_dt_min() == 60
    app._map_dt_custom_min = 30.5
    assert app._map_active_dt_min() == 30.5

    app._map_cur_agg = np.array([[1.0, 2.0], [np.nan, 4.0]])
    app._map_window_idx = 1
    values, valid = app._map_value_column()
    np.testing.assert_allclose(values, [2.0, 4.0])
    assert valid.all()
    assert app._map_cbar_full_range() == (1.0, 4.0)
    assert app._map_cbar_full_range() == (1.0, 4.0)

    norm, rgba = app._map_value_colors(
        np.array([2.0, np.nan]), np.array([True, False]), colormaps["viridis"], (0.0, 4.0)
    )
    assert norm.vmin == 0.0
    assert rgba[1, 3] == 0.0

    assert app._map_marker_mult() == 1.5
    assert app._map_cval("A", "issues") == 1
    assert app._map_cval("A", "wd_nan_pct") == 4.0
    assert app._map_cval("A", "n_variables") == 2
    assert app._map_cval("A", "n_pts") == 5
    assert app._map_qc_status("A") == "undecided"
    app.green_list.add("A")
    assert app._map_qc_status("A") == "green"
    app.skip_list["A"] = "bad"
    assert app._map_qc_status("A") == "skip"


@pytest.mark.filterwarnings(
    "ignore:Conversion of an array with ndim > 0 to a scalar is deprecated:DeprecationWarning"
)
def test_map_wind_columns_popup_modes_and_hit_testing():
    app = LogicMapApp()
    app._map_cur_agg = (
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        np.array([[90.0, 100.0], [180.0, 200.0]]),
    )
    app._map_window_idx = 1
    ws, wd = app._map_wind_columns()
    np.testing.assert_allclose(ws, [2.0, 4.0])
    np.testing.assert_allclose(wd, [100.0, 200.0])

    app.var_map_color.set("wind_combo")
    assert "WS: 2.0 m/s" in app._map_popup_lines("A")[1]
    app.var_map_color.set("qc_status")
    assert len(app._map_popup_lines("A")) == 2
    app.var_map_color.set("n_pts")
    assert app._map_popup_lines("A")[1].endswith("5")

    offsets = np.array([[0.0, 0.0], [1.0, 1.0]])
    app._map_offsets = offsets
    app.ax_map.set_xlim(-1, 2)
    app.ax_map.set_ylim(-1, 2)
    app.canvas_map.draw_idle()
    x, y = app.ax_map.transData.transform(offsets[0])
    event = SimpleNamespace(inaxes=app.ax_map, x=x, y=y, dblclick=False)
    assert app._map_nearest_station(event) == "A"
    app._on_map_click(event)
    assert app._map_selected_stid == "A"
    event.dblclick = True
    app._on_map_click(event)
    assert app.navigated == "A"


def test_map_empty_window_and_aggregation_fallbacks():
    app = LogicMapApp()
    for station in app.stations.values():
        station["times"] = []
    app._map_recompute_windows()
    assert app._map_window_bounds == []
    assert app._map_t_extent is None

    app._map_cur_agg = None
    values, valid = app._map_value_column()
    assert np.isnan(values).all()
    assert not valid.any()
    ws, wd = app._map_wind_columns()
    assert np.isnan(ws).all() and np.isnan(wd).all()
    assert app._map_cbar_full_range() is None
