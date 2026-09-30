import json
from datetime import datetime, timezone

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.benchmarks import wx_forecast

UTC = timezone.utc
CYCLE = datetime(2021, 8, 20, 0, tzinfo=UTC)
ORIGIN = CYCLE.isoformat()
UNITS = {
    "air_temperature": "degC",
    "relative_humidity": "percent",
    "wind_speed": "m/s",
    "wind_direction": "degree",
    "fuel_moisture_content_10h": "percent",
}
HEIGHTS = {
    "air_temperature": 2.0,
    "relative_humidity": 2.0,
    "wind_speed": 6.1,
    "wind_direction": 6.1,
    "fuel_moisture_content_10h": 0.3,
}


def _std(h5, tier=None):
    h5.attrs["FireBench_io_version"] = "1.0"
    h5.attrs["created_on"] = "2026-09-29T12:00:00+00:00"
    h5.attrs["created_by"] = "tests"
    if tier:
        h5.attrs["data_tier"] = tier


def _station(h5, name, minutes, values_by_variable):
    group = h5.create_group(f"time_series/station_{name}")
    time = group.create_dataset("time", data=np.asarray(minutes, dtype=float))
    time.attrs["time_origin"] = ORIGIN
    time.attrs["time_units"] = "min"
    for variable, values in values_by_variable.items():
        data = group.create_dataset(variable, data=np.asarray(values, dtype=float))
        data.attrs["units"] = UNITS[variable]
        data.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = HEIGHTS[variable]
        data.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
        data.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(fs.SH_TRUST_HIGHEST)


def _files(tmp_path, model_offset=1.0):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"
    minutes = np.arange(0, 181, 10)
    obs_values = {
        "air_temperature": 20 + minutes / 60.0,
        "relative_humidity": 30 + minutes / 60.0,
        "wind_speed": np.full(minutes.size, 3.0),
        "wind_direction": np.full(minutes.size, 270.0),
        "fuel_moisture_content_10h": np.full(minutes.size, 6.0),
    }
    hours = np.arange(4)
    model_values = {
        "air_temperature": 20 + hours + model_offset,
        "relative_humidity": 30 + hours + model_offset,
        "wind_speed": np.full(4, 3.0 + model_offset),
        "wind_direction": np.full(4, 280.0),
    }
    with h5py.File(obs_path, "w") as h5:
        _std(h5, tier="provisional")
        for name in ("A", "B"):
            _station(h5, name, minutes, obs_values)
    with h5py.File(model_path, "w") as h5:
        _std(h5)
        h5.attrs["height_policy"] = json.dumps({"wind_speed": {"log law": 2}})
        for name in ("A", "B"):
            _station(h5, name, hours * 60, model_values)
    return obs_path, model_path


def _spec(**overrides):
    return wx_forecast.WxForecastSpec(
        case_name="Test", cycle=CYCLE, horizon_hours=3, lead_bins=((1, 3),), **overrides
    )


def test_benchmark_ids_are_semantic_and_independent_of_spec_order(tmp_path):
    obs_path, model_path = _files(tmp_path)
    with h5py.File(obs_path) as obs, h5py.File(model_path) as model:
        forward = wx_forecast.build_registry(_spec(cadences=(1, 3)), model, obs)
        backward = wx_forecast.build_registry(
            _spec(cadences=(3, 1), variables=tuple(reversed(_spec().variables))), model, obs
        )

    assert set(forward.benchmark_functions) == set(backward.benchmark_functions)
    assert "WX-AT-MAE-MEAN-TSO-1H-F0103" in forward.benchmark_functions
    assert "WX-WD-CBIAS-MAX-ALL-3H-F0000" in forward.benchmark_functions
    keywords = forward.benchmark_functions["WX-AT-MAE-MEAN-TSO-1H-F0103"].keywords
    assert keywords["lead_window"] == (CYCLE.replace(hour=1), CYCLE.replace(hour=3))
    assert keywords["period"][0] < keywords["lead_window"][0]


def test_analysis_group_is_informational_and_all_source_kpis_have_zero_weight(tmp_path):
    obs_path, model_path = _files(tmp_path)
    with h5py.File(obs_path) as obs, h5py.File(model_path) as model:
        registry = wx_forecast.build_registry(_spec(), model, obs)

    assert registry.groups["Air Temp 1h F01-03"]["weight"] == 1
    assert registry.groups["Air Temp 1h F00 analysis"]["weight"] == 0
    weights = registry.groups["Air Temp 1h F01-03"]["benchmarks"]
    assert weights["WX-AT-MAE-MEAN-TSO-1H-F0103"] == 1
    assert weights["WX-AT-MAE-MEAN-ALL-1H-F0103"] == 0
    assert set(registry.aggregation) == {"ALL", "1H"}


def test_variable_without_model_data_is_excluded_with_its_reason(tmp_path):
    obs_path, model_path = _files(tmp_path)
    with h5py.File(obs_path) as obs, h5py.File(model_path) as model:
        registry = wx_forecast.build_registry(_spec(), model, obs)

    assert registry.excluded == [{"variable": "fuel_moisture_content_10h", "reason": "no model data"}]
    assert not any(name.startswith("FMC") for name in registry.groups)


def test_lead_bins_are_clamped_to_the_forecast_horizon():
    spec = wx_forecast.WxForecastSpec(
        case_name="T",
        cycle=CYCLE,
        horizon_hours=36,
        lead_bins=((1, 48), (40, 48)),
        informational_lead_bins=(),
    )

    assert [lead_bin.label for lead_bin in spec.bins()] == ["F01-36"]


def test_invalid_lead_bin_is_rejected():
    with pytest.raises(ValueError, match="invalid lead bin"):
        wx_forecast.WxForecastSpec(case_name="T", cycle=CYCLE, lead_bins=((5, 2),)).bins()


def test_run_writes_scores_json_and_pdf_and_keeps_the_analysis_out_of_the_total(tmp_path):
    obs_path, model_path = _files(tmp_path)

    result = wx_forecast.run_wx_forecast_benchmark(
        model_path,
        obs_path,
        _spec(),
        output_json=tmp_path / "out" / "rslt.json",
        score_card_report=tmp_path / "out" / "card.pdf",
    )

    card = result["score_card"]
    scored_groups = [name for name, group in card["Scheme"].items() if group["weight"] == 1]
    expected_total = np.mean([card[f"Score {name}"] for name in scored_groups])
    assert card["Score Total"] == pytest.approx(expected_total)
    assert "Score Air Temp 1h F00 analysis" in card
    assert result["benchmarks"]["WX-AT-MAE-MEAN-TSO-1H-F0103"][
        "Air temp MAE mean 1h F01-03 TSO"
    ] == pytest.approx(1.0)
    assert result["excluded_kpis"][0]["variable"] == "fuel_moisture_content_10h"
    assert result["data_tier"] == "provisional"
    assert result["evaluated_model_name"] == "model"
    assert result["height_policy"] == {"wind_speed": {"log law": 2}}
    assert (tmp_path / "out" / "card.pdf").is_file()
    written = json.loads((tmp_path / "out" / "rslt.json").read_text())
    assert written["score_card"]["aggregation_scheme_name"] == "ALL"


def test_existing_result_is_not_overwritten_by_default(tmp_path):
    obs_path, model_path = _files(tmp_path)
    output_json = tmp_path / "rslt.json"
    output_json.write_text("{}")

    with pytest.raises(FileExistsError):
        wx_forecast.run_wx_forecast_benchmark(
            model_path, obs_path, _spec(), output_json=output_json, score_card_report=tmp_path / "c.pdf"
        )


def test_unknown_target_lists_the_available_ones(tmp_path):
    obs_path, model_path = _files(tmp_path)

    with pytest.raises(ValueError, match="available: ALL, 1H"):
        wx_forecast.run_wx_forecast_benchmark(
            model_path,
            obs_path,
            _spec(),
            target="W1",
            output_json=tmp_path / "r.json",
            score_card_report=tmp_path / "c.pdf",
        )
