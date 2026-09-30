from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.hrrr.grid import HRRRGrid, LON_0, wind_rotation_angle
from firebench.adapters import hrrr_weather

CYCLE = datetime(2021, 8, 20, 0, tzinfo=timezone.utc)
UTC_ORIGIN = "2021-08-20T00:00:00+00:00"


class _Field:
    """Grid field evaluated lazily at the sampled cells: base + per_cell * i + per_hour * fxx."""

    def __init__(self, base: float, fxx: int, per_cell: float = 0.001, per_hour: float = 0.01) -> None:
        self.base = base
        self.fxx = fxx
        self.per_cell = per_cell
        self.per_hour = per_hour

    def __getitem__(self, index):
        _, i = index
        return self.base + self.per_cell * np.asarray(i, dtype=float) + self.per_hour * self.fxx


def _fake_read(path):
    fxx = int(Path(path).name)
    fields = {
        hrrr_weather.TEMPERATURE: _Field(290.0, fxx),
        hrrr_weather.HUMIDITY: _Field(40.0, fxx),
        hrrr_weather.WIND_U: _Field(0.0, fxx, per_cell=0.0, per_hour=0.0),
        hrrr_weather.WIND_V: _Field(5.0, fxx, per_cell=0.0, per_hour=0.0),
        hrrr_weather.ROUGHNESS: _Field(0.1, fxx, per_cell=0.0, per_hour=0.0),
    }
    if fxx == 0:
        fields[hrrr_weather.TERRAIN] = _Field(1500.0, fxx, per_cell=0.0, per_hour=0.0)
    return fields


def _cycle_files(hours=(0, 1, 2), missing=()):
    return CycleFiles(
        CYCLE, max(hours), files={fxx: Path(str(fxx)) for fxx in hours}, missing=list(missing)
    )


def _add_obs_station(h5, name, lat, lon, *, alt_ft=4921.26, heights=None, trusted=True):
    heights = heights or {
        "air_temperature": 2.0,
        "relative_humidity": 2.0,
        "wind_speed": 6.1,
        "wind_direction": 6.1,
    }
    group = h5.create_group(f"time_series/station_{name}")
    group.attrs["position_lat"] = lat
    group.attrs["position_lon"] = lon
    group.attrs["position_alt"] = alt_ft
    group.attrs["position_alt_units"] = "ft"
    time = group.create_dataset("time", data=[0.0, 60.0, 120.0])
    time.attrs["time_origin"] = UTC_ORIGIN
    time.attrs["time_units"] = "min"
    for variable, height in heights.items():
        data = group.create_dataset(variable, data=[1.0, 2.0, 3.0])
        data.attrs["units"] = hrrr_weather.VARIABLE_UNITS[variable]
        data.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
        data.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
        data.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(fs.SH_TRUST_HIGHEST if trusted else 0)


def _obs_file(tmp_path, stations):
    path = tmp_path / "obs.h5"
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-09-29T12:00:00+00:00"
        h5.attrs["created_by"] = "tests"
        for station in stations:
            _add_obs_station(h5, *station[:3], **(station[3] if len(station) > 3 else {}))
    return path


def test_station_file_is_standard_hourly_and_sampled_at_the_nearest_cell(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "hrrr.h5"

    summary = hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    i_cell, _ = HRRRGrid().ij_from_latlon(38.7, -120.3)
    with h5py.File(out, "r") as h5:
        fs.validate_h5_std(h5)
        group = h5["time_series/station_A"]
        assert group["time"][:].tolist() == [0.0, 3600.0, 7200.0]
        assert group["time"].attrs["time_origin"] == UTC_ORIGIN
        assert group["time"].attrs["time_units"] == "s"
        assert group["air_temperature"][:] == pytest.approx(290.0 + 0.001 * i_cell + 0.01 * np.arange(3))
        assert group["air_temperature"].attrs["units"] == "K"
        assert h5.attrs["hrrr_version"] == 4
        assert h5.attrs["model_name"] == "HRRR"
    assert summary["stations"] == 1
    assert summary["forecast_hours"] == [0, 1, 2]


def test_grid_relative_wind_is_rotated_to_earth_before_direction(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "hrrr.h5"

    hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    # West of lon_0 grid north points west of true north: a grid-northward wind blows towards the
    # north-north-west, so it comes from east of south, 180 deg + angle with angle < 0.
    angle = float(np.degrees(wind_rotation_angle(-120.3)))
    assert angle < 0
    with h5py.File(out, "r") as h5:
        direction = h5["time_series/station_A/wind_direction"][:]
    assert direction == pytest.approx(np.full(3, 180.0 + angle))
    assert 135.0 < direction[0] < 180.0


def test_wind_speed_is_brought_to_the_station_height_with_the_log_law(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "hrrr.h5"

    hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    expected = 5.0 * np.log(6.1 / 0.1) / np.log(10.0 / 0.1)
    with h5py.File(out, "r") as h5:
        speed = h5["time_series/station_A/wind_speed"]
        assert speed[:] == pytest.approx(np.full(3, expected))
        assert speed.attrs["model_native_height"] == 10.0
        assert "log law" in speed.attrs["height_adjustment"]


def test_log_law_is_undefined_for_roughness_above_the_reference_height():
    assert np.isnan(hrrr_weather.wind_at_height(5.0, 6.1, 12.0))
    assert hrrr_weather.wind_at_height(5.0, 10.0, 0.1) == pytest.approx(5.0)
    assert hrrr_weather.wind_at_height(5.0, 6.1, 0.0) == pytest.approx(
        5.0 * np.log(6.1 / hrrr_weather.Z0_MIN_M) / np.log(10.0 / hrrr_weather.Z0_MIN_M)
    )


def test_declared_heights_pass_the_trusted_source_height_check(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "hrrr.h5"

    hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(obs, "r") as obs_h5, h5py.File(out, "r") as model_h5:
        for variable in hrrr_weather.VARIABLE_UNITS:
            validation = fs.validate_weather_sensor_heights(
                obs_h5, model_h5, station="station_A", variable=variable
            )
            assert validation.valid, (variable, validation.reason)


def test_temperature_sensor_outside_the_screen_level_band_keeps_the_native_height(tmp_path):
    heights = {"air_temperature": 6.0, "relative_humidity": 1.5, "wind_speed": 6.1, "wind_direction": 6.1}
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3, {"heights": heights})])
    out = tmp_path / "hrrr.h5"

    summary = hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(obs, "r") as obs_h5, h5py.File(out, "r") as model_h5:
        assert model_h5["time_series/station_A/air_temperature"].attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == 2.0
        assert model_h5["time_series/station_A/relative_humidity"].attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == 1.5
        assert not fs.validate_weather_sensor_heights(
            obs_h5, model_h5, station="station_A", variable="air_temperature"
        ).valid
    assert summary["height_policy"]["air_temperature"] == {"none: native 2 m height": 1}


def test_terrain_height_difference_is_written_per_station(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3, {"alt_ft": 1000.0 / 0.3048})])
    out = tmp_path / "hrrr.h5"

    hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(out, "r") as h5:
        group = h5["time_series/station_A"]
        assert group.attrs["model_terrain_height"] == pytest.approx(1500.0)
        assert group.attrs["station_elevation"] == pytest.approx(1000.0)
        assert group.attrs["terrain_height_difference"] == pytest.approx(500.0)


def test_station_outside_the_hrrr_grid_is_an_error(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3), ("HAWAII", 21.3, -157.8)])

    with pytest.raises(ValueError, match="station_HAWAII"):
        hrrr_weather.build_hrrr_station_file(obs, _cycle_files(), tmp_path / "hrrr.h5", read=_fake_read)
    assert not (tmp_path / "hrrr.h5").exists()


def test_meteorological_direction_convention():
    assert hrrr_weather.wind_direction_from_components(0.0, -1.0) == pytest.approx(0.0)
    assert hrrr_weather.wind_direction_from_components(-1.0, 0.0) == pytest.approx(90.0)
    assert hrrr_weather.wind_direction_from_components(0.0, 1.0) == pytest.approx(180.0)
    assert hrrr_weather.wind_direction_from_components(1.0, 0.0) == pytest.approx(270.0)


def test_no_rotation_on_the_central_meridian():
    assert float(wind_rotation_angle(LON_0)) == 0.0
