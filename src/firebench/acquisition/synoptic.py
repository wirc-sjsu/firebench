"""
Synoptic Data weather API client: station time series for a bounding box and time window.

The client returns the raw Synoptic JSON payload that ``standardize_synoptic_raws_from_json`` and the
weather QC pipeline already consume, so downloaded and locally saved payloads follow the same path.

Synoptic caps a time-series request at 100,000 station-hours. The client first counts the stations
of the request with the metadata service, then splits the window into time chunks small enough to
stay under that cap, and merges the chunks. Finished chunks are cached; a chunk that ends less than
a day before now is always fetched again, because late observations keep arriving.

The token travels in the query string, so every URL is redacted before it reaches a log line, an
exception or the cache metadata.
"""

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cache import atomic_write_json, cache_subdir
from .http import HTTPStatusError, http_get
from .keys import fingerprint, redact, resolve_origins

logger = logging.getLogger(__name__)

API_ROOT = "https://api.synopticdata.com/v2"
TIMESERIES_URL = f"{API_ROOT}/stations/timeseries"
METADATA_URL = f"{API_ROOT}/stations/metadata"
CACHE_SUBDIR = "synoptic"

# Synoptic variable names behind firebench.standardize.synoptic_data.VARIABLE_CONVERSION
DEFAULT_VARIABLES = (
    "air_temp",
    "relative_humidity",
    "wind_speed",
    "wind_direction",
    "wind_gust",
    "solar_radiation",
    "fuel_moisture",
)
TIMESERIES_OPTIONS = {
    "units": "metric",
    "obtimezone": "UTC",  # the standardizer reads timestamps as UTC clock times
    "showemptystations": "0",
    "sensorvars": "1",  # sensor heights (SENSOR_VARIABLES.position)
    "complete": "1",  # STATE, MNET_ID, PROVIDERS, ... read by the standardizer and the QC
}
MAX_STATION_HOURS = 100_000
STATION_HOUR_SAFETY = 0.9
CHUNK_HOURS_LADDER = (168, 72, 24, 12, 6, 3, 1)
FINAL_CHUNK_AGE = timedelta(hours=24)
TIME_FORMAT = "%Y%m%d%H%M"

REQUIRED_STATION_KEYS = ("STID", "NAME", "STATE", "TIMEZONE", "LATITUDE", "LONGITUDE", "ID", "MNET_ID")
NUMERIC_STATION_KEYS = {
    "LATITUDE": float,
    "LONGITUDE": float,
    "ELEVATION": float,
    "ID": int,
    "MNET_ID": int,
}
METRIC_UNITS = {
    "air_temp": ("Celsius", "C", "degC"),
    "wind_speed": ("m/s",),
    "wind_gust": ("m/s",),
}


class SynopticError(RuntimeError):
    """The Synoptic API rejected a request; the message never contains the token."""

    def __init__(self, code, message: str, http_code: int | None = None) -> None:
        super().__init__(f"Synoptic API error {code}: {message}")
        self.code = code
        self.message = message
        self.http_code = http_code


def format_bbox(bbox: Sequence[float]) -> str:
    """Synoptic ``bbox`` parameter: ``lon_min,lat_min,lon_max,lat_max``."""
    lon_min, lat_min, lon_max, lat_max = (float(value) for value in bbox)
    if not (lon_min < lon_max and lat_min < lat_max):
        raise ValueError(f"invalid bbox {bbox!r}: expected [lon_min, lat_min, lon_max, lat_max]")
    return f"{lon_min:g},{lat_min:g},{lon_max:g},{lat_max:g}"


def chunk_hours_for(n_stations: int, max_chunk_days: float = 7) -> int:
    """Largest ladder chunk length keeping ``n_stations`` x hours under the station-hour cap."""
    limit = min(max_chunk_days * 24, STATION_HOUR_SAFETY * MAX_STATION_HOURS / max(n_stations, 1))
    for hours in CHUNK_HOURS_LADDER:
        if hours <= limit:
            return hours
    raise ValueError(
        f"{n_stations} stations exceed the Synoptic cap of {MAX_STATION_HOURS} station-hours even for a "
        "one-hour request; use a smaller bounding box or a network filter"
    )


def plan_chunks(start: datetime, end: datetime, chunk_hours: int) -> list[tuple[datetime, datetime]]:
    """
    Split ``[start, end]`` into consecutive chunks aligned on multiples of ``chunk_hours`` (UTC epoch).

    Aligned boundaries keep chunk cache keys stable across runs. Chunks do not overlap: each one
    ends one minute (the API resolution) before the next begins.
    """
    start = _utc_minute(start)
    end = _utc_minute(end)
    if end <= start:
        raise ValueError(f"window end {end.isoformat()} must be after start {start.isoformat()}")
    step = timedelta(hours=chunk_hours)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    boundary = epoch + ((start - epoch) // step + 1) * step
    chunks = []
    chunk_start = start
    while boundary < end:
        chunks.append((chunk_start, boundary - timedelta(minutes=1)))
        chunk_start = boundary
        boundary += step
    chunks.append((chunk_start, end))
    return chunks


class SynopticTimeseriesClient:
    """Token-authenticated client for the Synoptic station time-series service."""

    def __init__(
        self,
        token: str,
        *,
        origins: Sequence[str] | None = None,
        timeout: float = 60.0,
        opener: Callable = urllib.request.urlopen,
    ) -> None:
        if not token:
            raise ValueError("a Synoptic API token is required (see: firebench keys set synoptic)")
        self.origins, self.origin_source = resolve_origins(token, origins)
        self._preferred_origin = None
        self._token = token
        self.timeout = timeout
        self.opener = opener

    def count_stations(
        self,
        bbox: Sequence[float],
        start: datetime,
        end: datetime,
        variables: Sequence[str] = DEFAULT_VARIABLES,
        networks: Sequence[str] | None = None,
    ) -> int:
        """Number of stations reporting ``variables`` in ``bbox`` during ``[start, end]``."""
        params = {
            "bbox": format_bbox(bbox),
            "vars": ",".join(variables),
            "obrange": f"{_utc_minute(start):{TIME_FORMAT}},{_utc_minute(end):{TIME_FORMAT}}",
        }
        if networks:
            params["network"] = ",".join(str(network) for network in networks)
        payload = self._request(METADATA_URL, params)
        if payload is None:
            return 0
        summary = payload.get("SUMMARY") or {}
        return int(summary.get("NUMBER_OF_OBJECTS", len(payload.get("STATION") or [])))

    def check_token(self) -> str:
        """Make one tiny metadata request; returns the service response message."""
        payload = self._request(METADATA_URL, {"stid": "KSFO"})
        return str(((payload or {}).get("SUMMARY") or {}).get("RESPONSE_MESSAGE", "OK"))

    def fetch(
        self,
        bbox: Sequence[float],
        start: datetime,
        end: datetime,
        *,
        variables: Sequence[str] = DEFAULT_VARIABLES,
        networks: Sequence[str] | None = None,
        max_chunk_days: float = 7,
        cache_root: Path | None = None,
        now: datetime | None = None,
    ) -> dict:
        """Download the station time series of ``bbox`` over ``[start, end]`` as one merged payload."""
        params = {"bbox": format_bbox(bbox), "vars": ",".join(variables), **TIMESERIES_OPTIONS}
        if networks:
            params["network"] = ",".join(str(network) for network in networks)

        n_stations = self.count_stations(bbox, start, end, variables, networks)
        if n_stations == 0:
            logger.warning(
                "[synoptic] no station found in bbox %s for the requested window", params["bbox"]
            )
            return merge_payloads([])
        chunk_hours = chunk_hours_for(n_stations, max_chunk_days)
        chunks = plan_chunks(start, end, chunk_hours)
        logger.info(
            "[synoptic] %d stations, %d chunk(s) of up to %d h for %s .. %s",
            n_stations,
            len(chunks),
            chunk_hours,
            _utc_minute(start).isoformat(),
            _utc_minute(end).isoformat(),
        )

        cache_dir = cache_subdir(CACHE_SUBDIR, self._request_key(params), root=cache_root)
        atomic_write_json(cache_dir / "request.json", {"url": TIMESERIES_URL, "params": params})
        now = now or datetime.now(timezone.utc)
        payloads = []
        for chunk_start, chunk_end in chunks:
            payloads.append(self._fetch_chunk(params, chunk_start, chunk_end, cache_dir, now))
        return merge_payloads(payloads)

    def _fetch_chunk(
        self, params: dict, start: datetime, end: datetime, cache_dir: Path, now: datetime
    ) -> dict:
        path = cache_dir / f"chunk_{start:{TIME_FORMAT}}_{end:{TIME_FORMAT}}.json"
        final = end < now - FINAL_CHUNK_AGE
        if final and path.is_file():
            try:
                cached = json.loads(path.read_text())
                logger.debug("[synoptic] cache hit: %s", path.name)
                return cached["payload"]
            except (OSError, ValueError, KeyError):
                logger.warning("[synoptic] corrupt cache entry %s, fetching again", path)

        payload = self._request(
            TIMESERIES_URL, {**params, "start": f"{start:{TIME_FORMAT}}", "end": f"{end:{TIME_FORMAT}}"}
        )
        payload = payload if payload is not None else {"STATION": []}
        atomic_write_json(
            path,
            {
                "fetched_at": now.isoformat(timespec="seconds"),
                "final": final,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "payload": payload,
            },
        )
        return payload

    def _request_key(self, params: dict) -> str:
        identity = json.dumps({"params": params, "token": fingerprint(self._token)}, sort_keys=True)
        if self.origins:
            identity += json.dumps(self.origins)
        return hashlib.sha256(identity.encode()).hexdigest()[:16]

    def _request(self, url: str, params: dict) -> dict | None:
        candidates = list(self.origins) or [None]
        if self._preferred_origin in candidates:
            candidates.remove(self._preferred_origin)
            candidates.insert(0, self._preferred_origin)
        attempted = []
        for origin in candidates:
            attempted.append(origin)
            try:
                payload = self._request_with_origin(url, params, origin)
            except SynopticError as error:
                if str(error.code) != "403" and error.http_code != 403:
                    raise
                if origin == candidates[-1]:
                    if self.origins:
                        raise SynopticError(
                            error.code,
                            f"{error.message}; attempted origins: {', '.join(attempted)}",
                            error.http_code,
                        ) from None
                    raise
            else:
                self._preferred_origin = origin
                return payload
        return None

    def _request_with_origin(self, url: str, params: dict, origin: str | None) -> dict | None:
        """GET ``url`` with ``params``; returns the payload, or ``None`` when no station matches."""
        query = urllib.parse.urlencode({"token": self._token, **params})
        full_url = f"{url}?{query}"
        shown_url = redact(full_url, (self._token,))
        logger.debug("[synoptic] GET %s", shown_url)
        try:
            body = http_get(
                full_url,
                opener=self.opener,
                timeout=self.timeout,
                not_found_codes=(),
                display_url=shown_url,
                extra_headers={"Accept": "application/json", **({"Origin": origin} if origin else {})},
            )
        except HTTPStatusError as error:
            payload = _json_or_none(error.body)
            if payload is None:
                raise SynopticError(error.code, f"HTTP {error.code} without a JSON error body") from None
            return self._check_summary(payload, http_code=error.code)
        except ConnectionError as error:
            raise SynopticError("network", redact(str(error), (self._token,))) from None

        payload = _json_or_none(body)
        if not isinstance(payload, dict):
            raise SynopticError("invalid", "the response is not a JSON object")
        return self._check_summary(payload)

    def _check_summary(self, payload: dict, http_code: int | None = None) -> dict | None:
        summary = payload.get("SUMMARY") or {}
        try:
            code = int(summary.get("RESPONSE_CODE", 1 if http_code is None else http_code))
        except (TypeError, ValueError):
            code = summary.get("RESPONSE_CODE")
        message = redact(str(summary.get("RESPONSE_MESSAGE", "")), (self._token,))
        if code == 1 and http_code is None:
            return payload
        if code == 2 and http_code is None and "no stations found" in message.lower():
            return None
        suffix = f" (HTTP {http_code})" if http_code is not None else ""
        raise SynopticError(code, f"{message or 'request rejected'}{suffix}", http_code)


def merge_payloads(payloads: Sequence[dict]) -> dict:
    """
    Merge chronological chunk payloads into one, station by station.

    Observation columns are aligned on ``date_time`` (a column absent from a chunk is padded with
    ``None``), duplicate boundary timestamps are dropped, ``SENSOR_VARIABLES`` are united, and the
    station metadata of the first chunk is kept.
    """
    stations: dict[str, dict] = {}
    columns: dict[str, dict[str, list]] = {}
    units: dict = {}
    for payload in payloads:
        units = units or dict(payload.get("UNITS") or {})
        for station in payload.get("STATION") or []:
            stid = station.get("STID")
            if stid is None:
                continue
            if stid not in stations:
                stations[stid] = {key: value for key, value in station.items() if key != "OBSERVATIONS"}
                stations[stid]["SENSOR_VARIABLES"] = {}
                columns[stid] = {"date_time": []}
            _merge_sensor_variables(
                stations[stid]["SENSOR_VARIABLES"], station.get("SENSOR_VARIABLES") or {}
            )
            _append_observations(columns[stid], station.get("OBSERVATIONS") or {})

    merged_stations = []
    for stid, station in stations.items():
        observations = _drop_duplicate_times(columns[stid])
        if observations["date_time"]:
            merged_stations.append({**station, "OBSERVATIONS": observations})
    merged = {
        "SUMMARY": {
            "RESPONSE_CODE": 1,
            "RESPONSE_MESSAGE": f"merged by firebench from {len(payloads)} chunk(s)",
            "NUMBER_OF_OBJECTS": len(merged_stations),
        },
        "STATION": merged_stations,
    }
    if units:
        merged["UNITS"] = units
    return merged


def validate_payload(payload: dict) -> tuple[dict, list[dict]]:
    """
    Enforce the payload contract of the standardizer and the weather QC before processing.

    Metric units are required. Stations missing a key that the standardizer reads without a guard
    are dropped and reported rather than crashing the whole QC run. Returns the cleaned payload and
    ``[{"station": STID, "reason": ...}]`` for every dropped station.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("STATION"), list):
        raise SynopticError("invalid", "the payload has no STATION array")
    _check_metric_units(payload.get("UNITS") or {}, "payload")

    kept = []
    dropped = []
    for station in payload["STATION"]:
        reason = _station_problem(station)
        if reason is None:
            _check_metric_units(station.get("UNITS") or {}, f"station {station.get('STID')}")
            kept.append(station)
        else:
            dropped.append({"station": str(station.get("STID", "<no STID>")), "reason": reason})
            logger.warning("[synoptic] dropped station %s: %s", station.get("STID", "<no STID>"), reason)
    return {**payload, "STATION": kept}, dropped


def clip_payload(
    payload: dict, start: datetime, end: datetime, bbox: Sequence[float] | None = None
) -> dict:
    """
    Keep the observations of ``payload`` within ``[start, end]`` and, optionally, inside ``bbox``.

    Timestamps are read exactly like the standardizer does. Stations left without observations are
    dropped, as ``showemptystations=0`` would do for a download.
    """
    # pylint: disable-next=import-outside-toplevel
    from ..standardize.synoptic import parse_synoptic_timestamp_utc

    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    lon_min, lat_min, lon_max, lat_max = (
        (float(value) for value in bbox) if bbox is not None else (None,) * 4
    )
    stations = []
    for station in payload.get("STATION") or []:
        if bbox is not None:
            try:
                lat = float(station["LATITUDE"])
                lon = float(station["LONGITUDE"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                continue
        observations = station.get("OBSERVATIONS") or {}
        times = observations.get("date_time") or []
        keep = [
            index
            for index, value in enumerate(times)
            if start <= parse_synoptic_timestamp_utc(value) <= end
        ]
        if not keep:
            continue
        clipped = {
            key: (
                [values[index] for index in keep]
                if isinstance(values, list) and len(values) == len(times)
                else values
            )
            for key, values in observations.items()
        }
        stations.append({**station, "OBSERVATIONS": clipped})
    return {**{key: value for key, value in payload.items() if key != "STATION"}, "STATION": stations}


def _merge_sensor_variables(target: dict, source: dict) -> None:
    for family, sets in source.items():
        if isinstance(sets, dict):
            family_target = target.setdefault(family, {})
            for set_name, info in sets.items():
                family_target.setdefault(set_name, info)
        else:
            target.setdefault(family, sets)


def _append_observations(target: dict[str, list], observations: dict) -> None:
    times = list(observations.get("date_time") or [])
    n_before = len(target["date_time"])
    n_new = len(times)
    for key in observations:
        if key != "date_time" and key not in target:
            target[key] = [None] * n_before
    target["date_time"].extend(times)
    for key, values in target.items():
        if key == "date_time":
            continue
        new_values = observations.get(key)
        if isinstance(new_values, list) and len(new_values) == n_new:
            values.extend(new_values)
        else:
            values.extend([None] * n_new)


def _drop_duplicate_times(columns: dict[str, list]) -> dict[str, list]:
    seen = set()
    keep = []
    for index, value in enumerate(columns["date_time"]):
        if value not in seen:
            seen.add(value)
            keep.append(index)
    if len(keep) == len(columns["date_time"]):
        return columns
    return {key: [values[index] for index in keep] for key, values in columns.items()}


def _station_problem(station) -> str | None:
    if not isinstance(station, dict):
        return "not a JSON object"
    problems = [f"missing {key}" for key in REQUIRED_STATION_KEYS if station.get(key) in (None, "")]
    problems += [
        f"missing or non-numeric {key}"
        for key, cast in NUMERIC_STATION_KEYS.items()
        if not _castable(station.get(key), cast)
    ]
    if not (station.get("UNITS") or {}).get("elevation"):
        problems.append("missing UNITS.elevation")
    if not isinstance(station.get("SENSOR_VARIABLES"), dict):
        problems.append("missing SENSOR_VARIABLES")
    if not (station.get("OBSERVATIONS") or {}).get("date_time"):
        problems.append("no observation timestamps")
    return problems[0] if problems else None


def _castable(value, cast) -> bool:
    try:
        cast(value)
    except (TypeError, ValueError):
        return False
    return True


def _check_metric_units(units: dict, where: str) -> None:
    for variable, accepted in METRIC_UNITS.items():
        unit = units.get(variable)
        if unit is not None and unit not in accepted:
            raise SynopticError(
                "units", f"{where} reports {variable} in {unit!r}; request metric units (units=metric)"
            )


def _json_or_none(body: bytes):
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return None


def _utc_minute(when: datetime) -> datetime:
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(f"datetime {when!r} has no time zone")
    return when.astimezone(timezone.utc).replace(second=0, microsecond=0)


def expected_chunk_count(n_stations: int, start: datetime, end: datetime, max_chunk_days: float = 7) -> int:
    """Number of requests :meth:`SynopticTimeseriesClient.fetch` makes for ``n_stations`` stations."""
    return len(plan_chunks(start, end, chunk_hours_for(n_stations, max_chunk_days))) if n_stations else 0
