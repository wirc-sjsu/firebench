"""
Decoding of cached GRIB2 subsets on a shared Lambert conformal grid (NAM, RRFS) into numpy arrays.

The ``fields`` of a subset's JSON sidecar are its fields in decode order. The subset is read with
eccodes' multi-field support, so the sub-messages of one GRIB message (NAM's 10 m U and V) come one
after the other; a file of single-field messages reads the same. Every field is checked against its
expected parameter (eccodes ``shortName``, which tells U from V), level, instantaneous step type, the
model's Lambert parameters (``LambertParameters.mismatch``) and, for wind components, grid-relative
orientation, so a change of layout is an error rather than wrong values. eccodes is imported lazily.
"""

import json
from pathlib import Path

import numpy as np

from .hrrr.read import _check_message
from .lambert import LambertParameters

# eccodes short names of the fields FireBench reads
SHORT_NAMES = {
    "TMP:2 m above ground": "2t",
    "RH:2 m above ground": "2r",
    "UGRD:10 m above ground": "10u",
    "VGRD:10 m above ground": "10v",
    "SFCR:surface": "fsr",
    "HGT:surface": "orog",
}


def read_lambert_fields(
    grib_path: Path, parameters: LambertParameters, tolerance_deg: float, extra: str
) -> dict[str, np.ndarray]:
    """
    Decode every field of a cached subset on the grid ``parameters`` describes, keyed by ``VAR:LEVEL``
    (arrays of shape (ny, nx)). ``extra`` names the FireBench extra that installs eccodes.
    """
    try:
        import eccodes  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise ImportError(
            f"Decoding {extra.upper()} GRIB2 files needs eccodes: pip install 'firebench[{extra}]'"
        ) from error

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
                        _check_grid(eccodes, gid, grib_path, parameters, tolerance_deg)
                        _check_parameter(eccodes, gid, field, grib_path)
                        _check_message(eccodes, gid, field, grib_path)
                        values = np.asarray(eccodes.codes_get_values(gid), dtype=np.float64)
                        if eccodes.codes_get(gid, "bitmapPresent"):
                            values[values == eccodes.codes_get(gid, "missingValue")] = np.nan
                    finally:
                        eccodes.codes_release(gid)
                    arrays[field] = values.reshape(parameters.ny, parameters.nx)

                extra_gid = eccodes.codes_grib_new_from_file(f)
                if extra_gid is not None:
                    eccodes.codes_release(extra_gid)
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


def _check_grid(eccodes, gid, grib_path: Path, parameters: LambertParameters, tolerance_deg: float) -> None:
    """Ensure the message is on the expected Lambert grid, scanning from its south-west corner."""
    try:
        problem = LambertParameters.from_message(eccodes, gid).mismatch(parameters, tolerance_deg)
    except ValueError as error:
        problem = str(error)
    if problem:
        raise ValueError(f"{grib_path}: unexpected grid: {problem}")
