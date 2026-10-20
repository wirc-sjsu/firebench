"""
Embedded HRRR adapter: sample HRRR surface forecasts at weather stations.

For one forecast cycle, the adapter writes a FireBench-standard model file with one
``/time_series/station_<STID>`` group per observation station, at HRRR's native hourly valid times.
The sampling and every declared adjustment are shared with the other forecast adapters
(``firebench.adapters.nwp_weather``); HRRR's own part is its Lambert conformal grid, whose
grid-relative 10 m winds are rotated to earth-relative components, and its root attributes.
"""

from collections.abc import Callable
from pathlib import Path

from firebench.acquisition.hrrr import forecast as hrrr_forecast
from firebench.acquisition.hrrr.forecast import CycleFiles
from firebench.acquisition.hrrr.grid import HRRRGrid, rotate_winds_to_earth
from firebench.acquisition.hrrr.read import read_fields

# Re-exported: the names of this module before the shared sampling moved to nwp_weather
from .nwp_weather import (  # pylint: disable=unused-import
    HUMIDITY,
    ROUGHNESS,
    SCREEN_LEVEL_BAND_M,
    SCREEN_LEVEL_HEIGHT_M,
    TEMPERATURE,
    TERRAIN,
    VARIABLE_UNITS,
    WIND_REFERENCE_HEIGHT_M,
    WIND_U,
    WIND_V,
    Z0_MIN_M,
    ModelGrid,
    StationSite,
    read_station_sites,
    wind_at_height,
    wind_direction_from_components,
)
from .nwp_weather import build_station_file as _build_station_file
from .nwp_weather import sample_cycle as _sample_cycle

ADAPTER_NAME = "firebench.adapters.hrrr_weather"
HRRR_GRID = ModelGrid(
    model="HRRR",
    domain="HRRR CONUS grid",
    product=hrrr_forecast.PRODUCT,
    adapter=ADAPTER_NAME,
    grid=HRRRGrid(),
    earth_winds=rotate_winds_to_earth,
    root_attributes=lambda cycle: {
        "hrrr_cycle": cycle.isoformat(),
        "hrrr_version": hrrr_forecast.hrrr_version(cycle),
        "hrrr_product": hrrr_forecast.PRODUCT,
        "source_bucket": hrrr_forecast.SOURCE_BUCKET,
    },
)


def build_hrrr_station_file(
    obs_h5_path: Path,
    cycle_files: CycleFiles,
    out_h5_path: Path,
    *,
    screen_level_band_m: tuple[float, float] = SCREEN_LEVEL_BAND_M,
    read: Callable = read_fields,
) -> dict:
    """
    Write the station-collocated HRRR model file of one cycle; returns a summary.

    Every observation station must lie on the HRRR grid, because the benchmark requires the model to
    provide every selected station (a station outside the grid is an error, not a silent gap).
    """
    return _build_station_file(
        obs_h5_path,
        cycle_files,
        out_h5_path,
        model_grid=HRRR_GRID,
        read=read,
        screen_level_band_m=screen_level_band_m,
    )


# The adapter the `firebench wx` workflow calls for HRRR (`acquisition.forecast_models`)
build_station_file = build_hrrr_station_file


def sample_cycle(
    sites: list[StationSite], cycle_files: CycleFiles, *, read: Callable = read_fields
) -> dict:
    """Sample every forecast hour of a cycle at the nearest HRRR cell of each station."""
    return _sample_cycle(sites, cycle_files, HRRR_GRID, read=read)
