import copy
import hashlib
from datetime import datetime, timezone
from importlib.resources import files

import pytest

from firebench.benchmarks import wx_cadence, wx_forecast, wx_parameters
from firebench.workflows import wx_setup

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def _shipped() -> bytes:
    return files("firebench").joinpath(wx_parameters.PARAMETER_FILE).read_bytes()


def _document() -> dict:
    return tomllib.loads(_shipped().decode("utf-8"))


def _changed(path: str, value) -> dict:
    """The shipped document with one value replaced; ``path`` is dotted."""
    document = copy.deepcopy(_document())
    *tables, key = path.split(".")
    table = document
    for name in tables:
        table = table[name]
    table[key] = value
    return document


def test_shipped_file_is_valid_and_identified_by_its_checksum():
    parameters = wx_parameters.load_parameters()

    assert parameters.sha256 == hashlib.sha256(_shipped()).hexdigest()
    assert wx_parameters.parse_parameters(_document(), parameters.sha256) == parameters
    assert wx_forecast.PARAMETERS is parameters


def test_the_benchmark_scores_with_the_values_of_the_file():
    document = _document()
    defaults = document["setup_defaults"]
    spec = wx_forecast.WxForecastSpec(case_name="Test", cycle=datetime(2021, 8, 20, tzinfo=timezone.utc))

    # defaults of a spec and of a setup file
    assert spec.horizon_hours == defaults["horizon_hours"]
    assert [list(bounds) for bounds in spec.lead_bins] == defaults["lead_bins"]
    assert [list(bounds) for bounds in spec.informational_lead_bins] == defaults["informational_lead_bins"]
    assert list(spec.cadences) == defaults["cadences"]
    assert spec.obs_tolerance_s == defaults["obs_tolerance_min"] * 60
    assert spec.model_tolerance_s == defaults["model_tolerance_s"]
    assert spec.min_coverage == defaults["min_coverage"]
    options = wx_setup.BenchmarkOptions()
    assert options.obs_tolerance_min == defaults["obs_tolerance_min"]
    assert [list(bounds) for bounds in options.lead_bins] == defaults["lead_bins"]
    assert wx_setup.ModelOptions().horizon_hours == defaults["horizon_hours"]

    # missing model data, weights, normalizations, thresholds
    assert wx_cadence.PENALTY_VALUE == document["missing_model_data"]["penalty_value"]
    assert (
        wx_cadence.CIRCULAR_PENALTY_OFFSET_DEG
        == document["missing_model_data"]["circular_penalty_offset_deg"]
    )
    assert {code: weight for _, code, _, weight in wx_forecast.STATION_SETS} == document[
        "station_set_weights"
    ]
    for quantities, table in (
        (wx_forecast.WX_VARIABLE_SPECS, "variables"),
        ([item for item in wx_forecast.WX_DIAGNOSTIC_SPECS if "norm_m" in item], "indices"),
    ):
        assert {
            item["variable"]: {"unit": item["common_unit"], "norm_m": item["norm_m"]} for item in quantities
        } == document[table]
    events = document["events"]
    assert wx_forecast.LOW_RELATIVE_HUMIDITY_PERCENT == events["low_relative_humidity_max_percent"]
    assert wx_forecast.STRONG_WIND_SPEED_MS == events["strong_wind_speed_min_ms"]


def test_a_weight_keeps_the_type_the_file_gives_it():
    # a result file prints a weight as written: 1, not 1.0
    weights = wx_parameters.load_parameters().station_set_weights
    assert all(
        type(weights[code]) is type(value) for code, value in _document()["station_set_weights"].items()
    )


@pytest.mark.parametrize(
    "remove",
    [
        "events",
        "setup_defaults.min_coverage",
        "missing_model_data.penalty_value",
        "variables.wind_speed.norm_m",
    ],
)
def test_a_missing_key_is_refused(remove):
    document = _document()
    *tables, key = remove.split(".")
    table = document
    for name in tables:
        table = table[name]
    del table[key]

    with pytest.raises(wx_parameters.WxParameterError, match=f"missing {key}"):
        wx_parameters.parse_parameters(document)


@pytest.mark.parametrize(
    "path", ["thresholds", "setup_defaults.min_covrage", "events.wind", "indices.vapor_pressure_deficit.m"]
)
def test_an_unknown_key_is_refused(path):
    key = path.rsplit(".", 1)[-1]
    with pytest.raises(wx_parameters.WxParameterError, match=f"unknown {key}"):
        wx_parameters.parse_parameters(_changed(path, 1))


@pytest.mark.parametrize(
    "path, value",
    [
        ("variables.air_temperature.norm_m", 0),
        ("variables.air_temperature.norm_m", "5"),
        ("variables.air_temperature.unit", ""),
        ("setup_defaults.min_coverage", 1.5),
        ("setup_defaults.obs_tolerance_min", -1),
        ("setup_defaults.lead_bins", [[5, 1]]),
        ("setup_defaults.lead_bins", [[1, 48, 2]]),
        ("setup_defaults.cadences", []),
        ("setup_defaults.horizon_hours", 0),
        ("station_set_weights.TSO", -1),
        ("group_weights.event_threshold", True),
        ("events.low_relative_humidity_max_percent", 120),
        ("events.strong_wind_speed_min_ms", -0.1),
        ("missing_model_data.circular_penalty_offset_deg", 400),
    ],
)
def test_a_value_out_of_range_is_refused_and_named(path, value):
    with pytest.raises(wx_parameters.WxParameterError, match=path.replace(".", r"\.")):
        wx_parameters.parse_parameters(_changed(path, value))


def test_a_table_must_name_exactly_what_the_benchmark_defines():
    wx_parameters.check_names("variables", ["b", "a"], ("a", "b"))
    with pytest.raises(wx_parameters.WxParameterError, match=r"\[variables\] must have exactly.*a, b"):
        wx_parameters.check_names("variables", ["a", "c"], ("a", "b"))
