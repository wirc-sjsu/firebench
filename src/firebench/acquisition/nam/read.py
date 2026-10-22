"""
Decoding of cached NAM nest GRIB2 subsets into numpy arrays.

NAM's 10 m U and V are two sub-messages of one GRIB message, which the shared Lambert reader
(``firebench.acquisition.lambert_read``) decodes one after the other with eccodes' multi-field
support, checking each field's short name and every message against the nest's Lambert parameters
(``NAM_PARAMETERS``, to ``TOLERANCE_DEG``). eccodes is imported lazily (``pip install firebench[nam]``).
"""

from pathlib import Path

import numpy as np

from ..lambert_read import read_lambert_fields
from .grid import NAM_PARAMETERS, TOLERANCE_DEG


def read_fields(grib_path: Path) -> dict[str, np.ndarray]:
    """Decode every field of a cached subset, keyed by ``VAR:LEVEL`` (arrays of shape (NY, NX))."""
    return read_lambert_fields(grib_path, NAM_PARAMETERS, TOLERANCE_DEG, "nam")
