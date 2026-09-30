"""
NOAA HRRR surface forecasts: cycle/horizon rules, cached byte-range downloads of the ``wrfsfc``
product from the anonymous AWS Open Data bucket, grid geometry and GRIB2 decoding.

Ported from spear ``backends/hrrr``. Downloading needs only the standard library; decoding needs the
optional ``eccodes`` dependency (``pip install firebench[hrrr]``), imported lazily.
"""

from .forecast import (
    FIELDS,
    STATIC_FIELDS,
    CycleFiles,
    PendingCycle,
    fetch_cycle,
    fetch_file,
    hrrr_version,
    max_forecast_hour,
    submit_cycle,
    validate_cycle,
)
from .grid import HRRRGrid, rotate_winds_to_earth
from .read import read_fields

__all__ = [
    "FIELDS",
    "STATIC_FIELDS",
    "CycleFiles",
    "HRRRGrid",
    "PendingCycle",
    "fetch_cycle",
    "fetch_file",
    "hrrr_version",
    "max_forecast_hour",
    "read_fields",
    "rotate_winds_to_earth",
    "submit_cycle",
    "validate_cycle",
]
