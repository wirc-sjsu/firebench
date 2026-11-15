"""The catalogue benchmark: definition, bundle check, run, statistics, template, and CLI."""

import copy
import hashlib
import json
import math

import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from catalogue_helpers import (
    DAMAGE_E1,
    DAMAGE_E2,
    RADII,
    disc,
    fill_template,
    make_catalogue,
    perfect_bundle,
    write_model,
)
from firebench.benchmarks import catalogue_case, catalogue_parameters, catalogue_run, catalogue_scoring
from firebench.benchmarks import catalogue_template
from firebench.benchmarks.catalogue_statistics import summarize
from firebench.benchmarks.fire_case_definition import CaseDefinitionError, definition_sha256
from firebench.cli import main
from firebench.standardize import event_ids_sha256, read_event_catalogue

PARAMETERS = catalogue_parameters.load_parameters()


@pytest.fixture(name="catalogue")
def fixture_catalogue(tmp_path):
    return make_catalogue(tmp_path / "catalogue.h5")


@pytest.fixture(name="definition")
def fixture_definition(catalogue):
    return catalogue_case.propose_catalogue_case(catalogue, "Toy catalogue")


def _run(definition, catalogue, bundle, tmp_path, tag="run", **kwargs):
    kwargs.setdefault("workers", 1)
    return catalogue_run.run_catalogue_benchmark(
        definition,
        catalogue,
        bundle,
        output_json=tmp_path / f"{tag}.json",
        score_card_report=tmp_path / f"{tag}.pdf",
        event_table=tmp_path / f"{tag}.csv",
        overwrite=True,
        **kwargs,
    )


# ---------------------------
# Parameters
# ---------------------------
def test_the_parameter_file_is_the_one_the_brief_names():
    assert (PARAMETERS.set, PARAMETERS.version) == ("event_catalogue", "2026.1")
    assert PARAMETERS.projections == ("EPSG:5070", "EPSG:6933")
    assert PARAMETERS.size_classes[0] == ("A", 0) and PARAMETERS.size_classes[-1] == ("G", 5000)
    assert PARAMETERS.structure_loss.lost_classes == ("destroyed", "major")
    assert len(PARAMETERS.sha256) == 64


def test_the_parameter_file_refuses_a_missing_or_unknown_key():
    import tomllib
    from importlib.resources import files

    document = tomllib.loads(
        files("firebench").joinpath(catalogue_parameters.PARAMETER_FILE).read_text(encoding="utf-8")
    )
    broken = copy.deepcopy(document)
    del broken["coverage"]["min_coverage"]
    with pytest.raises(catalogue_parameters.CatalogueParameterError, match="missing min_coverage"):
        catalogue_parameters.parse_parameters(broken)
    broken = copy.deepcopy(document)
    broken["statistics"]["extra"] = 1
    with pytest.raises(catalogue_parameters.CatalogueParameterError, match="unknown extra"):
        catalogue_parameters.parse_parameters(broken)
    broken = copy.deepcopy(document)
    broken["structure_loss"]["lost_classes"] = ["gone"]
    with pytest.raises(catalogue_parameters.CatalogueParameterError, match="no damage class"):
        catalogue_parameters.parse_parameters(broken)


# ---------------------------
# Definition
# ---------------------------
def test_propose_check_and_load(catalogue, definition):
    assert definition["schema"] == "fb-catalogue-case-v1"
    assert definition["families"] == ["final_perimeter", "structure_loss"]
    assert definition["strata"] == ["size_class", "year"]
    assert definition["projection"] == "EPSG:5070"
    assert definition["event_ids_sha256"] == read_event_catalogue(catalogue).attrs["event_ids_sha256"]
    assert catalogue_case.check_catalogue_case(definition, catalogue) == []
    case = catalogue_case.load_catalogue_case(definition, catalogue)
    assert case.event_ids == sorted(RADII) and case.sha256 == definition_sha256(definition)
    # The hash is stable whatever the order of the keys.
    assert definition_sha256(dict(reversed(list(definition.items())))) == case.sha256


def test_the_default_families_follow_the_catalogue(tmp_path):
    path = make_catalogue(tmp_path / "plain.h5", structures=False)
    assert catalogue_case.propose_catalogue_case(path, "plain")["families"] == ["final_perimeter"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(schema="fb-case-v1"), "schema"),
        (lambda d: d.update(extra=1), "Unknown keys"),
        (lambda d: d.pop("strata"), "Missing keys"),
        (lambda d: d.update(parameters={"set": "event_catalogue", "version": "1999"}), "version"),
        (lambda d: d.update(parameters={"set": "other", "version": "2026.1"}), "parameter set"),
        (lambda d: d.update(projection="EPSG:4326"), "projection"),
        (lambda d: d.update(families=["final_perimeter", "progression"]), "later version"),
        (lambda d: d.update(families=["area_growth"]), "later version"),
        (lambda d: d.update(families=["final_perimeter", "final_perimeter"]), "twice"),
        (lambda d: d.update(families=["wind"]), "Unknown family"),
        (lambda d: d.update(strata=["fuel"]), "Unknown stratum"),
        (lambda d: d.update(event_ids_sha256="0" * 64), "event_ids_sha256"),
    ],
)
def test_check_refuses(catalogue, definition, change, message):
    broken = copy.deepcopy(definition)
    change(broken)
    problems = catalogue_case.check_catalogue_case(broken, catalogue)
    assert any(message in problem for problem in problems), problems
    with pytest.raises(CaseDefinitionError, match=message):
        catalogue_case.load_catalogue_case(broken, catalogue)


def test_structure_loss_needs_structures(tmp_path):
    path = make_catalogue(tmp_path / "plain.h5", structures=False)
    definition = catalogue_case.propose_catalogue_case(path, "plain")
    definition["families"] = ["structure_loss"]
    assert any("structures" in problem for problem in catalogue_case.check_catalogue_case(definition, path))
    with pytest.raises(CaseDefinitionError, match="structures"):
        catalogue_case.propose_catalogue_case(path, "plain", families=["structure_loss"])


def test_a_subset_is_named_by_its_ids(catalogue):
    ids = ["ev_c", "ev_a"]
    definition = catalogue_case.propose_catalogue_case(catalogue, "subset", event_ids=ids)
    assert definition["event_ids_sha256"] == event_ids_sha256(ids)
    assert catalogue_case.check_catalogue_case(definition, catalogue, event_ids=ids) == []
    assert catalogue_case.load_catalogue_case(definition, catalogue, event_ids=ids).event_ids == [
        "ev_a",
        "ev_c",
    ]
    # Without the list, the hash is not the catalogue's.
    assert catalogue_case.check_catalogue_case(definition, catalogue)
    assert any(
        "does not hold" in p for p in catalogue_case.check_catalogue_case(definition, catalogue, ["nope"])
    )
    assert any(
        "Duplicate" in p for p in catalogue_case.check_catalogue_case(definition, catalogue, ids + ["ev_a"])
    )
    assert catalogue_case.check_catalogue_case(definition, catalogue, ["ev_a", "ev_b"])


def test_the_projection_defaults_to_the_catalogues(tmp_path):
    path = make_catalogue(tmp_path / "world.h5", area_crs="EPSG:6933")
    assert catalogue_case.propose_catalogue_case(path, "world")["projection"] == "EPSG:6933"


# ---------------------------
# One event
# ---------------------------
def test_observed_perimeters_as_the_model_score_one(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    result = _run(definition, catalogue, bundle, tmp_path)
    collection = result["collection"]
    for kpi_id, expected in (("G-FP01", 1.0), ("G-FP02", 1.0), ("G-FP03", 0.0), ("G-FP04", 1.0)):
        block = collection["kpis"][kpi_id]
        assert block["n_samples"] == 6
        assert block["value"]["median"] == pytest.approx(expected, abs=2e-3)
        assert block["score"]["median"] == pytest.approx(100.0, abs=0.5)
    assert result["score_card"]["Score Total"] == pytest.approx(100.0, abs=0.5)
    rows = (tmp_path / "run.csv").read_text().splitlines()
    for row in rows[1:]:
        event, family, kpi_id, _, value, score, reason = row.split(",")
        if family == "final_perimeter" and kpi_id in ("G-FP01", "G-FP02"):
            assert float(value) == pytest.approx(1.0, abs=2e-3) and reason == ""


def test_a_buffered_circle_gives_the_analytic_indices(tmp_path, catalogue, definition):
    bundle = tmp_path / "bundle"
    distance = 400.0
    for event_id, radius in RADII.items():
        write_model(bundle / event_id, disc(event_id, extra=distance))
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    rows = [row.split(",") for row in (tmp_path / "run.csv").read_text().splitlines()[1:]]
    for event_id, radius in RADII.items():
        values = {row[2]: float(row[4]) for row in rows if row[0] == event_id}
        big = radius + distance
        assert values["G-FP01"] == pytest.approx(radius**2 / big**2, rel=2e-3)
        assert values["G-FP02"] == pytest.approx(2 * radius**2 / (radius**2 + big**2), rel=2e-3)
        assert values["G-FP03"] == pytest.approx((big**2 - radius**2) / radius**2, rel=2e-3)
        assert values["G-FP04"] == pytest.approx(big**2 / radius**2, rel=2e-3)
    assert result["collection"]["families"] == ["final_perimeter"]


def test_an_empty_model_perimeter_is_scored_not_null(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_c",))
    write_model(bundle / "ev_c", None)
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    rows = [
        row.split(",")
        for row in (tmp_path / "run.csv").read_text().splitlines()[1:]
        if row.startswith("ev_c")
    ]
    by_kpi = {row[2]: row for row in rows}
    assert float(by_kpi["G-FP01"][4]) == 0.0 and float(by_kpi["G-FP02"][4]) == 0.0
    assert float(by_kpi["G-FP03"][4]) == -1.0 and float(by_kpi["G-FP04"][4]) == 0.0
    assert float(by_kpi["G-FP04"][5]) == 0.0 and by_kpi["G-FP01"][6] == ""
    assert result["collection"]["coverage"]["final_perimeter"]["n_given"] == 6


def test_a_missing_event_is_null_and_lowers_coverage(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_f",))
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["missing"] == ["ev_f"] and report["refusals"] == []
    assert report["families"]["final_perimeter"] == {
        "n_expected": 6,
        "n_given": 5,
        "share": 5 / 6,
        "min_coverage": 0.8,
        "reaches": True,
    }
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    assert result["collection"]["kpis"]["G-FP01"]["n_samples"] == 5
    rows = [
        row.split(",")
        for row in (tmp_path / "run.csv").read_text().splitlines()[1:]
        if row.startswith("ev_f")
    ]
    assert len(rows) == 4 and all(
        row[4] == "" and row[5] == "" and row[6] == "no model output" for row in rows
    )
    assert result["score_card"]["Score Total"] == pytest.approx(100.0, abs=0.5)


def test_below_coverage_there_is_no_total(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_e", "ev_f"))
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    card = result["score_card"]
    assert "Score Total" not in card and "final_perimeter" in card["no_total_reason"]
    assert "4 of 6" in card["no_total_reason"] and "80%" in card["no_total_reason"]
    assert "Score Final Perimeter" not in card and result["benchmarks"] == {}
    assert set(result["collection"]["omitted_kpis"]) == {"G-FP01", "G-FP02", "G-FP03", "G-FP04"}
    assert result["collection"]["coverage"]["final_perimeter"]["reaches"] is False
    assert result["collection"]["kpis"]["G-FP01"]["n_samples"] == 4  # the samples are still reported


def test_a_family_chosen_alone_gives_a_total_over_it(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    both = _run(definition, catalogue, bundle, tmp_path, tag="both")
    alone = _run(definition, catalogue, bundle, tmp_path, tag="alone", families=["structure_loss"])
    assert set(both["score_card"]["Scheme"]) == {"Final Perimeter", "Structure Loss"}
    assert set(alone["score_card"]["Scheme"]) == {"Structure Loss"}
    assert alone["score_card"]["Score Total"] == alone["score_card"]["Score Structure Loss"]
    assert alone["score_card"]["aggregation_scheme_name"].startswith("C-")
    assert both["score_card"]["aggregation_scheme_name"] == "A"
    weights = PARAMETERS.family_weights
    expected = (
        both["score_card"]["Score Final Perimeter"] * weights["final_perimeter"]
        + both["score_card"]["Score Structure Loss"] * weights["structure_loss"]
    ) / sum(weights.values())
    assert both["score_card"]["Score Total"] == pytest.approx(expected)


def test_the_score_of_a_kpi_is_the_median_of_the_scores(tmp_path, catalogue, definition):
    # Bias of -0.5 and +0.5 on two events: the median value is a small number, the scores are not 100.
    bundle = tmp_path / "bundle"
    for event_id, radius in RADII.items():
        scale = {"ev_a": -0.5, "ev_b": 0.5}.get(event_id, 0.0)
        extra = (math.sqrt(1 + scale) - 1) * radius
        write_model(bundle / event_id, disc(event_id, extra=extra))
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"], workers=1)
    block = result["collection"]["kpis"]["G-FP03"]
    assert block["value"]["median"] == pytest.approx(0.0, abs=2e-3)
    assert block["score"]["median"] == pytest.approx(100.0, abs=0.5)  # four of six events are exact
    assert block["score"]["q1"] < 50.0  # the two scattered events pull the lower quartile down
    assert result["benchmarks"]["G-FP03"]["Score"] == block["score"]["median"]


# ---------------------------
# Structure loss
# ---------------------------
def test_structure_loss_counts_lost_structures(tmp_path, catalogue, definition):
    bundle = perfect_bundle(
        tmp_path / "bundle",
        catalogue,
        labels={
            "ev_a": ["Destroyed (>50%)"] * 5 + ["No Damage"] * 7,  # 5 lost against 10: (5-10)/10 = -0.5
            "ev_b": ["Major (26-50%)", "Minor (10-25%)", "Destroyed (>50%)"],  # 2 against 1: 1/10
        },
    )
    result = _run(definition, catalogue, bundle, tmp_path, families=["structure_loss"])
    rows = [row.split(",") for row in (tmp_path / "run.csv").read_text().splitlines()[1:]]
    by_event = {row[0]: row for row in rows}
    assert float(by_event["ev_a"][4]) == pytest.approx(-0.5) and float(
        by_event["ev_a"][5]
    ) == pytest.approx(50.0)
    assert float(by_event["ev_b"][4]) == pytest.approx(0.1)
    # An event without structures is not scored, and not in the denominator.
    for event in ("ev_c", "ev_d", "ev_e", "ev_f"):
        assert by_event[event][4] == "" and by_event[event][6] == "no observation"
    coverage = result["collection"]["coverage"]["structure_loss"]
    assert (coverage["n_expected"], coverage["n_given"], coverage["share"]) == (2, 2, 1.0)
    assert result["collection"]["kpis"]["G-SL01"]["n_samples"] == 2
    assert result["score_card"]["Score Total"] == pytest.approx(
        result["collection"]["kpis"]["G-SL01"]["score"]["median"]
    )


def test_a_length_mismatch_is_null_with_its_reason(tmp_path, catalogue, definition):
    bundle = perfect_bundle(
        tmp_path / "bundle", catalogue, labels={"ev_a": DAMAGE_E1[:5], "ev_b": DAMAGE_E2}
    )
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["events"]["ev_a"]["problems"] == [
        "structure_loss: the model gives 5 structures, the catalogue has 12"
    ]
    assert (
        report["families"]["structure_loss"]["n_given"] == 1
        and report["families"]["structure_loss"]["reaches"] is False
    )
    result = _run(definition, catalogue, bundle, tmp_path, families=["structure_loss"])
    rows = [
        row.split(",")
        for row in (tmp_path / "run.csv").read_text().splitlines()[1:]
        if row.startswith("ev_a")
    ]
    assert rows[0][4] == "" and "5 structures" in rows[0][6]
    assert "Score Total" not in result["score_card"]


# ---------------------------
# The bundle
# ---------------------------
def test_unknown_stray_and_duplicate_files_are_refused(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    write_model(bundle / "unknown_event", disc("ev_a"))
    with pytest.raises(ValueError, match="unknown events: unknown_event"):
        _run(definition, catalogue, bundle, tmp_path)
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["unknown"] == ["unknown_event"] and report["refusals"]
    (bundle / "unknown_event" / "model.h5").unlink()
    for item in (bundle / "unknown_event").iterdir():
        item.unlink()
    (bundle / "unknown_event").rmdir()

    (bundle / "notes.txt").write_text("hello")
    with pytest.raises(ValueError, match="beside the event directories: notes.txt"):
        _run(definition, catalogue, bundle, tmp_path)
    (bundle / "notes.txt").unlink()

    write_model(bundle / "ev_a" / "second", disc("ev_a"))
    with pytest.raises(ValueError, match="more than one .h5 file: ev_a"):
        _run(definition, catalogue, bundle, tmp_path)
    assert catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)["duplicate"] == [
        "ev_a"
    ]


def test_an_event_outside_a_subset_is_unknown(tmp_path, catalogue):
    ids = ["ev_a", "ev_b"]
    definition = catalogue_case.propose_catalogue_case(catalogue, "subset", event_ids=ids)
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    with pytest.raises(ValueError, match="unknown events"):
        _run(definition, catalogue, bundle, tmp_path, event_ids=ids)


def test_disagreeing_model_attributes_are_refused(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    write_model(bundle / "ev_a", disc("ev_a"), attributes={"model_version": "2"})
    with pytest.raises(ValueError, match="`model_version` differs"):
        _run(definition, catalogue, bundle, tmp_path)
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["model_attributes"]["agree"] is False
    assert report["model_attributes"]["values"]["model_version"] == {"1": 5, "2": 1}


def test_a_template_submitted_unchanged_is_refused(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_a",))
    catalogue_template.write_event_template(catalogue, "ev_a", bundle / "ev_a" / "template.h5")
    with pytest.raises(ValueError, match="model-output template, not an observation file"):
        _run(definition, catalogue, bundle, tmp_path)
    assert catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)["templates"] == [
        "ev_a"
    ]


def test_a_file_problem_is_not_a_refusal(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_a", "ev_b", "ev_c"))
    (bundle / "ev_a").mkdir()
    (bundle / "ev_a" / "model.h5").write_text("not a standard file")
    write_model(bundle / "ev_b", disc("ev_b"))
    (bundle / "ev_b" / "perimeter.kml").write_text("changed after the hash")
    write_model(bundle / "ev_c", disc("ev_c"))
    with h5py.File(bundle / "ev_c" / "model.h5", "a") as h5:
        h5["polygons/final_perimeter"].attrs["rel_path"] = "../ev_d/perimeter.kml"
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["refusals"] == [] and report["unreadable"] == ["ev_a"]
    problems = {event: info["problems"] for event, info in report["events"].items() if info["problems"]}
    assert "not a standard file" in problems["ev_a"][0]
    assert "sha256" in problems["ev_b"][0]
    assert "not inside the event's directory" in problems["ev_c"][0]
    assert report["families"]["final_perimeter"]["n_given"] == 3
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    assert result["collection"]["kpis"]["G-FP01"]["n_samples"] == 3
    assert "Score Total" not in result["score_card"]


def test_an_unreadable_perimeter_file_is_null_not_a_failed_run(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue, skip=("ev_a",))
    write_model(bundle / "ev_a", disc("ev_a"))
    kml_path = bundle / "ev_a" / "perimeter.kml"
    kml_path.write_text("<kml><Document><Placemark><Polygon>broken", encoding="utf-8")
    with h5py.File(bundle / "ev_a" / "model.h5", "a") as h5:
        h5["polygons/final_perimeter"].attrs["sha256"] = hashlib.sha256(kml_path.read_bytes()).hexdigest()
    result = _run(definition, catalogue, bundle, tmp_path, families=["final_perimeter"])
    coverage = result["collection"]["coverage"]["final_perimeter"]
    assert coverage["n_given"] == coverage["n_expected"] - 1


def test_the_families_must_be_a_subset(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    for bad in ([], ["progression"]):
        with pytest.raises(ValueError, match="non-empty subset"):
            _run(definition, catalogue, bundle, tmp_path, families=bad)
    with pytest.raises(ValueError, match="not a directory"):
        _run(definition, catalogue, tmp_path / "nothing", tmp_path)


# ---------------------------
# Determinism and the card
# ---------------------------
def test_two_runs_with_different_pools_agree(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    write_model(bundle / "ev_c", disc("ev_c", extra=250.0))
    one = _run(definition, catalogue, bundle, tmp_path, tag="one", workers=1)
    two = _run(definition, catalogue, bundle, tmp_path, tag="two", workers=2)
    assert (tmp_path / "one.csv").read_bytes() == (tmp_path / "two.csv").read_bytes()
    for card in (one, two):
        card.pop("created_on"), card.pop("score_card_report_hash")
    assert one == two


def test_the_card_has_the_shape_the_site_reads(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    result = _run(definition, catalogue, bundle, tmp_path)
    assert result["case_schema"] == "fb-catalogue-case-v1" and result["case_id"] is None
    assert result["case_definition_sha256"] == definition_sha256(definition)
    assert result["event_ids_sha256"] == definition["event_ids_sha256"]
    assert result["parameters"] == {
        "set": "event_catalogue",
        "version": "2026.1",
        "sha256": PARAMETERS.sha256,
    }
    assert result["evaluated_model_name"] == "toy" and len(result["bundle_sha256"]) == 64
    assert result["collection"]["event_table_sha256"] == catalogue_run.ft.calculate_sha256(
        tmp_path / "run.csv"
    )
    assert result["certificates_input"] == {"from_obs_std_file": {}}
    assert result["score_card"]["group_display_names"] == {
        "Final Perimeter": "Final Perimeter",
        "Structure Loss": "Structure Loss",
    }
    assert result["benchmarks"]["G-FP01"] == {
        "Final Perimeter Jaccard": pytest.approx(1.0, abs=2e-3),
        "Score": result["benchmarks"]["G-FP01"]["Score"],
    }
    assert json.loads((tmp_path / "run.json").read_text()) == result
    assert (tmp_path / "run.pdf").stat().st_size > 2000
    named = _run(definition, catalogue, bundle, tmp_path, tag="named", name="My model")
    assert named["evaluated_model_name"] == "My model"


def test_strata_are_reported_by_size_class_and_year(tmp_path, catalogue, definition):
    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    strata = _run(definition, catalogue, bundle, tmp_path)["collection"]["strata"]
    # 300 m: 70 acres (B), 1000 m: 776 (D), 2000 m: 3,100 (F), 3000 m: 7,000 (G), 4000 m: 12,400 (G), 5000 m: 19,400 (G).
    sizes = {label: block["n_events"] for label, block in strata["size_class"].items()}
    assert sizes == {"C": 1, "E": 1, "F": 1, "G": 3}
    assert strata["size_class"]["G"]["kpis"]["G-FP01"]["n_samples"] == 3
    assert {label: block["n_events"] for label, block in strata["year"].items()} == {"2020": 3, "2021": 3}


def test_statistics_on_a_known_sample():
    statistics = PARAMETERS.statistics
    sample = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    summary = summarize(sample, statistics)
    assert (summary["median"], summary["q1"], summary["q3"]) == (5.0, 3.0, 7.0)
    assert (
        summary["interval_reason"] is None and 2.0 <= summary["ci_low"] <= 5.0 <= summary["ci_high"] <= 8.0
    )
    assert summarize(sample, statistics) == summary  # the seed fixes the interval
    assert summarize([*sample, None], statistics) == summary  # nulls are left out
    few = summarize([1.0, 2.0, 9.0, 4.0], statistics)
    assert few["median"] == 3.0 and few["ci_low"] is None and "fewer than 5" in few["interval_reason"]
    assert summarize([], statistics)["median"] is None
    scattered = np.random.default_rng(0).normal(size=40).tolist()
    reseeded = type(statistics)(**{**statistics.__dict__, "bootstrap_seed": 1})
    assert summarize(scattered, reseeded) != summarize(scattered, statistics)
    assert summarize(scattered, statistics) == summarize(scattered, statistics)


# ---------------------------
# Template
# ---------------------------
def test_the_template_holds_the_ignition_box_window_and_no_observed_perimeter(
    tmp_path, catalogue, definition
):
    template = catalogue_template.write_event_template(
        catalogue, "ev_a", tmp_path / "t.h5", definition=definition
    )
    events = read_event_catalogue(catalogue).events.set_index("event_id")
    row = events.loc["ev_a"]
    with h5py.File(template, "r") as h5:
        assert h5.attrs["firebench_template"] == "catalogue_event" and h5.attrs["event_id"] == "ev_a"
        assert h5.attrs["catalogue_case_sha256"] == definition_sha256(definition)
        assert json.loads(h5.attrs["catalogue_case_definition"]) == definition
        event = h5["event"]
        assert (
            event.attrs["ignition_lat"] == row["ignition_lat"] and event.attrs["anchor_precision"] == "day"
        )
        assert event.attrs["window_start"] == "2020-08-11T00:00:00Z"
        # No containment: the default window.
        assert event.attrs["window_end"] == "2020-08-25T00:00:00Z"
        box = [event.attrs[name] for name in ("box_west", "box_south", "box_east", "box_north")]
        assert box[0] < row["ignition_lon"] < box[2] and box[1] < row["ignition_lat"] < box[3]
        assert box[3] - box[1] == pytest.approx(2 * 50 / 111.2, rel=0.01)  # 50 km each side of the ignition
        assert (box[0] + box[2]) / 2 == pytest.approx(row["ignition_lon"], abs=1e-3)
        perimeter = h5["polygons/final_perimeter"]
        assert perimeter.attrs["time"] == "2020-08-25T00:00:00Z"
        assert "rel_path" not in perimeter.attrs and len(perimeter) == 0 and not perimeter.keys()
        assert perimeter.attrs["license"] == "Public domain"
        damage = h5[BUILDING_PATH]
        assert [value.decode() for value in damage[()]] == [""] * 12
        assert h5["points/building_damaged"].attrs["license"] == "CC BY 4.0"
        assert len(h5["points/building_damaged/position_lat"]) == 12
        # The observed geometry is nowhere in it.
        names = []
        h5.visit(names.append)
        assert not [name for name in names if "events" in name]


BUILDING_PATH = catalogue_scoring.BUILDING_DAMAGE_PATH


def test_the_window_ends_at_the_containment(tmp_path, catalogue):
    template = catalogue_template.write_event_template(catalogue, "ev_b", tmp_path / "t.h5", window_days=3)
    with h5py.File(template, "r") as h5:
        # Contained on 2021-08-21, a day precision: the window ends at the end of that UTC day.
        assert h5["event"].attrs["window_end"] == "2021-08-22T00:00:00Z"
        assert h5["event"].attrs["containment_time"] == "2021-08-21"
        assert "catalogue_case_sha256" not in h5.attrs
    other = catalogue_template.write_event_template(catalogue, "ev_a", tmp_path / "u.h5", window_days=3)
    with h5py.File(other, "r") as h5:
        assert h5["event"].attrs["window_end"] == "2020-08-14T00:00:00Z"


def test_the_template_keeps_inaccessible_and_refuses_bad_requests(tmp_path):
    import geopandas as gpd  # pylint: disable=import-outside-toplevel
    import pandas as pd  # pylint: disable=import-outside-toplevel
    from shapely.geometry import Point  # pylint: disable=import-outside-toplevel

    from firebench.standardize import write_event_catalogue  # pylint: disable=import-outside-toplevel

    events = gpd.GeoDataFrame(
        [
            {
                "event_id": "x",
                "ignition_lat": 38.0,
                "ignition_lon": -121.0,
                "anchor_time": "2021-08-14T06:00:00Z",
                "anchor_precision": "second",
            }
        ],
        geometry=[Point(-121.0, 38.0).buffer(0.05)],
        crs="EPSG:4326",
    )
    structures = pd.DataFrame(
        {
            "event_id": ["x", "x"],
            "lat": [38.0, 38.01],
            "lon": [-121.0, -121.0],
            "damage": ["Inaccessible", "Destroyed (>50%)"],
        }
    )
    path = write_event_catalogue(
        tmp_path / "c.h5",
        events,
        "tests",
        "CC0",
        "tests",
        structures=structures,
        structures_license="CC0",
        structures_data_source="DINS",
    )
    template = catalogue_template.write_event_template(path, "x", tmp_path / "t.h5")
    with h5py.File(template, "r") as h5:
        assert [value.decode() for value in h5[BUILDING_PATH][()]] == ["Inaccessible", ""]
        assert h5["event"].attrs["window_start"] == "2021-08-14T06:00:00Z"
        assert h5["event"].attrs["window_end"] == "2021-08-28T06:00:00Z"
    with pytest.raises(FileExistsError):
        catalogue_template.write_event_template(path, "x", tmp_path / "t.h5")
    with pytest.raises(ValueError, match="does not hold"):
        catalogue_template.write_event_template(path, "nope", tmp_path / "n.h5")
    with pytest.raises(ValueError, match="above 0"):
        catalogue_template.write_event_template(path, "x", tmp_path / "n.h5", window_days=0)


def test_a_template_filled_in_is_scored(tmp_path, catalogue, definition):
    out = tmp_path / "templates"
    paths = catalogue_template.write_event_templates(catalogue, out, definition=definition)
    assert [path.parent.name for path in paths] == sorted(RADII)
    bundle = tmp_path / "bundle"
    for path in paths:
        event_id = path.parent.name
        labels = {"ev_a": DAMAGE_E1, "ev_b": DAMAGE_E2}.get(event_id)
        fill_template(path, bundle / event_id, disc(event_id), labels)
    report = catalogue_run.check_catalogue_bundle(definition, catalogue, bundle, workers=1)
    assert report["refusals"] == [] and all(item["reaches"] for item in report["families"].values())
    assert report["families_present"] == {"final_perimeter": 6, "structure_loss": 2}
    result = _run(definition, catalogue, bundle, tmp_path)
    assert result["score_card"]["Score Total"] == pytest.approx(100.0, abs=0.5)


def test_event_ids_cannot_name_a_directory_outside_the_output(tmp_path, catalogue):
    with pytest.raises(ValueError, match="does not hold"):
        catalogue_template.write_event_templates(catalogue, tmp_path, ["../x"])


# ---------------------------
# CLI
# ---------------------------
def test_cli_template_check_run(tmp_path, catalogue, definition):
    runner = CliRunner()
    definition_path = tmp_path / "def.json"
    definition_path.write_text(json.dumps(definition))
    templates = tmp_path / "templates"
    result = runner.invoke(
        main,
        [
            "catalogue",
            "template",
            str(catalogue),
            str(templates),
            "--event",
            "ev_a",
            "--definition",
            str(definition_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (templates / "ev_a" / "template.h5").is_file() and not (templates / "ev_b").exists()
    assert (
        runner.invoke(
            main, ["catalogue", "template", str(catalogue), str(templates), "--event", "nope"]
        ).exit_code
        == 1
    )

    bundle = perfect_bundle(tmp_path / "bundle", catalogue)
    ids = tmp_path / "ids.txt"
    ids.write_text("\n".join(sorted(RADII)) + "\n")
    checked = runner.invoke(main, ["catalogue", "check", str(definition_path), str(catalogue), str(bundle)])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["families"]["final_perimeter"]["n_given"] == 6
    outputs = ["-o", str(tmp_path / "r.json"), "-r", str(tmp_path / "r.pdf"), "-t", str(tmp_path / "r.csv")]
    ran = runner.invoke(
        main,
        [
            "catalogue",
            "run",
            str(definition_path),
            str(catalogue),
            str(bundle),
            *outputs,
            "--workers",
            "1",
            "--family",
            "final_perimeter",
        ],
    )
    assert ran.exit_code == 0, ran.output
    assert "Total score 99" in ran.output or "Total score 100" in ran.output
    card = json.loads((tmp_path / "r.json").read_text())
    assert card["collection"]["families"] == ["final_perimeter"]
    again = runner.invoke(
        main,
        [
            "catalogue",
            "run",
            str(definition_path),
            str(catalogue),
            str(bundle),
            *outputs,
            "--family",
            "progression",
        ],
    )
    assert again.exit_code == 1 and "non-empty subset" in again.output
