import h5py
import pytest

from firebench import adapter_common
from firebench import standardize as fs
from firebench import ureg


def test_adapter_uses_trusted_observation_height_and_records_prepared_height(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        observation = obs_h5.create_dataset(
            "time_series/station_TEST/wind_speed",
            data=[2.0, 3.0],
        )
        observation.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = 20
        observation.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "ft"
        observation.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = 2

        target_height = adapter_common.trusted_observation_sensor_height(
            obs_h5,
            "station_TEST",
            "wind_speed",
        )

    assert target_height.to("ft").magnitude == pytest.approx(20)

    with h5py.File(model_path, "w") as model_h5:
        model = model_h5.create_dataset(
            "time_series/station_TEST/wind_speed",
            data=[2.0, 3.0],
        )
        adapter_common.write_model_sensor_height_metadata(model, target_height)

        assert model.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == pytest.approx(6.096)
        assert model.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] == "m"


def test_adapter_rejects_untrusted_observation_height(tmp_path):
    obs_path = tmp_path / "obs.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        observation = obs_h5.create_dataset(
            "time_series/station_TEST/wind_speed",
            data=[2.0],
        )
        observation.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = 10
        observation.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
        observation.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = 1

        with pytest.raises(ValueError, match="is not TSO"):
            adapter_common.trusted_observation_sensor_height(
                obs_h5,
                "station_TEST",
                "wind_speed",
            )


def test_adapter_rejects_dimensionless_prepared_height(tmp_path):
    model_path = tmp_path / "model.h5"

    with h5py.File(model_path, "w") as model_h5:
        model = model_h5.create_dataset(
            "time_series/station_TEST/wind_speed",
            data=[2.0],
        )

        with pytest.raises(ValueError, match="compatible units"):
            adapter_common.write_model_sensor_height_metadata(model, 10 * ureg.second)
