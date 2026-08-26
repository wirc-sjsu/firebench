from dataclasses import dataclass
from enum import Enum, IntEnum
from numbers import Integral

import numpy as np
from pint.errors import PintError

from ..tools.logging_config import logger
from ..tools.units import ureg
from .std_file_info import TIME_SERIES

SENSOR_HEIGHT_ATTRIBUTE = "sensor_height"
SENSOR_HEIGHT_UNITS_ATTRIBUTE = "sensor_height_units"
SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE = "sensor_height_source_confidence_lvl"
SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE = "sensor_height_source_confidence_description"
SENSOR_HEIGHT_MATCH_TOLERANCE_METERS = 0.01


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

# Frozen historical values of `sensor_height_source_confidence_lvl`. FireBench releases before
# 0.10 wrote the confidence as a combined "<level> - <description>" string instead of the
# canonical scalar integer. The set never changed while that encoding was in use, so it is matched
# exactly: only these three strings are recognized, and any other string stays level 0. Read-only
# compatibility for already published observational packages; new files must write the integer.
LEGACY_SENSOR_HEIGHT_CONFIDENCE_VALUES = {
    "0 - unknown (guessed or missing metadata)": SensorHeightConfidence.UNKNOWN,
    "1 - provider default (not verified)": SensorHeightConfidence.PROVIDER_DEFAULT,
    "2 - verified measurement": SensorHeightConfidence.VERIFIED,
}


@dataclass(frozen=True)
class SensorHeightValidation:
    """Result of validating prepared model height against a TSO observation."""

    valid: bool
    reason: str | None
    observation_height_m: float | None = None
    model_height_m: float | None = None


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

    legacy_confidence = _legacy_sensor_height_confidence(parsed_value)
    if legacy_confidence is not None:
        if warning_cache is None or warning_key not in warning_cache:
            logger.info(
                "Reading legacy sensor-height confidence for station %s variable %s: %r. "
                "Interpreting it as level %d.",
                station,
                variable,
                parsed_value,
                int(legacy_confidence),
            )
            if warning_cache is not None:
                warning_cache.add(warning_key)
        return legacy_confidence

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


def read_sensor_height(dataset, *, dataset_path: str, allow_legacy_text: bool = False) -> ureg.Quantity:
    """
    Read and convert a dataset's scalar sensor height to meters.

    ``allow_legacy_text`` additionally accepts a decimal string, which observational packages
    standardized before FireBench 0.10 wrote whenever the height came from the provider metadata.
    Model output is always required to record a numeric height.
    """
    raw_height = _single_value(dataset.attrs.get(SENSOR_HEIGHT_ATTRIBUTE))
    if allow_legacy_text:
        legacy_height = _legacy_sensor_height_text(raw_height)
        if legacy_height is not None:
            logger.info(
                "Reading legacy text sensor height for dataset '%s': %r.",
                dataset_path,
                raw_height,
            )
            raw_height = legacy_height
    if isinstance(raw_height, (bool, np.bool_)) or not isinstance(
        raw_height, (Integral, float, np.floating)
    ):
        raise ValueError(
            f"Dataset '{dataset_path}' is missing a numeric `{SENSOR_HEIGHT_ATTRIBUTE}` attribute."
        )

    height = float(raw_height)
    if not np.isfinite(height) or height < 0:
        raise ValueError(
            f"Dataset '{dataset_path}' has invalid `{SENSOR_HEIGHT_ATTRIBUTE}`={raw_height!r}."
        )

    raw_units = _single_value(dataset.attrs.get(SENSOR_HEIGHT_UNITS_ATTRIBUTE))
    if isinstance(raw_units, bytes):
        raw_units = raw_units.decode()
    if not isinstance(raw_units, str) or not raw_units.strip():
        attribute = SENSOR_HEIGHT_UNITS_ATTRIBUTE
        raise ValueError(f"Dataset '{dataset_path}' is missing a valid `{attribute}` attribute.")

    try:
        return ureg.Quantity(height, raw_units).to("m")
    except (TypeError, ValueError, PintError) as exc:
        raise ValueError(
            f"Dataset '{dataset_path}' has incompatible sensor-height units {raw_units!r}."
        ) from exc


def validate_weather_sensor_heights(
    observation_dataset,
    model_dataset,
    *,
    station: str,
    variable: str,
    warning_cache: set[tuple[str, str]] | None = None,
    tolerance_m: float = SENSOR_HEIGHT_MATCH_TOLERANCE_METERS,
) -> SensorHeightValidation:
    """Validate a prepared model variable against its trusted observational sensor height."""
    data_path = f"{TIME_SERIES}/{station}/{variable}"
    if data_path not in observation_dataset:
        return SensorHeightValidation(False, f"observational dataset `{data_path}` is missing")

    confidence = parse_sensor_height_confidence(
        observation_dataset[data_path].attrs.get(SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE),
        station=station,
        variable=variable,
        warning_cache=warning_cache,
    )
    if confidence is not SensorHeightConfidence.VERIFIED:
        return SensorHeightValidation(
            False,
            f"observational confidence level {int(confidence)} is not eligible for TSO",
        )

    try:
        observation_height = read_sensor_height(
            observation_dataset[data_path],
            dataset_path=data_path,
            allow_legacy_text=True,
        )
    except ValueError as exc:
        return SensorHeightValidation(False, f"observational {exc}")

    if data_path not in model_dataset:
        return SensorHeightValidation(False, f"model dataset `{data_path}` is missing")
    try:
        model_height = read_sensor_height(
            model_dataset[data_path],
            dataset_path=data_path,
        )
    except ValueError as exc:
        return SensorHeightValidation(False, f"model {exc}")

    observation_height_m = float(observation_height.magnitude)
    model_height_m = float(model_height.magnitude)
    if abs(observation_height_m - model_height_m) > tolerance_m:
        return SensorHeightValidation(
            False,
            f"model sensor height {model_height_m:g} m does not match observational height "
            f"{observation_height_m:g} m within {tolerance_m:g} m",
            observation_height_m,
            model_height_m,
        )

    return SensorHeightValidation(
        True,
        None,
        observation_height_m,
        model_height_m,
    )


def _legacy_sensor_height_text(value) -> float | None:
    """Return the height encoded by a pre-0.10 decimal-string `sensor_height`, if any."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _legacy_sensor_height_confidence(value) -> SensorHeightConfidence | None:
    """Return the confidence encoded by a pre-0.10 combined level/description string, if any."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    return LEGACY_SENSOR_HEIGHT_CONFIDENCE_VALUES.get(value.strip())


def _single_value(value):
    if value is None:
        return None
    array = np.asarray(value)
    if array.ndim == 0:
        return array.item()
    if array.size == 1:
        return array.reshape(-1)[0].item()
    return value
