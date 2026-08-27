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
            "verified by hand",
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


def test_parse_sensor_height_confidence_reads_legacy_combined_strings(caplog):
    """Packages standardized before 0.10 stored the level as a combined string."""
    with caplog.at_level(logging.WARNING, logger="firebench"):
        assert (
            fs.parse_sensor_height_confidence(
                "2 - verified measurement",
                station="station_TEST",
                variable="wind_speed",
            )
            is fs.SensorHeightConfidence.VERIFIED
        )
        assert (
            fs.parse_sensor_height_confidence(
                b"1 - provider default (not verified)",
                station="station_TEST",
                variable="wind_speed",
            )
            is fs.SensorHeightConfidence.PROVIDER_DEFAULT
        )
        assert (
            fs.parse_sensor_height_confidence(
                np.bytes_(b"0 - unknown (guessed or missing metadata)"),
                station="station_TEST",
                variable="wind_speed",
            )
            is fs.SensorHeightConfidence.UNKNOWN
        )

    assert caplog.records == []


def test_parse_sensor_height_confidence_rejects_unrecognized_confidence_strings():
    """Only the frozen historical strings are trusted, never an arbitrary description."""
    for value in ("2 - my own guess", "2", "verified measurement", "3 - verified measurement"):
        assert (
            fs.parse_sensor_height_confidence(
                value,
                station="station_TEST",
                variable="wind_speed",
            )
            is fs.SensorHeightConfidence.UNKNOWN
        )


def test_parse_sensor_height_confidence_logs_legacy_reads_once(caplog):
    warning_cache = set()

    # Other tests leave the shared FireBench logger above INFO, so raise it for this logger only.
    with caplog.at_level(logging.INFO, logger="firebench"):
        for _ in range(2):
            assert (
                fs.parse_sensor_height_confidence(
                    "2 - verified measurement",
                    station="station_TEST",
                    variable="wind_speed",
                    warning_cache=warning_cache,
                )
                is fs.SensorHeightConfidence.VERIFIED
            )

    legacy_records = [record for record in caplog.records if "legacy" in record.message]
    assert len(legacy_records) == 1
    assert legacy_records[0].levelno == logging.INFO


def test_read_sensor_height_accepts_legacy_text_only_when_allowed(tmp_path):
    """Observational packages before 0.10 stored provider heights as decimal strings."""
    h5_path = tmp_path / "heights.h5"
    with h5py.File(h5_path, "w") as h5:
        dataset = h5.create_dataset("wind_speed", data=[1.0, 2.0])
        dataset.attrs["sensor_height"] = "6.1"
        dataset.attrs["sensor_height_units"] = "m"

    with h5py.File(h5_path, "r") as h5:
        dataset = h5["wind_speed"]
        height = fs.read_sensor_height(
            dataset,
            dataset_path="wind_speed",
            allow_legacy_text=True,
        )
        assert height.to("m").magnitude == pytest.approx(6.1)

        # Model output must always record a numeric height.
        with pytest.raises(ValueError, match="numeric"):
            fs.read_sensor_height(dataset, dataset_path="wind_speed")


def test_read_sensor_height_rejects_non_numeric_legacy_text(tmp_path):
    h5_path = tmp_path / "heights.h5"
    with h5py.File(h5_path, "w") as h5:
        dataset = h5.create_dataset("wind_speed", data=[1.0, 2.0])
        dataset.attrs["sensor_height"] = "about ten metres"
        dataset.attrs["sensor_height_units"] = "m"

    with h5py.File(h5_path, "r") as h5:
        with pytest.raises(ValueError, match="numeric"):
            fs.read_sensor_height(
                h5["wind_speed"],
                dataset_path="wind_speed",
                allow_legacy_text=True,
            )


def test_validate_weather_sensor_heights_accepts_a_legacy_observation(tmp_path):
    """A pre-0.10 observation is TSO-eligible when the model matches its height."""
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"
    with h5py.File(obs_path, "w") as h5:
        dataset = h5.create_dataset("time_series/station_TEST/wind_speed", data=[1.0, 2.0])
        dataset.attrs["sensor_height"] = "6.1"
        dataset.attrs["sensor_height_units"] = "m"
        dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = "2 - verified measurement"
    with h5py.File(model_path, "w") as h5:
        dataset = h5.create_dataset("time_series/station_TEST/wind_speed", data=[1.1, 2.1])
        dataset.attrs["sensor_height"] = 6.1
        dataset.attrs["sensor_height_units"] = "m"

    with h5py.File(obs_path, "r") as obs, h5py.File(model_path, "r") as model:
        validation = fs.validate_weather_sensor_heights(
            obs,
            model,
            station="station_TEST",
            variable="wind_speed",
        )

    assert validation.valid
    assert validation.reason is None
    assert validation.observation_height_m == pytest.approx(6.1)


def test_validate_weather_sensor_heights_accepts_legacy_model_height_for_same_file(tmp_path):
    """The released observation file can also serve as model input for a smoke test."""
    h5_path = tmp_path / "weather.h5"
    with h5py.File(h5_path, "w") as h5:
        dataset = h5.create_dataset("time_series/station_TEST/wind_speed", data=[1.0, 2.0])
        dataset.attrs["sensor_height"] = "6.1"
        dataset.attrs["sensor_height_units"] = "m"
        dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = "2 - verified measurement"

    with h5py.File(h5_path, "r") as obs, h5py.File(h5_path, "r") as model:
        validation = fs.validate_weather_sensor_heights(
            obs,
            model,
            station="station_TEST",
            variable="wind_speed",
        )

    assert validation.valid
    assert validation.reason is None
    assert validation.observation_height_m == pytest.approx(6.1)
    assert validation.model_height_m == pytest.approx(6.1)


def test_validate_weather_sensor_heights_rejects_legacy_model_height_in_separate_file(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"
    for path in (obs_path, model_path):
        with h5py.File(path, "w") as h5:
            dataset = h5.create_dataset("time_series/station_TEST/wind_speed", data=[1.0, 2.0])
            dataset.attrs["sensor_height"] = "6.1"
            dataset.attrs["sensor_height_units"] = "m"
            dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = "2 - verified measurement"

    with h5py.File(obs_path, "r") as obs, h5py.File(model_path, "r") as model:
        validation = fs.validate_weather_sensor_heights(
            obs,
            model,
            station="station_TEST",
            variable="wind_speed",
        )

    assert not validation.valid
    assert "missing a numeric `sensor_height`" in validation.reason


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
