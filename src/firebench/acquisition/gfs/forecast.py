"""
GFS forecast cycles and cached byte-range downloads of the 0.25 degree product (``pgrb2.0p25``).

Files come from the anonymous NOAA Open Data bucket on AWS. Only the GRIB messages FireBench needs
are downloaded (``.idx``-driven byte ranges, the same inventory rules as HRRR), and each cached
subset carries a JSON sidecar listing its messages in byte order.

Only GFS v16, operational since 2021-03-22 12Z, is read: an older cycle is refused rather than read
with another version's layout. Forecast hours are read up to f120, where hourly output ends.

Cache layout: ``<cache>/gfs/<YYYYMMDD>/t<HH>z/gfs.t<HH>z.pgrb2.0p25.f<FFF>.fb.grib2`` (+ ``.fb.json``).
"""

import logging
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ..cache import get_cache_dir
from ..hrrr.forecast import CycleFiles, PendingCycle, as_utc, is_cached, submit_hours, write_sidecar
from ..hrrr.inventory import parse_index, select_messages
from ..http import download_subset, fetch_text

logger = logging.getLogger(__name__)

BASE_URL = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
SOURCE_BUCKET = "s3://noaa-gfs-bdp-pds"
PRODUCT = "pgrb2.0p25"
CACHE_SUBDIR = "gfs"

# GRIB `VAR:LEVEL` fields downloaded at every forecast hour
FIELDS = (
    "TMP:2 m above ground",
    "RH:2 m above ground",
    "UGRD:10 m above ground",
    "VGRD:10 m above ground",
    "SFCR:surface",
)
# Time-invariant fields, downloaded at f000 only
STATIC_FIELDS = ("HGT:surface",)

CYCLE_HOURS = (0, 6, 12, 18)
VERSION = "16"
VERSION_START = datetime(2021, 3, 22, 12, tzinfo=timezone.utc)
MAX_FXX_HOURLY = 120


def validate_cycle(cycle: datetime) -> datetime:
    """A GFS cycle is an aware datetime at 00, 06, 12 or 18 UTC, from GFS v16 on."""
    cycle = as_utc(cycle)
    if cycle.minute or cycle.second or cycle.microsecond or cycle.hour not in CYCLE_HOURS:
        raise ValueError(f"GFS cycles start at 00, 06, 12 or 18 UTC, got {cycle.isoformat()}")
    if cycle < VERSION_START:
        raise ValueError(
            f"GFS cycle {cycle:%Y-%m-%d %HZ} is older than GFS v{VERSION} "
            f"({VERSION_START:%Y-%m-%d %HZ}), the only version FireBench reads"
        )
    return cycle


def gfs_version(cycle: datetime) -> str:
    """Operational GFS version that produced ``cycle``; only v16 is read."""
    validate_cycle(cycle)
    return VERSION


def max_forecast_hour(cycle: datetime) -> int:
    """Forecast horizon FireBench reads from ``cycle``: f120, the end of the hourly output."""
    validate_cycle(cycle)
    return MAX_FXX_HOURLY


def output_hours(cycle: datetime) -> tuple[int, ...]:
    """Forecast hours FireBench reads from a GFS cycle: every hour up to f120."""
    return tuple(range(max_forecast_hour(cycle) + 1))


def fields_for_hour(fxx: int) -> tuple[str, ...]:
    """Fields to download for forecast hour ``fxx`` (static fields at f000 only)."""
    return FIELDS + STATIC_FIELDS if fxx == 0 else FIELDS


def grib_filename(cycle: datetime, fxx: int) -> str:
    """Name of the GFS 0.25 degree file of ``cycle`` at forecast hour ``fxx``."""
    return f"gfs.t{cycle:%H}z.{PRODUCT}.f{fxx:03d}"


def grib_url(cycle: datetime, fxx: int) -> str:
    """URL of the GFS 0.25 degree file of ``cycle`` at forecast hour ``fxx``."""
    return f"{BASE_URL}/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos/{grib_filename(cycle, fxx)}"


def cycle_cache_dir(cycle: datetime, cache_root: Path | None = None) -> Path:
    """Cache directory of one cycle."""
    root = Path(cache_root) if cache_root is not None else get_cache_dir()
    return root / CACHE_SUBDIR / f"{cycle:%Y%m%d}" / f"t{cycle:%H}z"


def cached_file_path(cycle: datetime, fxx: int, cache_root: Path | None = None) -> Path:
    """Path of the cached subset of one forecast hour (the sidecar is ``.with_suffix('.json')``)."""
    return cycle_cache_dir(cycle, cache_root) / f"{grib_filename(cycle, fxx)}.fb.grib2"


def fetch_file(
    cycle: datetime, fxx: int, fields=None, cache_root: Path | None = None, **http_kwargs
) -> Path:
    """
    Download the subset of one GFS file into the cache; a no-op on cache hit.

    Raises ``FileNotFoundError`` when the archive does not hold that forecast hour.
    """
    cycle = validate_cycle(cycle)
    fields = tuple(fields) if fields is not None else fields_for_hour(fxx)
    dest = cached_file_path(cycle, fxx, cache_root)
    if is_cached(dest, fields):
        logger.debug("[gfs] cache hit: %s", dest)
        return dest

    url = grib_url(cycle, fxx)
    try:
        index = parse_index(fetch_text(url + ".idx", **http_kwargs))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"GFS file not available for cycle {cycle:%Y-%m-%d %HZ} f{fxx:03d}: {error}"
        ) from None

    messages = select_messages(index, fields)
    size = download_subset(url, messages, dest, **http_kwargs)
    write_sidecar(dest, url, cycle, fxx, messages, size)
    logger.info("[gfs] downloaded %s (%.1f MB)", dest.name, size / 1e6)
    return dest


def _fetch_or_none(cycle: datetime, fxx: int, cache_root: Path | None) -> Path | None:
    try:
        return fetch_file(cycle, fxx, cache_root=cache_root)
    except FileNotFoundError as error:
        logger.warning("[gfs] %s", error)
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
            f"horizon {horizon} h is outside the hourly GFS forecast range FireBench reads (0-{max_fxx} h)"
        )
    cycle_cache_dir(cycle, cache_root).mkdir(parents=True, exist_ok=True)
    return submit_hours(cycle, horizon, output_hours(cycle), executor, _fetch_or_none, cache_root)


def fetch_cycle(
    cycle: datetime, horizon: int | None = None, *, workers: int = 8, cache_root: Path | None = None
) -> CycleFiles:
    """Download (or find in the cache) the forecast hours of ``cycle`` up to ``horizon``."""
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gfs") as executor:
        return submit_cycle(cycle, horizon, executor, cache_root).result()
