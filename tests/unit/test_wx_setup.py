from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from firebench.workflows import wx_setup

UTC = timezone.utc
SETUP_PATH = Path("/work/setups/demo.yml")


def _parse(text: str, path: Path = SETUP_PATH):
    return wx_setup.parse_setup(yaml.safe_load(text), path)


def _problems(text: str) -> list[str]:
    with pytest.raises(wx_setup.SetupError) as excinfo:
        _parse(text)
    return excinfo.value.problems


def test_caldor_preset_defines_the_h012_bbox_window_and_single_cycle():
    setup = _parse("case: {id: 2021_Caldor, period: H012}")

    assert setup.bbox == (-120.8, 38.4, -119.7, 39.0)
    assert setup.start == datetime(2021, 8, 20, 0, tzinfo=UTC)
    assert setup.end == datetime(2021, 8, 22, 0, tzinfo=UTC)
    assert [(cycle.label, cycle.horizon_hours) for cycle in setup.cycles] == [("2021082000", 48)]
    assert setup.preset["period"] == "H012"
    assert setup.name == "demo"
    assert setup.output_dir == Path("/work/setups/runs/demo")


@pytest.mark.parametrize("case_id", ("001", "1", "caldor", "2021_CALDOR"))
def test_caldor_case_aliases(case_id):
    assert _parse(f"case: {{id: {case_id}, period: h12}}").preset["period"] == "H012"


def test_curated_period_needs_explicit_cycles_because_no_full_cycle_fits():
    problems = _problems("case: {id: 2021_Caldor, period: P02}")
    setup = _parse("case: {id: 2021_Caldor, period: P02}\nmodel: {cycles: [2021-08-20T00:00Z]}")

    assert any("list model.cycles explicitly" in problem for problem in problems)
    assert setup.start == datetime(2021, 8, 20, 3, 45, tzinfo=UTC)
    assert [cycle.label for cycle in setup.cycles] == ["2021082000"]


def test_explicit_domain_and_window_override_the_preset_and_are_noted():
    setup = _parse("""
case: {id: 2021_Caldor, period: H012}
domain: {bbox: [-120.5, 38.5, -120.0, 38.9]}
window: {start: 2021-08-20T06:00Z, end: 2021-08-22T06:00Z}
""")

    assert setup.bbox == (-120.5, 38.5, -120.0, 38.9)
    assert setup.cycles[0].label == "2021082006"
    assert len(setup.notes) == 2


def test_window_in_another_time_zone_is_converted_to_utc():
    setup = _parse("""
domain: {bbox: [-120.5, 38.5, -120.0, 38.9]}
window: {start: "2021-08-19T17:00:00-07:00", end: "2021-08-21T17:00:00-07:00"}
""")

    assert setup.start == datetime(2021, 8, 20, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("window", "message"),
    (
        ("{start: 2021-08-20T00:00, end: 2021-08-22T00:00Z}", "has no time zone"),
        ("{start: 2021-08-20, end: 2021-08-22T00:00Z}", "date without a time"),
        ("{start: 2021-08-22T00:00Z, end: 2021-08-20T00:00Z}", "must be after"),
    ),
)
def test_ambiguous_or_inverted_windows_are_rejected(window, message):
    problems = _problems(f"domain: {{bbox: [-120.5, 38.5, -120.0, 38.9]}}\nwindow: {window}")

    assert any(message in problem for problem in problems)


def test_window_without_a_full_cycle_is_explained():
    problems = _problems(
        "domain: {bbox: [-120.5, 38.5, -120.0, 38.9]}\nwindow: {start: 2021-08-20T00:00Z, end: 2021-08-21T00:00Z}"
    )

    assert any("no 00/06/12/18Z cycle with a full 48 h forecast" in problem for problem in problems)


def test_hrrr_v3_cycles_are_clamped_to_their_36_hour_horizon():
    setup = _parse(
        "domain: {bbox: [-120.5, 38.5, -120.0, 38.9]}\n"
        "window: {start: 2020-09-15T00:00Z, end: 2020-09-16T12:00Z}\n"
        "model: {cycle_hours: [0]}"
    )

    assert [(cycle.label, cycle.horizon_hours) for cycle in setup.cycles] == [("2020091500", 36)]


def test_explicit_cycles_are_used_as_given():
    setup = _parse(
        "case: {id: 2021_Caldor, period: H012}\nmodel: {cycles: [2021-08-20T06:00Z, 2021-08-20T00:00Z]}"
    )

    assert [cycle.label for cycle in setup.cycles] == ["2021082000", "2021082006"]


def test_inline_token_is_rejected_with_the_keys_hint():
    problems = _problems("case: {id: 2021_Caldor, period: H012}\nobservations: {token: abc123}")

    assert any("firebench keys set synoptic" in problem for problem in problems)
    assert not any("abc123" in problem for problem in problems)


def test_every_problem_is_reported_at_once():
    problems = _problems("""
case: {id: 2021_Caldor, period: H999}
observations: {h5: missing.h5, synoptic_json: missing.json}
model: {name: GFS}
benchmark: {cadences: [2], obs_tolerance_min: 45, min_coverage: 2}
extra: 1
""")

    joined = "\n".join(problems)
    for expected in (
        "unknown top-level key 'extra'",
        "unknown Caldor period 'H999'",
        "mutually exclusive",
        "observations.h5 does not exist",
        "model.name 'GFS' is not supported",
        "benchmark.cadences",
        "min_coverage must be between 0 and 1",
    ):
        assert expected in joined, expected


def test_tolerance_must_stay_below_half_the_cadence():
    problems = _problems("case: {id: 2021_Caldor, period: H012}\nbenchmark: {obs_tolerance_min: 30}")

    assert any("below half the shortest cadence" in problem for problem in problems)


def test_qc_mode_cannot_be_overridden():
    problems = _problems("case: {id: 2021_Caldor, period: H012}\nqc: {overrides: {mode: review}}")

    assert any("conservative_auto" in problem for problem in problems)


def test_bbox_outside_the_hrrr_grid_is_rejected():
    problems = _problems(
        "domain: {bbox: [-158.0, 21.0, -157.5, 21.5]}\nwindow: {start: 2021-08-20T00:00Z, end: 2021-08-22T00:00Z}"
    )

    assert any("not fully inside the HRRR CONUS grid" in problem for problem in problems)


def test_relative_paths_resolve_against_the_setup_file(tmp_path):
    saved = tmp_path / "data" / "wx.json"
    saved.parent.mkdir()
    saved.write_text("{}")

    setup = _parse(
        "case: {id: 2021_Caldor, period: H012}\nobservations: {synoptic_json: data/wx.json}",
        path=tmp_path / "setup.yml",
    )

    assert setup.observations.synoptic_json == saved
    assert setup.observations.source == "synoptic_json"


def test_fetch_window_and_bbox_include_the_qc_context_and_margin():
    setup = _parse(
        "case: {id: 2021_Caldor, period: H012}\nobservations: {context_hours: 6, bbox_margin_deg: 0.5}"
    )

    assert setup.fetch_window == (
        datetime(2021, 8, 19, 18, tzinfo=UTC),
        datetime(2021, 8, 22, 6, tzinfo=UTC),
    )
    assert setup.fetch_bbox == pytest.approx((-121.3, 37.9, -119.2, 39.5))


def test_section_hash_changes_with_the_section_only():
    first = _parse("case: {id: 2021_Caldor, period: H012}\nbenchmark: {min_coverage: 0.5}")
    second = _parse("case: {id: 2021_Caldor, period: H012}\nbenchmark: {min_coverage: 0.6}")

    assert first.section_hash("benchmark") != second.section_hash("benchmark")
    assert first.section_hash("qc") == second.section_hash("qc")


@pytest.mark.parametrize("kwargs", ({"case": "2021_Caldor", "period": "H012"}, {}))
def test_setup_template_is_a_valid_setup(kwargs):
    setup = _parse(wx_setup.setup_template("demo", **kwargs))

    assert setup.cycles


def test_observation_origin_is_normalized():
    setup = _parse("case: {id: 2021_Caldor, period: H012}\nobservations: {origin: 'https://EXAMPLE.com/'}")
    assert setup.observations.origin == "https://example.com"


@pytest.mark.parametrize("origin", ["https://example.com/path", "", "https://*.example.com"])
def test_invalid_observation_origin_is_setup_error(origin):
    assert any(
        "observations.origin" in problem
        for problem in _problems(
            f"case: {{id: 2021_Caldor, period: H012}}\nobservations: {{origin: '{origin}'}}"
        )
    )
