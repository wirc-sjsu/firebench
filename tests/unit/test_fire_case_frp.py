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
# GOES every 10 min from 00:05, no fire until 00:45, 100 MW after. Five VIIRS overpasses of 100 MW
# and one that saw 40 % of the frame.
GOES_TIMES = [START + timedelta(minutes=5 + 10 * index) for index in range(36)]
GOES_FRP = [0.0 if time <= START + timedelta(minutes=45) else 100.0 for time in GOES_TIMES]
VIIRS_TIMES = [START + timedelta(minutes=minutes) for minutes in (90, 130, 170, 210, 250, 290)]
VIIRS_FRACTIONS = [1.0, 0.4, 1.0, 1.0, 1.0, 1.0]
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
            [100.0] * 6,
            VIIRS_FRACTIONS,
            ("viirs_lnh", 1),
        )
        if extra_stream:
            _stream(h5, "other", "Elsewhere", "XYZ", VIIRS_TIMES, [100.0] * 6, [1.0] * 6, ("viirs_lnh", 1))
    return path


def _model(path, low=60.0, high=120.0, times=MODEL_TIMES):
    with new_std_file(path, "tester") as h5:
        group = h5.create_group(fire_case_frp.MODEL_GROUP)
        seconds = np.array([(time - START).total_seconds() for time in times])
        time = group.create_dataset("time", data=seconds)
        time.attrs["time_origin"] = START.isoformat()
        time.attrs["time_units"] = "s"
        fire = np.array([time > START + timedelta(minutes=45) for time in times])
        for name, value in ((fire_case_frp.LOWER, low), (fire_case_frp.UPPER, high)):
            values = np.where(fire, value, 0.0)
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
        _stream(h5, "other", "Elsewhere", "XYZ", VIIRS_TIMES, [100.0] * 6, [1.0] * 6, ("viirs_lnh", 1))

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

    # GOES: no fire on either side until 00:45 (5 scans left out); nothing within 15 min of a model time
    # after 05:15 (4 left out). VIIRS: the overpass that saw 40 % of the frame is left out.
    assert len(goes.observed) == 27
    assert goes.time[0] == np.datetime64("2021-08-17T00:55:00", "ms")
    # 00:55 is two thirds of the way from 00:45 (0) to 01:00 (60, 120).
    assert goes.lower[0] == pytest.approx(40.0) and goes.upper[0] == pytest.approx(80.0)
    assert goes.upper[-1] == pytest.approx(120.0)
    assert len(viirs.observed) == 5


def test_a_band_holding_the_observations(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    result = _run(case, _model(tmp_path / "model.h5"), obs, tmp_path)

    values = _values(result)
    # The GOES scan at 00:55 has 100 MW while the model's fire is starting (band 40 to 80): above.
    assert values["In-Band Fraction Geostationary"] == pytest.approx(26 / 27)
    assert values["In-Band Fraction Polar Orbiters"] == 1.0
    assert values["In-Band Fraction All"] == pytest.approx(31 / 32)
    assert values["Above-Band Fraction"] == pytest.approx(1 / 32)
    assert values["Below-Band Fraction"] == 0.0
    assert set(result["benchmarks"]) == {f"G-FR{index:02d}" for index in range(1, 6)}
    assert result["score_card"]["Score Total"] == pytest.approx((100 * 26 / 27 + 100) / 2)


def test_a_model_too_strong_is_below_its_band(obs, tmp_path):
    case = load_case(_definition(obs), obs)

    result = _run(case, _model(tmp_path / "model.h5", low=150.0, high=300.0), obs, tmp_path)

    values = _values(result)
    # Only the GOES scan at 00:55 (band 100 to 200) holds its 100 MW.
    assert values["In-Band Fraction Geostationary"] == pytest.approx(1 / 27)
    assert values["In-Band Fraction Polar Orbiters"] == 0.0
    assert values["Below-Band Fraction"] == pytest.approx(31 / 32)
    assert values["Above-Band Fraction"] == 0.0
    # The group weighs the two systems equally; the pooled and side KPIs weigh 0.
    assert result["score_card"]["Score Total"] == pytest.approx(100 / 27 / 2)


def test_a_system_with_too_few_observations_is_left_out(obs, tmp_path):
    case = load_case(_definition(obs), obs)
    # The model stops at 03:00: the VIIRS overpasses kept are 01:30 and 02:50.
    model = _model(tmp_path / "model.h5", times=MODEL_TIMES[:13])

    result = _run(case, model, obs, tmp_path)

    assert "In-Band Fraction Polar Orbiters" not in _values(result)
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
