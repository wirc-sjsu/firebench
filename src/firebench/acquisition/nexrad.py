"""
NEXRAD Level II volume scans of the WSR-88D weather radars, from the NOAA Open Data archive on AWS
(``unidata-nexrad-level2``), anonymous.

:func:`nexrad_sites` reads the table of sites kept with FireBench, :func:`sites_in_range` keeps
those within reach of a box, :func:`list_volumes` lists the volumes of a site in a window,
:func:`select_volumes` keeps one volume per time step, and :func:`fetch_volumes` downloads them with
a few threads and yields them in time order, deleting each file once the caller has moved on.
``firebench.standardize.standardize_nexrad_level2`` reads the volumes.

The archive was ``noaa-nexrad-level2`` until 1 September 2025; NODD moved it to
``unidata-nexrad-level2`` with the same keys, ``YYYY/MM/DD/SITE/SITEYYYYMMDD_HHMMSS_V06``.
"""

import csv
import hashlib
import logging
import math
import os
import re
import tempfile
import urllib.request
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from .goes_fdc import sha256_file
from .http import http_get, list_s3_keys

logger = logging.getLogger(__name__)

BUCKET = "unidata-nexrad-level2"
# 0 keeps every volume; a WSR-88D scans a volume every 4 to 10 minutes, depending on its pattern.
TIME_STEPS_MIN = (0, 5, 10, 15, 30, 60)
# The reach of a WSR-88D for plumes: reflectivity is useful to about 230 km, where the lowest beam
# is already 4 to 5 km above the ground.
DEFAULT_MAX_RANGE_KM = 230.0
EARTH_RADIUS_M = 6_371_008.8
_FT = 0.3048
VOLUME_KEY = re.compile(
    r"^(?P<site>[A-Z0-9]{4})(?P<stamp>\d{8}_\d{6})(?:_V(?P<version>\d{2}))?(?P<gz>\.gz)?$"
)


@dataclass(frozen=True)
class NexradSite:
    """A WSR-88D site of the table kept with FireBench."""

    icao: str
    name: str
    state: str
    country: str
    latitude: float
    longitude: float
    elevation_m: float


@dataclass(frozen=True)
class NexradVolume:
    """One Level II volume file in the archive."""

    bucket: str
    key: str
    site: str
    time_start: datetime
    size: int | None = None


@dataclass(frozen=True)
class FetchedVolume:
    """A volume on disk with its SHA-256, or the reason it could not be fetched."""

    volume: NexradVolume
    path: Path | None
    sha256: str | None
    error: str | None = None


@lru_cache(maxsize=1)
def nexrad_sites() -> dict[str, NexradSite]:
    """The WSR-88D sites by ICAO identifier, from NOAA NCEI's station list (``resources/``)."""
    text = files("firebench").joinpath("resources/nexrad_sites.csv").read_text(encoding="utf-8")
    rows = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    return {
        row["icao"]: NexradSite(
            icao=row["icao"],
            name=row["name"],
            state=row["state"],
            country=row["country"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            elevation_m=round(float(row["elevation_ft"]) * _FT, 1),
        )
        for row in rows
    }


def site(icao: str) -> NexradSite:
    """One site of the table; ``ValueError`` names an unknown identifier."""
    sites = nexrad_sites()
    if icao not in sites:
        raise ValueError(f"unknown NEXRAD site {icao!r}")
    return sites[icao]


def distance_to_box_km(latitude: float, longitude: float, bbox) -> float:
    """Great-circle distance from a point to the nearest point of a box, 0 inside it."""
    west, south, east, north = _bbox(bbox)
    lat = min(max(latitude, south), north)
    lon = min(max(longitude, west), east)
    return _haversine_m(latitude, longitude, lat, lon) / 1000.0


def sites_in_range(bbox, max_km: float = DEFAULT_MAX_RANGE_KM) -> list[tuple[NexradSite, float]]:
    """The sites within ``max_km`` of a box ``(west, south, east, north)``, nearest first."""
    found = []
    for item in nexrad_sites().values():
        distance = distance_to_box_km(item.latitude, item.longitude, bbox)
        if distance <= max_km:
            found.append((item, round(distance, 1)))
    return sorted(found, key=lambda pair: (pair[1], pair[0].icao))


def volume_time(key: str) -> datetime:
    """Start of a volume, to the second, from the stamp of its key."""
    match = VOLUME_KEY.match(key.rsplit("/", 1)[-1])
    if match is None:
        raise ValueError(f"not a NEXRAD Level II volume key: {key!r}")
    return datetime.strptime(match["stamp"], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)


def is_volume_key(key: str) -> bool:
    """True for a volume file; False for the metadata files (``_MDM``) and anything else."""
    return VOLUME_KEY.match(key.rsplit("/", 1)[-1]) is not None


def list_volumes(
    icao: str,
    start: datetime,
    end: datetime,
    *,
    bucket: str = BUCKET,
    opener: Callable = urllib.request.urlopen,
) -> list[NexradVolume]:
    """The volumes of a site whose start is in ``[start, end)``, in time order."""
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError(f"the window ends ({end.isoformat()}) before it starts ({start.isoformat()})")
    site(icao)
    volumes = {}
    day = start.date()
    while datetime(day.year, day.month, day.day, tzinfo=timezone.utc) < end:
        for key, size in list_s3_keys(bucket, f"{day:%Y/%m/%d}/{icao}/", opener=opener):
            if not is_volume_key(key):
                continue
            time_start = volume_time(key)
            if start <= time_start < end:
                volumes[key] = NexradVolume(bucket, key, icao, time_start, size)
        day += timedelta(days=1)
    return sorted(volumes.values(), key=lambda volume: (volume.time_start, volume.key))


def select_volumes(volumes: Iterable[NexradVolume], time_step_min: int) -> list[NexradVolume]:
    """
    The first volume of each ``time_step_min`` bin, bins counted from the Unix epoch, in time order.

    A step of 0 keeps every volume. The rule is the one of ``goes_fdc.select_scans``.
    """
    if time_step_min not in TIME_STEPS_MIN:
        raise ValueError(f"time step {time_step_min!r} min is not one of {TIME_STEPS_MIN}")
    ordered = sorted(volumes, key=lambda item: (item.time_start, item.key))
    if time_step_min == 0:
        return ordered
    kept, seen = [], set()
    for volume in ordered:
        bin_id = (volume.site, int(volume.time_start.timestamp()) // (time_step_min * 60))
        if bin_id not in seen:
            seen.add(bin_id)
            kept.append(volume)
    return kept


def fetch_volumes(
    volumes: Sequence[NexradVolume],
    directory: Path,
    *,
    workers: int = 4,
    keep: bool = False,
    opener: Callable = urllib.request.urlopen,
) -> Iterator[FetchedVolume]:
    """
    Download volumes into ``directory`` (bucket layout) and yield them in the order given.

    Up to ``workers`` downloads run ahead of the caller. Unless ``keep``, a yielded file is deleted
    when the caller asks for the next one or closes the iterator, so the directory holds about
    ``workers`` files at a time. A volume that fails after the retries of ``http_get`` is yielded
    with its error and no path.
    """
    directory = Path(directory)
    width = max(1, workers)
    pending: deque[tuple[NexradVolume, Future]] = deque()
    queue = iter(volumes)
    previous: Path | None = None
    with ThreadPoolExecutor(max_workers=width) as pool:
        try:
            for volume in queue:
                pending.append((volume, pool.submit(_fetch_one, volume, directory, opener)))
                if len(pending) >= width:
                    break
            while pending:
                _, future = pending.popleft()
                fetched = future.result()
                following = next(queue, None)
                if following is not None:
                    pending.append((following, pool.submit(_fetch_one, following, directory, opener)))
                if previous is not None and not keep:
                    previous.unlink(missing_ok=True)
                previous = fetched.path
                yield fetched
        finally:
            for _, future in pending:
                future.cancel()
            if not keep:
                if previous is not None:
                    previous.unlink(missing_ok=True)
                for _, future in pending:
                    if future.done() and not future.cancelled() and future.result().path is not None:
                        future.result().path.unlink(missing_ok=True)


def local_volumes(
    directory: Path, icao: str, start: datetime, end: datetime, *, bucket: str = BUCKET
) -> list[NexradVolume]:
    """The volumes of a site found in a directory laid out like the bucket (``<bucket>/<key>``)."""
    start, end = _utc(start), _utc(end)
    root = Path(directory) / bucket
    volumes = []
    for path in sorted(root.glob(f"*/*/*/{icao}/*")):
        key = path.relative_to(root).as_posix()
        if not path.is_file() or not is_volume_key(key):
            continue
        time_start = volume_time(key)
        if start <= time_start < end:
            volumes.append(NexradVolume(bucket, key, icao, time_start, path.stat().st_size))
    return sorted(volumes, key=lambda volume: (volume.time_start, volume.key))


def local_fetched_volumes(volumes: Iterable[NexradVolume], directory: Path) -> Iterator[FetchedVolume]:
    """Yield volumes read in place from a directory in the bucket layout. Nothing is deleted."""
    for volume in volumes:
        path = Path(directory) / volume.bucket / volume.key
        if path.is_file():
            yield FetchedVolume(volume, path, sha256_file(path))
        else:
            yield FetchedVolume(volume, None, None, f"missing file {path}")


def _fetch_one(volume: NexradVolume, directory: Path, opener: Callable) -> FetchedVolume:
    dest = directory / volume.bucket / volume.key
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = http_get(f"https://{volume.bucket}.s3.amazonaws.com/{volume.key}", opener=opener)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".part", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return FetchedVolume(volume, dest, hashlib.sha256(body).hexdigest())
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.warning("[nexrad] %s/%s: %s", volume.bucket, volume.key, error)
        return FetchedVolume(volume, None, None, str(error))


def _bbox(bbox) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid box {bbox!r}: expected west < east and south < north, in degrees")
    return west, south, east, north


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)
