"""
Forecast models ``firebench wx`` downloads and brings to weather stations, one per ``model.name``.

Each entry names the module that fetches the model's cycles into the cache (``submit_cycle``,
``fetch_file``, ``is_cached``, ``cached_file_path``, ``fields_for_hour``, ``max_forecast_hour``,
``PRODUCT``, ``FIELDS``, ``STATIC_FIELDS``) and the adapter module that samples them at stations
(``build_station_file``). The forecast module is looked up when it is called, so tests can replace
its functions.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType

from .gfs import forecast as gfs_forecast
from .hrrr import forecast as hrrr_forecast


@dataclass(frozen=True)
class ForecastModel:
    """One forecast model of ``firebench wx``."""

    name: str
    source: str
    forecast: ModuleType
    version: Callable[[datetime], str]
    adapter_module: str
    # Measured subset sizes in MB: forecast hour 0 (which carries the terrain field), then each other hour
    file_mb: tuple[float, float]
    domain_problem: Callable[[tuple[float, float, float, float]], str | None]

    def download_mb(self, horizon_hours: int) -> float:
        """Estimated download of one cycle of ``horizon_hours`` hours, in MB."""
        return round(self.file_mb[0] + self.file_mb[1] * horizon_hours, 1)


def _hrrr_domain_problem(bbox) -> str | None:
    # pylint: disable-next=import-outside-toplevel
    from .hrrr.grid import HRRRGrid

    lon_min, lat_min, lon_max, lat_max = bbox
    grid = HRRRGrid()
    i, j = grid.ij_arrays_from_latlon(
        [lat_min, lat_min, lat_max, lat_max], [lon_min, lon_max, lon_min, lon_max]
    )
    if not all(grid.contains(i, j)):
        return f"domain.bbox {list(bbox)} is not fully inside the HRRR CONUS grid"
    return None


MODELS = {
    "HRRR": ForecastModel(
        name="HRRR",
        source="NOAA Open Data on AWS, anonymous access",
        forecast=hrrr_forecast,
        version=lambda cycle: str(hrrr_forecast.hrrr_version(cycle)),
        adapter_module="firebench.adapters.hrrr_weather",
        file_mb=(11.6, 9.4),
        domain_problem=_hrrr_domain_problem,
    ),
    "GFS": ForecastModel(
        name="GFS",
        source="NOAA Open Data on AWS, anonymous access",
        forecast=gfs_forecast,
        version=gfs_forecast.gfs_version,
        adapter_module="firebench.adapters.gfs_weather",
        file_mb=(4.6, 3.7),
        domain_problem=lambda bbox: None,
    ),
}


def get_model(name: str) -> ForecastModel:
    """The forecast model of a setup's ``model.name`` (case-insensitive)."""
    try:
        return MODELS[str(name).upper()]
    except KeyError:
        raise ValueError(f"unknown forecast model '{name}' (available: {', '.join(MODELS)})") from None


def download_mb_per_cycle(name: str, horizon_hours: int) -> float:
    """Estimated download of one cycle of model ``name``, in MB."""
    return get_model(name).download_mb(horizon_hours)
