"""
Embedded NAM adapter: sample NAM CONUS nest forecasts at weather stations.

For one forecast cycle, the adapter writes a FireBench-standard model file with one
``/time_series/station_<STID>`` group per observation station, at NAM's native hourly valid times.
The sampling and every declared adjustment are shared with the other forecast adapters
(``firebench.adapters.nwp_weather``); NAM's own part is its 3 km Lambert conformal grid, whose
grid-relative 10 m winds are rotated to earth-relative components, and its root attributes.
"""

from collections.abc import Callable
from pathlib import Path

from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.nam import forecast as nam_forecast
from firebench.acquisition.nam.grid import NAMGrid, earth_winds
from firebench.acquisition.nam.read import read_fields

from .nwp_weather import SCREEN_LEVEL_BAND_M, ModelGrid
from .nwp_weather import build_station_file as _build_station_file

ADAPTER_NAME = "firebench.adapters.nam_weather"
NAM_GRID = ModelGrid(
    model="NAM",
    domain="NAM CONUS nest grid",
    product=nam_forecast.PRODUCT,
    adapter=ADAPTER_NAME,
    grid=NAMGrid(),
    earth_winds=earth_winds,
    root_attributes=lambda cycle: {
        "nam_cycle": cycle.isoformat(),
        "nam_version": nam_forecast.nam_version(cycle),
        "nam_product": nam_forecast.PRODUCT,
        "source_bucket": nam_forecast.SOURCE_BUCKET,
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
    Write the station-collocated NAM model file of one cycle; returns a summary.

    Every observation station must lie on the NAM nest grid, because the benchmark requires the model
    to provide every selected station (a station outside the grid is an error, not a silent gap).
    """
    return _build_station_file(
        obs_h5_path,
        cycle_files,
        out_h5_path,
        model_grid=NAM_GRID,
        read=read,
        screen_level_band_m=screen_level_band_m,
    )
