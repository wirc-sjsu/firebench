"""Stable array-based tests for weather-station QC data semantics."""

import numpy as np
import pytest

from firebench.tools.wx_qc.constants import (
    default_config,
    parse_nonnegative_finite,
    validate_gui_config,
)
from firebench.tools.wx_qc.data import (
    compute_outage_stats,
    compute_stats,
    run_assertions,
    run_outage_assertions,
)
from firebench.tools.wx_qc.loader import LoaderMixin


def _station(relative_minutes, **variables):
    relative_minutes = np.asarray(relative_minutes, dtype=np.float64)
    origin = np.datetime64("2021-01-01T00:00:00", "us")
    offsets = np.rint(relative_minutes * 60_000_000).astype(np.int64).astype("timedelta64[us]")
    return {
        "times": origin + offsets,
        "rel_min": relative_minutes,
        "time_axis_error": None,
        "variables": {name: np.asarray(values, dtype=np.float64) for name, values in variables.items()},
    }


def _stats_with_outages(station, leading_gap=0.0, trailing_gap=0.0, global_duration=None):
    stats = compute_stats(station)
    compute_outage_stats(
        station,
        stats,
        leading_gap_min=leading_gap,
        trailing_gap_min=trailing_gap,
        global_duration_min=global_duration,
    )
    return stats


def test_default_config_has_no_nan_threshold_but_raw_nan_stats_remain():
    assert "nan_pct" not in default_config()

    station = _station([0, 10, 20, 30], air_temperature=[1.0, np.nan, 3.0, np.nan])
    stats = compute_stats(station)

    assert stats["air_temperature"]["nan_ct"] == 2
    assert stats["air_temperature"]["nan_pct"] == 50.0


def test_frozen_runs_are_interrupted_by_nan_and_temporal_gap():
    nan_station = _station(
        [0, 10, 20, 30, 40],
        air_temperature=[5.0, 5.0, np.nan, 5.0, 5.0],
    )
    assert compute_stats(nan_station)["air_temperature"]["longest_frozen"] == 2

    gap_station = _station(
        [0, 10, 20, 100, 110, 120],
        air_temperature=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
    )
    assert compute_stats(gap_station)["air_temperature"]["longest_frozen"] == 3


def test_wind_direction_dropout_requires_one_sustained_run():
    cfg = default_config()
    scattered = _station(
        [0, 10, 20, 30, 40],
        wind_speed=[1, 1, 1, 1, 1],
        wind_direction=[np.nan, 10, np.nan, 20, np.nan],
    )
    scattered_stats = compute_stats(scattered)
    assert not any(key == "dropout" for _, key, _ in run_assertions(scattered, scattered_stats, cfg))

    sustained = _station(
        [0, 10, 20, 30, 40],
        wind_speed=[1, 1, 1, 1, 1],
        wind_direction=[10, np.nan, np.nan, np.nan, 20],
    )
    sustained_stats = compute_stats(sustained)
    issues = run_assertions(sustained, sustained_stats, cfg)
    assert any(key == "dropout" and "longest run=3" in message for _, key, message in issues)


def test_calm_wind_breaks_dropout_and_wind_outage_runs():
    station = _station(
        np.arange(0, 90, 10),
        wind_speed=[1, 1, 1, 1, 0, 1, 1, 1, 1],
        wind_direction=[np.nan] * 9,
    )
    stats = _stats_with_outages(
        station,
        leading_gap=50,
        trailing_gap=50,
        global_duration=180,
    )

    assert stats["wind_direction"]["longest_outage_min"] == 30.0
    assert stats["wind_direction"]["cumulative_outage_min"] == 60.0
    assert stats["wind_direction"]["outage_pct"] == 100.0


def test_longest_and_cumulative_outages_keep_edge_runs_separate():
    station = _station(
        np.arange(0, 100, 10),
        air_temperature=[1, 1, np.nan, np.nan, np.nan, np.nan, 1, np.nan, np.nan, np.nan],
    )
    stats = _stats_with_outages(
        station,
        leading_gap=40,
        trailing_gap=20,
        global_duration=150,
    )
    variable = stats["air_temperature"]

    assert variable["longest_outage_min"] == 40.0
    assert variable["cumulative_outage_min"] == 70.0
    assert variable["outage_pct"] == pytest.approx(100.0 * 70.0 / 150.0)
    assert stats["_time"]["max_var_outage_min"] == 40.0
    assert stats["_time"]["full_outage_min"] == 40.0

    cfg = default_config()
    cfg["max_var_outage_min"] = 50
    cfg["full_outage_min"] = 50
    assert run_outage_assertions(stats, cfg) == []


def test_loader_uses_global_duration_and_separate_station_edge_gaps():
    global_station = _station(
        np.arange(0, 160, 10),
        air_temperature=np.arange(16, dtype=float),
    )
    shorter_station = _station(
        np.arange(40, 140, 10),
        air_temperature=[1, 1, np.nan, np.nan, np.nan, np.nan, 1, np.nan, np.nan, np.nan],
    )
    loader = object.__new__(LoaderMixin)
    loader.stations = {"GLOBAL": global_station, "SHORT": shorter_station}
    loader.all_stats = {stid: compute_stats(station) for stid, station in loader.stations.items()}
    loader.all_issues = {
        stid: run_assertions(station, loader.all_stats[stid], default_config())
        for stid, station in loader.stations.items()
    }
    loader.cfg = default_config()

    loader._compute_global_time_extent()

    stats = loader.all_stats["SHORT"]
    assert stats["_time"]["leading_gap_min"] == 40.0
    assert stats["_time"]["trailing_gap_min"] == 20.0
    assert stats["_time"]["global_duration_min"] == 150.0
    assert stats["air_temperature"]["outage_pct"] == pytest.approx(100.0 * 70.0 / 150.0)


def test_short_leading_and_trailing_gaps_do_not_merge_into_an_outage():
    station = _station(np.arange(0, 50, 10), air_temperature=[1, 2, 3, 4, 5])
    stats = _stats_with_outages(
        station,
        leading_gap=20,
        trailing_gap=20,
        global_duration=80,
    )

    assert stats["air_temperature"]["longest_outage_min"] == 0.0
    assert stats["air_temperature"]["cumulative_outage_min"] == 0.0
    assert stats["_time"]["full_outage_min"] == 0.0


@pytest.mark.parametrize(
    ("relative_minutes", "expected_issue"),
    [
        ([0, 10, 10, 20], "dup_ts"),
        ([0, 10, 5, 20], "time_neg"),
    ],
)
def test_unsorted_time_axes_disable_cadence_and_outage_derivatives(relative_minutes, expected_issue):
    station = _station(relative_minutes, air_temperature=[1, np.nan, np.nan, 2])
    stats = _stats_with_outages(station, global_duration=20)
    issues = run_assertions(station, stats, default_config())

    assert stats["_time"]["time_axis_valid"] is False
    assert stats["_time"]["avg_freq_min"] is None
    assert stats["_time"]["max_dt_min"] is None
    assert stats["air_temperature"]["longest_gap_hr"] is None
    assert stats["air_temperature"]["longest_outage_min"] is None
    assert stats["air_temperature"]["outage_pct"] is None
    assert any(key == expected_issue for _, key, _ in issues)


def test_parser_error_disables_derivatives_and_creates_time_axis_issue():
    station = _station([0, 10, 20], air_temperature=[1, 2, 3])
    station["time_axis_error"] = "missing string time_origin attribute"
    stats = _stats_with_outages(station, global_duration=20)
    issues = run_assertions(station, stats, default_config())

    assert stats["_time"]["time_axis_valid"] is False
    assert stats["_time"]["avg_freq_min"] is None
    assert stats["air_temperature"]["outage_pct"] is None
    assert any(key == "time_axis" for _, key, _ in issues)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("frozen_min_run", 0),
        ("frozen_min_run", 2.5),
        ("compare_n_neighbors", -1),
        ("compare_n_neighbors", 1.5),
        ("max_var_outage_min", -1),
        ("full_outage_min", np.nan),
    ],
)
def test_invalid_settings_are_rejected(key, value):
    config = default_config()
    config[key] = value

    with pytest.raises(ValueError):
        validate_gui_config(config)


def test_invalid_physical_bounds_and_calm_thresholds_are_rejected():
    config = default_config()
    config["bounds"]["air_temperature"] = (10.0, 10.0, "C")
    with pytest.raises(ValueError, match="lower bound"):
        validate_gui_config(config)

    for value in (-0.1, np.nan, np.inf, "not-a-number"):
        with pytest.raises(ValueError):
            parse_nonnegative_finite(value, "Calm-wind threshold")
