"""
HRRR forecast cycles and cached byte-range downloads of the surface product (``wrfsfc``).

Files come from the anonymous NOAA Open Data bucket on AWS. Only the GRIB messages FireBench needs
are downloaded (``.idx``-driven byte ranges), and each cached subset carries a JSON sidecar listing
its messages in byte order. Ported from spear ``backends/hrrr/forecast`` (which fetches ``wrfnat``).

Cache layout: ``<cache>/hrrr/<YYYYMMDD>/t<HH>z/hrrr.t<HH>z.wrfsfcf<FF>.fb.grib2`` (+ ``.fb.json``).
"""

import json
import logging
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..cache import atomic_write_json, get_cache_dir
from ..http import download_subset, fetch_text
from .inventory import parse_index, select_messages

logger = logging.getLogger(__name__)

BASE_URL = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com"
SOURCE_BUCKET = "s3://noaa-hrrr-bdp-pds"
PRODUCT = "wrfsfc"
CACHE_SUBDIR = "hrrr"

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

EXTENDED_CYCLE_HOURS = (0, 6, 12, 18)
HRRR_V3_START = datetime(2018, 7, 12, 12, tzinfo=timezone.utc)
HRRR_V4_START = datetime(2020, 12, 2, 12, tzinfo=timezone.utc)
MAX_FXX_V4_EXTENDED = 48
MAX_FXX_V3_EXTENDED = 36
MAX_FXX_STANDARD = 18


def as_utc(when: datetime) -> datetime:
    """Return an aware UTC datetime; naive values are rejected to avoid silent time shifts."""
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(f"datetime {when!r} has no time zone; use an explicit UTC offset such as 'Z'")
    return when.astimezone(timezone.utc)


def validate_cycle(cycle: datetime) -> datetime:
    """An HRRR cycle is an aware datetime at the top of a UTC hour."""
    cycle = as_utc(cycle)
    if cycle.minute or cycle.second or cycle.microsecond:
        raise ValueError(f"HRRR cycles start at the top of the hour, got {cycle.isoformat()}")
    return cycle


def hrrr_version(cycle: datetime) -> int:
    """Operational HRRR version that produced ``cycle`` (2, 3 or 4)."""
    cycle = as_utc(cycle)
    if cycle >= HRRR_V4_START:
        return 4
    if cycle >= HRRR_V3_START:
        return 3
    return 2


def max_forecast_hour(cycle: datetime) -> int:
    """Forecast horizon of ``cycle``: 48 h (v4) or 36 h (v3) at 00/06/12/18Z, 18 h otherwise."""
    cycle = validate_cycle(cycle)
    if cycle.hour not in EXTENDED_CYCLE_HOURS:
        return MAX_FXX_STANDARD
    version = hrrr_version(cycle)
    if version >= 4:
        return MAX_FXX_V4_EXTENDED
    if version == 3:
        return MAX_FXX_V3_EXTENDED
    return MAX_FXX_STANDARD


def fields_for_hour(fxx: int) -> tuple[str, ...]:
    """Fields to download for forecast hour ``fxx`` (static fields at f00 only)."""
    return FIELDS + STATIC_FIELDS if fxx == 0 else FIELDS


def grib_filename(cycle: datetime, fxx: int) -> str:
    """Name of the HRRR surface file of ``cycle`` at forecast hour ``fxx``."""
    return f"hrrr.t{cycle:%H}z.{PRODUCT}f{fxx:02d}.grib2"


def grib_url(cycle: datetime, fxx: int) -> str:
    """URL of the HRRR surface file of ``cycle`` at forecast hour ``fxx``."""
    return f"{BASE_URL}/hrrr.{cycle:%Y%m%d}/conus/{grib_filename(cycle, fxx)}"


def cycle_cache_dir(cycle: datetime, cache_root: Path | None = None) -> Path:
    """Cache directory of one cycle."""
    root = Path(cache_root) if cache_root is not None else get_cache_dir()
    return root / CACHE_SUBDIR / f"{cycle:%Y%m%d}" / f"t{cycle:%H}z"


def cached_file_path(cycle: datetime, fxx: int, cache_root: Path | None = None) -> Path:
    """Path of the cached subset of one forecast hour (the sidecar is ``.with_suffix('.json')``)."""
    stem = Path(grib_filename(cycle, fxx)).stem
    return cycle_cache_dir(cycle, cache_root) / f"{stem}.fb.grib2"


def read_sidecar(path: Path) -> dict | None:
    """Return the JSON sidecar of a cached subset, or ``None`` if absent or unreadable."""
    sidecar = Path(path).with_suffix(".json")
    try:
        return json.loads(sidecar.read_text())
    except (OSError, ValueError):
        return None


def is_cached(path: Path, fields) -> bool:
    """A cached subset is valid when it holds every requested field and has the recorded size."""
    sidecar = read_sidecar(path)
    if sidecar is None or not Path(path).is_file():
        return False
    return set(fields) <= set(sidecar.get("fields", [])) and Path(path).stat().st_size == sidecar.get(
        "size"
    )


def fetch_file(
    cycle: datetime, fxx: int, fields=None, cache_root: Path | None = None, **http_kwargs
) -> Path:
    """
    Download the subset of one HRRR file into the cache; a no-op on cache hit.

    Raises ``FileNotFoundError`` when the archive does not hold that forecast hour.
    """
    cycle = validate_cycle(cycle)
    fields = tuple(fields) if fields is not None else fields_for_hour(fxx)
    dest = cached_file_path(cycle, fxx, cache_root)
    if is_cached(dest, fields):
        logger.debug("[hrrr] cache hit: %s", dest)
        return dest

    url = grib_url(cycle, fxx)
    try:
        index = parse_index(fetch_text(url + ".idx", **http_kwargs))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"HRRR file not available for cycle {cycle:%Y-%m-%d %HZ} f{fxx:02d}: {error}"
        ) from None

    messages = select_messages(index, fields)
    size = download_subset(url, messages, dest, **http_kwargs)
    atomic_write_json(
        dest.with_suffix(".json"),
        {
            "source_url": url,
            "cycle": cycle.isoformat(),
            "forecast_hour": fxx,
            "fields": [message.field for message in messages],
            "messages": [
                {"field": message.field, "level": message.level, "forecast": message.forecast}
                for message in messages
            ],
            "size": size,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    logger.info("[hrrr] downloaded %s (%.1f MB)", dest.name, size / 1e6)
    return dest


@dataclass
class CycleFiles:
    """Cached subset files of one HRRR cycle, by forecast hour, and the hours the archive lacks."""

    cycle: datetime
    horizon: int
    files: dict[int, Path] = field(default_factory=dict)
    missing: list[int] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Whether every forecast hour 0..horizon was retrieved."""
        return not self.missing and sorted(self.files) == list(range(self.horizon + 1))


@dataclass
class PendingCycle:
    """Downloads of one cycle submitted to an executor; ``result()`` waits for them."""

    cycle: datetime
    horizon: int
    futures: dict[int, Future]

    def result(self) -> CycleFiles:
        """Wait for every forecast hour and gather the files and the missing hours."""
        cycle_files = CycleFiles(self.cycle, self.horizon)
        for fxx, future in sorted(self.futures.items()):
            path = future.result()
            if path is None:
                cycle_files.missing.append(fxx)
            else:
                cycle_files.files[fxx] = path
        return cycle_files


def _fetch_or_none(cycle: datetime, fxx: int, cache_root: Path | None) -> Path | None:
    try:
        return fetch_file(cycle, fxx, cache_root=cache_root)
    except FileNotFoundError as error:
        logger.warning("[hrrr] %s", error)
        return None


def submit_cycle(
    cycle: datetime, horizon: int | None, executor: Executor, cache_root: Path | None = None
) -> PendingCycle:
    """Submit the downloads of forecast hours 0..horizon of ``cycle`` to ``executor``."""
    cycle = validate_cycle(cycle)
    max_fxx = max_forecast_hour(cycle)
    horizon = max_fxx if horizon is None else int(horizon)
    if not 0 <= horizon <= max_fxx:
        raise ValueError(
            f"horizon {horizon} h is outside the HRRR v{hrrr_version(cycle)} forecast range of cycle "
            f"{cycle:%Y-%m-%d %HZ} (0-{max_fxx} h)"
        )
    cycle_cache_dir(cycle, cache_root).mkdir(parents=True, exist_ok=True)
    futures = {fxx: executor.submit(_fetch_or_none, cycle, fxx, cache_root) for fxx in range(horizon + 1)}
    return PendingCycle(cycle, horizon, futures)


def fetch_cycle(
    cycle: datetime, horizon: int | None = None, *, workers: int = 8, cache_root: Path | None = None
) -> CycleFiles:
    """Download (or find in the cache) forecast hours 0..horizon of ``cycle``."""
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hrrr") as executor:
        return submit_cycle(cycle, horizon, executor, cache_root).result()
