"""
NASA FIRMS area API: VIIRS and MODIS active-fire detections, with their fire radiative power, as one
reproducible file.

FIRMS answers a request for one product, one box, and at most five days with a CSV of detections.
:func:`download_firms_bundle` covers a window with such requests, prefers the standard (archive)
product to the near-real-time one day by day, and keeps every CSV verbatim in a JSON **bundle**,
with the overpasses of each satellite found in NASA CMR (:mod:`firebench.acquisition.cmr`) and every
request that failed. The bundle never holds the MAP_KEY. ``firebench.standardize`` turns a bundle
into standard groups.

A MAP_KEY is free (https://firms.modaps.eosdis.nasa.gov/api/map_key/); FireBench resolves it as the
``firms`` service (``FIRMS_MAP_KEY``, or ``firebench keys set firms``). Ported from spear
``backends/satellite/firms.py``.
"""

import json
import logging
import math
import os
import tempfile
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import cmr
from .http import http_get
from .keys import redact

logger = logging.getLogger(__name__)

FIRMS_ROOT = "https://firms.modaps.eosdis.nasa.gov/api"
AREA_CSV = f"{FIRMS_ROOT}/area/csv"
MAX_DAY_RANGE = 5  # the area API refuses longer requests
BUNDLE_FORMAT = "firebench-firms-bundle"
BUNDLE_VERSION = 1


@dataclass(frozen=True)
class FirmsStream:
    """One satellite of FIRMS, as a stream of the standard file."""

    name: str
    satellite: str
    instrument: str
    # FIRMS products in order of preference: standard processing first
    products: tuple[str, ...]
    # values of the CSV `satellite` column that belong to the stream, upper case
    csv_satellites: tuple[str, ...]


STREAMS: dict[str, FirmsStream] = {
    stream.name: stream
    for stream in (
        FirmsStream("viirs_snpp", "Suomi NPP", "VIIRS", ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"), ("N",)),
        FirmsStream("viirs_noaa20", "NOAA-20", "VIIRS", ("VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"), ("N20",)),
        FirmsStream("viirs_noaa21", "NOAA-21", "VIIRS", ("VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"), ("N21",)),
        # FIRMS serves Terra and Aqua as one MODIS product: requested once, split by satellite
        FirmsStream("modis_terra", "Terra", "MODIS", ("MODIS_SP", "MODIS_NRT"), ("TERRA", "T")),
        FirmsStream("modis_aqua", "Aqua", "MODIS", ("MODIS_SP", "MODIS_NRT"), ("AQUA", "A")),
    )
}


@dataclass(frozen=True)
class FirmsRequest:
    """One area request: a product over ``n_days`` days from ``day``, serving ``streams``."""

    product: str
    day: date
    n_days: int
    streams: tuple[str, ...]


def check_streams(streams: Sequence[str]) -> list[str]:
    """Return ``streams`` without duplicates, in the order of :data:`STREAMS`, or raise ``ValueError``."""
    unknown = [stream for stream in streams if stream not in STREAMS]
    if unknown or not streams:
        raise ValueError(
            f"unknown or missing FIRMS streams {unknown or list(streams)}; known: {', '.join(STREAMS)}"
        )
    return [stream for stream in STREAMS if stream in streams]


def data_availability(
    map_key: str, *, opener: Callable = urllib.request.urlopen
) -> dict[str, tuple[date, date]]:
    """The days each FIRMS product covers: ``{product: (first day, last day)}``."""
    url = f"{FIRMS_ROOT}/data_availability/csv/{map_key}/ALL"
    text = http_get(url, opener=opener, display_url=redact(url, (map_key,))).decode()
    lines = [line.split(",") for line in text.strip().splitlines()]
    if not lines or lines[0][:3] != ["data_id", "min_date", "max_date"]:
        raise ValueError(
            f"FIRMS returned no availability table: {redact(text.strip()[:120], (map_key,))!r}"
        )
    return {
        row[0]: (date.fromisoformat(row[1]), date.fromisoformat(row[2]))
        for row in lines[1:]
        if len(row) >= 3
    }


def request_days(start: datetime, end: datetime) -> list[date]:
    """The UTC days a window touches. A window ending at midnight does not touch the next day."""
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError(f"the window ends ({end.isoformat()}) before it starts ({start.isoformat()})")
    last = (end - timedelta(microseconds=1)).date()
    return [start.date() + timedelta(days=offset) for offset in range((last - start.date()).days + 1)]


def plan_firms_requests(
    streams: Sequence[str],
    start: datetime,
    end: datetime,
    availability: dict[str, tuple[date, date]] | None,
) -> tuple[list[FirmsRequest], dict[str, list[date]]]:
    """
    The requests that cover the window, and the days no product covers, per stream.

    Each day takes the first product of the stream whose availability holds it (all the first
    product when ``availability`` is None). Consecutive days of one product are grouped in requests
    of at most :data:`MAX_DAY_RANGE` days. Streams that share products (Terra and Aqua) share
    requests.
    """
    days = request_days(start, end)
    families: dict[tuple[str, ...], list[str]] = {}
    for stream in check_streams(streams):
        families.setdefault(STREAMS[stream].products, []).append(stream)

    requests: list[FirmsRequest] = []
    uncovered: dict[str, list[date]] = {}
    for products, members in families.items():
        chosen = [_product_for(day, products, availability) for day in days]
        for stream in members:
            missing = [day for day, product in zip(days, chosen) if product is None]
            if missing:
                uncovered[stream] = missing
        run: list[date] = []
        for index, day in enumerate(days):
            product = chosen[index]
            if product is None:
                continue
            run.append(day)
            following = chosen[index + 1] if index + 1 < len(days) else None
            if following != product or len(run) == MAX_DAY_RANGE:
                requests.append(FirmsRequest(product, run[0], len(run), tuple(members)))
                run = []
    return requests, uncovered


def download_firms_bundle(
    bbox: Sequence[float],
    start: datetime,
    end: datetime,
    streams: Sequence[str],
    map_key: str,
    *,
    opener: Callable = urllib.request.urlopen,
    with_overpasses: bool = True,
) -> dict:
    """
    Download the FIRMS detections of ``streams`` over ``bbox`` and the window, and their overpasses.

    A request that fails after the retries of ``http_get`` is recorded with its error, and the
    download goes on. Every error text is redacted: the MAP_KEY is in FIRMS URLs. The bundle holds
    no URL and no key. ``bbox`` is ``(west, south, east, north)`` in degrees; ``start`` and ``end``
    are aware datetimes.
    """
    from .. import __version__  # pylint: disable=import-outside-toplevel

    west, south, east, north = cmr.check_bbox(bbox)
    start, end = _utc(start), _utc(end)
    streams = check_streams(streams)
    if not map_key:
        raise ValueError("a FIRMS MAP_KEY is needed")

    try:
        availability = data_availability(map_key, opener=opener)
        availability_error = None
    except Exception as error:  # pylint: disable=broad-exception-caught
        availability, availability_error = None, redact(str(error), (map_key,))
        logger.warning("[firms] data availability failed (%s); using the first product", availability_error)
    plan, uncovered = plan_firms_requests(streams, start, end, availability)

    requests = []
    for item in plan:
        box = _box_text(west, south, east, north)
        url = f"{AREA_CSV}/{map_key}/{item.product}/{box}/{item.n_days}/{item.day}"
        record = {
            "product": item.product,
            "streams": list(item.streams),
            "day": item.day.isoformat(),
            "n_days": item.n_days,
            "status": "ok",
            "error": None,
            "csv": None,
        }
        try:
            text = http_get(url, opener=opener, display_url=redact(url, (map_key,))).decode()
            if not text.lstrip().lower().startswith("latitude"):
                raise ValueError(f"FIRMS returned no CSV: {text.strip()[:120]!r}")
            record["csv"] = text
        except Exception as error:  # pylint: disable=broad-exception-caught
            record["status"], record["error"] = "failed", redact(str(error), (map_key,))
            logger.warning("[firms] %s from %s: %s", item.product, item.day, record["error"])
        requests.append(record)

    found_overpasses = {}
    if with_overpasses:
        for stream in streams:
            try:
                items, collections = cmr.stream_overpasses(stream, bbox, start, end, opener=opener)
                found_overpasses[stream] = {
                    "status": "ok",
                    "error": None,
                    "collections": collections,
                    "items": [overpass_to_dict(overpass) for overpass in items],
                }
            except Exception as error:  # pylint: disable=broad-exception-caught
                found_overpasses[stream] = {
                    "status": "failed",
                    "error": redact(str(error), (map_key,)),
                    "collections": [],
                    "items": [],
                }
                logger.warning("[firms] overpasses of %s: %s", stream, found_overpasses[stream]["error"])

    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "bbox": [west, south, east, north],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "streams": streams,
        "created_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "firebench_version": __version__,
        "availability": (
            {
                product: [first.isoformat(), last.isoformat()]
                for product, (first, last) in availability.items()
            }
            if availability is not None
            else None
        ),
        "availability_error": availability_error,
        "uncovered_days": {stream: [day.isoformat() for day in days] for stream, days in uncovered.items()},
        "requests": requests,
        "overpasses": found_overpasses,
    }


def write_firms_bundle(bundle: dict, path: Path) -> Path:
    """Write a bundle as compact JSON, atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(bundle, stream, separators=(",", ":"), allow_nan=False)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def read_firms_bundle(path: Path) -> dict:
    """Read a bundle written by :func:`write_firms_bundle`; raise ``ValueError`` for anything else."""
    try:
        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} is not a FIRMS bundle: {error}") from None
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"{path} is not a FIRMS bundle (format {BUNDLE_FORMAT!r} expected)")
    if bundle.get("version") != BUNDLE_VERSION:
        raise ValueError(
            f"{path} is a FIRMS bundle of version {bundle.get('version')!r}; {BUNDLE_VERSION} is read"
        )
    for name in ("bbox", "start", "end", "streams", "requests", "overpasses"):
        if name not in bundle:
            raise ValueError(f"{path} is a FIRMS bundle without `{name}`")
    return bundle


def overpass_to_dict(overpass: cmr.Overpass) -> dict:
    """An overpass as JSON values; an unknown observed fraction is null."""
    fraction = overpass.observed_fraction
    return {
        "time_start": overpass.time_start.isoformat(),
        "time_end": overpass.time_end.isoformat(),
        "granule_ids": list(overpass.granule_ids),
        "observed_fraction": None if math.isnan(fraction) else fraction,
    }


def overpass_from_dict(item: dict) -> cmr.Overpass:
    """The inverse of :func:`overpass_to_dict`."""
    fraction = item.get("observed_fraction")
    return cmr.Overpass(
        time_start=_utc(datetime.fromisoformat(item["time_start"])),
        time_end=_utc(datetime.fromisoformat(item["time_end"])),
        granule_ids=tuple(item.get("granule_ids") or ()),
        observed_fraction=math.nan if fraction is None else float(fraction),
    )


def _product_for(day: date, products: Sequence[str], availability) -> str | None:
    if availability is None:
        return products[0]
    for product in products:
        covered = availability.get(product)
        if covered and covered[0] <= day <= covered[1]:
            return product
    return None


def _box_text(west: float, south: float, east: float, north: float) -> str:
    return ",".join(f"{round(value, 5):g}" for value in (west, south, east, north))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} has no time zone")
    return value.astimezone(timezone.utc)
