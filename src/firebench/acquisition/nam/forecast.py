"""
NAM CONUS nest forecast cycles and cached byte-range downloads of its 3 km product (``conusnest.hiresf``).

Files come from the anonymous NOAA Open Data bucket on AWS, which holds NAM from the 2021-09-16 00Z
cycle on: an older cycle is refused with that bound (``check_archive``). Only the GRIB messages
FireBench needs are downloaded (``.idx``-driven byte ranges, the same inventory rules as HRRR). NAM
packs its 10 m U and V in one GRIB message (``612.1`` and ``612.2``), which is downloaded once and
decoded as two fields; each cached subset carries a JSON sidecar listing its fields in decode order.

The nest runs at 00, 06, 12 and 18 UTC, with hourly output to f60.

Cache layout: ``<cache>/nam/<YYYYMMDD>/t<HH>z/nam.t<HH>z.conusnest.hiresf<FF>.tm00.fb.grib2``
(+ ``.fb.json``).
"""

import logging
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ..cache import get_cache_dir
from ..hrrr.forecast import (
    CycleFiles,
    PendingCycle,
    as_utc,
    check_archive,
    is_cached,
    submit_hours,
    write_sidecar,
)
from ..hrrr.inventory import parse_index, select_messages
from ..http import download_subset, fetch_text

logger = logging.getLogger(__name__)

BASE_URL = "https://noaa-nam-pds.s3.amazonaws.com"
SOURCE_BUCKET = "s3://noaa-nam-pds"
PRODUCT = "conusnest.hiresf"
CACHE_SUBDIR = "nam"

# GRIB `VAR:LEVEL` fields downloaded at every forecast hour
FIELDS = (
    "TMP:2 m above ground",
    "RH:2 m above ground",
    "UGRD:10 m above ground",
    "VGRD:10 m above ground",
    "SFCR:surface",
)
# Time-invariant fields, downloaded at f00 only
STATIC_FIELDS = ("HGT:surface",)

CYCLE_HOURS = (0, 6, 12, 18)
VERSION = "4"
# The first cycle of the AWS archive (checked on 2026-10-19); NAM is still produced, so no last cycle.
FIRST_CYCLE = datetime(2021, 9, 16, 0, tzinfo=timezone.utc)
LAST_CYCLE = None
MAX_FXX = 60


def validate_cycle(cycle: datetime) -> datetime:
    """A NAM nest cycle is an aware datetime at 00, 06, 12 or 18 UTC that its archive holds."""
    cycle = as_utc(cycle)
    if cycle.minute or cycle.second or cycle.microsecond or cycle.hour not in CYCLE_HOURS:
        raise ValueError(f"NAM cycles start at 00, 06, 12 or 18 UTC, got {cycle.isoformat()}")
    return check_archive("NAM", cycle, FIRST_CYCLE, LAST_CYCLE)


def nam_version(cycle: datetime) -> str:
    """Operational NAM version that produced ``cycle``: v4 since 2017, before the archive starts."""
    validate_cycle(cycle)
    return VERSION


def max_forecast_hour(cycle: datetime) -> int:
    """Forecast horizon of a NAM nest cycle: f60."""
    validate_cycle(cycle)
    return MAX_FXX


def output_hours(cycle: datetime) -> tuple[int, ...]:
    """Forecast hours the NAM nest outputs for ``cycle``: every hour up to f60."""
    return tuple(range(max_forecast_hour(cycle) + 1))


def fields_for_hour(fxx: int) -> tuple[str, ...]:
    """Fields to download for forecast hour ``fxx`` (static fields at f00 only)."""
    return FIELDS + STATIC_FIELDS if fxx == 0 else FIELDS


def grib_filename(cycle: datetime, fxx: int) -> str:
    """Name of the NAM nest file of ``cycle`` at forecast hour ``fxx``."""
    return f"nam.t{cycle:%H}z.{PRODUCT}{fxx:02d}.tm00.grib2"


def grib_url(cycle: datetime, fxx: int) -> str:
    """URL of the NAM nest file of ``cycle`` at forecast hour ``fxx``."""
    return f"{BASE_URL}/nam.{cycle:%Y%m%d}/{grib_filename(cycle, fxx)}"


def cycle_cache_dir(cycle: datetime, cache_root: Path | None = None) -> Path:
    """Cache directory of one cycle."""
    root = Path(cache_root) if cache_root is not None else get_cache_dir()
    return root / CACHE_SUBDIR / f"{cycle:%Y%m%d}" / f"t{cycle:%H}z"


def cached_file_path(cycle: datetime, fxx: int, cache_root: Path | None = None) -> Path:
    """Path of the cached subset of one forecast hour (the sidecar is ``.with_suffix('.json')``)."""
    stem = Path(grib_filename(cycle, fxx)).stem
    return cycle_cache_dir(cycle, cache_root) / f"{stem}.fb.grib2"


def fetch_file(
    cycle: datetime, fxx: int, fields=None, cache_root: Path | None = None, **http_kwargs
) -> Path:
    """
    Download the subset of one NAM nest file into the cache; a no-op on cache hit.

    Raises ``FileNotFoundError`` when the archive does not hold that forecast hour.
    """
    cycle = validate_cycle(cycle)
    fields = tuple(fields) if fields is not None else fields_for_hour(fxx)
    dest = cached_file_path(cycle, fxx, cache_root)
    if is_cached(dest, fields):
        logger.debug("[nam] cache hit: %s", dest)
        return dest

    url = grib_url(cycle, fxx)
    try:
        index = parse_index(fetch_text(url + ".idx", **http_kwargs))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"NAM file not available for cycle {cycle:%Y-%m-%d %HZ} f{fxx:02d}: {error}"
        ) from None

    # U and V share a message: it is downloaded once, and the sidecar lists both in decode order.
    messages = select_messages(index, fields, shared=True)
    size = download_subset(url, messages, dest, **http_kwargs)
    write_sidecar(dest, url, cycle, fxx, messages, size)
    logger.info("[nam] downloaded %s (%.1f MB)", dest.name, size / 1e6)
    return dest


def _fetch_or_none(cycle: datetime, fxx: int, cache_root: Path | None) -> Path | None:
    try:
        return fetch_file(cycle, fxx, cache_root=cache_root)
    except FileNotFoundError as error:
        logger.warning("[nam] %s", error)
        return None


def submit_cycle(
    cycle: datetime, horizon: int | None, executor: Executor, cache_root: Path | None = None
) -> PendingCycle:
    """Submit the downloads of the forecast hours of ``cycle`` up to ``horizon`` to ``executor``."""
    max_fxx = max_forecast_hour(cycle)
    cycle = validate_cycle(cycle)
    horizon = max_fxx if horizon is None else int(horizon)
    if not 0 <= horizon <= max_fxx:
        raise ValueError(
            f"horizon {horizon} h is outside the NAM nest forecast range of cycle {cycle:%Y-%m-%d %HZ} "
            f"(0-{max_fxx} h)"
        )
    cycle_cache_dir(cycle, cache_root).mkdir(parents=True, exist_ok=True)
    return submit_hours(cycle, horizon, output_hours(cycle), executor, _fetch_or_none, cache_root)


def fetch_cycle(
    cycle: datetime, horizon: int | None = None, *, workers: int = 8, cache_root: Path | None = None
) -> CycleFiles:
    """Download (or find in the cache) the forecast hours of ``cycle`` up to ``horizon``."""
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nam") as executor:
        return submit_cycle(cycle, horizon, executor, cache_root).result()
