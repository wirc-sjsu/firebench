import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import geopandas as gpd
import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from firebench.benchmarks import c001_caldor
from firebench.benchmarks import fire_case
from firebench.benchmarks import fire_case_definition as definition_module
from firebench.benchmarks import fire_case_parameters as parameters_module
from firebench.cli import main
from firebench.signing import hdf5_subject_digest_sha256

W2_START, W2_END = c001_caldor.cfg.CURATED_PERIODS["W2"]
W2_PERIMETERS = c001_caldor.cfg.CURATED_PERIMETERS["W2"]
STATION_START = datetime(2021, 8, 19, tzinfo=timezone.utc)
STATION_HOURS = 96
OBS_SQUARES = [
    [(-120.5, 38.5), (-120.4, 38.5), (-120.4, 38.6), (-120.5, 38.6), (-120.5, 38.5)],
    [(-120.5, 38.5), (-120.35, 38.5), (-120.35, 38.62), (-120.5, 38.62), (-120.5, 38.5)],
]
MODEL_SQUARES = [
    [(-120.48, 38.5), (-120.38, 38.5), (-120.38, 38.6), (-120.48, 38.6), (-120.48, 38.5)],
    [(-120.5, 38.48), (-120.3, 38.48), (-120.3, 38.6), (-120.5, 38.6), (-120.5, 38.48)],
]
DAMAGE_OBS = ["No Damage", "Destroyed (>50%)", "Minor (10-25%)", "Major (26-50%)", "Destroyed (>50%)"]
DAMAGE_MODEL = ["Destroyed (>50%)", "Destroyed (>50%)", "No Damage", "No Damage", "Destroyed (>50%)"]
CBI_OBS = np.array([[0, 1, 4], [4, 2, 3]], dtype=np.uint8)
CBI_MODEL = np.array([[4, 4, 4], [1, 0, 3]], dtype=np.uint8)


def _kml(ring) -> str:
    coordinates = " ".join(f"{lon!r},{lat!r},0" for lon, lat in ring)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<Placemark><name>perimeter</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        "</Document></kml>"
    )


def _write_case_file(  # pylint: disable=too-many-arguments
    directory,
    squares=OBS_SQUARES,
    damage=DAMAGE_OBS,
    cbi=CBI_OBS,
    temperature_offset=0.0,
    observational=True,
    perimeters=True,
    stations=True,
):
    """A standard file with Caldor's W2 perimeters, building damage, a CBI grid, and one station."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "case.h5"
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-10-16T12:00:00+00:00"
        h5.attrs["created_by"] = "FireBench tests"
        h5.attrs["description"] = "Test fire"
        h5.attrs["version"] = "test"
        if perimeters:
            for index, perimeter in enumerate(W2_PERIMETERS):
                kml_path = directory / f"perimeter_{index}.kml"
                kml_path.write_text(_kml(squares[index]), encoding="utf-8")
                dataset = h5.create_dataset(perimeter, data=0)
                dataset.attrs["rel_path"] = kml_path.name
                dataset.attrs["file_size_bytes"] = kml_path.stat().st_size
                dataset.attrs["sha256"] = hashlib.sha256(kml_path.read_bytes()).hexdigest()
                dataset.attrs["time"] = perimeter.rsplit("_", 1)[-1]
        if damage is not None:
            dataset = h5.create_dataset(
                definition_module.BUILDING_DAMAGE_PATH, data=np.array(damage, dtype="S")
            )
            dataset.attrs["units"] = "dimensionless"
        if cbi is not None:
            group = h5.create_group("spatial_2d/ravg_cbi")
            group.attrs["crs"] = "EPSG:4326"
            dataset = group.create_dataset("ravg_composite_burn_index_severity", data=cbi)
            dataset.attrs["units"] = "dimensionless"
            dataset.attrs["_FillValue"] = 0
            lat, lon = np.meshgrid([38.6, 38.5], [-120.5, -120.4, -120.3], indexing="ij")
            group.create_dataset("position_lat", data=lat).attrs["units"] = "degree"
            group.create_dataset("position_lon", data=lon).attrs["units"] = "degree"
        if stations:
            station = h5.create_group("time_series/station_A")
            time = station.create_dataset("time", data=np.arange(STATION_HOURS + 1, dtype=float))
            time.attrs["time_origin"] = STATION_START.isoformat()
            time.attrs["time_units"] = "hour"
            hours = np.arange(STATION_HOURS + 1)
            values = 290 + np.sin(hours / 5) + temperature_offset * (0.5 + np.cos(hours / 3))
            variable = station.create_dataset("air_temperature", data=values)
            variable.attrs["units"] = "degK"
            variable.attrs[c001_caldor.fs.SENSOR_HEIGHT_ATTRIBUTE] = 2
            variable.attrs[c001_caldor.fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
            if observational:
                variable.attrs[c001_caldor.fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = 2
    return path


@pytest.fixture(name="files")
def fixture_files(tmp_path):
    obs = _write_case_file(tmp_path / "obs")
    model = _write_case_file(
        tmp_path / "model",
        squares=MODEL_SQUARES,
        damage=DAMAGE_MODEL,
        cbi=CBI_MODEL,
        temperature_offset=1.5,
        observational=False,
    )
    return obs, model


def _iso(value: datetime) -> str:
    return definition_module.iso_utc(value)


def _definition() -> dict:
    """A definition of Caldor's W2 period with the four families."""
    return {
        "schema": "fb-case-v1",
        "name": "Test fire",
        "parameters": {"set": "fire_case", "version": parameters_module.load_parameters().version},
        "projection": "EPSG:5070",
        "periods": [{"name": "P02", "start": _iso(W2_START), "end": _iso(W2_END), "origin": "custom"}],
        "families": [
            {
                "family": "fire_perimeters",
                "periods": [{"period": "P02", "perimeters": list(W2_PERIMETERS)}],
            },
            {"family": "building_damage", "dataset": definition_module.BUILDING_DAMAGE_PATH},
            {"family": "burn_severity_cbi", "dataset": definition_module.CBI_PATH},
            {"family": "weather_stations", "periods": ["P02"], "station_sets": ["TSO", "ALL"]},
        ],
    }


def _values(result: dict) -> list:
    return [value for key, value in result.items()]


# ---------------------------
# Parameters
# ---------------------------
def test_parameter_file_holds_fb001_values():
    parameters = parameters_module.load_parameters()

    assert parameters.reference() == {"set": "fire_case", "version": parameters.version}
    assert parameters.projections == ("EPSG:5070",)
    assert parameters.area_relative_error_at_score_50 == c001_caldor.AREA_RELATIVE_ERROR_AT_SCORE_50
    assert parameters.cbi_high_classes == (4,)
    assert [(spec.variable, spec.norm_m) for spec in parameters.variables] == [
        (spec["variable"], spec["norm_m"]) for spec in c001_caldor.cfg.WX_VARIABLE_SPECS
    ]
    assert len(parameters.sha256) == 64


def test_parameter_file_refuses_an_unknown_key():
    content = parameters_module.files("firebench").joinpath(parameters_module.PARAMETER_FILE).read_text()
    document = parameters_module.tomllib.loads(content)
    document["fire_perimeters"]["extra"] = 1

    with pytest.raises(parameters_module.FireCaseParameterError, match="unknown extra"):
        parameters_module.parse_parameters(document)


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ({"set": "other", "version": "2026.1"}, "Unknown parameter set"),
        ({"set": "fire_case", "version": "1999.1"}, "is not this FireBench"),
        ({"set": "fire_case"}, "must name"),
    ],
)
def test_a_definition_names_this_firebench_parameter_set(reference, message):
    with pytest.raises(parameters_module.FireCaseParameterError, match=message):
        parameters_module.parameters_for(reference)


# ---------------------------
# The document
# ---------------------------
def test_canonical_json_names_a_definition_whatever_the_key_order():
    definition = _definition()
    reordered = json.loads(json.dumps(definition, sort_keys=False))
    reordered = dict(reversed(list(reordered.items())))

    assert definition_module.canonical_json(definition) == definition_module.canonical_json(reordered)
    assert (
        definition_module.definition_sha256(definition)
        == hashlib.sha256(definition_module.canonical_json(definition)).hexdigest()
    )
    assert b" " not in definition_module.canonical_json({"a": [1, 2]})


def test_definition_round_trips_through_the_file_with_a_stable_digest(files):
    obs, _ = files
    definition = _definition()

    digest = definition_module.write_case_definition(obs, definition)

    assert digest == definition_module.definition_sha256(definition)
    assert definition_module.read_case_definition(obs) == definition
    with h5py.File(obs, "r") as h5:
        dataset = h5[definition_module.DEFINITION_PATH]
        assert dataset.dtype.kind == "S"
        assert dataset.attrs["schema"] == b"fb-case-v1"
    assert hdf5_subject_digest_sha256(str(obs)) == hdf5_subject_digest_sha256(str(obs))
    # Writing it again replaces it.
    definition_module.write_case_definition(obs, {**definition, "name": "Renamed"})
    assert definition_module.read_case_definition(obs)["name"] == "Renamed"


def test_a_definition_changed_in_the_file_is_refused(files):
    obs, _ = files
    definition_module.write_case_definition(obs, _definition())
    with h5py.File(obs, "a") as h5:
        h5[definition_module.DEFINITION_PATH].attrs["sha256"] = np.bytes_(b"0" * 64)

    with pytest.raises(definition_module.CaseDefinitionError, match="does not match"):
        definition_module.read_case_definition(obs)


def test_a_file_without_a_definition_reads_none(files):
    obs, _ = files

    assert definition_module.read_case_definition(obs) is None


# ---------------------------
# Proposal
# ---------------------------
def test_propose_case_offers_every_family_the_file_allows(files):
    obs, _ = files

    proposal = definition_module.propose_case(obs)
    definition = proposal["definition"]

    assert definition["name"] == "Test fire"
    assert definition["projection"] == "EPSG:5070"
    names = [period["name"] for period in definition["periods"]]
    assert names == ["P01", "P02", "H001", "H002", "H003", "H004"]
    assert definition["periods"][0]["start"] == _iso(STATION_START)
    assert definition["periods"][1]["origin"] == "perimeters"
    assert [period["start"] for period in definition["periods"][2:]] == [
        "2021-08-20T06:00:00Z",
        "2021-08-20T12:00:00Z",
        "2021-08-20T18:00:00Z",
        "2021-08-21T00:00:00Z",
    ]
    assert [item["family"] for item in definition["families"]] == [
        "fire_perimeters",
        "building_damage",
        "burn_severity_cbi",
        "weather_stations",
    ]
    perimeters = definition_module.family(definition, "fire_perimeters")["periods"]
    # P02 starts at the first perimeter, which the model starts from: it holds one perimeter only.
    assert [item["period"] for item in perimeters] == ["P01", "H001", "H002", "H003", "H004"]
    assert perimeters[1]["perimeters"] == list(W2_PERIMETERS)
    assert proposal["left_out"] == []
    assert definition_module.check_case(definition, obs) == []


def test_propose_case_uses_the_window_given(files):
    obs, _ = files
    start = datetime(2021, 8, 19, 12, tzinfo=timezone.utc)
    end = datetime(2021, 8, 22, 12, tzinfo=timezone.utc)

    definition = definition_module.propose_case(obs, window=(start, end), name="Named")["definition"]

    assert definition["name"] == "Named"
    assert definition["periods"][0] == {
        "name": "P01",
        "start": _iso(start),
        "end": _iso(end),
        "origin": "window",
    }
    assert all(_iso(start) <= period["start"] for period in definition["periods"])


def test_propose_case_gives_the_reason_of_each_family_left_out(tmp_path):
    path = _write_case_file(tmp_path / "bare", damage=None, cbi=None, perimeters=False)
    with h5py.File(path, "a") as h5:
        h5.create_group("spatial_2d/ravg_cc")

    proposal = definition_module.propose_case(path)

    assert [item["family"] for item in proposal["definition"]["families"]] == ["weather_stations"]
    reasons = {item["family"]: item["reason"] for item in proposal["left_out"]}
    assert reasons["building_damage"] == "no building damage group"
    assert reasons["burn_severity_cbi"] == "no RAVG CBI grid"
    assert "perimeters" in reasons["fire_perimeters"]
    assert reasons["canopy_cover_loss"] == definition_module.CANOPY_COVER_REASON


def test_propose_case_needs_some_time_in_the_file(tmp_path):
    path = _write_case_file(tmp_path / "empty", perimeters=False, stations=False)

    with pytest.raises(definition_module.CaseDefinitionError, match="no perimeter or station"):
        definition_module.propose_case(path)


# ---------------------------
# Check
# ---------------------------
def _broken(change) -> dict:
    definition = copy.deepcopy(_definition())
    change(definition)
    return definition


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(schema="fb-case-v0"), "Unknown schema"),
        (lambda d: d.update(extra=1), "unknown extra"),
        (lambda d: d.update(parameters={"set": "x", "version": "1"}), "Unknown parameter set"),
        (lambda d: d.update(projection="EPSG:3310"), "projection"),
        (lambda d: d["families"].append({"family": "canopy_cover_loss"}), "Unknown family"),
        (lambda d: d["families"][1].update(dataset="/points/none"), "Building damage"),
        (lambda d: d["families"][2].update(dataset="/spatial_2d/none/cbi"), "Burn severity"),
        (lambda d: d["periods"][0].update(end=d["periods"][0]["start"]), "is empty"),
        (lambda d: d["periods"][0].update(end="2021-09-30T00:00:00Z"), "not inside the data"),
        (lambda d: d["periods"][0].update(name="W2"), "not a period name"),
        (lambda d: d["families"][0]["periods"][0]["perimeters"].pop(), "a period needs at least 2"),
        (
            lambda d: d["families"][0]["periods"][0]["perimeters"].append("/polygons/none"),
            "not a perimeter",
        ),
        (lambda d: d["families"][3].update(periods=["P09"]), "unknown period"),
        (lambda d: d["families"][3].update(station_sets=["TSO", "TSO"]), "station_sets"),
        (lambda d: d.update(families=[]), "no family"),
    ],
)
def test_check_case_names_each_problem(files, change, message):
    obs, _ = files

    problems = definition_module.check_case(_broken(change), obs)

    assert problems
    assert any(message in problem for problem in problems), problems


def test_check_case_passes_a_good_definition(files):
    obs, _ = files

    assert definition_module.check_case(_definition(), obs) == []


def test_load_case_refuses_a_definition_with_problems(files):
    obs, _ = files

    with pytest.raises(definition_module.CaseDefinitionError, match="not inside the data"):
        fire_case.load_case(_broken(lambda d: d["periods"][0].update(end="2021-09-30T00:00:00Z")), obs)


def test_load_case_reads_the_definition_kept_in_the_file(files):
    obs, _ = files
    definition_module.write_case_definition(obs, _definition())

    case = fire_case.load_case(None, obs)

    assert case.definition == _definition()
    assert case.sha256 == definition_module.definition_sha256(_definition())


# ---------------------------
# Registries and targets
# ---------------------------
def test_kpi_ids_follow_the_order_of_the_definition(files):
    obs, _ = files
    case = fire_case.load_case(_definition(), obs)

    ids = list(case.BENCHMARK_FUNCTIONS)

    assert ids[:8] == [f"G-FP{index:02d}" for index in range(1, 9)]
    assert ids[8:14] == [f"G-BD{index:02d}" for index in range(1, 7)]
    assert ids[14:20] == [f"G-SV{index:02d}" for index in range(1, 7)]
    assert ids[20] == "G-WX001"
    assert list(fire_case.load_case(_definition(), obs).BENCHMARK_FUNCTIONS) == ids
    assert list(case.GROUPS)[:4] == [
        "Fire Perimeters P02",
        "Building Damage",
        "Burn Severity",
        "Air Temp P02",
    ]


def test_groups_take_the_weights_of_the_parameter_file(files):
    obs, _ = files
    case = fire_case.load_case(_definition(), obs)

    assert list(case.GROUPS["Fire Perimeters P02"]["benchmarks"].values()) == [2, 1, 0, 0, 0, 0, 1, 1]
    assert case.GROUPS["Air Temp P02"]["benchmarks"] == {
        bench_id: weight
        for bench_id, weight in zip(case.GROUPS["Air Temp P02"]["benchmarks"], [1, 1, 1, 0, 0, 0] * 3)
    }
    assert {group["weight"] for group in case.GROUPS.values()} == {1}


def test_targets_resolve_periods_and_flags(files):
    obs, _ = files
    case = fire_case.load_case(_definition(), obs)

    assert case.resolve_benchmark_target("p02_wp") == "P02_PW"
    assert set(case.AGGREGATION["P02_PW"]) == {
        "Fire Perimeters P02",
        *(f"{spec.group_label} P02" for spec in parameters_module.load_parameters().variables),
    }
    assert set(case.AGGREGATION[case.resolve_benchmark_target("P02_BS")]) == {
        "Building Damage",
        "Burn Severity",
    }
    tso = case.AGGREGATION[case.resolve_benchmark_target("P02_T")]
    assert set(tso["Air Temp P02"]["benchmarks"].values()) == {1}
    with pytest.raises(ValueError, match="cannot be combined"):
        case.resolve_benchmark_target("P02_TW")
    with pytest.raises(ValueError, match="Unknown period"):
        case.resolve_benchmark_target("P07_P")
    with pytest.raises(ValueError, match="Invalid benchmark target"):
        case.resolve_benchmark_target("W2")


def test_describe_available_targets_lists_the_case(files):
    obs, _ = files
    case = fire_case.load_case(_definition(), obs)

    summary = case.describe_available_targets()

    assert summary["periods"] == [
        {
            "target": "P02",
            "start": W2_START.astimezone(timezone.utc),
            "end": W2_END.astimezone(timezone.utc),
        }
    ]
    assert summary["kpi_groups"] == {
        "B": "Building Damage",
        "S": "Burn Severity",
        "P": "Fire Perimeters",
        "T": "Weather Stations (TSO only)",
        "W": "Weather Stations (TSO and all sources)",
    }
    assert set(summary["standalone_targets"]) == {"A", "B", "S", "FP", "WX"}
    detail = case.describe_available_targets("P02_P")
    assert [item["path"] for item in detail["perimeters"]] == list(W2_PERIMETERS)
    assert detail["kpis"][0]["name"] == "Average Jaccard Index"


def test_composed_groups_cover_every_group_and_compose_stably(files):
    obs, _ = files
    case = fire_case.load_case(_definition(), obs)

    groups = case.describe_composable_groups()

    assert [group["name"] for group in groups] == list(case.GROUPS)
    by_name = {group["name"]: group for group in groups}
    assert by_name["Building Damage"]["period"] is None
    assert by_name["Fire Perimeters P02"]["kind"] == "P"
    assert by_name["Air Temp P02"]["variable"] == "air_temperature"
    target = case.compose_target(["Burn Severity", "Building Damage"])
    assert target.startswith(case.COMPOSED_TARGET_PREFIX)
    assert case.compose_target(["Building Damage", "Burn Severity"]) == target
    with pytest.raises(ValueError, match="Unknown KPI group"):
        case.compose_target(["Canopy Cover Loss"])


# ---------------------------
# Parity with FB001, and the KPIs it does not share
# ---------------------------
def _run(functions: dict, ids, obs, model) -> list:
    with h5py.File(obs, "r") as obs_h5, h5py.File(model, "r") as model_h5:
        ctx = {}
        return [_values(functions[bench_id](model_h5, obs_h5, ctx)) for bench_id in ids]


def test_building_damage_matches_fb001(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)
    c001_caldor.build_registries()

    generic = _run(case.BENCHMARK_FUNCTIONS, [f"G-BD{index:02d}" for index in range(1, 7)], obs, model)
    caldor = _run(
        c001_caldor.BENCHMARK_FUNCTIONS, [f"FB001_BD{index:02d}" for index in range(1, 7)], obs, model
    )

    assert generic == caldor


def test_perimeter_indices_match_fb001(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)
    c001_caldor.build_registries()
    # FB001's group of W2 lists its six indices first, then the two area KPIs.
    caldor_ids = list(c001_caldor.GROUPS["Fire Perimeter W2"]["benchmarks"])[:6]

    generic = _run(case.BENCHMARK_FUNCTIONS, [f"G-FP{index:02d}" for index in range(1, 7)], obs, model)
    caldor = _run(c001_caldor.BENCHMARK_FUNCTIONS, caldor_ids, obs, model)

    assert [values[0] for values in generic] == pytest.approx([values[0] for values in caldor])
    assert [values[1] for values in generic] == pytest.approx([values[1] for values in caldor])


def test_weather_kpis_match_fb001(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)
    c001_caldor.build_registries()

    generic = _run(case.BENCHMARK_FUNCTIONS, list(case.GROUPS["Air Temp P02"]["benchmarks"]), obs, model)
    caldor = _run(
        c001_caldor.BENCHMARK_FUNCTIONS, list(c001_caldor.GROUPS["Air Temp W2"]["benchmarks"]), obs, model
    )

    assert len(generic) == 18
    assert len({round(values[0], 9) for values in generic}) > 1
    assert [value for values in generic for value in values] == pytest.approx(
        [value for values in caldor for value in values]
    )


def test_burn_areas_are_computed_in_the_case_projection(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    def area(ring):
        return (
            gpd.GeoSeries.from_wkt([f"POLYGON(({', '.join(f'{x} {y}' for x, y in ring)}))"], crs=4326)
            .to_crs(5070)
            .area.sum()
        )

    acre = 43560 * (1200 / 3937) ** 2
    expected_bias = (area(MODEL_SQUARES[-1]) - area(OBS_SQUARES[-1])) / acre

    (bias,) = _run(case.BENCHMARK_FUNCTIONS, ["G-FP07"], obs, model)

    assert bias[0] == pytest.approx(expected_bias, rel=1e-9)


def test_high_burn_severity_leaves_out_cells_without_a_class(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    accuracy, precision, recall = _run(case.BENCHMARK_FUNCTIONS, ["G-SV01", "G-SV02", "G-SV03"], obs, model)

    # Cells both files classify: obs high [0, 1, 1, 0], model high [1, 1, 0, 0].
    assert accuracy == [0.5, 50.0]
    assert precision[0] == pytest.approx(0.5)
    assert recall[0] == pytest.approx(0.5)


def test_burn_severity_needs_the_observation_grid(files, tmp_path):
    obs, _ = files
    other = _write_case_file(tmp_path / "other", cbi=np.ones((3, 3), dtype=np.uint8), observational=False)
    case = fire_case.load_case(_definition(), obs)

    with pytest.raises(ValueError, match="observation grid"):
        _run(case.BENCHMARK_FUNCTIONS, ["G-SV01"], obs, other)


# ---------------------------
# Run
# ---------------------------
def test_run_benchmark_writes_a_score_card_named_by_the_definition(files, tmp_path):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    result = case.run_benchmark(
        model,
        "A",
        name="Test model",
        obs_data=obs,
        output_json=tmp_path / "result.json",
        score_card_report=tmp_path / "card.pdf",
    )

    written = json.loads((tmp_path / "result.json").read_text())
    assert written["case_id"] is None
    assert written["case_schema"] == "fb-case-v1"
    assert written["case_definition_sha256"] == case.sha256
    assert written["parameters"]["set"] == "fire_case"
    assert written["evaluated_model_name"] == "Test model"
    assert 0 < result["score_card"]["Score Total"] < 100
    # Only air temperature is observed: FireBench ignores the KPIs of the other variables, as in FB001.
    scored = {*case.GROUPS["Fire Perimeters P02"]["benchmarks"], *case.GROUPS["Air Temp P02"]["benchmarks"]}
    scored |= {*case.GROUPS["Building Damage"]["benchmarks"], *case.GROUPS["Burn Severity"]["benchmarks"]}
    assert set(written["benchmarks"]) == scored


def test_run_benchmark_scores_chosen_groups(files, tmp_path):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    result = case.run_benchmark(
        model,
        "",
        groups=["Building Damage"],
        obs_data=obs,
        output_json=tmp_path / "result.json",
        score_card_report=tmp_path / "card.pdf",
    )

    assert result["score_card"]["aggregation_scheme_name"] == case.compose_target(["Building Damage"])
    assert set(result["benchmarks"]) == {f"G-BD{index:02d}" for index in range(1, 7)}


def test_run_benchmark_needs_the_observation_file(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    with pytest.raises(ValueError, match="observation file"):
        case.run_benchmark(model, "A")


# ---------------------------
# Command line
# ---------------------------
def test_cli_proposes_and_checks_a_definition(files, tmp_path):
    obs, _ = files
    output = tmp_path / "definition.json"
    runner = CliRunner()

    proposed = runner.invoke(main, ["case", "propose", str(obs), "-o", str(output)])
    checked = runner.invoke(main, ["case", "check", str(output), str(obs)])

    assert proposed.exit_code == 0, proposed.output
    assert json.loads(output.read_text())["schema"] == "fb-case-v1"
    assert checked.exit_code == 0, checked.output
    assert "can be run" in checked.output


def test_cli_check_lists_the_problems(files, tmp_path):
    obs, _ = files
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(_broken(lambda d: d.update(projection="EPSG:3310"))))

    result = CliRunner().invoke(main, ["case", "check", str(path), str(obs)])

    assert result.exit_code != 0
    assert "projection" in result.output


def test_cli_runs_the_definition_kept_in_the_observation_file(files, tmp_path):
    obs, model = files
    definition_module.write_case_definition(obs, _definition())
    output = tmp_path / "result.json"

    result = CliRunner().invoke(
        main,
        [
            "case",
            "run",
            str(obs),
            str(model),
            "-t",
            "B",
            "--output-json",
            str(output),
            "--score-card",
            str(tmp_path / "c.pdf"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["score_card"]["aggregation_scheme_name"] == "B"


def test_forecast_windows_follow_fb001(files):
    obs, _ = files
    parameters = parameters_module.load_parameters()
    with h5py.File(obs, "r") as h5:
        times = definition_module.perimeter_times(h5)
    within = (STATION_START, STATION_START + timedelta(hours=STATION_HOURS))

    windows = definition_module._forecast_windows(
        times, within, parameters
    )  # pylint: disable=protected-access

    assert all(end - start == timedelta(hours=parameters.forecast_hours) for start, end in windows)
    assert all(start.hour in parameters.forecast_cycle_hours for start, _ in windows)


def test_edit_case_removes_and_adds_periods(files):
    obs, _ = files
    definition = definition_module.propose_case(obs)["definition"]
    start = datetime(2021, 8, 21, tzinfo=timezone.utc)
    end = datetime(2021, 8, 22, 12, tzinfo=timezone.utc)

    edited = definition_module.edit_case(
        definition,
        obs,
        remove_families=["building_damage"],
        remove_periods=["H001", "H002"],
        add_periods=[(start, end)],
    )

    names = [period["name"] for period in edited["periods"]]
    assert names == ["P01", "P02", "H003", "H004", "P03"]
    assert edited["periods"][-1] == {
        "name": "P03",
        "start": _iso(start),
        "end": _iso(end),
        "origin": "custom",
    }
    assert definition_module.family(edited, "building_damage") is None
    perimeters = definition_module.family(edited, "fire_perimeters")["periods"]
    assert [item["period"] for item in perimeters] == ["P01", "H003", "H004", "P03"]
    assert perimeters[-1]["perimeters"] == list(W2_PERIMETERS)
    assert definition_module.family(edited, "weather_stations")["periods"] == names
    assert definition_module.check_case(edited, obs) == []
    # The definition given is left as it was.
    assert [period["name"] for period in definition["periods"]][2:4] == ["H001", "H002"]


def test_edit_case_drops_a_family_left_without_a_period(files):
    obs, _ = files
    definition = _definition()

    edited = definition_module.edit_case(definition, obs, remove_periods=["P02"])

    assert [item["family"] for item in edited["families"]] == ["building_damage", "burn_severity_cbi"]
    assert "no period" in " ".join(definition_module.check_case(edited, obs))


def test_perimeter_values_give_what_the_perimeter_kpis_aggregate(files):
    obs, model = files
    case = fire_case.load_case(_definition(), obs)

    with h5py.File(model, "r") as model_h5, h5py.File(obs, "r") as obs_h5:
        values = case.perimeter_values(model_h5, obs_h5)

    assert [item["path"] for item in values] == list(W2_PERIMETERS)
    assert [item["time"] for item in values] == [path.rsplit("_", 1)[-1] for path in W2_PERIMETERS]
    mean_jaccard, min_jaccard = _run(case.BENCHMARK_FUNCTIONS, ["G-FP01", "G-FP02"], obs, model)
    jaccard = [item["jaccard"] for item in values]
    assert np.mean(jaccard) == pytest.approx(mean_jaccard[0])
    assert min(jaccard) == pytest.approx(min_jaccard[0])
    (bias,) = _run(case.BENCHMARK_FUNCTIONS, ["G-FP07"], obs, model)
    last = values[-1]
    assert (last["model_area"] - last["observed_area"]).to("acre").magnitude == pytest.approx(bias[0])
    assert all(0 < item["dice"] <= 1 for item in values)


def test_caldor_perimeter_values_use_its_own_area_projection(files):
    obs, model = files
    c001_caldor.build_registries()

    with h5py.File(model, "r") as model_h5, h5py.File(obs, "r") as obs_h5:
        values = c001_caldor.perimeter_values(model_h5, obs_h5)

    caldor_bias_id = list(c001_caldor.GROUPS["Fire Perimeter W2"]["benchmarks"])[6]
    (bias,) = _run(c001_caldor.BENCHMARK_FUNCTIONS, [caldor_bias_id], obs, model)
    last = values[-1]
    assert (last["model_area"] - last["observed_area"]).to("acre").magnitude == pytest.approx(bias[0])


def test_perimeter_values_leave_out_a_perimeter_the_model_lacks(files):
    obs, model = files
    with h5py.File(model, "a") as model_h5:
        del model_h5[W2_PERIMETERS[0]]

    with h5py.File(model, "r") as model_h5, h5py.File(obs, "r") as obs_h5:
        values = c001_caldor.perimeter_values(model_h5, obs_h5)

    assert [item["path"] for item in values] == list(W2_PERIMETERS[1:])
