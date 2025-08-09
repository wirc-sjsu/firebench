from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo
from typing import Optional, Union
import h5py
from .logging_config import logger
from .units import ureg

_TZLike = Union[str, tzinfo]


def _resolve_tz(tz: Optional[_TZLike]) -> Optional[tzinfo]:
    if tz is None:
        return None
    if isinstance(tz, str):
        return ZoneInfo(tz)
    return tz  # already a tzinfo


def datetime_to_iso8601(
    dt: datetime,
    include_seconds: bool = True,
    tz: Optional[_TZLike] = None,
) -> str:
    """
    Convert a given datetime to an ISO 8601 formatted string (YYYY-MM-DDTHH:MM[:SS]±HH:MM).

    This function ensures the output always includes a timezone offset and can format
    the time either with seconds precision or minutes precision.

    Parameters
    ----------
    dt : datetime
        The datetime object to format. Can be naive (no timezone) or timezone-aware.
    include_seconds : bool, default=True
        Whether to include seconds in the output string. If False, output is rounded
        to the nearest minute.
    tz : str | tzinfo | None, default=None
        Target timezone for the output. Accepted forms:
        - String timezone key (e.g., "UTC", "Europe/Paris")
        - tzinfo or ZoneInfo object
        - None to use the timezone already set on `dt`

        Behavior:
        - If `tz` is provided and `dt` is naive: attach `tz` without shifting the time.
        - If `tz` is provided and `dt` is aware: convert `dt` to the specified `tz`.
        - If `tz` is None: `dt` must be timezone-aware; otherwise, a ValueError is raised.

    Returns
    -------
    str
        ISO 8601 formatted datetime string, always including a timezone offset.

    Raises
    ------
    ValueError
        If `tz` is None and `dt` is naive (no timezone information).
    """  # pylint: disable=line-too-long
    target_tz = _resolve_tz(tz)

    if target_tz is not None:
        if dt.tzinfo is None:
            # Treat naive dt as wall time in the given tz
            dt = dt.replace(tzinfo=target_tz)
        else:
            # Convert aware dt to the target tz
            dt = dt.astimezone(target_tz)
    else:
        # No tz provided—require dt to already be aware so the string has an offset
        if dt.tzinfo is None:
            raise ValueError("Timezone is required: pass `tz` or provide a timezone-aware `datetime`.")

    return dt.isoformat(timespec=("seconds" if include_seconds else "minutes"))


def current_datetime_iso8601(
    include_seconds: bool = True,
    tz: Optional[_TZLike] = None,
) -> str:
    """
    Get the current datetime as an ISO 8601 formatted string (YYYY-MM-DDTHH:MM[:SS]±HH:MM).

    The function retrieves the current local time, applies the specified timezone if given,
    and formats the result in ISO 8601 format with either seconds or minutes precision.

    Parameters
    ----------
    include_seconds : bool, default=True
        Whether to include seconds in the output string. If False, output is rounded
        to the nearest minute.
    tz : str | tzinfo | None, default=None
        Target timezone for the output. Accepted forms:
        - String timezone key (e.g., "UTC", "Europe/Paris")
        - tzinfo or ZoneInfo object
        - None to use the system's local timezone by default.

        Behavior:
        - If `tz` is provided: current local time is converted to the given timezone.
        - If `tz` is None: current local timezone is used by default.

    Returns
    -------
    str
        ISO 8601 formatted current datetime string, always including a timezone offset.
    """  # pylint: disable=line-too-long
    if tz is None:
        local_now = datetime.now().astimezone()
        # Log in the style you asked for
        logger.info("current_datetime_iso8601: no timezone specified, local timezone used.")
        # We already have an aware local time; pass through without forcing tz
        return datetime_to_iso8601(local_now, include_seconds)

    # Start from local now, then convert to requested tz for consistency
    now_local = datetime.now().astimezone()
    return datetime_to_iso8601(now_local, include_seconds, tz)


def read_quantity_from_fb_dataset(dataset_path: str, file_object: h5py.File | h5py.Group | h5py.Dataset):
    """
    Read a dataset from an HDF5 file, group, or dataset node and return it as a Pint Quantity
    according to the FireBench I/O standard.

    This function expects the dataset to comply with the FireBench standard I/O format
    (version >= 0.1), meaning it must define a string `units` attribute specifying the
    physical units of the stored values. The full dataset is loaded into memory and
    wrapped into a `pint.Quantity` using the global `ureg` registry.

    Parameters
    ----------
    dataset_path : str
        Path to the target dataset relative to `file_object`. For an `h5py.File`,
        this is the absolute or group-relative path (e.g., "/2D_raster/0001/temperature").
    file_object : h5py.File | h5py.Group | h5py.Dataset
        HDF5 file, group, or dataset object from which the dataset will be read.
        Must support item access via `__getitem__` and store datasets with `.attrs`.

    Returns
    -------
    pint.Quantity
        The dataset values loaded into memory, associated with the units taken from
        the dataset's `units` attribute.

    Raises
    ------
    KeyError
        If `dataset_path` does not exist in `file_object`.
    ValueError
        If the dataset has no `units` attribute or it is not a non-empty string.

    Notes
    -----
    - The function reads the **entire dataset** into memory; for very large datasets,
    consider reading subsets instead.
    - Compliant with FireBench I/O standard >= 0.1.
    """
    ds = file_object[dataset_path]

    units = ds.attrs.get("units", None)
    if not isinstance(units, str) or not units.strip():
        raise ValueError(
            f"Dataset '{dataset_path}' is missing a valid `units` attribute required by FireBench I/O standard."
        )
    
    return ureg.Quantity(ds[()], ds.attrs["units"])
