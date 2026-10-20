from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.acquisition.gfs.grid import GFSGrid
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.adapters import gfs_weather, nwp_weather

CYCLE = datetime(2021, 8, 20, 0, tzinfo=timezone.utc)
UTC_ORIGIN = "2021-08-20T00:00:00+00:00"


class _Field:
    """Grid field evaluated at the sampled cells: base + per_cell * i + per_hour * fxx."""

    def __init__(self, base: float, fxx: int, per_cell: float = 0.0, per_hour: float = 0.0) -> None:
        self.base = base
        self.fxx = fxx
        self.per_cell = per_cell
        self.per_hour = per_hour
        self.cells = None

    def __getitem__(self, index):
        j, i = index
        self.cells = (np.asarray(j), np.asarray(i))
        assert np.all((np.asarray(i) >= 0) & (np.asarray(i) < GFSGrid.nx))
        return self.base + self.per_cell * np.asarray(i, dtype=float) + self.per_hour * self.fxx


def _fake_read(path):
    fxx = int(Path(path).name)
    fields = {
        nwp_weather.TEMPERATURE: _Field(290.0, fxx, per_cell=0.001, per_hour=0.01),
        nwp_weather.HUMIDITY: _Field(40.0, fxx),
        nwp_weather.WIND_U: _Field(0.0, fxx),
        nwp_weather.WIND_V: _Field(5.0, fxx),
        nwp_weather.ROUGHNESS: _Field(0.1, fxx),
    }
    if fxx == 0:
        fields[nwp_weather.TERRAIN] = _Field(1500.0, fxx)
    return fields


def _cycle_files(hours=(0, 1, 2)):
    return CycleFiles(CYCLE, max(hours), files={fxx: Path(str(fxx)) for fxx in hours})


def _obs_file(tmp_path, stations):
    path = tmp_path / "obs.h5"
    heights = {"air_temperature": 2.0, "relative_humidity": 2.0, "wind_speed": 6.1, "wind_direction": 6.1}
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-10-19T12:00:00+00:00"
        h5.attrs["created_by"] = "tests"
        for name, lat, lon in stations:
            group = h5.create_group(f"time_series/station_{name}")
            group.attrs["position_lat"] = lat
            group.attrs["position_lon"] = lon
            group.attrs["position_alt"] = 1000.0
            group.attrs["position_alt_units"] = "m"
            time = group.create_dataset("time", data=[0.0, 60.0, 120.0])
            time.attrs["time_origin"] = UTC_ORIGIN
            time.attrs["time_units"] = "min"
            for variable, height in heights.items():
                data = group.create_dataset(variable, data=[1.0, 2.0, 3.0])
                data.attrs["units"] = nwp_weather.VARIABLE_UNITS[variable]
                data.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
                data.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
                data.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(fs.SH_TRUST_HIGHEST)
    return path


def test_station_file_is_standard_and_declares_gfs(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "gfs.h5"

    summary = gfs_weather.build_station_file(obs, _cycle_files(), out, read=_fake_read)

    i_cell = round((360.0 - 120.3) / 0.25)
    with h5py.File(out, "r") as h5:
        fs.validate_h5_std(h5)
        group = h5["time_series/station_A"]
        assert group["time"][:].tolist() == [0.0, 3600.0, 7200.0]
        assert group["air_temperature"][:] == pytest.approx(290.0 + 0.001 * i_cell + 0.01 * np.arange(3))
        assert group.attrs["model_grid_j"] == pytest.approx((90.0 - 38.7) / 0.25)
        assert group.attrs["terrain_height_difference"] == pytest.approx(500.0)
        assert h5.attrs["model_name"] == "GFS"
        assert h5.attrs["gfs_version"] == "16"
        assert h5.attrs["gfs_product"] == "pgrb2.0p25"
        assert h5.attrs["adapter"] == "firebench.adapters.gfs_weather"
        assert "nearest GFS grid cell" in h5.attrs["interpolation"]
        assert "GFS SFCR" in group["wind_speed"].attrs["height_adjustment"]
    assert summary["stations"] == 1


def test_earth_relative_wind_is_not_rotated(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "gfs.h5"

    gfs_weather.build_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(out, "r") as h5:
        direction = h5["time_series/station_A/wind_direction"][:]
    assert direction == pytest.approx(np.full(3, 180.0))


def test_station_next_to_the_greenwich_meridian_samples_the_wrapped_cell(tmp_path):
    obs = _obs_file(tmp_path, [("WEST", 51.5, -0.1), ("EAST", 51.5, 0.1)])
    out = tmp_path / "gfs.h5"
    reads = []

    def recording_read(path):
        fields = _fake_read(path)
        reads.append(fields[nwp_weather.TEMPERATURE])
        return fields

    gfs_weather.build_station_file(obs, _cycle_files(), out, read=recording_read)

    _, i_cells = reads[0].cells
    assert i_cells.tolist() == [0, 0]


def test_declared_heights_pass_the_trusted_source_height_check(tmp_path):
    obs = _obs_file(tmp_path, [("A", 38.7, -120.3)])
    out = tmp_path / "gfs.h5"

    gfs_weather.build_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(obs, "r") as obs_h5, h5py.File(out, "r") as model_h5:
        for variable in nwp_weather.VARIABLE_UNITS:
            validation = fs.validate_weather_sensor_heights(
                obs_h5, model_h5, station="station_A", variable=variable
            )
            assert validation.valid, (variable, validation.reason)
