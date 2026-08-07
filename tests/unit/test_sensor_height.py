import logging

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.standardize import synoptic


def test_parse_sensor_height_confidence_accepts_canonical_integer_scalars():
    assert (
        fs.parse_sensor_height_confidence(
            2,
            station="station_TEST",
            variable="wind_speed",
        )
        is fs.SensorHeightConfidence.VERIFIED
    )
    assert (
        fs.parse_sensor_height_confidence(
            np.array([1], dtype=np.int8),
            station="station_TEST",
            variable="wind_speed",
        )
        is fs.SensorHeightConfidence.PROVIDER_DEFAULT
    )


def test_parse_sensor_height_confidence_warns_once_for_malformed_metadata(caplog):
    warning_cache = set()

    with caplog.at_level(logging.WARNING):
        first = fs.parse_sensor_height_confidence(
            "2 - verified measurement",
            station="station_TEST",
            variable="wind_speed",
            warning_cache=warning_cache,
        )
        second = fs.parse_sensor_height_confidence(
            None,
            station="station_TEST",
            variable="wind_speed",
            warning_cache=warning_cache,
        )

    assert first is second is fs.SensorHeightConfidence.UNKNOWN
    assert len(caplog.records) == 1
    assert "station_TEST" in caplog.text
    assert "wind_speed" in caplog.text


def test_station_set_membership_is_explicit():
    assert fs.station_set_includes(
        fs.WeatherStationSet.TSO,
        fs.SensorHeightConfidence.VERIFIED,
    )
    assert not fs.station_set_includes(
        fs.WeatherStationSet.TSO,
        fs.SensorHeightConfidence.PROVIDER_DEFAULT,
    )
    assert fs.station_set_includes(
        fs.WeatherStationSet.ALL_SOURCES,
        fs.SensorHeightConfidence.UNKNOWN,
    )


def test_synoptic_writer_uses_numeric_confidence_and_separate_description(tmp_path):
    h5_path = tmp_path / "weather.h5"
    variable_info = {
        "std_name": "wind_speed",
        "units": "m/s",
        "dtype": np.float64,
    }

    with h5py.File(h5_path, "w") as h5:
        station = h5.create_group("time_series/station_TEST")
        synoptic.__add_sh_to_group(
            station,
            [1.0, 2.0],
            variable_info,
            10,
            "m",
            "from_data",
            fs.SensorHeightConfidence.VERIFIED,
            1,
        )

        dataset = station["wind_speed"]
        assert dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] == 2
        assert (
            dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE]
            == "verified measurement or accepted trusted record"
        )


def _add_weather_variable(
    h5,
    station,
    *,
    height=None,
    height_units=None,
    confidence=None,
):
    variable = h5.create_dataset(f"time_series/{station}/wind_speed", data=[1.0])
    if height is not None:
        variable.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
    if height_units is not None:
        variable.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = height_units
    if confidence is not None:
        variable.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = confidence
    return variable


def test_validate_weather_sensor_heights_converts_units(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        _add_weather_variable(
            obs_h5,
            "station_TEST",
            height=10,
            height_units="m",
            confidence=2,
        )
    with h5py.File(model_path, "w") as model_h5:
        _add_weather_variable(
            model_h5,
            "station_TEST",
            height=1000,
            height_units="cm",
        )

    with h5py.File(obs_path, "r") as obs_h5, h5py.File(model_path, "r") as model_h5:
        validation = fs.validate_weather_sensor_heights(
            obs_h5,
            model_h5,
            station="station_TEST",
            variable="wind_speed",
        )

    assert validation.valid is True
    assert validation.reason is None
    assert validation.observation_height_m == 10
    assert validation.model_height_m == 10


def test_validate_weather_sensor_heights_reports_missing_and_mismatch(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        _add_weather_variable(
            obs_h5,
            "station_TEST",
            height=10,
            height_units="m",
            confidence=2,
        )
    with h5py.File(model_path, "w") as model_h5:
        _add_weather_variable(model_h5, "station_TEST")

    with h5py.File(obs_path, "r") as obs_h5, h5py.File(model_path, "r+") as model_h5:
        missing = fs.validate_weather_sensor_heights(
            obs_h5,
            model_h5,
            station="station_TEST",
            variable="wind_speed",
        )
        model_h5["time_series/station_TEST/wind_speed"].attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = 9
        model_h5["time_series/station_TEST/wind_speed"].attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
        mismatch = fs.validate_weather_sensor_heights(
            obs_h5,
            model_h5,
            station="station_TEST",
            variable="wind_speed",
        )

    assert missing.valid is False
    assert "missing a numeric `sensor_height`" in missing.reason
    assert mismatch.valid is False
    assert "does not match" in mismatch.reason


@pytest.mark.parametrize(
    ("model_height_cm", "expected_valid"),
    (
        (999.0, True),
        (998.9, False),
    ),
)
def test_validate_weather_sensor_heights_applies_matching_tolerance(
    tmp_path,
    model_height_cm,
    expected_valid,
):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        _add_weather_variable(
            obs_h5,
            "station_TEST",
            height=10,
            height_units="m",
            confidence=2,
        )
    with h5py.File(model_path, "w") as model_h5:
        _add_weather_variable(
            model_h5,
            "station_TEST",
            height=model_height_cm,
            height_units="cm",
        )

    with h5py.File(obs_path, "r") as obs_h5, h5py.File(model_path, "r") as model_h5:
        validation = fs.validate_weather_sensor_heights(
            obs_h5,
            model_h5,
            station="station_TEST",
            variable="wind_speed",
        )

    assert validation.valid is expected_valid
    assert (validation.reason is None) is expected_valid
