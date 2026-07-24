from enum import Enum, IntEnum
from numbers import Integral

import numpy as np

from ..tools.logging_config import logger

SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE = "sensor_height_source_confidence_lvl"
SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE = "sensor_height_source_confidence_description"


class SensorHeightConfidence(IntEnum):
    """Confidence in the source of observational sensor-height metadata."""

    UNKNOWN = 0
    PROVIDER_DEFAULT = 1
    VERIFIED = 2


class WeatherStationSet(str, Enum):
    """Weather-station populations available to a benchmark."""

    TSO = "TSO"
    ALL_SOURCES = "all sources"


SENSOR_HEIGHT_CONFIDENCE_DESCRIPTIONS = {
    SensorHeightConfidence.UNKNOWN: "unknown (guessed or missing metadata)",
    SensorHeightConfidence.PROVIDER_DEFAULT: "provider default (not verified)",
    SensorHeightConfidence.VERIFIED: "verified measurement or accepted trusted record",
}


def parse_sensor_height_confidence(
    value,
    *,
    station: str,
    variable: str,
    warning_cache: set[tuple[str, str]] | None = None,
) -> SensorHeightConfidence:
    """Return canonical confidence, treating missing or malformed values as unknown."""
    parsed_value = _single_value(value)
    if isinstance(parsed_value, Integral) and not isinstance(parsed_value, (bool, np.bool_)):
        try:
            return SensorHeightConfidence(int(parsed_value))
        except ValueError:
            pass

    warning_key = (station, variable)
    if warning_cache is None or warning_key not in warning_cache:
        logger.warning(
            "Missing or malformed sensor-height confidence for station %s variable %s: %r. "
            "Treating it as level 0.",
            station,
            variable,
            value,
        )
        if warning_cache is not None:
            warning_cache.add(warning_key)
    return SensorHeightConfidence.UNKNOWN


def sensor_height_confidence_description(confidence: SensorHeightConfidence | int) -> str:
    """Return the canonical human-readable description for a confidence value."""
    canonical = SensorHeightConfidence(int(confidence))
    return SENSOR_HEIGHT_CONFIDENCE_DESCRIPTIONS[canonical]


def station_set_includes(station_set: WeatherStationSet, confidence: SensorHeightConfidence) -> bool:
    """Return whether a confidence level belongs to the requested station set."""
    if station_set is WeatherStationSet.ALL_SOURCES:
        return True
    if station_set is WeatherStationSet.TSO:
        return confidence is SensorHeightConfidence.VERIFIED
    raise ValueError(f"Unsupported weather station set: {station_set!r}")


def _single_value(value):
    if value is None:
        return None
    array = np.asarray(value)
    if array.ndim == 0:
        return array.item()
    if array.size == 1:
        return array.reshape(-1)[0].item()
    return value
