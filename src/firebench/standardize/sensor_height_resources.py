"""Validated sensor-height resources and source-precedence resolution."""

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib.resources import files
import json
from numbers import Integral, Real

import numpy as np
from pint.errors import PintError

from ..tools.units import ureg
from .sensor_height import SensorHeightConfidence
from .synoptic_data import VARIABLE_CONVERSION

SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION = 1
SENSOR_HEIGHT_RESOURCE_TYPES = (
    "station-specific",
    "historical",
    "provider-default",
)
SENSOR_HEIGHT_RECORD_STATUSES = (
    "active",
    "proposed",
    "superseded",
    "revoked",
)
SENSOR_HEIGHT_RESOURCE_FILES = {
    "station-specific": "wx_sensor_height_stations.json",
    "historical": "wx_sensor_height_trusted_history.json",
    "provider-default": "wx_sensor_height_providers.json",
}

_RESOURCE_SOURCE_NAMES = {
    "station-specific": "firebench_trusted_stations",
    "historical": "firebench_trusted_history",
    "provider-default": "firebench_providers_default",
}
_EXPECTED_CONFIDENCE = {
    "station-specific": SensorHeightConfidence.VERIFIED,
    "historical": SensorHeightConfidence.VERIFIED,
    "provider-default": SensorHeightConfidence.PROVIDER_DEFAULT,
}


@dataclass(frozen=True)
class SensorHeightRecord:
    """One resolved variable entry from a versioned sensor-height resource."""

    record_id: str
    record_type: str
    variable: str
    height: float
    units: str
    confidence: SensorHeightConfidence
    status: str
    provider: str
    station: str | None
    source_reference: str
    source_date: str | None
    verification_date: str
    reviewer_or_authority: str
    notes: str | None


@dataclass(frozen=True)
class SensorHeightResolution:
    """Sensor height selected for one station and variable."""

    height: float
    units: str
    confidence: SensorHeightConfidence
    source: str
    provider: str
    source_reference: str
    source_date: str | None
    verification_date: str
    reviewer_or_authority: str
    notes: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class SensorHeightResources:
    """Validated records grouped by source-precedence class."""

    station_specific: tuple[SensorHeightRecord, ...]
    historical: tuple[SensorHeightRecord, ...]
    provider_default: tuple[SensorHeightRecord, ...]


def _require_nonempty_string(value, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} requires a non-empty `{field}` string.")
    return value


def _validate_optional_date(value, field: str, context: str) -> str | None:
    if value is None:
        return None
    value = _require_nonempty_string(value, field, context)
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{context} has invalid `{field}`={value!r}; expected YYYY-MM-DD.") from error
    return value


def _effective_provenance(document: dict, record: dict, context: str) -> dict:
    default = document.get("provenance")
    if not isinstance(default, dict):
        raise ValueError(f"{context} requires a top-level `provenance` object.")
    override = record.get("provenance", {})
    if not isinstance(override, dict):
        raise ValueError(f"{context} has a non-object `provenance` override.")
    provenance = {**default, **override}
    source_reference = _require_nonempty_string(
        provenance.get("source_reference"),
        "source_reference",
        context,
    )
    verification_date = _validate_optional_date(
        provenance.get("verification_date"),
        "verification_date",
        context,
    )
    if verification_date is None:
        raise ValueError(f"{context} requires `verification_date`.")
    reviewer = _require_nonempty_string(
        provenance.get("reviewer_or_authority"),
        "reviewer_or_authority",
        context,
    )
    source_date = _validate_optional_date(provenance.get("source_date"), "source_date", context)
    notes = provenance.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError(f"{context} has a non-string `notes` value.")
    return {
        "source_reference": source_reference,
        "source_date": source_date,
        "verification_date": verification_date,
        "reviewer_or_authority": reviewer,
        "notes": notes,
    }


def validate_sensor_height_resource(
    document: dict,
    *,
    expected_type: str | None = None,
) -> tuple[SensorHeightRecord, ...]:
    """Validate and expand one versioned sensor-height resource document.

    A resource record may apply one height to several variables. The returned
    tuple contains one immutable entry per station/provider and variable so the
    resolver cannot silently overwrite duplicate selectors.
    """

    # The explicit branches below keep every schema failure contextual.
    # pylint: disable=too-many-branches
    if not isinstance(document, dict):
        raise ValueError("Sensor-height resource must be a JSON object.")
    if document.get("schema_version") != SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported sensor-height resource `schema_version`; "
            f"expected {SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION}."
        )

    record_type = document.get("record_type")
    if record_type not in SENSOR_HEIGHT_RESOURCE_TYPES:
        raise ValueError(f"Unknown sensor-height resource `record_type`: {record_type!r}.")
    if expected_type is not None and record_type != expected_type:
        raise ValueError(f"Expected `{expected_type}` resource, found `{record_type}`.")

    raw_records = document.get("records")
    if not isinstance(raw_records, list):
        raise ValueError(f"Sensor-height `{record_type}` resource requires a `records` list.")

    records = []
    record_ids = set()
    active_selectors = set()
    for index, raw_record in enumerate(raw_records):
        context = f"{record_type} record #{index + 1}"
        if not isinstance(raw_record, dict):
            raise ValueError(f"{context} must be an object.")

        record_id = _require_nonempty_string(raw_record.get("record_id"), "record_id", context)
        if record_id in record_ids:
            raise ValueError(f"Duplicate sensor-height `record_id`: {record_id!r}.")
        record_ids.add(record_id)

        station = raw_record.get("station")
        if record_type == "provider-default":
            if station is not None:
                raise ValueError(f"{context} must not define `station`.")
        else:
            station = _require_nonempty_string(station, "station", context)

        provider = _require_nonempty_string(raw_record.get("provider"), "provider", context)
        variables = raw_record.get("variables")
        if not isinstance(variables, list) or not variables:
            raise ValueError(f"{context} requires a non-empty `variables` list.")
        if len(variables) != len(set(variables)):
            raise ValueError(f"{context} contains duplicate variables.")
        unsupported = sorted(set(variables).difference(VARIABLE_CONVERSION))
        if unsupported:
            raise ValueError(f"{context} contains unsupported variables: {unsupported}.")

        height = raw_record.get("height")
        if (
            isinstance(height, (bool, np.bool_))
            or not isinstance(height, Real)
            or not np.isfinite(height)
            or height < 0
        ):
            raise ValueError(f"{context} has invalid `height`={height!r}.")
        units = _require_nonempty_string(raw_record.get("units"), "units", context)
        try:
            (float(height) * ureg(units)).to("m")
        except (PintError, TypeError, ValueError) as error:
            raise ValueError(f"{context} has non-length `units`={units!r}.") from error

        confidence = raw_record.get("confidence")
        if isinstance(confidence, (bool, np.bool_)) or not isinstance(confidence, Integral):
            raise ValueError(f"{context} has unknown `confidence`={confidence!r}.")
        try:
            canonical_confidence = SensorHeightConfidence(int(confidence))
        except ValueError as error:
            raise ValueError(f"{context} has unknown `confidence`={confidence!r}.") from error
        if canonical_confidence is not _EXPECTED_CONFIDENCE[record_type]:
            raise ValueError(
                f"{context} has confidence {int(canonical_confidence)}; "
                f"`{record_type}` records require {int(_EXPECTED_CONFIDENCE[record_type])}."
            )

        status = raw_record.get("status")
        if status not in SENSOR_HEIGHT_RECORD_STATUSES:
            raise ValueError(f"{context} has unknown `status`={status!r}.")
        provenance = _effective_provenance(document, raw_record, context)

        for variable in variables:
            selector = (station if station is not None else provider, variable)
            if status in ("active", "proposed") and selector in active_selectors:
                raise ValueError(
                    f"Duplicate active/proposed sensor-height selector {selector!r} "
                    f"in `{record_type}` resource."
                )
            if status in ("active", "proposed"):
                active_selectors.add(selector)
            records.append(
                SensorHeightRecord(
                    record_id=record_id,
                    record_type=record_type,
                    variable=variable,
                    height=float(height),
                    units=units,
                    confidence=canonical_confidence,
                    status=status,
                    provider=provider,
                    station=station,
                    **provenance,
                )
            )
    return tuple(records)


def _load_resource_document(record_type: str) -> dict:
    path = files("firebench").joinpath(f"resources/{SENSOR_HEIGHT_RESOURCE_FILES[record_type]}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_sensor_height_resources() -> SensorHeightResources:
    """Load and validate all installed sensor-height resources."""

    loaded = {
        record_type: validate_sensor_height_resource(
            _load_resource_document(record_type),
            expected_type=record_type,
        )
        for record_type in SENSOR_HEIGHT_RESOURCE_TYPES
    }
    return SensorHeightResources(
        station_specific=loaded["station-specific"],
        historical=loaded["historical"],
        provider_default=loaded["provider-default"],
    )


def validate_installed_sensor_height_resources() -> dict[str, int]:
    """Validate installed resources and return expanded record counts."""

    load_sensor_height_resources.cache_clear()
    resources = load_sensor_height_resources()
    return {
        "station-specific": len(resources.station_specific),
        "historical": len(resources.historical),
        "provider-default": len(resources.provider_default),
    }


def _resolution_from_record(record: SensorHeightRecord) -> SensorHeightResolution:
    return SensorHeightResolution(
        height=record.height,
        units=record.units,
        confidence=record.confidence,
        source=_RESOURCE_SOURCE_NAMES[record.record_type],
        provider=record.provider,
        source_reference=record.source_reference,
        source_date=record.source_date,
        verification_date=record.verification_date,
        reviewer_or_authority=record.reviewer_or_authority,
        notes=record.notes,
        record_id=record.record_id,
    )


def resolve_sensor_height(
    *,
    station: str,
    variable: str,
    provider: str | None,
    synoptic_height: float | None = None,
    synoptic_source_reference: str | None = None,
    synoptic_source_date: str | None = None,
    verification_date: str,
    resources: SensorHeightResources | None = None,
) -> SensorHeightResolution:
    """Resolve one height using Synoptic, station, history, provider, then defaults."""

    if variable not in VARIABLE_CONVERSION:
        raise ValueError(f"Unsupported Synoptic sensor-height variable: {variable!r}.")
    verification_date = _validate_optional_date(
        verification_date,
        "verification_date",
        f"sensor-height resolution for {station}/{variable}",
    )
    if verification_date is None:
        raise ValueError(f"Sensor-height resolution for {station}/{variable} requires a date.")
    synoptic_source_date = _validate_optional_date(
        synoptic_source_date,
        "synoptic_source_date",
        f"Synoptic metadata for {station}/{variable}",
    )

    if synoptic_height is not None:
        if (
            isinstance(synoptic_height, (bool, np.bool_))
            or not isinstance(synoptic_height, Real)
            or not np.isfinite(synoptic_height)
            or synoptic_height < 0
        ):
            raise ValueError(f"Invalid Synoptic sensor height: {synoptic_height!r}.")
        source_reference = _require_nonempty_string(
            synoptic_source_reference,
            "synoptic_source_reference",
            f"Synoptic metadata for {station}/{variable}",
        )
        return SensorHeightResolution(
            height=float(synoptic_height),
            units="m",
            confidence=SensorHeightConfidence.VERIFIED,
            source="from_data",
            provider=provider or "Synoptic",
            source_reference=source_reference,
            source_date=synoptic_source_date,
            verification_date=verification_date,
            reviewer_or_authority="Synoptic Data PBC",
            notes="Height supplied with the downloaded Synoptic sensor metadata.",
        )

    resources = resources or load_sensor_height_resources()
    for records in (
        resources.station_specific,
        resources.historical,
    ):
        for record in records:
            if record.status == "active" and record.station == station and record.variable == variable:
                return _resolution_from_record(record)
    if provider is not None:
        for record in resources.provider_default:
            if record.status == "active" and record.provider == provider and record.variable == variable:
                return _resolution_from_record(record)

    return SensorHeightResolution(
        height=float(VARIABLE_CONVERSION[variable]["default_sensor_height"]),
        units="m",
        confidence=SensorHeightConfidence.UNKNOWN,
        source="firebench_default",
        provider=provider or "unknown",
        source_reference="firebench:VARIABLE_CONVERSION",
        source_date=None,
        verification_date=verification_date,
        reviewer_or_authority="FireBench maintainers",
        notes="Variable-wide fallback; not evidence of a station installation height.",
    )
