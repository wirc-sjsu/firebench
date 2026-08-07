import json
import shutil

from h5py import File
import pytest

from firebench import __version__
from firebench import standardize as fs
from firebench.benchmarks import c001_caldor
from firebench.benchmarks.weather_release_inventory import (
    build_weather_release_inventory,
    write_weather_release_inventory,
)
from firebench.tools import calculate_sha256


def _synoptic_station(station_id, provider, values, *, sensor_height=None):
    sensor_metadata = {}
    if sensor_height is not None:
        sensor_metadata = {
            "wind": {
                "wind_speed_set_1": {
                    "position": sensor_height,
                }
            }
        }
    return {
        "STID": station_id,
        "NAME": f"Station {station_id}",
        "ID": str(len(station_id)),
        "MNET_ID": "2",
        "STATE": "CA",
        "TIMEZONE": "UTC",
        "LATITUDE": "38.0",
        "LONGITUDE": "-120.0",
        "ELEVATION": "1000",
        "UNITS": {"elevation": "ft"},
        "PROVIDERS": [{"name": provider}],
        "OBSERVATIONS": {
            "date_time": [
                "2021-08-18T04:00:00Z",
                "2021-08-18T05:00:00Z",
            ],
            "wind_speed_set_1": values,
        },
        "SENSOR_VARIABLES": sensor_metadata,
    }


def _standardize_three_confidence_levels(tmp_path):
    source_path = tmp_path / "synoptic.json"
    source = {
        "STATION": [
            _synoptic_station(
                "E2E_TRUSTED",
                "Test provider",
                [1.0, 1.5],
                sensor_height=7.5,
            ),
            _synoptic_station(
                "E2E_PROVIDER",
                "Bureau of Land Management",
                [2.0, 2.5],
            ),
            _synoptic_station(
                "E2E_UNKNOWN",
                "Unknown provider",
                [3.0, 3.5],
            ),
        ]
    }
    source_path.write_text(json.dumps(source), encoding="utf-8")
    observation_path = tmp_path / "observations.h5"
    with File(observation_path, "w") as output:
        fs.standardize_synoptic_raws_from_json(source_path, output)
        output.attrs["FireBench_io_version"] = "1.0"
        output.attrs["created_on"] = "2026-07-24T12:00:00+00:00"
        output.attrs["created_by"] = "FireBench tests"
        output.attrs["description"] = "Synthetic release inventory observations"
        output.attrs["version"] = "test-data"
    return observation_path


def test_synoptic_standardization_executes_tso_and_all_sources_kpis(tmp_path):
    observation_path = _standardize_three_confidence_levels(tmp_path)
    model_path = tmp_path / "model.h5"
    shutil.copyfile(observation_path, model_path)
    period = c001_caldor.cfg.CURATED_PERIODS["W1"]

    with File(observation_path, "r") as observations:
        context = {}
        tso_selection = c001_caldor._select_weather_stations(
            observations,
            "wind_speed",
            period,
            fs.WeatherStationSet.TSO,
            context,
        )
        all_sources_selection = c001_caldor._select_weather_stations(
            observations,
            "wind_speed",
            period,
            fs.WeatherStationSet.ALL_SOURCES,
            context,
        )

        assert [item["station"] for item in tso_selection["included"]] == ["station_E2E_TRUSTED"]
        assert {item["confidence"] for item in all_sources_selection["included"]} == {0, 1, 2}
        for station_name, expected_confidence in (
            ("station_E2E_TRUSTED", 2),
            ("station_E2E_PROVIDER", 1),
            ("station_E2E_UNKNOWN", 0),
        ):
            dataset = observations[f"time_series/{station_name}/wind_speed"]
            assert dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] == expected_confidence
            assert dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE] == (
                fs.sensor_height_confidence_description(expected_confidence)
            )

    target = c001_caldor.describe_available_targets("P01_W", obs_data=observation_path)
    cli_wind_counts = next(item for item in target["weather_stations"] if item["variable"] == "wind_speed")

    with File(model_path, "r") as model, File(observation_path, "r") as observations:
        tso_result = c001_caldor.bench_wx_generic_index(
            model,
            observations,
            {},
            kpi_name_custom="Wind Speed test TSO",
            period=period,
            wx_variable_name="wind_speed",
            common_unit="m/s",
            metric_func=lambda _model, _observation: 0.0,
            stat_func=len,
            value_norm_param_m=5,
            station_set=fs.WeatherStationSet.TSO,
        )
        all_sources_result = c001_caldor.bench_wx_generic_index(
            model,
            observations,
            {},
            kpi_name_custom="Wind Speed test All sources",
            period=period,
            wx_variable_name="wind_speed",
            common_unit="m/s",
            metric_func=lambda _model, _observation: 0.0,
            stat_func=len,
            value_norm_param_m=5,
            station_set=fs.WeatherStationSet.ALL_SOURCES,
        )

    assert tso_result["Wind Speed test TSO"] == cli_wind_counts["trusted_stations"] == 1
    assert all_sources_result["Wind Speed test All sources"] == cli_wind_counts["stations"] == 3


def test_weather_release_inventory_binds_inputs_and_counts(tmp_path):
    observation_path = _standardize_three_confidence_levels(tmp_path)

    inventory = build_weather_release_inventory(
        observation_path,
        benchmark_data_version="test-data",
    )

    assert inventory["inventory_schema_version"] == 1
    assert inventory["firebench_version"] == __version__
    assert inventory["benchmark"]["data_version"] == "test-data"
    assert inventory["observation"]["sha256"] == calculate_sha256(observation_path)
    assert inventory["trusted_height_resources"]["schema_version"] == 1
    assert len(inventory["trusted_height_resources"]["combined_sha256"]) == 64
    assert inventory["weather_dataset_totals"] == {
        "variable_datasets": 3,
        "confidence_levels": {"0": 1, "1": 1, "2": 1},
        "sensor_height_sources": {
            "firebench_default": 1,
            "firebench_providers_default": 1,
            "from_data": 1,
        },
        "canonical_numeric_confidence": 3,
        "noncanonical_or_missing_confidence": 0,
        "canonical_confidence_with_matching_description": 3,
    }
    wind_w1 = next(
        row for row in inventory["periods"] if row["period"] == "W1" and row["variable"] == "wind_speed"
    )
    assert wind_w1["all_sources_stations"] == 3
    assert wind_w1["tso_stations"] == 1
    assert wind_w1["confidence_levels"] == {"0": 1, "1": 1, "2": 1}
    assert inventory["release_checks"] == {
        "all_weather_confidence_is_canonical_numeric": True,
        "all_weather_confidence_has_matching_description": True,
    }

    output_path = tmp_path / "inventory.json"
    written = write_weather_release_inventory(
        observation_path,
        output_path,
        benchmark_data_version="test-data",
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == written == inventory


def test_weather_release_inventory_rejects_wrong_data_version(tmp_path):
    observation_path = _standardize_three_confidence_levels(tmp_path)

    with pytest.raises(ValueError, match="does not match"):
        build_weather_release_inventory(
            observation_path,
            benchmark_data_version="wrong-version",
        )
