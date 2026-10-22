"""
NOAA RRFS forecasts: cycle/horizon rules and archive bounds, cached byte-range downloads of the 3 km
CONUS ``2dfld`` product from the anonymous AWS Open Data bucket, grid geometry and GRIB2 decoding.

Downloading needs only the standard library; decoding needs the optional ``eccodes`` dependency
(``pip install firebench[rrfs]``), imported lazily.
"""

from .forecast import (
    FIELDS,
    FIRST_CYCLE,
    STATIC_FIELDS,
    VERSION,
    fetch_cycle,
    fetch_file,
    max_forecast_hour,
    output_hours,
    rrfs_version,
    submit_cycle,
    validate_cycle,
)
from .grid import RRFSGrid, earth_winds
from .read import read_fields

__all__ = [
    "FIELDS",
    "FIRST_CYCLE",
    "STATIC_FIELDS",
    "VERSION",
    "RRFSGrid",
    "earth_winds",
    "fetch_cycle",
    "fetch_file",
    "max_forecast_hour",
    "output_hours",
    "read_fields",
    "rrfs_version",
    "submit_cycle",
    "validate_cycle",
]
