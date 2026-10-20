"""
Decoding of cached GFS GRIB2 subsets into numpy arrays.

Messages in a subset file are in the byte order of the source file, which is the order of the
``fields`` listed by its JSON sidecar. Every message is checked against its expected level,
instantaneous step type, the 0.25 degree grid and, for wind components, earth-relative orientation,
so a change of layout in a later GFS version is an error rather than wrong values. eccodes is
imported lazily (``pip install firebench[gfs]``).
"""

import json
from pathlib import Path

import numpy as np

from ..hrrr.read import expected_level
from .grid import LAT_FIRST, LON_FIRST, NX, NY

WIND_VARS = ("UGRD", "VGRD")


def read_fields(grib_path: Path) -> dict[str, np.ndarray]:
    """Decode every message of a cached subset, keyed by ``VAR:LEVEL`` (arrays of shape (NY, NX))."""
    try:
        import eccodes  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise ImportError("Decoding GFS GRIB2 files needs eccodes: pip install 'firebench[gfs]'") from error

    grib_path = Path(grib_path)
    fields = json.loads(grib_path.with_suffix(".json").read_text())["fields"]
    arrays: dict[str, np.ndarray] = {}
    with open(grib_path, "rb") as f:
        for field in fields:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                raise EOFError(f"{grib_path}: expected {len(fields)} GRIB messages, got {len(arrays)}")
            try:
                _check_grid(eccodes, gid, grib_path)
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
                f"{grib_path}: holds more GRIB messages than its sidecar lists ({len(fields)})"
            )
    return arrays


def _check_message(eccodes, gid, field: str, grib_path: Path) -> None:
    type_of_level, level = expected_level(field)
    actual_type = eccodes.codes_get(gid, "typeOfLevel")
    actual_level = eccodes.codes_get(gid, "level")
    step_type = eccodes.codes_get(gid, "stepType")
    if actual_type != type_of_level or (level is not None and float(actual_level) != level):
        raise ValueError(
            f"{grib_path}: message for {field} is on level {actual_type} {actual_level}, "
            f"expected {type_of_level} {level}"
        )
    if step_type != "instant":
        raise ValueError(f"{grib_path}: message for {field} has stepType {step_type!r}, expected 'instant'")
    if field.split(":", 1)[0] in WIND_VARS and eccodes.codes_get(gid, "uvRelativeToGrid") != 0:
        raise ValueError(f"{grib_path}: {field} is grid-relative; GFS winds are expected earth-relative")


def _check_grid(eccodes, gid, grib_path: Path) -> None:
    """Ensure the message is on the GFS 0.25 degree grid and scan order."""
    ni = eccodes.codes_get(gid, "Ni")
    nj = eccodes.codes_get(gid, "Nj")
    lat_1 = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees")
    lon_1 = eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
    i_neg = eccodes.codes_get(gid, "iScansNegatively")
    j_pos = eccodes.codes_get(gid, "jScansPositively")

    if (
        (ni, nj, i_neg, j_pos) != (NX, NY, 0, 0)
        or abs(lat_1 - LAT_FIRST) > 1e-4
        or abs(lon_1 % 360.0 - LON_FIRST) > 1e-4
    ):
        raise ValueError(
            f"{grib_path}: unexpected grid (Ni={ni}, Nj={nj}, first point=({lat_1}, {lon_1}), "
            f"iScansNegatively={i_neg}, jScansPositively={j_pos})"
        )
