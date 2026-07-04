from pathlib import Path
from datetime import datetime

import h5py
import numpy as np
import pytest
import pytz

from firebench.benchmarks import c001_caldor


def test_build_registries_is_fresh():
    c001_caldor.build_registries()
    first_r08_count = len(c001_caldor.REQUIREMENTS["R08"]["benchmarks"])
    first_benchmark_count = len(c001_caldor.BENCHMARK_FUNCTIONS)

    c001_caldor.build_registries()

    assert len(c001_caldor.REQUIREMENTS["R08"]["benchmarks"]) == first_r08_count
    assert len(c001_caldor.BENCHMARK_FUNCTIONS) == first_benchmark_count
    assert first_r08_count == 1188


def test_hrrr_weather_aggregation_schemes_are_generated():
    c001_caldor.build_registries()

    assert "WX_WH1" in c001_caldor.AGGREGATION
    assert "WX_WH62" in c001_caldor.AGGREGATION
    assert "WX_WH_ALL" in c001_caldor.AGGREGATION
    assert list(c001_caldor.AGGREGATION["WX_WH1"]) == [
        "Air Temp WH1",
        "RH WH1",
        "Wind Speed WH1",
        "Wind Direction WH1",
        "FMC 10h WH1",
    ]
    assert len(c001_caldor.AGGREGATION["WX_WH_ALL"]) == 5 * len(c001_caldor.WH_PERIODS)


def test_hrrr_fire_perimeter_aggregation_schemes_are_generated():
    c001_caldor.build_registries()

    assert "FP_H1" in c001_caldor.AGGREGATION
    assert "FP_H12" in c001_caldor.AGGREGATION
    assert "FP_H62" in c001_caldor.AGGREGATION
    assert len(c001_caldor.AGGREGATION["FP_H12"]["FP_H12"]["benchmarks"]) == 8
    assert "R_FP_H12" in c001_caldor.REQUIREMENTS
    assert len(c001_caldor.REQUIREMENTS["R_FP_H12"]["benchmarks"]) == 8


def test_hrrr_benchmark_target_selects_matching_fire_perimeter_group():
    c001_caldor.build_registries()

    selected_target = c001_caldor.resolve_benchmark_target("h013_p")

    assert selected_target == "H013_P"
    assert c001_caldor.AGGREGATION["H013_P"] == c001_caldor.AGGREGATION["FP_H13"]
    assert c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "H013_P") == (
        c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "FP_H13")
    )
    assert c001_caldor._target_group_display_names("H013_P") == {"FP_H13": "Fire Perimeters"}


def test_describe_available_targets_with_full_target_includes_details():
    target_info = c001_caldor.describe_available_targets("H013_P")

    assert target_info["target"] == "H013_P"
    assert target_info["period"]["target"] == "H013"
    assert target_info["kpi_groups"] == {"P": "Fire Perimeters"}
    assert target_info["perimeters"] == [
        {
            "time": "2021-08-21T21:15-07:00",
            "path": "/polygons/Caldor_2021-08-21T21:15-07:00",
        },
    ]
    assert target_info["kpis"][0] == {
        "id": "FB001_FPH097",
        "name": "Average Jaccard Index",
        "group": "Fire Perimeters",
        "weight": 1,
        "value_norm_param_m": None,
    }
    assert target_info["kpis"][-2:] == [
        {
            "id": "FB001_FPH103",
            "name": "Final Burn Area Bias",
            "group": "Fire Perimeters",
            "weight": 2,
            "value_norm_param_m": 10000,
        },
        {
            "id": "FB001_FPH104",
            "name": "Burn Area RMSE",
            "group": "Fire Perimeters",
            "weight": 2,
            "value_norm_param_m": 10000,
        },
    ]


def test_curated_benchmark_target_selects_matching_fire_perimeter_group():
    c001_caldor.build_registries()

    selected_target = c001_caldor.resolve_benchmark_target("P02_P")

    assert selected_target == "P02_P"
    assert list(c001_caldor.AGGREGATION["P02_P"]) == ["Fire Perimeter W2"]
    assert c001_caldor.AGGREGATION["P02_P"]["Fire Perimeter W2"] == (
        c001_caldor.GROUPS["Fire Perimeter W2"]
    )


@pytest.mark.parametrize("benchmark_target", ["H999_P", "P99_P", "H013_X", "bad"])
def test_invalid_benchmark_target_fails_clearly(benchmark_target):
    c001_caldor.build_registries()

    with pytest.raises(ValueError, match="benchmark target|Unsupported|Unknown"):
        c001_caldor.resolve_benchmark_target(benchmark_target)


def test_demo_aggregation_contains_wh16_weather_and_fire_perimeter():
    c001_caldor.build_registries()

    assert list(c001_caldor.AGGREGATION["DEMO"]) == [
        "Air Temp WH16",
        "RH WH16",
        "Wind Speed WH16",
        "Wind Direction WH16",
        "FMC 10h WH16",
        "FP_H16",
    ]
    assert len(c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "DEMO")) == 86
    assert "FB001_WX343" in c001_caldor.AGGREGATION["DEMO"]["Air Temp WH16"]["benchmarks"]


def test_demo_wx0_sets_weather_group_weights_to_zero():
    c001_caldor.build_registries()

    assert list(c001_caldor.AGGREGATION["DEMO_WX0"]) == [
        "Air Temp WH16",
        "RH WH16",
        "Wind Speed WH16",
        "Wind Direction WH16",
        "FMC 10h WH16",
        "FP_H16",
    ]
    for group_name, group in c001_caldor.AGGREGATION["DEMO_WX0"].items():
        if group_name == "FP_H16":
            assert group["weight"] == 1
        else:
            assert group["weight"] == 0
            assert set(group["benchmarks"].values()) == {1}


def test_describe_benchmark_registry_prints_selected_groups():
    description = c001_caldor.describe_benchmark_registry("DEMO")

    assert "Benchmark target: DEMO" in description
    assert "Selected groups: 6" in description
    assert "- Air Temp WH16" in description
    assert "- FP_H16" in description
    assert "FB001_WX" in description
    assert "FB001_FPH" in description
    assert "Air temp" in description
    assert "Perimeters:" in description
    assert "/polygons/Caldor_2021-08-21T21:15-07:00" in description


def test_get_list_benchmark_with_aggregation_scheme():
    c001_caldor.build_registries()

    assert c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "B") == [
        "FB001_BD01",
        "FB001_BD02",
        "FB001_BD03",
        "FB001_BD04",
        "FB001_BD05",
        "FB001_BD06",
    ]
    assert set(c001_caldor.get_list_benchmark_with_agg(c001_caldor.AGGREGATION, "0")) == set(
        c001_caldor.BENCHMARK_FUNCTIONS
    )


def test_overwrite_previous_run(monkeypatch, tmp_path):
    output_path = tmp_path / "Caldor_rslt.json"

    assert c001_caldor.overwrite_previous_run(False, output_path) is True

    output_path.write_text("{}")
    assert c001_caldor.overwrite_previous_run(True, output_path) is True

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert c001_caldor.overwrite_previous_run(False, output_path) is False

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert c001_caldor.overwrite_previous_run(False, output_path) is True


def test_resolve_h5_relative_path(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    class FakeH5File:
        filename = str(data_dir / "Caldor.h5")

    assert (
        c001_caldor.resolve_h5_relative_path(FakeH5File(), "kml/perimeter.kml")
        == (data_dir / "kml" / "perimeter.kml").resolve()
    )

    absolute_path = (tmp_path / "absolute.kml").resolve()
    assert c001_caldor.resolve_h5_relative_path(FakeH5File(), absolute_path) == absolute_path


def test_get_mask_from_period_handles_byte_string_absolute_times(tmp_path):
    h5_path = tmp_path / "times.h5"
    with h5py.File(h5_path, "w") as h5:
        station = h5.create_group("time_series/station_TEST")
        station.create_dataset(
            "time",
            data=np.array(
                [
                    b"2021-08-20T16:00:00-07:00",
                    b"2021-08-20T18:00:00-07:00",
                    b"2021-08-20T20:00:00-07:00",
                ]
            ),
        )

    tz_ref = pytz.timezone("US/Pacific")
    period = (
        tz_ref.localize(datetime(2021, 8, 20, 17)),
        tz_ref.localize(datetime(2021, 8, 20, 19)),
    )
    with h5py.File(h5_path, "r") as h5:
        mask = c001_caldor.get_mask_from_period(h5, "time_series/station_TEST", period)

    assert mask.tolist() == [False, True, False]


def test_weather_benchmark_skips_missing_model_station_outside_period(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        time_series = obs_h5.create_group("time_series")
        station_outside = time_series.create_group("station_OUTSIDE")
        station_outside.create_dataset("time", data=[0, 1])
        station_outside["time"].attrs["time_origin"] = "2021-08-20T00:00:00+00:00"
        station_outside["time"].attrs["time_units"] = "hour"
        outside_var = station_outside.create_dataset("air_temperature", data=[290, 291])
        outside_var.attrs["units"] = "degK"
        outside_var.attrs["sensor_height_source_confidence_lvl"] = [0]

        station_inside = time_series.create_group("station_INSIDE")
        station_inside.create_dataset("time", data=[24, 25])
        station_inside["time"].attrs["time_origin"] = "2021-08-20T00:00:00+00:00"
        station_inside["time"].attrs["time_units"] = "hour"
        inside_var = station_inside.create_dataset("air_temperature", data=[292, 293])
        inside_var.attrs["units"] = "degK"
        inside_var.attrs["sensor_height_source_confidence_lvl"] = [0]

    with h5py.File(model_path, "w") as model_h5:
        time_series = model_h5.create_group("time_series")
        station_inside = time_series.create_group("station_INSIDE")
        station_inside.create_dataset("time", data=[24, 25])
        station_inside["time"].attrs["time_origin"] = "2021-08-20T00:00:00+00:00"
        station_inside["time"].attrs["time_units"] = "hour"
        inside_var = station_inside.create_dataset("air_temperature", data=[292, 293])
        inside_var.attrs["units"] = "degK"

    period = (
        datetime(2021, 8, 21, 0, tzinfo=pytz.UTC),
        datetime(2021, 8, 21, 1, tzinfo=pytz.UTC),
    )
    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        result = c001_caldor.bench_wx_generic_index(
            model_h5,
            obs_h5,
            {},
            kpi_name_custom="Air temp test",
            period=period,
            wx_variable_name="air_temperature",
            common_unit="degK",
            metric_func=lambda model, obs: float(np.mean(model - obs)),
            stat_func=lambda values: float(np.mean(values)),
            value_norm_param_m=5,
            use_all_sensor_height_trust_lvl=True,
        )

    assert result["Air temp test"] == 0.0
