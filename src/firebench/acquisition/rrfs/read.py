"""
Decoding of cached RRFS 3 km CONUS GRIB2 subsets into numpy arrays.

The shared Lambert reader (``firebench.acquisition.lambert_read``) checks each field's short name,
level, step type, and wind orientation, and every message against RRFS's Lambert parameters
(``RRFS_PARAMETERS``, to ``TOLERANCE_DEG``). eccodes is imported lazily (``pip install firebench[rrfs]``).
"""

from pathlib import Path

import numpy as np

from ..lambert_read import read_lambert_fields
from .grid import RRFS_PARAMETERS, TOLERANCE_DEG


def read_fields(grib_path: Path) -> dict[str, np.ndarray]:
    """Decode every field of a cached subset, keyed by ``VAR:LEVEL`` (arrays of shape (NY, NX))."""
    return read_lambert_fields(grib_path, RRFS_PARAMETERS, TOLERANCE_DEG, "rrfs")
