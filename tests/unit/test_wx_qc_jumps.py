"""Tests for local-context weather-variable excursion detection."""

import numpy as np
import pytest

from firebench.tools.wx_qc.jumps import analyze_jump_excursions, validate_jump_policy


def _station(values, minutes=None, variable="air_temperature"):
    if minutes is None:
        minutes = np.arange(len(values), dtype=float) * 5.0
    origin = np.datetime64("2021-08-17T00:00:00")
    times = origin + np.asarray(minutes, dtype="timedelta64[m]")
    return {
        "times": times,
        "variables": {variable: np.asarray(values, dtype=float)},
    }


def _config():
    return {
        "context_hours": 6.0,
        "minimum_context_points": 5,
        "temporal_break_factor": 3.0,
        "thresholds": {
            "air_temperature": {
                "minimum_change": 10.0,
                "minimum_rate_per_hour": 60.0,
                "minimum_deviation": 10.0,
            }
        },
    }


def test_jump_detector_groups_a_multi_sample_excursion():
    values = [5.0, 5.2, 5.1, 4.9, 5.0, -18.0, -17.9, -18.1, 5.1, 5.2, 5.0]

    result = analyze_jump_excursions({"TEST": _station(values)}, _config())

    evidence = result["TEST"][0]
    assert evidence["variable"] == "air_temperature"
    assert evidence["records"] == 3
    assert len(evidence["ranges"]) == 1
    assert evidence["ranges"][0]["start"] == "2021-08-17T00:25:00Z"
    assert evidence["ranges"][0]["end"] == "2021-08-17T00:35:00Z"
    assert evidence["ranges"][0]["entry"]["rate_per_hour"] > 60.0
    assert evidence["ranges"][0]["exit"]["rate_per_hour"] > 60.0


def test_jump_detector_accepts_one_confirming_boundary_but_not_a_long_gap():
    trailing_excursion = [5.0, 5.2, 5.1, 4.9, 5.0, -18.0, -17.9]
    long_gap = _station(
        [5.0, 5.2, 5.1, 4.9, 5.0, -18.0, -17.9],
        minutes=[0, 5, 10, 15, 20, 720, 725],
    )

    result = analyze_jump_excursions({"EDGE": _station(trailing_excursion), "GAP": long_gap}, _config())

    assert result["EDGE"][0]["records"] == 2
    assert result["EDGE"][0]["ranges"][0]["exit"] is None
    assert "GAP" not in result


@pytest.mark.parametrize("missing", [np.nan, np.inf, -np.inf])
def test_jump_detector_rejects_nonfinite_boundary_evidence(missing):
    values = [5.0, 5.2, 5.1, 4.9, 5.0, missing, -18.0, -17.9]

    assert analyze_jump_excursions({"TEST": _station(values)}, _config()) == {}


def test_jump_detector_rejects_zero_duration_boundary_evidence():
    station = _station(
        [5.0, 5.2, 5.1, 4.9, 5.0, -18.0, -17.9],
        minutes=[0, 5, 10, 15, 20, 20, 25],
    )

    assert analyze_jump_excursions({"TEST": station}, _config()) == {}


def test_jump_detector_preserves_gradual_cold_weather_and_small_fast_changes():
    stations = {
        "COLD": _station([5.0, 2.0, -1.0, -4.0, -7.0, -10.0, -11.0, -10.0, -9.0]),
        "SMALL": _station([5.0, 5.1, 5.2, -2.5, 5.0, 5.1, 5.2]),
    }

    assert analyze_jump_excursions(stations, _config()) == {}


def test_jump_detector_uses_variable_specific_humidity_and_fuel_moisture_thresholds():
    config = {
        "context_hours": 6.0,
        "minimum_context_points": 5,
        "temporal_break_factor": 3.0,
        "thresholds": {
            "relative_humidity": {
                "minimum_change": 35.0,
                "minimum_rate_per_hour": 240.0,
                "minimum_deviation": 25.0,
            },
            "fuel_moisture_content_10h": {
                "minimum_change": 15.0,
                "minimum_rate_per_hour": 60.0,
                "minimum_deviation": 15.0,
            },
        },
    }
    stations = {
        "RH": _station(
            [40.0, 41.0, 40.0, 39.0, 40.0, 90.0, 89.0, 90.0, 40.0, 41.0, 40.0],
            variable="relative_humidity",
        ),
        "FMC": _station(
            [5.0, 5.1, 5.0, 4.9, 5.0, 25.0, 24.0, 25.0, 5.0, 5.1, 5.0],
            variable="fuel_moisture_content_10h",
        ),
        "FMC_BELOW": _station(
            [5.0, 5.1, 5.0, 4.9, 5.0, 19.0, 18.0, 19.0, 5.0, 5.1, 5.0],
            variable="fuel_moisture_content_10h",
        ),
    }

    result = analyze_jump_excursions(stations, config)

    assert result["RH"][0]["records"] == 3
    assert result["FMC"][0]["records"] == 3
    assert "FMC_BELOW" not in result


def test_jump_policy_validation_rejects_bad_thresholds_and_variables():
    policy = {
        "context_hours": 6.0,
        "minimum_context_points": 5,
        "thresholds": {
            "air_temperature": {
                "minimum_change": 10.0,
                "minimum_rate_per_hour": 60.0,
                "minimum_deviation": 10.0,
            }
        },
    }
    validate_jump_policy(policy, {"air_temperature"})

    policy["thresholds"]["air_temperature"]["minimum_change"] = 0.0
    with pytest.raises(ValueError, match="positive finite"):
        validate_jump_policy(policy, {"air_temperature"})

    policy["thresholds"] = {"unknown": {}}
    with pytest.raises(ValueError, match="supported variable"):
        validate_jump_policy(policy, {"air_temperature"})
