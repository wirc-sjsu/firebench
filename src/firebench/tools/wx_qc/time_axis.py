"""Validated conversion of FireBench HDF5 time axes."""

from datetime import datetime, timezone

import h5py
import numpy as np


class TimeAxisError(ValueError):
    """Raised when an HDF5 time dataset cannot be converted to timestamps."""


def parse_h5_time_axis(time_dataset: h5py.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Convert a FireBench HDF5 time dataset to UTC-naive timestamps.

    FireBench stores time as numeric minutes relative to the dataset's ISO
    ``time_origin`` attribute. This parser validates that representation before
    converting it so loading and exports interpret time identically.

    Args:
        time_dataset: One-dimensional HDF5 dataset containing relative minutes.

    Returns:
        A pair ``(timestamps, relative_minutes)``. ``timestamps`` has
        ``datetime64[us]`` dtype and ``relative_minutes`` has ``float64`` dtype.

    Raises:
        TimeAxisError: If the dataset cannot be read, is not one-dimensional,
            contains non-finite or non-numeric values, has no valid
            ``time_origin``, or cannot be represented at microsecond precision.
    """
    try:
        relative_minutes = np.asarray(time_dataset[:], dtype=np.float64)
    except (OSError, TypeError, ValueError) as exc:
        raise TimeAxisError(f"cannot read numeric relative minutes: {exc}") from exc

    if relative_minutes.ndim != 1:
        raise TimeAxisError(f"expected a one-dimensional time dataset, got {relative_minutes.ndim}D")
    if not np.all(np.isfinite(relative_minutes)):
        raise TimeAxisError("time dataset contains NaN or infinite values")

    origin_value = time_dataset.attrs.get("time_origin")
    if isinstance(origin_value, bytes):
        try:
            origin_value = origin_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TimeAxisError("time_origin is not valid UTF-8") from exc
    if not isinstance(origin_value, str) or not origin_value.strip():
        raise TimeAxisError("missing string time_origin attribute")

    try:
        origin = datetime.fromisoformat(origin_value)
    except ValueError as exc:
        raise TimeAxisError(f"invalid time_origin {origin_value!r}") from exc
    if origin.tzinfo is not None:
        origin = origin.astimezone(timezone.utc).replace(tzinfo=None)

    microseconds = relative_minutes * 60_000_000.0
    int64_limit = np.iinfo(np.int64).max
    if np.any(np.abs(microseconds) > int64_limit):
        raise TimeAxisError("relative minutes exceed datetime64 microsecond range")

    try:
        offsets = np.rint(microseconds).astype(np.int64).astype("timedelta64[us]")
        timestamps = np.datetime64(origin, "us") + offsets
    except (OverflowError, TypeError, ValueError) as exc:
        raise TimeAxisError(f"cannot construct timestamps: {exc}") from exc
    if np.isnat(timestamps).any():
        raise TimeAxisError("time axis contains unrepresentable timestamps")
    return timestamps, relative_minutes
