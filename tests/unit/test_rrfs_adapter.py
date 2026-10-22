from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.hrrr.grid import HRRRGrid
from firebench.adapters import hrrr_weather, rrfs_weather, nwp_weather

CYCLE = datetime(2026, 8, 28, 0, tzinfo=timezone.utc)
UTC_ORIGIN = "2026-08-28T00:00:00+00:00"


def _fake_read(path):
    fxx = int(Path(path).name)
    shape = (1059, 1799)
    fields = {
        nwp_weather.TEMPERATURE: np.full(shape, 290.0 + fxx),
        nwp_weather.HUMIDITY: np.full(shape, 40.0),
        nwp_weather.WIND_U: np.zeros(shape),
        nwp_weather.WIND_V: np.full(shape, 5.0),  # grid north
        nwp_weather.ROUGHNESS: np.full(shape, 0.1),
    }
    if fxx == 0:
        fields[nwp_weather.TERRAIN] = np.full(shape, 1500.0)
    return fields


def _obs_file(tmp_path, stations):
    path = tmp_path / "obs.h5"
    heights = {"air_temperature": 2.0, "relative_humidity": 2.0, "wind_speed": 6.1, "wind_direction": 6.1}
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-10-21T12:00:00+00:00"
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


def _cycle_files(hours=(0, 1, 2)):
    return CycleFiles(CYCLE, max(hours), files={fxx: Path(str(fxx)) for fxx in hours})


def test_station_file_is_standard_and_declares_rrfs(tmp_path):
    obs = _obs_file(tmp_path, [("A", 44.85, -118.2)])
    out = tmp_path / "rrfs.h5"

    summary = rrfs_weather.build_station_file(obs, _cycle_files(), out, read=_fake_read)

    with h5py.File(out, "r") as h5:
        fs.validate_h5_std(h5)
        group = h5["time_series/station_A"]
        assert group["time"][:].tolist() == [0.0, 3600.0, 7200.0]
        assert group["air_temperature"][:] == pytest.approx([290.0, 291.0, 292.0])
        assert group.attrs["terrain_height_difference"] == pytest.approx(500.0)
        assert h5.attrs["model_name"] == "RRFS"
        assert h5.attrs["rrfs_version"] == "1"
        assert h5.attrs["rrfs_cycle"] == "2026-08-28T00:00:00+00:00"
        assert h5.attrs["rrfs_product"] == "2dfld.3km.conus"
        assert h5.attrs["source_bucket"] == "s3://noaa-rrfs-ops-pds"
        assert h5.attrs["adapter"] == "firebench.adapters.rrfs_weather"
        assert "nearest RRFS grid cell" in h5.attrs["interpolation"]
        assert "RRFS SFCR" in group["wind_speed"].attrs["height_adjustment"]
    assert summary["stations"] == 1


def test_grid_relative_wind_is_rotated_as_hrrrs(tmp_path):
    # RRFS gives its CONUS output on HRRR's grid, so a grid-north wind gets the same earth direction.
    obs = _obs_file(tmp_path, [("A", 44.85, -118.2)])
    rrfs_out, hrrr_out = tmp_path / "rrfs.h5", tmp_path / "hrrr.h5"

    rrfs_weather.build_station_file(obs, _cycle_files(), rrfs_out, read=_fake_read)
    hrrr_weather.build_station_file(obs, _cycle_files(), hrrr_out, read=_fake_read)

    with h5py.File(rrfs_out, "r") as rrfs, h5py.File(hrrr_out, "r") as hrrr:
        direction = rrfs["time_series/station_A/wind_direction"][:]
        assert direction == pytest.approx(hrrr["time_series/station_A/wind_direction"][:], abs=1e-6)
    angle = np.degrees(HRRRGrid().wind_rotation_angle(-118.2))
    assert direction == pytest.approx(np.full(3, (180.0 + angle) % 360.0))


def test_station_outside_the_conus_grid_is_an_error(tmp_path):
    obs = _obs_file(tmp_path, [("FAIRBANKS", 64.8, -147.7)])

    with pytest.raises(ValueError, match="stations outside the RRFS CONUS grid: station_FAIRBANKS"):
        rrfs_weather.build_station_file(obs, _cycle_files(), tmp_path / "rrfs.h5", read=_fake_read)
