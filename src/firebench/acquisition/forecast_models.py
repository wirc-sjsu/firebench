"""
Forecast models ``firebench wx`` downloads and brings to weather stations, one per ``model.name``.

Each entry names the module that fetches the model's cycles into the cache (``submit_cycle``,
``fetch_file``, ``is_cached``, ``cached_file_path``, ``fields_for_hour``, ``max_forecast_hour``,
``output_hours``, ``PRODUCT``, ``FIELDS``, ``STATIC_FIELDS``) and the adapter module that samples them
at stations (``build_station_file``). ``max_forecast_hour`` refuses a cycle the model's archive does
not hold (``hrrr.forecast.check_archive``); ``output_hours`` lists the forecast hours a cycle holds,
which a setup's cadences must find (``wx_setup``). The forecast module is looked up when it is
called, so tests can replace its functions.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType

from .gfs import forecast as gfs_forecast
from .hrrr import forecast as hrrr_forecast
from .nam import forecast as nam_forecast
from .rrfs import forecast as rrfs_forecast


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


def _outside_grid(grid, domain: str, bbox) -> str | None:
    """The problem of a bounding box whose corners are not all on a limited-area grid."""
    lon_min, lat_min, lon_max, lat_max = bbox
    i, j = grid.ij_arrays_from_latlon(
        [lat_min, lat_min, lat_max, lat_max], [lon_min, lon_max, lon_min, lon_max]
    )
    if not all(grid.contains(i, j)):
        return f"domain.bbox {list(bbox)} is not fully inside the {domain}"
    return None


def _hrrr_domain_problem(bbox) -> str | None:
    # pylint: disable-next=import-outside-toplevel
    from .hrrr.grid import HRRRGrid

    return _outside_grid(HRRRGrid(), "HRRR CONUS grid", bbox)


def _nam_domain_problem(bbox) -> str | None:
    # pylint: disable-next=import-outside-toplevel
    from .nam.grid import NAMGrid

    return _outside_grid(NAMGrid(), "NAM CONUS nest grid", bbox)


def _rrfs_domain_problem(bbox) -> str | None:
    # pylint: disable-next=import-outside-toplevel
    from .rrfs.grid import RRFSGrid

    return _outside_grid(RRFSGrid(), "RRFS CONUS grid", bbox)


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
    "NAM": ForecastModel(
        name="NAM",
        source="NOAA Open Data on AWS, anonymous access",
        forecast=nam_forecast,
        version=nam_forecast.nam_version,
        adapter_module="firebench.adapters.nam_weather",
        file_mb=(10.5, 8.9),
        domain_problem=_nam_domain_problem,
    ),
    "RRFS": ForecastModel(
        name="RRFS",
        source="NOAA Open Data on AWS, anonymous access",
        forecast=rrfs_forecast,
        version=rrfs_forecast.rrfs_version,
        adapter_module="firebench.adapters.rrfs_weather",
        file_mb=(10.0, 8.3),
        domain_problem=_rrfs_domain_problem,
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
