"""
Daily counts of cloud-to-ground lightning strikes in 0.1° cells, from the NLDN tiles that NOAA NCEI
publishes in its Severe Weather Data Inventory (SWDI), anonymous.

NCEI counts the strikes of the Vaisala National Lightning Detection Network (NLDN) that reached the
ground in each cell of a 0.1° grid for each UTC day, and publishes one gzipped CSV per year
(``nldn-tiles-YYYY.csv.gz``), or per month for the year in progress (``nldn-tiles-YYYYMM.csv.gz``).
The strokes themselves, with their time and position, are not public.

:func:`fetch_nldn_tiles` lists the directory, downloads the files of a window, and keeps the cells
of a box on the days that overlap the window. ``firebench.standardize.standardize_nldn_tiles``
writes them in a standard file.
"""

import hashlib
import io
import logging
import re
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .http import http_get

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/database-csv/v2/"
PRODUCT = "nldn-tiles"
CELL_SIZE = 0.1  # degree
FILE_NAME = re.compile(r"nldn-tiles-(\d{4})(\d{2})?\.csv\.gz")
COLUMNS = ("day", "lon", "lat", "count")


@dataclass(frozen=True)
class NldnTiles:
    """
    The cells of a box with at least one strike, on the UTC days that overlap a window.

    ``day`` is the first instant of each row's UTC day (``datetime64[D]``). ``files`` names each file
    read with its SHA-256 and the rows kept from it; ``missing`` names the months of the window that
    no published file covers yet.
    """

    bbox: tuple[float, float, float, float]  # west, south, east, north
    start: datetime
    end: datetime
    day: np.ndarray
    lat: np.ndarray  # cell centre
    lon: np.ndarray
    count: np.ndarray
    files: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def window_days(start: datetime, end: datetime) -> tuple[date, date]:
    """The first and last UTC days that overlap ``[start, end]``; an end at midnight adds no day."""
    start, end = _utc(start), _utc(end)
    if end < start:
        raise ValueError(f"end {end.isoformat()} is before start {start.isoformat()}")
    last = end.date()
    if end > start and end.time() == datetime.min.time():
        last -= timedelta(days=1)
    return start.date(), last


def list_tile_files(*, opener: Callable = urllib.request.urlopen) -> list[str]:
    """The NLDN tile files NCEI lists, by name."""
    listing = http_get(BASE_URL, opener=opener).decode(errors="replace")
    return sorted(set(match.group(0) for match in FILE_NAME.finditer(listing)))


def tile_files(start: datetime, end: datetime, available: Iterable[str]) -> tuple[list[str], list[str]]:
    """
    The files that cover a window, and the months no file covers.

    A year is read from its annual file when it is published, and from its monthly files otherwise.
    Missing months are named ``YYYY-MM``.
    """
    available = set(available)
    first, last = window_days(start, end)
    names, missing = [], []
    for year in range(first.year, last.year + 1):
        annual = f"{PRODUCT}-{year}.csv.gz"
        if annual in available:
            names.append(annual)
            continue
        month_first = first.month if year == first.year else 1
        month_last = last.month if year == last.year else 12
        for month in range(month_first, month_last + 1):
            monthly = f"{PRODUCT}-{year}{month:02d}.csv.gz"
            if monthly in available:
                names.append(monthly)
            else:
                missing.append(f"{year}-{month:02d}")
    return names, missing


def read_tile_rows(payload: bytes, bbox, start: datetime, end: datetime) -> pd.DataFrame:
    """The rows of a gzipped tile file whose cell centre is in the box and day overlaps the window."""
    west, south, east, north = (float(value) for value in bbox)
    first, last = window_days(start, end)
    frame = pd.read_csv(
        io.BytesIO(payload),
        compression="gzip",
        comment="#",
        header=None,
        names=COLUMNS,
        dtype={"day": np.int64, "lon": np.float64, "lat": np.float64, "count": np.int64},
    )
    keep = (
        (frame["day"] >= int(first.strftime("%Y%m%d")))
        & (frame["day"] <= int(last.strftime("%Y%m%d")))
        & (frame["lon"] >= west)
        & (frame["lon"] <= east)
        & (frame["lat"] >= south)
        & (frame["lat"] <= north)
    )
    return frame[keep]


def fetch_nldn_tiles(
    bbox,
    start: datetime,
    end: datetime,
    *,
    opener: Callable = urllib.request.urlopen,
    local_dir: Path | None = None,
) -> NldnTiles:
    """
    The NLDN tiles of a box and window, from NCEI or from a local copy of its directory.

    ``local_dir`` holds files named as NCEI names them; nothing is downloaded then.

    Raises
    ------
    ValueError
        If the box is empty or no file covers any day of the window.
    """
    west, south, east, north = (float(value) for value in bbox)
    if not (west < east and south < north):
        raise ValueError(f"empty box {bbox}")
    start, end = _utc(start), _utc(end)
    if local_dir is not None:
        available = [path.name for path in Path(local_dir).iterdir() if FILE_NAME.fullmatch(path.name)]
    else:
        available = list_tile_files(opener=opener)
    names, missing = tile_files(start, end, available)
    if not names:
        raise ValueError(f"NCEI publishes no NLDN tile file for {', '.join(missing)} yet")

    parts, files = [], []
    for name in names:
        if local_dir is not None:
            payload = (Path(local_dir) / name).read_bytes()
        else:
            payload = http_get(BASE_URL + name, opener=opener)
        rows = read_tile_rows(payload, (west, south, east, north), start, end)
        logger.info("[nldn tiles] %s: %d cells kept", name, len(rows))
        files.append(
            {"name": name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "rows": len(rows)}
        )
        parts.append(rows)

    rows = pd.concat(parts, ignore_index=True).sort_values(["day", "lat", "lon"], kind="stable")
    days = pd.to_datetime(rows["day"].astype(str), format="%Y%m%d").to_numpy().astype("datetime64[D]")
    return NldnTiles(
        bbox=(west, south, east, north),
        start=start,
        end=end,
        day=days,
        lat=rows["lat"].to_numpy(dtype=np.float64),
        lon=rows["lon"].to_numpy(dtype=np.float64),
        count=rows["count"].to_numpy(dtype=np.int64),
        files=files,
        missing=missing,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)
