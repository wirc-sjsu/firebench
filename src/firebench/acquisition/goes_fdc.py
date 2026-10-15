"""
GOES-R ABI fire detections (Fire Detection and Characterization, CONUS sector, ``ABI-L2-FDCC``) from
the NOAA Open Data buckets on AWS, anonymous.

A platform (GOES-East, GOES-West) is served by different satellites over time, each with its own
bucket. :func:`goes_segments` splits a window at the switches, :func:`list_fdc_scans` lists the
scans of a segment, :func:`select_scans` keeps one scan per time step, and :func:`fetch_fdc_scans`
downloads them with a few threads and yields them in time order, deleting each file once the caller
has moved on. ``firebench.standardize`` reads the scans.

Ported from spear ``backends/satellite/goes_fdc.py``. The scan times are read from the file names,
to the second, as spear does.
"""

import hashlib
import logging
import os
import re
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405 - parses the listing of a fixed public bucket
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .http import http_get

logger = logging.getLogger(__name__)

PRODUCT = "ABI-L2-FDCC"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
# The satellite serving each platform, from the date it took over (UTC midnight).
SWITCHES: dict[str, list[tuple[date | None, int]]] = {
    "east": [(None, 16), (date(2025, 4, 7), 19)],
    "west": [(None, 17), (date(2023, 1, 4), 18)],
}
TIME_STEPS_MIN = (5, 10, 15, 30, 60)  # 5 keeps every CONUS scan
SCAN_STAMP = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d_e(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d_")


@dataclass(frozen=True)
class GoesSegment:
    """The part of a window one satellite served for a platform."""

    platform: str
    satellite: int
    bucket: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class FdcScan:
    """One FDCC file in a bucket."""

    bucket: str
    key: str
    time_start: datetime
    time_end: datetime
    size: int | None = None


@dataclass(frozen=True)
class FetchedScan:
    """A scan on disk with its SHA-256, or the reason it could not be fetched."""

    scan: FdcScan
    path: Path | None
    sha256: str | None
    error: str | None = None


def bucket_name(satellite: int) -> str:
    """The NOAA Open Data bucket of a GOES satellite."""
    return f"noaa-goes{satellite}"


def goes_segments(
    start: datetime, end: datetime, platforms: Sequence[str] = ("east", "west")
) -> list[GoesSegment]:
    """Split ``[start, end)`` per platform at the dates another satellite took over."""
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError(f"the window ends ({end.isoformat()}) before it starts ({start.isoformat()})")
    unknown = [platform for platform in platforms if platform not in SWITCHES]
    if unknown or not platforms:
        raise ValueError(
            f"unknown or missing GOES platforms {unknown or list(platforms)}; known: east, west"
        )
    segments = []
    for platform in dict.fromkeys(platforms):
        switches = SWITCHES[platform]
        for index, (since, satellite) in enumerate(switches):
            begin = _midnight(since) if since else None
            until = _midnight(switches[index + 1][0]) if index + 1 < len(switches) else None
            seg_start = max(start, begin) if begin else start
            seg_end = min(end, until) if until else end
            if seg_start < seg_end:
                segments.append(
                    GoesSegment(platform, satellite, bucket_name(satellite), seg_start, seg_end)
                )
    return segments


def scan_times(key: str) -> tuple[datetime, datetime]:
    """Start and end of a scan, to the second, from the ``_s`` and ``_e`` stamps of its key."""
    match = SCAN_STAMP.search(key)
    if match is None:
        raise ValueError(f"no scan time stamps in {key!r}")
    values = match.groups()
    return _stamp(values[:5]), _stamp(values[5:])


def list_fdc_scans(segment: GoesSegment, *, opener: Callable = urllib.request.urlopen) -> list[FdcScan]:
    """The scans of a segment whose start is in ``[segment.start, segment.end)``, in time order."""
    scans = {}
    day = segment.start.date()
    while datetime(day.year, day.month, day.day, tzinfo=timezone.utc) < segment.end:
        prefix = f"{PRODUCT}/{day:%Y}/{day.timetuple().tm_yday:03d}/"
        for key, size in _list_prefix(segment.bucket, prefix, opener):
            if not key.endswith(".nc"):
                continue
            time_start, time_end = scan_times(key)
            if segment.start <= time_start < segment.end:
                scans[key] = FdcScan(segment.bucket, key, time_start, time_end, size)
        day += timedelta(days=1)
    return sorted(scans.values(), key=lambda scan: (scan.time_start, scan.key))


def select_scans(scans: Iterable[FdcScan], time_step_min: int) -> list[FdcScan]:
    """
    The first scan of each ``time_step_min`` bin, bins counted from the Unix epoch, in time order.

    spear's ``subsample_by_time`` rule, so both keep the same scans. A step of 5 keeps every CONUS
    scan.
    """
    if time_step_min not in TIME_STEPS_MIN:
        raise ValueError(f"time step {time_step_min!r} min is not one of {TIME_STEPS_MIN}")
    kept, seen = [], set()
    for scan in sorted(scans, key=lambda item: (item.time_start, item.key)):
        bin_id = (scan.bucket, int(scan.time_start.timestamp()) // (time_step_min * 60))
        if bin_id not in seen:
            seen.add(bin_id)
            kept.append(scan)
    return kept


def fetch_fdc_scans(
    scans: Sequence[FdcScan],
    directory: Path,
    *,
    workers: int = 8,
    keep: bool = False,
    opener: Callable = urllib.request.urlopen,
) -> Iterator[FetchedScan]:
    """
    Download scans into ``directory`` (bucket layout) and yield them in the order given.

    Up to ``workers`` downloads run ahead of the caller. Unless ``keep``, a yielded file is deleted
    when the caller asks for the next one or closes the iterator, so the directory holds about
    ``workers`` files at a time. A scan that fails after the retries of ``http_get`` is yielded with
    its error and no path.
    """
    directory = Path(directory)
    pending: deque[tuple[FdcScan, Future]] = deque()
    queue = iter(scans)
    previous: Path | None = None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        try:
            for scan in queue:
                pending.append((scan, pool.submit(_fetch_one, scan, directory, opener)))
                if len(pending) >= max(1, workers):
                    break
            while pending:
                scan, future = pending.popleft()
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


def local_fdc_scans(directory: Path, segment: GoesSegment) -> list[FdcScan]:
    """The scans of a segment found in a directory laid out like the buckets (``<bucket>/<key>``)."""
    root = Path(directory) / segment.bucket
    scans = []
    for path in sorted(root.glob(f"{PRODUCT}/*/*/*/*.nc")):
        key = path.relative_to(root).as_posix()
        time_start, time_end = scan_times(key)
        if segment.start <= time_start < segment.end:
            scans.append(FdcScan(segment.bucket, key, time_start, time_end, path.stat().st_size))
    return sorted(scans, key=lambda scan: (scan.time_start, scan.key))


def local_fetched_scans(scans: Iterable[FdcScan], directory: Path) -> Iterator[FetchedScan]:
    """Yield scans read in place from a directory in the bucket layout. Nothing is deleted."""
    for scan in scans:
        path = Path(directory) / scan.bucket / scan.key
        if path.is_file():
            yield FetchedScan(scan, path, sha256_file(path))
        else:
            yield FetchedScan(scan, None, None, f"missing file {path}")


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch_one(scan: FdcScan, directory: Path, opener: Callable) -> FetchedScan:
    dest = directory / scan.bucket / scan.key
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = http_get(f"https://{scan.bucket}.s3.amazonaws.com/{scan.key}", opener=opener)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".part", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
            os.replace(tmp_name, dest)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return FetchedScan(scan, dest, hashlib.sha256(body).hexdigest())
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.warning("[goes] %s/%s: %s", scan.bucket, scan.key, error)
        return FetchedScan(scan, None, None, str(error))


def _list_prefix(bucket: str, prefix: str, opener: Callable) -> list[tuple[str, int | None]]:
    """Keys and sizes under a prefix, with the anonymous S3 listing (``list-type=2``)."""
    items, token = [], None
    while True:
        url = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={urllib.parse.quote(prefix)}"
        if token:
            url += f"&continuation-token={urllib.parse.quote(token)}"
        root = ET.fromstring(http_get(url, opener=opener).decode())  # nosec B314 - fixed public bucket
        for content in root.iter(f"{S3_NS}Contents"):
            size = content.findtext(f"{S3_NS}Size")
            items.append((content.findtext(f"{S3_NS}Key"), int(size) if size else None))
        if root.findtext(f"{S3_NS}IsTruncated") != "true":
            return items
        token = root.findtext(f"{S3_NS}NextContinuationToken")


def _stamp(values) -> datetime:
    year, doy, hour, minute, second = (int(value) for value in values)
    return datetime(year, 1, 1, hour, minute, second, tzinfo=timezone.utc) + timedelta(days=doy - 1)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)
