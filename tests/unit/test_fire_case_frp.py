"""The fire radiative power family of the generic cases, on synthetic GOES and VIIRS streams."""

from datetime import datetime, timedelta, timezone

import h5py
import numpy as np
import pytest

from firebench.benchmarks import fire_case_frp
from firebench.benchmarks.fire_case import load_case
from firebench.benchmarks.fire_case_definition import (
    CaseDefinitionError,
    check_case,
    edit_case,
    family,
    propose_case,
)
from firebench.benchmarks.fire_case_parameters import load_parameters
from firebench.benchmarks.fire_case_template import case_requirements, write_model_output_template
from firebench.standardize import fire_detections as fd
from firebench.standardize import new_std_file

START = datetime(2021, 8, 17, tzinfo=timezone.utc)
CALDOR = (-120.8, 38.4, -119.7, 39.0)
# GOES every 10 min from 00:05, no fire until 00:45, 100 MW after. Six VIIRS overpasses of 100 MW,
# one of which saw 40 % of the frame, and one at 03:50 that saw no fire and 30 % of the frame.
GOES_TIMES = [START + timedelta(minutes=5 + 10 * index) for index in range(36)]
GOES_FRP = [0.0 if time <= START + timedelta(minutes=45) else 100.0 for time in GOES_TIMES]
VIIRS_TIMES = [START + timedelta(minutes=minutes) for minutes in (90, 130, 170, 210, 230, 250, 290)]
VIIRS_FRP = [100.0, 100.0, 100.0, 100.0, 0.0, 100.0, 100.0]
VIIRS_FRACTIONS = [1.0, 0.4, 1.0, 1.0, 0.3, 1.0, 1.0]
# The model every 15 min until 05:00, without fire until 00:45, then the band [low, high].
MODEL_TIMES = [START + timedelta(minutes=15 * index) for index in range(21)]


def _naive(times) -> np.ndarray:
    return np.array([time.replace(tzinfo=None) for time in times], dtype="datetime64[ms]")


def _stream(
    h5, stream, satellite, instrument, times, frp, fractions, confidence
):  # pylint: disable=too-many-arguments
    owner = [index for index, value in enumerate(frp) if value > 0]
    count = len(owner)
    starts = _naive(times)
    detections = {
        "time": (fd._seconds_since(starts[owner], START), fd._time_attrs(START)),
        "position_lat": (np.full(count, 38.7), {"units": "degree"}),
        "position_lon": (np.full(count, -120.2), {"units": "degree"}),
        "fire_radiative_power": (np.array([frp[index] for index in owner]), {"units": "MW"}),
        "fire_detection_confidence": (
            np.full(count, confidence[1], dtype=np.int16),
            {"confidence_scale": confidence[0], "_FillValue": -1},
        ),
        "observation_index": (np.array(owner, dtype=np.int32), {}),
    }
    observations = {
        "time": (fd._seconds_since(starts, START), fd._time_attrs(START)),
        "time_end": (fd._seconds_since(starts, START) + 60, fd._time_attrs(START)),
        "observed_fraction": (np.array(fractions, dtype=np.float64), {"units": "1", "method": "swath"}),
    }
    attrs = {
        "satellite": satellite,
        "instrument": instrument,
        **fd._frame_attrs(CALDOR, START, START + timedelta(hours=6)),
    }
    fd._write_stream(h5, stream, attrs, detections, observations, 1)


def _observations(path, extra_stream=False):
    with new_std_file(path, "tester") as h5:
        _stream(h5, "goes17", "GOES-17", "ABI", GOES_TIMES, GOES_FRP, [1.0] * 36, ("goes_fdc_mask", 10))
        _stream(
            h5,
            "viirs_snpp",
            "Suomi NPP",
            "VIIRS",
            VIIRS_TIMES,
            VIIRS_FRP,
            VIIRS_FRACTIONS,
            ("viirs_lnh", 1),
        )
        if extra_stream:
            _stream(h5, "other", "Elsewhere", "XYZ", VIIRS_TIMES, VIIRS_FRP, [1.0] * 7, ("viirs_lnh", 1))
    return path


def _model(path, low=60.0, high=120.0, times=MODEL_TIMES, before=(0.0, 0.0)):
    """The band [low, high] from 00:45 on, ``before`` until then."""
    with new_std_file(path, "tester") as h5:
        group = h5.create_group(fire_case_frp.MODEL_GROUP)
        seconds = np.array([(time - START).total_seconds() for time in times])
        time = group.create_dataset("time", data=seconds)
        time.attrs["time_origin"] = START.isoformat()
        time.attrs["time_units"] = "s"
        fire = np.array([time > START + timedelta(minutes=45) for time in times])
        for name, value, early in (
            (fire_case_frp.LOWER, low, before[0]),
            (fire_case_frp.UPPER, high, before[1]),
        ):
            values = np.where(fire, value, early)
            group.create_dataset(name, data=values * 1e6).attrs["units"] = "W"
    return path


@pytest.fixture(name="obs")
def fixture_obs(tmp_path):
    return _observations(tmp_path / "obs.h5")


def _definition(obs) -> dict:
    return propose_case(obs)["definition"]


def _run(case, model, obs, tmp_path, target="FR"):
    return case.run_benchmark(
        model,
        target,
        obs_data=obs,
        output_json=tmp_path / "result.json",
        score_card_report=tmp_path / "card.pdf",
    )


def _values(result) -> dict:
    return {
        name: value
        for kpi in result["benchmarks"].values()
        for name, value in kpi.items()
        if name != "Score"
    }


def test_a_case_proposes_frp_by_observing_system(obs):
    definition = _definition(obs)

    assert family(definition, "fire_radiative_power") == {
        "family": "fire_radiative_power",
        "periods": ["P01"],
        "systems": {"geostationary": ["goes17"], "polar": ["viirs_snpp"]},
        "frame": list(CALDOR),
        "model_group": "/time_series/fire_total",
    }
    # The period is the span of the observations, which are the file's only data.
    assert definition["periods"][0]["start"] == "2021-08-17T00:05:00Z"
    assert definition["periods"][0]["end"] == "2021-08-17T05:55:00Z"
    assert check_case(definition, obs) == []


def test_a_stream_of_an_instrument_no_system_lists_is_not_scored(tmp_path):
    obs = _observations(tmp_path / "obs.h5", extra_stream=True)

    entry = family(_definition(obs), "fire_radiative_power")

    assert "other" not in [stream for streams in entry["systems"].values() for stream in streams]


def test_the_family_is_left_out_with_its_reason(tmp_path):
    path = tmp_path / "obs.h5"
    with new_std_file(path, "tester") as h5:
        _stream(h5, "other", "Elsewhere", "XYZ", VIIRS_TIMES, VIIRS_FRP, [1.0] * 7, ("viirs_lnh", 1))

    proposal = propose_case(path)

    assert family(proposal["definition"], "fire_radiative_power") is None
    reasons = {item["family"]: item["reason"] for item in proposal["left_out"]}
    assert "XYZ" not in reasons["fire_radiative_power"] and "other" in reasons["fire_radiative_power"]


def test_the_observations_scored_and_the_band_at_their_time(obs, tmp_path):
    model = _model(tmp_path / "model.h5")
    parameters = load_parameters().fire_radiative_power
    period = (START, START + timedelta(hours=6))
    with h5py.File(obs, "r") as obs_h5, h5py.File(model, "r") as model_h5:
        goes = fire_case_frp.frp_pairs(
            model_h5, obs_h5, "goes17", period, CALDOR, "/time_series/fire_total", parameters
        )
        viirs = fire_case_frp.frp_pairs(
            model_h5, obs_h5, "viirs_snpp", period, CALDOR, "/time_series/fire_total", parameters
        )

    # GOES: no detectable fire on either side until 00:45 (5 scans left out); nothing within 15 min of a
    # model time after 05:15 (4 left out). VIIRS: the overpass that saw 40 % of the frame has fire and is
    # scored; the one that saw no fire and 30 % of it is left out.
    assert len(goes.observed) == 27
    assert goes.time[0] == np.datetime64("2021-08-17T00:55:00", "ms")
    # 00:55 is two thirds of the way from 00:45 (0) to 01:00 (60, 120).
    assert goes.lower[0] == pytest.approx(40.0) and goes.upper[0] == pytest.approx(80.0)
    assert goes.upper[-1] == pytest.approx(120.0)
    assert len(viirs.observed) == 6
    assert set(goes.limit) == {50.0} and set(viirs.limit) == {5.0}


def test_a_band_holding_the_observations(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    result = _run(case, _model(tmp_path / "model.h5"), obs, tmp_path)

    values = _values(result)
    # The GOES scan at 00:55 has 100 MW while the model's fire is starting (band 40 to 80, raised to 50
    # to 80 by ABI's detection limit): above, by log10(100 / 80) decades.
    above = np.log10(100 / 80)
    assert values["In-Band Fraction Geostationary"] == pytest.approx(26 / 27)
    assert values["In-Band Fraction Polar Orbiters"] == 1.0
    assert values["In-Band Fraction All"] == pytest.approx(32 / 33)
    assert values["Above-Band Fraction"] == pytest.approx(1 / 33)
    assert values["Below-Band Fraction"] == 0.0
    assert values["Band Log Error Geostationary"] == pytest.approx(above / 27)
    assert values["Band Log Error Polar Orbiters"] == 0.0
    # The log error KPIs follow the others, so the ids of those did not change.
    assert {kpi: next(iter(item)) for kpi, item in result["benchmarks"].items()} == {
        "G-FR01": "In-Band Fraction Geostationary",
        "G-FR02": "In-Band Fraction Polar Orbiters",
        "G-FR03": "In-Band Fraction All",
        "G-FR04": "Above-Band Fraction",
        "G-FR05": "Below-Band Fraction",
        "G-FR06": "Band Log Error Geostationary",
        "G-FR07": "Band Log Error Polar Orbiters",
    }
    assert result["score_card"]["Score Total"] == pytest.approx(
        (100 * 26 / 27 + 100 + 100 * (1 - above / 27) + 100) / 4
    )


def test_a_model_too_strong_is_below_its_band(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    result = _run(case, _model(tmp_path / "model.h5", low=150.0, high=300.0), obs, tmp_path)

    values = _values(result)
    # Only the GOES scan at 00:55 (band 100 to 200) holds its 100 MW; the others are 150 to 300.
    below = np.log10(150 / 100)
    assert values["In-Band Fraction Geostationary"] == pytest.approx(1 / 27)
    assert values["In-Band Fraction Polar Orbiters"] == 0.0
    assert values["Below-Band Fraction"] == pytest.approx(32 / 33)
    assert values["Above-Band Fraction"] == 0.0
    assert values["Band Log Error Geostationary"] == pytest.approx(26 * below / 27)
    assert values["Band Log Error Polar Orbiters"] == pytest.approx(below)
    # The group weighs the two systems and their two KPIs equally; the pooled and side KPIs weigh 0.
    assert result["score_card"]["Score Total"] == pytest.approx(
        (100 / 27 + 0 + 100 * (1 - 26 * below / 27) + 100 * (1 - below)) / 4
    )


def test_a_log_error_counts_ten_times_off_as_the_cap(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    result = _run(case, _model(tmp_path / "model.h5", low=0.5, high=1.0), obs, tmp_path)

    # 100 MW against a band raised to the detection limit (50 MW for ABI, 5 MW for VIIRS): log10(2)
    # decades for GOES, more than the cap of 1 for VIIRS.
    values = _values(result)
    assert values["Band Log Error Geostationary"] == pytest.approx(np.log10(2))
    assert values["Band Log Error Polar Orbiters"] == 1.0
    assert values["In-Band Fraction Geostationary"] == 0.0


def test_a_system_with_too_few_observations_is_left_out(obs, tmp_path):
    case = load_case(_definition(obs), obs)
    model = _model(tmp_path / "model.h5", times=MODEL_TIMES[:13])

    result = _run(case, model, obs, tmp_path)

    # The model stops at 03:00: the VIIRS overpasses kept are 01:30, 02:10, and 02:50.
    assert "In-Band Fraction Polar Orbiters" not in _values(result)
    assert "Band Log Error Polar Orbiters" not in _values(result)
    assert _values(result)["In-Band Fraction Geostationary"] == pytest.approx(14 / 15)


def test_a_band_upside_down_is_refused(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    with pytest.raises(ValueError, match="fire_radiative_power_lower <= fire_radiative_power_upper"):
        _run(case, _model(tmp_path / "model.h5", low=120.0, high=60.0), obs, tmp_path)


def test_period_targets_take_the_flag_f(obs):
    case = load_case(_definition(obs), obs)

    assert case.resolve_benchmark_target("p01_f") == "P01_F"
    assert case.describe_available_targets()["kpi_groups"]["F"] == "Fire Radiative Power"
    assert "FR" in case.describe_available_targets()["standalone_targets"]


def test_check_case_refuses_a_stream_in_the_wrong_system(obs):
    definition = _definition(obs)
    family(definition, "fire_radiative_power")["systems"] = {"geostationary": ["goes17", "viirs_snpp"]}

    problems = check_case(definition, obs)

    assert any(
        "viirs_snpp (VIIRS) is not of the observing system geostationary" in item for item in problems
    )
    with pytest.raises(CaseDefinitionError):
        load_case(definition, obs)


def test_an_added_period_is_scored_for_frp(obs):
    edited = edit_case(
        _definition(obs), obs, add_periods=[(START + timedelta(hours=1), START + timedelta(hours=3))]
    )

    assert family(edited, "fire_radiative_power")["periods"] == ["P01", "P02"]
    assert check_case(edited, obs) == []


def test_the_template_and_the_requirements_name_the_frp_band(obs, tmp_path):
    definition = _definition(obs)

    template = write_model_output_template(obs, definition, tmp_path / "template.h5")
    requirements = case_requirements(definition, obs)

    with h5py.File(template, "r") as h5:
        group = h5[fire_case_frp.MODEL_GROUP]
        assert list(group) == []
        assert [group.attrs[key] for key in fire_case_frp.FRAME_KEYS] == list(CALDOR)
        assert "fire_detections" not in h5.get("unstructured", {})
    (item,) = [entry for entry in requirements["requirements"] if entry["name"] == "R_FR"]
    assert item["family"] == "fire_radiative_power"
    assert set(item["datasets"]) == {
        "/time_series/fire_total/time",
        "/time_series/fire_total/fire_radiative_power_lower",
        "/time_series/fire_total/fire_radiative_power_upper",
    }


# ---------------------------
# Values for figures
# ---------------------------
def _frp_values(obs, model, definition=None):
    case = load_case(definition or _definition(obs), obs)
    with h5py.File(obs, "r") as obs_h5, h5py.File(model, "r") as model_h5:
        return case.frp_values(model_h5, obs_h5)


@pytest.mark.parametrize("band", [(60.0, 120.0), (150.0, 300.0), (20.0, 50.0)])
def test_frp_values_give_the_positions_the_kpis_count(obs, tmp_path, band):
    model = _model(tmp_path / "model.h5", low=band[0], high=band[1])
    definition = edit_case(
        _definition(obs), obs, add_periods=[(START + timedelta(hours=1), START + timedelta(hours=3))]
    )
    case = load_case(definition, obs)

    values = _frp_values(obs, model, definition)

    observations = values["observations"]
    for period in values["periods"]:
        folder = tmp_path / period["period"]
        folder.mkdir()
        result = _run(case, model, obs, folder, target=f"{period['period']}_F")
        expected = _values(result)
        position = observations["position"][period["scored"]]
        assert np.all(observations["kept"][period["scored"]])
        for name, where in (
            ("In-Band Fraction All", "in"),
            ("Above-Band Fraction", "above"),
            ("Below-Band Fraction", "below"),
        ):
            assert np.mean(position == where) == pytest.approx(expected[name])
        for system, label in (("polar", "Polar Orbiters"), ("geostationary", "Geostationary")):
            scored = period["scored"][observations["system"][period["scored"]] == system]
            if f"In-Band Fraction {label}" in expected:
                assert np.mean(observations["position"][scored] == "in") == pytest.approx(
                    expected[f"In-Band Fraction {label}"]
                )
                assert np.mean(observations["log_error"][scored]) == pytest.approx(
                    expected[f"Band Log Error {label}"]
                )


def test_frp_values_say_why_an_observation_is_not_scored(obs, tmp_path):
    values = _frp_values(obs, _model(tmp_path / "model.h5"))

    observations = values["observations"]
    reasons = dict(zip(observations["time"].tolist(), observations["reason"]))
    ok = dict(zip(observations["time"].tolist(), observations["observation_ok"].tolist()))
    early, late, partial_fire, partial_none = (
        np.datetime64(f"2021-08-17T{clock}", "ms").item() for clock in ("00:05", "05:25", "02:10", "03:50")
    )
    assert reasons[early] == "no detectable fire on either side" and ok[early]
    assert reasons[late] == "no model output time within 900 s" and ok[late]
    # A sensor that saw a part of its frame and fire there is scored; one that saw no fire is not.
    assert reasons[partial_fire] is None and ok[partial_fire]
    assert reasons[partial_none] == "no fire seen, and it saw 30% of its frame, less than 90%"
    assert not ok[partial_none]
    scored = observations["kept"]
    assert all(reason is None for reason, kept in zip(observations["reason"], scored) if kept)
    assert set(observations["position"][~scored]) == {""}
    assert np.all(np.isnan(observations["log_error"][~scored]))
    assert set(observations["limit"][observations["system"] == "geostationary"]) == {50.0}
    assert [system["name"] for system in values["systems"]] == ["geostationary", "polar"]
    assert values["systems"][0]["label"] == "Geostationary"
    assert set(observations["satellite"]) == {"GOES-17", "Suomi NPP"}
    # The model's band at its own times, in MW.
    assert values["model"]["upper"].max() == pytest.approx(120.0)
    assert len(values["model"]["time"]) == len(MODEL_TIMES)


@pytest.mark.parametrize(
    ("before", "reason", "position"),
    [
        # Both under ABI's 50 MW: neither side has detectable fire.
        ((10.0, 40.0), "no detectable fire on either side", ""),
        # The band reaches above the limit and its lower bound is under it: 0 MW is in.
        ((20.0, 80.0), None, "in"),
        # The whole band is above the limit: 0 MW is below it.
        ((60.0, 120.0), None, "below"),
    ],
)
def test_no_fire_seen_is_compared_at_the_detection_limit(obs, tmp_path, before, reason, position):
    values = _frp_values(obs, _model(tmp_path / "model.h5", before=before))

    observations = values["observations"]
    index = observations["time"].tolist().index(np.datetime64("2021-08-17T00:15", "ms").item())
    assert observations["frp_total"][index] == 0.0
    assert observations["reason"][index] == reason
    assert observations["position"][index] == position
