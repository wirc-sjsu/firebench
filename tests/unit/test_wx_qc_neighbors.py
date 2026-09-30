"""Tests for neighbour-consistency air-temperature QC."""

import numpy as np
import pytest

from firebench.tools.wx_qc.neighbors import analyze_neighbor_bias, validate_neighbor_policy

HOURS = 24


def _config(**overrides):
    return {
        "radius_km": 20.0,
        "neighbor_count": 8,
        "minimum_neighbors": 3,
        "minimum_paired_hours": 12,
        "lapse_rate_c_per_km": 6.5,
        "maximum_bias": 10.0,
        **overrides,
    }


def _station(lat_offset, offset=0.0, alt=1000.0, units="m", hours=None, step_minutes=15):
    """Return a station with a diurnal air temperature cycle and the given elevation."""
    if hours is None:
        minutes = np.arange(0, HOURS * 60, step_minutes)
    else:
        minutes = np.asarray(hours) * 60
    times = np.datetime64("2021-08-20T00:00") + minutes.astype("timedelta64[m]")
    elevation_m = alt * 0.3048 if units == "ft" else alt
    values = 20.0 + 8.0 * np.sin(2 * np.pi * minutes / 1440.0) - 6.5e-3 * (elevation_m - 1000.0) + offset
    return {
        "lat": 38.0 + lat_offset,
        "lon": -120.0,
        "alt": alt,
        "alt_units": units,
        "times": times,
        "variables": {"air_temperature": values},
    }


def _network(**extra):
    stations = {f"N{index}": _station(0.02 * index) for index in range(1, 5)}
    stations.update(extra)
    return stations


def test_biased_station_is_flagged_against_its_neighbours():
    result = analyze_neighbor_bias(_network(BAD=_station(0.0, offset=-40.0)), _config())

    assert set(result) == {"BAD"}
    assert result["BAD"]["bias"] == pytest.approx(-40.0)
    assert result["BAD"]["paired_hours"] == HOURS
    assert result["BAD"]["neighbors"] == ["N1", "N2", "N3", "N4"]


def test_lapse_rate_explains_a_colder_high_station():
    result = analyze_neighbor_bias(_network(HIGH=_station(0.0, alt=2000.0)), _config())

    assert result == {}


def test_feet_and_metre_elevations_are_equivalent():
    feet = _station(0.0, alt=2000.0 / 0.3048, units="ft")
    unknown = _station(0.0, offset=-40.0, units=None)

    assert analyze_neighbor_bias(_network(HIGH=feet), _config()) == {}
    assert analyze_neighbor_bias(_network(UNKNOWN=unknown), _config()) == {}


def test_stations_without_enough_neighbours_or_paired_hours_are_not_tested():
    isolated = {"FAR": _station(1.0, offset=-40.0), "N1": _station(0.02), "N2": _station(0.04)}
    daily = _station(0.0, offset=-40.0, hours=[13, 37, 61, 85])

    assert analyze_neighbor_bias(isolated, _config()) == {}
    assert analyze_neighbor_bias(_network(COOP=daily), _config()) == {}


def test_a_biased_neighbour_does_not_flag_consistent_stations():
    result = analyze_neighbor_bias(_network(BAD=_station(0.01, offset=40.0)), _config())

    assert set(result) == {"BAD"}


def test_neighbour_policy_validation():
    validate_neighbor_policy(_config(lapse_rate_c_per_km=0.0))
    with pytest.raises(ValueError, match="must be a table"):
        validate_neighbor_policy(None)
    with pytest.raises(ValueError, match="must define"):
        validate_neighbor_policy(_config(radius=20.0))
    with pytest.raises(ValueError, match="neighbor_count must be a positive integer"):
        validate_neighbor_policy(_config(neighbor_count=0))
    with pytest.raises(ValueError, match="radius_km must be greater than zero"):
        validate_neighbor_policy(_config(radius_km=0.0))
    with pytest.raises(ValueError, match="lapse_rate_c_per_km must be non-negative"):
        validate_neighbor_policy(_config(lapse_rate_c_per_km=-1.0))
    with pytest.raises(ValueError, match="maximum_bias must be a finite number"):
        validate_neighbor_policy(_config(maximum_bias=float("inf")))
    with pytest.raises(ValueError, match="must not exceed neighbor_count"):
        validate_neighbor_policy(_config(neighbor_count=2))
