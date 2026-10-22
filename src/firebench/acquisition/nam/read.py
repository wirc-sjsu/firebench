"""
Decoding of cached NAM nest GRIB2 subsets into numpy arrays.

The ``fields`` of a subset's JSON sidecar are its fields in decode order. NAM's 10 m U and V are two
sub-messages of one GRIB message, so the subset is read with eccodes' multi-field support, which
returns them one after the other. Every field is checked against its expected parameter (eccodes
``shortName``, which tells U from V), level, instantaneous step type, the nest's Lambert parameters
(``LambertParameters.mismatch``) and, for wind components, grid-relative orientation, so a change of
layout is an error rather than wrong values. eccodes is imported lazily (``pip install firebench[nam]``).
"""

import json
from pathlib import Path

import numpy as np

from ..hrrr.read import _check_message
from ..lambert import LambertParameters
from .grid import NAM_PARAMETERS, NX, NY, TOLERANCE_DEG

# eccodes short names of the fields FireBench reads
SHORT_NAMES = {
    "TMP:2 m above ground": "2t",
    "RH:2 m above ground": "2r",
    "UGRD:10 m above ground": "10u",
    "VGRD:10 m above ground": "10v",
    "SFCR:surface": "fsr",
    "HGT:surface": "orog",
}


def read_fields(grib_path: Path) -> dict[str, np.ndarray]:
    """Decode every field of a cached subset, keyed by ``VAR:LEVEL`` (arrays of shape (NY, NX))."""
    try:
        import eccodes  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise ImportError("Decoding NAM GRIB2 files needs eccodes: pip install 'firebench[nam]'") from error

    grib_path = Path(grib_path)
    fields = json.loads(grib_path.with_suffix(".json").read_text())["fields"]
    arrays: dict[str, np.ndarray] = {}
    eccodes.codes_grib_multi_support_on()
    try:
        with open(grib_path, "rb") as f:
            try:
                for field in fields:
                    gid = eccodes.codes_grib_new_from_file(f)
                    if gid is None:
                        raise EOFError(
                            f"{grib_path}: expected {len(fields)} GRIB fields, got {len(arrays)}"
                        )
                    try:
                        _check_grid(eccodes, gid, grib_path)
                        _check_parameter(eccodes, gid, field, grib_path)
                        _check_message(eccodes, gid, field, grib_path)
                        values = np.asarray(eccodes.codes_get_values(gid), dtype=np.float64)
                        if eccodes.codes_get(gid, "bitmapPresent"):
                            values[values == eccodes.codes_get(gid, "missingValue")] = np.nan
                    finally:
                        eccodes.codes_release(gid)
                    arrays[field] = values.reshape(NY, NX)

                extra = eccodes.codes_grib_new_from_file(f)
                if extra is not None:
                    eccodes.codes_release(extra)
                    raise ValueError(
                        f"{grib_path}: holds more GRIB fields than its sidecar lists ({len(fields)})"
                    )
            finally:
                eccodes.codes_grib_multi_support_reset_file(f)
    finally:
        eccodes.codes_grib_multi_support_off()
    return arrays


def _check_parameter(eccodes, gid, field: str, grib_path: Path) -> None:
    expected = SHORT_NAMES.get(field)
    actual = eccodes.codes_get(gid, "shortName")
    if expected is not None and actual != expected:
        raise ValueError(f"{grib_path}: field for {field} is {actual!r}, expected {expected!r}")


def _check_grid(eccodes, gid, grib_path: Path) -> None:
    """Ensure the message is on the NAM CONUS nest grid, scanning from its south-west corner."""
    try:
        problem = LambertParameters.from_message(eccodes, gid).mismatch(NAM_PARAMETERS, TOLERANCE_DEG)
    except ValueError as error:
        problem = str(error)
    if problem:
        raise ValueError(f"{grib_path}: unexpected grid: {problem}")
