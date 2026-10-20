"""
NOAA GFS 0.25 degree forecasts: cycle/horizon rules, cached byte-range downloads of the
``pgrb2.0p25`` product from the anonymous AWS Open Data bucket, grid geometry and GRIB2 decoding.

Only GFS v16 is read. Downloading needs only the standard library; decoding needs the optional
``eccodes`` dependency (``pip install firebench[gfs]``), imported lazily.
"""

from .forecast import (
    FIELDS,
    STATIC_FIELDS,
    VERSION,
    fetch_cycle,
    fetch_file,
    gfs_version,
    max_forecast_hour,
    output_hours,
    submit_cycle,
    validate_cycle,
)
from .grid import GFSGrid, earth_winds
from .read import read_fields

__all__ = [
    "FIELDS",
    "STATIC_FIELDS",
    "VERSION",
    "GFSGrid",
    "earth_winds",
    "fetch_cycle",
    "fetch_file",
    "gfs_version",
    "max_forecast_hour",
    "output_hours",
    "read_fields",
    "submit_cycle",
    "validate_cycle",
]
