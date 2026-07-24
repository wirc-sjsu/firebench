import logging

import h5py
import numpy as np

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
