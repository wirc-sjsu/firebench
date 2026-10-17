import hashlib
import json
import shutil
from datetime import timedelta

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from firebench import adapter_common
from firebench import standardize as fs
from firebench.benchmarks import fire_case
from firebench.benchmarks import fire_case_definition as definition_module
from firebench.benchmarks import fire_case_template as template_module
from firebench.benchmarks import wx_common as wxc
from firebench.cli import main
from test_fire_case import (
    CBI_MODEL,
    DAMAGE_OBS,
    MODEL_SQUARES,
    STATION_HOURS,
    STATION_START,
    W2_PERIMETERS,
    _definition,
    _kml,
    _write_case_file,
)

DAMAGE = [*DAMAGE_OBS, "Inaccessible"]
DAMAGE_MODEL = [
    "Destroyed (>50%)",
    "No Damage",
    "No Damage",
    "No Damage",
    "Destroyed (>50%)",
    "Inaccessible",
]


def _station(h5, name, variable, values, confidence, height, start=STATION_START):
    station = h5.create_group(f"time_series/{name}")
    station.attrs["position_lat"] = 38.55
    station.attrs["position_lon"] = -120.45
    station.attrs["license"] = "/DATA_LICENSES/Synoptic.txt"
    time = station.create_dataset("time", data=np.arange(len(values), dtype=float))
    time.attrs["time_origin"] = start.isoformat()
    time.attrs["time_units"] = "hour"
    dataset = station.create_dataset(variable, data=values)
    dataset.attrs["units"] = "%" if variable == "relative_humidity" else "degK"
    dataset.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
    dataset.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
    dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = confidence


@pytest.fixture(name="obs")
def fixture_obs(tmp_path):
    """The case file of `test_fire_case`, with more stations, a building not surveyed, and other data.

    station_A observes air temperature (trusted height, TSO), station_B relative humidity (height not
    trusted: all sources only), and station_C air temperature only after the period (never selected).
    """
    path = _write_case_file(tmp_path / "obs", damage=DAMAGE)
    hours = np.arange(STATION_HOURS + 1)
    with h5py.File(path, "a") as h5:
        h5["time_series/station_A"].attrs["license"] = "/DATA_LICENSES/Synoptic.txt"
        buildings = h5[definition_module.BUILDING_DAMAGE_PATH].parent
        buildings.attrs["license"] = "/DATA_LICENSES/calfire.txt"
        for name, values in (
            ("position_lat", np.linspace(38.5, 38.6, 6)),
            ("position_lon", np.full(6, -120.4)),
        ):
            buildings.create_dataset(name, data=values).attrs["units"] = "degree"
        buildings.create_dataset("dins_matched", data=np.ones(6, dtype=bool))
        _station(h5, "station_B", "relative_humidity", 30 + np.cos(hours / 4), confidence=1, height=6.1)
        _station(
            h5,
            "station_C",
            "air_temperature",
            290 + np.sin(hours),
            confidence=2,
            height=2,
            start=STATION_START + timedelta(days=60),
        )
        for perimeter in W2_PERIMETERS:
            h5[perimeter].attrs["burnt_area"] = 1234.5
            h5[perimeter].attrs["license"] = "/DATA_LICENSES/NIFC.txt"
        h5.create_dataset("points/fire_detections/frp", data=np.ones(3)).attrs["units"] = "MW"
    return path


@pytest.fixture(name="template")
def fixture_template(obs, tmp_path):
    return template_module.write_model_output_template(obs, _definition(), tmp_path / "kit" / "template.h5")


def _objects(path) -> dict[str, h5py.HLObject]:
    found = {}

    def visit(name, item):
        found[f"/{name}"] = type(item)

    with h5py.File(path, "r") as h5:
        h5.visititems(visit)
    return found


# ---------------------------
# Template
# ---------------------------
def test_the_template_holds_the_groups_the_case_scores_and_no_other(template):
    objects = _objects(template)

    assert sorted(path for path, kind in objects.items() if kind is h5py.Dataset) == sorted(
        [
            "/benchmark_case/definition",
            "/points/building_damaged/building_damage",
            "/points/building_damaged/position_lat",
            "/points/building_damaged/position_lon",
            "/spatial_2d/ravg_cbi/position_lat",
            "/spatial_2d/ravg_cbi/position_lon",
            "/spatial_2d/ravg_cbi/ravg_composite_burn_index_severity",
            "/time_series/station_A/air_temperature",
            "/time_series/station_A/time",
            "/time_series/station_B/relative_humidity",
            "/time_series/station_B/time",
        ]
        + list(W2_PERIMETERS)
    )
    with h5py.File(template, "r") as h5:
        assert h5.attrs[definition_module.TEMPLATE_ATTRIBUTE] == "model-output"
        assert h5.attrs["case_definition_sha256"] == definition_module.definition_sha256(_definition())
        assert h5.attrs["created_by"].startswith("FireBench ")
    assert definition_module.read_case_definition(template) == _definition()


def test_the_template_holds_no_observed_value(template):
    with h5py.File(template, "r") as h5:
        cbi = h5[definition_module.CBI_PATH]
        assert np.all(cbi[()] == cbi.attrs["_FillValue"])
        assert cbi.shape == (2, 3)
        damage = [value.decode() for value in h5[definition_module.BUILDING_DAMAGE_PATH][()]]
        assert damage == ["", "", "", "", "", "Inaccessible"]
        assert np.all(np.isnan(h5["time_series/station_A/air_temperature"][()]))
        assert np.all(np.isnan(h5["time_series/station_B/relative_humidity"][()]))
        for perimeter in W2_PERIMETERS:
            attrs = h5[perimeter].attrs
            assert not {"rel_path", "sha256", "file_size_bytes", "burnt_area"} & set(attrs)
            assert attrs["time"] == perimeter.rsplit("_", 1)[-1]


def test_the_template_keeps_times_positions_heights_and_licences(obs, template):
    with h5py.File(obs, "r") as source, h5py.File(template, "r") as h5:
        for path in ("time_series/station_A/time", "spatial_2d/ravg_cbi/position_lat"):
            assert np.array_equal(h5[path][()], source[path][()])
            assert dict(h5[path].attrs) == dict(source[path].attrs)
        variable = h5["time_series/station_B/relative_humidity"]
        assert variable.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == pytest.approx(6.1)
        assert variable.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] == 1
        assert h5["time_series/station_A"].attrs["license"] == "/DATA_LICENSES/Synoptic.txt"
        assert h5["time_series/station_B"].attrs["position_lat"] == pytest.approx(38.55)
        assert h5[W2_PERIMETERS[0]].attrs["license"] == "/DATA_LICENSES/NIFC.txt"
        assert h5["spatial_2d/ravg_cbi"].attrs["crs"] == "EPSG:4326"
        height = adapter_common.trusted_observation_sensor_height(h5, "station_A", "air_temperature")
        assert height.magnitude == pytest.approx(2)


def test_the_template_passes_the_standard_check(template):
    with h5py.File(template, "r") as h5:
        fs.validate_h5_std(h5)


def test_a_template_is_never_an_observation_file(template, tmp_path):
    with pytest.raises(definition_module.CaseDefinitionError, match="model-output template"):
        fire_case.load_case(_definition(), template)
    with pytest.raises(definition_module.CaseDefinitionError, match="model-output template"):
        fire_case.load_case(None, template)
    assert definition_module.check_case(_definition(), template) == [definition_module.TEMPLATE_REFUSAL]
    with pytest.raises(definition_module.CaseDefinitionError, match="model-output template"):
        fire_case.FireCase(_definition()).run_benchmark(
            template,
            obs_data=template,
            output_json=tmp_path / "r.json",
            score_card_report=tmp_path / "c.pdf",
        )


def test_an_existing_template_is_replaced_only_when_asked(obs, template):
    with pytest.raises(FileExistsError):
        template_module.write_model_output_template(obs, _definition(), template)

    template_module.write_model_output_template(obs, _definition(), template, overwrite=True)


# ---------------------------
# Requirement list
# ---------------------------
def _requirements(obs) -> dict:
    return template_module.case_requirements(_definition(), obs)


def test_the_requirement_list_names_each_requirement_of_the_case(obs):
    document = _requirements(obs)
    case = fire_case.load_case(_definition(), obs)
    by_name = {item["name"]: item for item in document["requirements"]}

    assert document["schema"] == "fb-requirements-v1"
    assert document["case"]["definition_sha256"] == case.sha256
    assert document["periods"] == _definition()["periods"]
    assert list(by_name) == list(case.REQUIREMENTS)
    for name, requirement in case.REQUIREMENTS.items():
        assert by_name[name]["kpis"] == requirement["benchmarks"]
    assert by_name["R_FP_P02"]["family"] == "fire_perimeters"
    assert by_name["R_FP_P02"]["period"] == "P02"
    assert by_name["R_FP_P02"]["datasets"] == {path: ["rel_path", "time"] for path in W2_PERIMETERS}
    assert by_name["R_FP_P02"]["files"] == template_module.FILES_TEXT
    assert by_name["R_BD"]["kpi_groups"] == ["Building Damage"]
    assert by_name["R_SV"]["datasets"][definition_module.CBI_PATH] == ["units", "_FillValue"]
    assert by_name["R_WX_air_temperature"]["kpi_groups"] == ["Air Temp P02"]
    assert by_name["R_WX_air_temperature"]["at_observation_times"] is True
    assert by_name["R_WX_air_temperature"]["sensor_height"] == template_module.SENSOR_HEIGHT_TEXT
    assert (
        by_name["R_WX_fuel_moisture_content_10h"]["sensor_height"]
        == template_module.SENSOR_HEIGHT_EXEMPT_TEXT
    )
    assert json.loads(json.dumps(document)) == document


def test_the_requirement_list_gives_the_stations_of_each_period_and_set(obs):
    by_name = {item["name"]: item for item in _requirements(obs)["requirements"]}

    temperature = {item["station_set"]: item for item in by_name["R_WX_air_temperature"]["stations"]}
    humidity = {item["station_set"]: item for item in by_name["R_WX_relative_humidity"]["stations"]}
    assert temperature["TSO"]["period"] == "P02"
    assert temperature["TSO"]["included"] == ["station_A"]
    assert temperature["ALL"]["excluded"] == [
        {"station": "station_C", "reason": "no samples in selected period"}
    ]
    assert humidity["ALL"]["included"] == ["station_B"]
    assert humidity["TSO"]["included"] == []
    assert humidity["TSO"]["excluded"][0]["station"] == "station_B"


def test_the_summary_counts_what_the_case_needs(obs):
    summary = _requirements(obs)["summary"]
    weather = {item["variable"]: item for item in summary["weather"]}

    assert summary["families"] == [
        "fire_perimeters",
        "building_damage",
        "burn_severity_cbi",
        "weather_stations",
    ]
    assert summary["periods"] == 1
    assert summary["perimeters"] == len(W2_PERIMETERS)
    assert weather["air_temperature"] == {
        "variable": "air_temperature",
        "label": "Air temp",
        "stations": 1,
        "tso_stations": 1,
        "sensor_heights_m": [2.0],
    }
    assert weather["relative_humidity"]["tso_stations"] == 0
    assert weather["relative_humidity"]["sensor_heights_m"] == [6.1]
    assert weather["wind_speed"]["stations"] == 0


def test_the_stations_listed_are_those_firebench_selects(obs):
    case = fire_case.load_case(_definition(), obs)
    with h5py.File(obs, "r") as h5:
        for item in _requirements(obs)["requirements"]:
            if item["family"] != "weather_stations":
                continue
            listed = {station for entry in item["stations"] for station in entry["included"]}
            selected = wxc.weather_requirement_selected_stations(
                h5, case.BENCHMARK_FUNCTIONS, item["kpis"], {}
            )
            assert listed == selected


# ---------------------------
# Parity: a model output written on the template's layout
# ---------------------------
def _model_from_template(template, directory):
    """What an adapter writes: the template's layout, with model values and the perimeters' KML files."""
    directory.mkdir()
    path = directory / "model.h5"
    shutil.copy(template, path)
    with h5py.File(path, "a") as h5:
        del h5.attrs[definition_module.TEMPLATE_ATTRIBUTE]
        del h5["benchmark_case"]
        for index, perimeter in enumerate(W2_PERIMETERS):
            kml = directory / f"model_{index}.kml"
            kml.write_text(_kml(MODEL_SQUARES[index]), encoding="utf-8")
            h5[perimeter].attrs["rel_path"] = kml.name
            h5[perimeter].attrs["file_size_bytes"] = kml.stat().st_size
            h5[perimeter].attrs["sha256"] = hashlib.sha256(kml.read_bytes()).hexdigest()
        h5[definition_module.CBI_PATH][...] = CBI_MODEL
        h5[definition_module.BUILDING_DAMAGE_PATH][...] = np.array(DAMAGE_MODEL, dtype="S")
        for name in ("station_A/air_temperature", "station_B/relative_humidity"):
            dataset = h5[f"time_series/{name}"]
            dataset[...] = 1.5 + np.nan_to_num(dataset[()], nan=290.0)
    return path


def _met(case, model, obs) -> dict[str, bool]:
    """Whether each requirement of the case gives a result on ``model``, as ``FireCase`` runs it."""
    met = {}
    with h5py.File(model, "r") as model_h5, h5py.File(obs, "r") as obs_h5:
        for name, requirement in case.REQUIREMENTS.items():
            ctx = {"ignored_benchmarks": set()}
            output = requirement["main"](
                model_h5, obs_h5, requirement["benchmarks"], requirement["required_datasets"], ctx
            )
            met[name] = bool(output)
    return met


def _expected(document) -> dict[str, bool]:
    """A requirement can be scored unless it is a weather variable with no station selected."""
    return {
        item["name"]: item["family"] != "weather_stations"
        or any(entry["included"] for entry in item["stations"])
        for item in document["requirements"]
    }


def test_a_model_on_the_template_meets_every_requirement_listed(obs, template, tmp_path):
    case = fire_case.load_case(_definition(), obs)
    model = _model_from_template(template, tmp_path / "model")

    assert _met(case, model, obs) == _expected(_requirements(obs))


def test_a_station_left_out_fails_the_requirements_that_name_it(obs, template, tmp_path):
    case = fire_case.load_case(_definition(), obs)
    model = _model_from_template(template, tmp_path / "model")
    with h5py.File(model, "a") as h5:
        del h5["time_series/station_B/relative_humidity"]
    document = _requirements(obs)
    naming = {
        item["name"]
        for item in document["requirements"]
        if any("station_B" in entry["included"] for entry in item.get("stations", []))
    }

    met = _met(case, model, obs)

    assert naming == {"R_WX_relative_humidity"}
    assert met == {name: value and name not in naming for name, value in _expected(document).items()}


# ---------------------------
# Command line
# ---------------------------
def test_cli_writes_the_template_and_the_requirements_of_the_kept_definition(obs, tmp_path):
    definition_module.write_case_definition(obs, _definition())
    template, requirements = tmp_path / "t.h5", tmp_path / "r.json"
    runner = CliRunner()

    written = runner.invoke(main, ["case", "template", "-", str(obs), "-o", str(template)])
    again = runner.invoke(main, ["case", "template", "-", str(obs), "-o", str(template)])
    listed = runner.invoke(main, ["case", "requirements", "-", str(obs), "-o", str(requirements)])

    assert written.exit_code == 0, written.output
    assert definition_module.is_template(template)
    assert again.exit_code != 0
    assert "--overwrite" in again.output
    assert listed.exit_code == 0, listed.output
    assert json.loads(requirements.read_text())["schema"] == "fb-requirements-v1"


def test_cli_reads_a_definition_file(obs, tmp_path):
    path = tmp_path / "definition.json"
    path.write_text(json.dumps(_definition()))

    output = tmp_path / "requirements.json"

    result = CliRunner().invoke(main, ["case", "requirements", str(path), str(obs), "-o", str(output)])

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["case"]["name"] == "Test fire"
