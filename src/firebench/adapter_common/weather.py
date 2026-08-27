import numpy as np
from pint.errors import PintError

from ..standardize.sensor_height import (
    SENSOR_HEIGHT_ATTRIBUTE,
    SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE,
    SENSOR_HEIGHT_UNITS_ATTRIBUTE,
    SensorHeightConfidence,
    parse_sensor_height_confidence,
    read_sensor_height,
)
from ..standardize.std_file_info import TIME_SERIES


def trusted_observation_sensor_height(
    observation_dataset,
    station: str,
    variable: str,
    *,
    units: str = "m",
):
    """Return the trusted observational height an adapter must use as its interpolation target."""
    data_path = f"{TIME_SERIES}/{station}/{variable}"
    if data_path not in observation_dataset:
        raise ValueError(f"Observational dataset `{data_path}` is missing.")

    dataset = observation_dataset[data_path]
    confidence = parse_sensor_height_confidence(
        dataset.attrs.get(SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE),
        station=station,
        variable=variable,
    )
    if confidence is not SensorHeightConfidence.VERIFIED:
        raise ValueError(
            f"Observational dataset `{data_path}` is not TSO: confidence level " f"{int(confidence)}."
        )

    return read_sensor_height(dataset, dataset_path=data_path, allow_legacy_text=True).to(units)


def write_model_sensor_height_metadata(model_variable, prepared_height) -> None:
    """Record the height actually used to prepare or interpolate a model variable."""
    try:
        height_m = prepared_height.to("m")
    except (AttributeError, TypeError, ValueError, PintError) as exc:
        raise ValueError("`prepared_height` must be a scalar height with compatible units.") from exc

    magnitude = np.asarray(height_m.magnitude)
    if magnitude.ndim != 0 or not np.isfinite(float(magnitude)) or float(magnitude) < 0:
        raise ValueError("`prepared_height` must be a finite, non-negative scalar height.")

    model_variable.attrs[SENSOR_HEIGHT_ATTRIBUTE] = float(magnitude)
    model_variable.attrs[SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
