"""
Embedded RRFS adapter: sample RRFS 3 km CONUS forecasts at weather stations.

For one forecast cycle, the adapter writes a FireBench-standard model file with one
``/time_series/station_<STID>`` group per observation station, at RRFS's native hourly valid times.
The sampling and every declared adjustment are shared with the other forecast adapters
(``firebench.adapters.nwp_weather``); RRFS's own part is its 3 km Lambert conformal CONUS grid (HRRR's),
whose grid-relative 10 m winds are rotated to earth-relative components, and its root attributes.
"""

from collections.abc import Callable
from pathlib import Path

from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.rrfs import forecast as rrfs_forecast
from firebench.acquisition.rrfs.grid import RRFSGrid, earth_winds
from firebench.acquisition.rrfs.read import read_fields

from .nwp_weather import SCREEN_LEVEL_BAND_M, ModelGrid
from .nwp_weather import build_station_file as _build_station_file

ADAPTER_NAME = "firebench.adapters.rrfs_weather"
RRFS_GRID = ModelGrid(
    model="RRFS",
    domain="RRFS CONUS grid",
    product=rrfs_forecast.PRODUCT,
    adapter=ADAPTER_NAME,
    grid=RRFSGrid(),
    earth_winds=earth_winds,
    root_attributes=lambda cycle: {
        "rrfs_cycle": cycle.isoformat(),
        "rrfs_version": rrfs_forecast.rrfs_version(cycle),
        "rrfs_product": rrfs_forecast.PRODUCT,
        "source_bucket": rrfs_forecast.SOURCE_BUCKET,
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
    """
    Write the station-collocated RRFS model file of one cycle; returns a summary.

    Every observation station must lie on the RRFS CONUS grid, because the benchmark requires the model
    to provide every selected station (a station outside the grid is an error, not a silent gap).
    """
    return _build_station_file(
        obs_h5_path,
        cycle_files,
        out_h5_path,
        model_grid=RRFS_GRID,
        read=read,
        screen_level_band_m=screen_level_band_m,
    )
