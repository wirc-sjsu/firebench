"""
Embedded GFS adapter: sample GFS 0.25 degree forecasts at weather stations.

For one forecast cycle, the adapter writes a FireBench-standard model file with one
``/time_series/station_<STID>`` group per observation station, at GFS's native hourly valid times.
The sampling and every declared adjustment are shared with the other forecast adapters
(``firebench.adapters.nwp_weather``). A station is sampled at its nearest cell of the global
0.25 degree grid, about 25 km wide, whose terrain-height difference with the station is written as
a per-station diagnostic; GFS winds are earth-relative and need no rotation.
"""

from collections.abc import Callable
from pathlib import Path

from firebench.acquisition.gfs import forecast as gfs_forecast
from firebench.acquisition.gfs.grid import GFSGrid, earth_winds
from firebench.acquisition.gfs.read import read_fields
from firebench.acquisition.hrrr.forecast import CycleFiles

from .nwp_weather import SCREEN_LEVEL_BAND_M, ModelGrid
from .nwp_weather import build_station_file as _build_station_file

ADAPTER_NAME = "firebench.adapters.gfs_weather"
GFS_GRID = ModelGrid(
    model="GFS",
    domain="GFS 0.25 degree grid",
    product=gfs_forecast.PRODUCT,
    adapter=ADAPTER_NAME,
    grid=GFSGrid(),
    earth_winds=earth_winds,
    root_attributes=lambda cycle: {
        "gfs_cycle": cycle.isoformat(),
        "gfs_version": gfs_forecast.gfs_version(cycle),
        "gfs_product": gfs_forecast.PRODUCT,
        "source_bucket": gfs_forecast.SOURCE_BUCKET,
    },
)


def build_station_file(
    obs_h5_path: Path,
    cycle_files: CycleFiles,
    out_h5_path: Path,
    *,
    screen_level_band_m: tuple[float, float] = SCREEN_LEVEL_BAND_M,
    read: Callable = read_fields,
) -> dict:
    """Write the station-collocated GFS model file of one cycle; returns a summary."""
    return _build_station_file(
        obs_h5_path,
        cycle_files,
        out_h5_path,
        model_grid=GFS_GRID,
        read=read,
        screen_level_band_m=screen_level_band_m,
    )
