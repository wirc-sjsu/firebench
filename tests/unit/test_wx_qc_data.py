"""Stable array-based tests for weather-station QC data semantics."""

import numpy as np
import pytest

from firebench.tools.wx_qc.constants import (
    default_config,
    parse_nonnegative_finite,
    validate_gui_config,
)
from firebench.tools.wx_qc.data import (
    apply_frozen_analysis,
    compute_outage_stats,
    compute_stats,
    run_assertions,
    run_outage_assertions,
)
from firebench.tools.wx_qc.loader import LoaderMixin
from firebench.tools.wx_qc.frozen import _finite_temporal_coverage, infer_reporting_resolution


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


def test_assertion_severity_override_replaces_default_severity():
    cfg = default_config()
    station = _station([0, 10, 20, 30, 40], air_temperature=[500.0] * 5)
    stats = compute_stats(station)
    default_issues = run_assertions(station, stats, cfg)
    assert any(sev == "ERROR" and key == "hi:air_temperature" for sev, key, _ in default_issues)

    cfg["assertion_severity_override"] = {"hi:": "WARN"}
    overridden_issues = run_assertions(station, stats, cfg)
    assert any(sev == "WARN" and key == "hi:air_temperature" for sev, key, _ in overridden_issues)


def test_single_station_assertions_defer_frozen_detection_to_network_analysis():
    cfg = default_config()
    station = _station(
        [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        wind_direction=[10.0] * 11,
        relative_humidity=[50.0] * 11,
    )
    stats = compute_stats(station)
    issues = run_assertions(station, stats, cfg)
    assert not any(key.startswith("frozen:") for _, key, _ in issues)


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


def test_frozen_analysis_requires_neighbor_change_and_reports_quantization():
    minutes = np.arange(0, 390, 30)
    stations = {
        "TARGET": _station(minutes, air_temperature=[4.0] + [5.0] * 11 + [6.0]),
        "N1": _station(minutes, air_temperature=np.arange(len(minutes), dtype=float)),
        "N2": _station(minutes, air_temperature=np.arange(len(minutes), dtype=float) + 10.0),
    }
    for index, station in enumerate(stations.values()):
        station.update({"lat": 38.0, "lon": -120.0 + index * 0.01})
    cfg = default_config()
    cfg["frozen_min_duration_hours"]["air_temperature"] = 1.0
    stats = {station_id: compute_stats(station) for station_id, station in stations.items()}
    issues = {station_id: [] for station_id in stations}

    findings, resolutions = apply_frozen_analysis(stations, stats, issues, cfg)

    target = findings["TARGET"][0]
    assert target["confidence"] == "ambiguous"
    assert target["disposition"] == "review"
    assert target["resolution"] == pytest.approx(1.0)
    assert target["quantization_uncertainty"] == pytest.approx(0.5)
    assert sum(item["changed"] for item in target["neighbors"]) == 2
    assert any(key == "frozen:air_temperature" for _, key, _ in issues["TARGET"])
    assert resolutions["pooled"]["air_temperature"] == pytest.approx(1.0)


def test_frozen_analysis_keeps_plausible_constant_neighbors_as_audit_findings():
    minutes = np.arange(0, 390, 30)
    target = _station(minutes, relative_humidity=[50.0] * len(minutes))
    target.update({"lat": 38.0, "lon": -120.0})
    cfg = default_config()
    cfg["frozen_min_duration_hours"]["relative_humidity"] = 1.0

    stats = {"TARGET": compute_stats(target)}
    issues = {"TARGET": []}
    findings, _resolutions = apply_frozen_analysis({"TARGET": target}, stats, issues, cfg)
    assert findings["TARGET"][0]["confidence"] == "low"
    assert any(key == "frozen_unconfirmed:relative_humidity" for _, key, _ in issues["TARGET"])

    stations = {"TARGET": target}
    for index, station_id in enumerate(("N1", "N2"), 1):
        neighbor = _station(minutes, relative_humidity=[50.0] * len(minutes))
        neighbor.update({"lat": 38.0, "lon": -120.0 + index * 0.01})
        stations[station_id] = neighbor
    stats = {station_id: compute_stats(station) for station_id, station in stations.items()}
    issues = {station_id: [] for station_id in stations}
    findings, _resolutions = apply_frozen_analysis(stations, stats, issues, cfg)
    assert findings["TARGET"][0]["disposition"] == "audit"
    assert any(key == "frozen_unconfirmed:relative_humidity" for _, key, _ in issues["TARGET"])


def test_reporting_resolution_tolerates_float_noise_and_slow_quantized_change_is_not_frozen():
    values = np.tile(np.arange(10, dtype=float) / 10.0, 3)
    values[7] += 1e-13
    assert infer_reporting_resolution(values) == pytest.approx(0.1)

    minutes = np.arange(0, 360, 30)
    station = _station(minutes, air_temperature=np.repeat([5.0, 5.1, 5.2, 5.3], 3))
    station.update({"lat": 38.0, "lon": -120.0})
    cfg = default_config()
    cfg["frozen_min_duration_hours"]["air_temperature"] = 2.0
    stats = {"TARGET": compute_stats(station)}
    issues = {"TARGET": []}

    findings, _resolutions = apply_frozen_analysis({"TARGET": station}, stats, issues, cfg)

    assert "TARGET" not in findings


def test_calm_wind_and_nighttime_zero_solar_are_plausible_constant_regimes():
    minutes = np.arange(0, 180, 30)
    station = _station(
        minutes,
        wind_speed=np.zeros(len(minutes)),
        wind_direction=np.full(len(minutes), 180.0),
        solar_radiation=np.zeros(len(minutes)),
    )
    station["times"] = np.datetime64("2021-01-01T08:00:00") + minutes.astype("timedelta64[m]")
    station.update({"lat": 38.0, "lon": -120.0})
    cfg = default_config()
    for variable in ("wind_speed", "wind_direction", "solar_radiation"):
        cfg["frozen_min_duration_hours"][variable] = 0.5
    stats = {"TARGET": compute_stats(station)}
    issues = {"TARGET": []}

    findings, _resolutions = apply_frozen_analysis({"TARGET": station}, stats, issues, cfg)

    assert "TARGET" not in findings


def test_neighbor_coverage_does_not_bridge_large_internal_gaps():
    times = np.array(
        ["2021-01-01T00:00", "2021-01-01T01:00", "2021-01-07T23:00", "2021-01-08T00:00"],
        dtype="datetime64[m]",
    )
    values = np.ones(len(times))

    coverage = _finite_temporal_coverage(
        times,
        values,
        np.datetime64("2021-01-01T00:00"),
        np.datetime64("2021-01-08T00:00"),
    )

    assert coverage == pytest.approx(2 / (7 * 24))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("frozen_neighbor_count", 0),
        ("frozen_neighbor_count", 2.5),
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
