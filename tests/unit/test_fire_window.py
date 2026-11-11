from datetime import datetime, timedelta, timezone

import h5py
import numpy as np
import pytest

from firebench import standardize as fs
from firebench.benchmarks import fire_case_definition as case_module
from firebench.benchmarks import fire_window as fw

START = datetime(2026, 8, 22, 2, 17, tzinfo=timezone.utc)
END = START + timedelta(hours=24)
FRAME = [-120.6, 38.4, -120.2, 38.8]
FIRE_FRAME = [-120.42, 38.58, -120.38, 38.62]


def _station(h5, name, lat, lon, variables, height=2.0):
    group = h5.create_group(f"time_series/{name}")
    group.attrs["position_lat"] = lat
    group.attrs["position_lon"] = lon
    time = group.create_dataset("time", data=np.arange(3, dtype=float))
    time.attrs["time_origin"] = (START - timedelta(hours=3)).isoformat()
    time.attrs["time_units"] = "hour"
    for variable, units in variables.items():
        dataset = group.create_dataset(variable, data=np.array([1.0, 2.0, 3.0]))
        dataset.attrs["units"] = units
        dataset.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = height
        dataset.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
        dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = 2


@pytest.fixture(name="fragments")
def fixture_fragments(tmp_path):
    """Two pieces of observation: station_A in both, station_B in one, station_FAR outside the frame."""
    paths = []
    for index, stations in enumerate(
        (
            {"station_A": {"air_temperature": "degK"}, "station_FAR": {"air_temperature": "degK"}},
            {"station_A": {"relative_humidity": "%"}, "station_B": {"air_temperature": "degK"}},
        )
    ):
        path = tmp_path / f"fragment-{index}.h5"
        h5 = fs.new_std_file(path, authors="test")
        for name, variables in stations.items():
            lon = -119.0 if name == "station_FAR" else -120.4
            _station(h5, name, 38.6, lon, variables)
        h5.close()
        paths.append(path)
    return paths


@pytest.fixture(name="definition")
def fixture_definition(fragments):
    proposal = fw.propose_window("FW24-1", START, END, FRAME, fire_frame=FIRE_FRAME, std_files=fragments)
    assert proposal["left_out"] == []
    return proposal["definition"]


def _fill(path, definition, lat=(38.5, 38.7), lon=(-120.5, -120.3), span=(START, END)):
    """A model output written on the template: every station value, and an arrival-time field."""
    template = fw.write_window_template(definition, path)
    with h5py.File(template, "a") as h5:
        del h5.attrs[case_module.TEMPLATE_ATTRIBUTE]
        for station in h5["time_series"].values():
            for name, dataset in station.items():
                if name != "time":
                    dataset[...] = 290.0
        group = h5[fw.ARRIVAL_GROUP]
        group.create_dataset("position_lat", data=np.linspace(*lat, 5))
        group.create_dataset("position_lon", data=np.linspace(*lon, 4))
        field = group.create_dataset(fw.ARRIVAL, data=np.full((5, 4), np.nan))
        field.attrs["units"] = "s"
        field.attrs["time_origin"] = START.isoformat()
        group.create_dataset("time", data=np.array([item.isoformat() for item in span], dtype="S32"))
    return template


def _status(report, name):
    return next(item for item in report["families"] if item["family"] == name)


def test_proposal_asks_the_stations_of_the_frame(definition):
    assert fw.check_window(definition) == []
    assert definition["schema"] == "fb-window-v1"
    assert definition["period"] == {"start": "2026-08-22T02:17:00Z", "end": "2026-08-23T02:17:00Z"}
    stations = fw.family(definition, fw.STATIONS)["stations"]
    assert [item["station"] for item in stations] == ["station_A", "station_B"]
    assert stations[0]["variables"] == ["air_temperature", "relative_humidity"]
    assert stations[0]["sensor_heights"] == {"air_temperature": 2.0, "relative_humidity": 2.0}
    assert fw.family(definition, fw.ARRIVAL) == {"family": fw.ARRIVAL, "model_group": fw.ARRIVAL_GROUP}


def test_proposal_without_station_leaves_the_family_out():
    proposal = fw.propose_window("FW24-1", START, END, FRAME)
    assert [item["family"] for item in proposal["definition"]["families"]] == [fw.ARRIVAL]
    assert proposal["left_out"] == [{"family": fw.STATIONS, "reason": "no station is known in the frame"}]
    assert proposal["definition"]["fire_frame"] == FRAME


def test_times_are_round_edges_around_the_period(definition):
    times = fw.window_times(definition)
    assert times[0] == datetime(2026, 8, 22, 2, tzinfo=timezone.utc)
    assert times[-1] == datetime(2026, 8, 23, 3, tzinfo=timezone.utc)
    assert len(times) == 26


@pytest.mark.parametrize(
    "change, problem",
    [
        ({"schema": "fb-case-v1"}, "Unknown schema"),
        ({"period": {"start": "2026-08-23T00:00:00Z", "end": "2026-08-22T00:00:00Z"}}, "ends before"),
        ({"period": {"start": "2026-08-22T00:00:00", "end": "2026-08-23T00:00:00"}}, "UTC offset"),
        ({"frame": [1, 2, 3]}, "four numbers"),
        ({"fire_frame": [-121.0, 38.58, -120.38, 38.62]}, "inside `frame`"),
        ({"parameters": {"set": "other", "version": "1"}}, "Unknown parameter set"),
        ({"families": []}, "asks no family"),
        ({"extra": 1}, "unknown extra"),
    ],
)
def test_check_window_names_the_problem(definition, change, problem):
    problems = fw.check_window({**definition, **change})
    assert any(problem in item for item in problems), problems


def test_check_window_checks_the_stations(definition):
    entry = fw.family(definition, fw.STATIONS)
    broken = {**entry, "cadence_minutes": 7, "stations": [{**entry["stations"][0], "variables": ["snow"]}]}
    problems = fw.check_window({**definition, "families": [broken]})
    assert any("divides a day" in item for item in problems)
    assert any("does not score: snow" in item for item in problems)


def test_definition_is_kept_in_the_template(definition, tmp_path):
    template = fw.write_window_template(definition, tmp_path / "template.h5")
    assert fw.read_window_definition(template) == definition
    with h5py.File(template, "r") as h5:
        assert h5.attrs["window_definition_sha256"] == case_module.definition_sha256(definition)
        series = h5["time_series/station_A"]
        assert series["time"].shape == (26,)
        assert np.isnan(series["air_temperature"][()]).all()
        assert series["air_temperature"].attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == 2.0
        assert "relative_humidity" not in h5["time_series/station_B"]
        assert list(h5[fw.ARRIVAL_GROUP]) == []
    assert case_module.is_template(template)


def test_template_is_not_a_model_output(definition, tmp_path):
    template = fw.write_window_template(definition, tmp_path / "template.h5")
    report = fw.check_model_for_window(definition, template)
    assert (report["accepted"], report["reason"]) == (False, fw.EMPTY_TEMPLATE)


def test_file_that_is_not_standard_is_refused(definition, tmp_path):
    text = tmp_path / "model.h5"
    text.write_text("not hdf5")
    assert fw.check_model_for_window(definition, text)["reason"] == fw.NOT_HDF5
    bare = tmp_path / "bare.h5"
    h5py.File(bare, "w").close()
    assert "not a FireBench standard file" in fw.check_model_for_window(definition, bare)["reason"]


def test_filled_template_enters_every_family(definition, tmp_path):
    report = fw.check_model_for_window(definition, _fill(tmp_path / "model.h5", definition))
    assert report["schema"] == "fb-window-check-v1"
    assert report["accepted"] is True
    assert report["window"]["definition_sha256"] == case_module.definition_sha256(definition)
    assert [item["status"] for item in report["families"]] == ["eligible", "eligible"]
    arrival = _status(report, fw.ARRIVAL)
    assert arrival["label"] == "Fire arrival time"
    assert arrival["frame_coverage"] == 0.25
    assert arrival["grid"] == {"cells": 20, "box": [-120.5, 38.5, -120.3, 38.7]}
    assert "25% of the window's frame" in arrival["notes"][0]
    assert "larger domain is recommended" in arrival["notes"][0]
    assert "evaluation on arrival time is discarded" in arrival["notes"][0]
    stations = _status(report, fw.STATIONS)
    assert [(part["name"], part["stations"], part["covered"]) for part in stations["parts"]] == [
        ("air_temperature", 2, 2),
        ("relative_humidity", 1, 1),
    ]


def test_same_file_gives_the_same_report(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition)
    assert fw.check_model_for_window(definition, model) == fw.check_model_for_window(definition, model)


def test_station_that_lacks_a_time_blocks_its_variable(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition)
    with h5py.File(model, "a") as h5:
        h5["time_series/station_B/air_temperature"][5] = np.nan
    stations = _status(fw.check_model_for_window(definition, model), fw.STATIONS)
    assert stations["status"] == "partial"
    part = stations["parts"][0]
    assert (part["status"], part["covered"]) == ("unavailable", 1)
    assert "first: station_B lacks a value at 1 of the 26 times asked" in part["reason"]
    assert stations["parts"][1]["status"] == "eligible"


def test_units_that_do_not_convert_block_the_station(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition)
    with h5py.File(model, "a") as h5:
        h5["time_series/station_A/relative_humidity"].attrs["units"] = "m/s"
        del h5["time_series/station_A/air_temperature"]
        del h5["time_series/station_B"]
    stations = _status(fw.check_model_for_window(definition, model), fw.STATIONS)
    assert stations["status"] == "unavailable"
    assert stations["reason"] == "No variable is given for every station asked."
    assert "station_A is not in the file" in stations["parts"][0]["reason"]
    assert "has no `units` that convert" in stations["parts"][1]["reason"]


def test_arrival_time_must_cover_the_period(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition, span=(START, END - timedelta(hours=6)))
    arrival = _status(fw.check_model_for_window(definition, model), fw.ARRIVAL)
    assert arrival["status"] == "unavailable"
    assert "not the window's period" in arrival["reason"]
    assert arrival["span"]["end"] == "2026-08-22T20:17:00Z"


def test_arrival_grid_must_hold_the_fire(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition, lon=(-120.3, -120.25))
    arrival = _status(fw.check_model_for_window(definition, model), fw.ARRIVAL)
    assert arrival["status"] == "unavailable"
    assert "does not hold the frame of the fire" in arrival["reason"]


def test_arrival_group_must_be_whole(definition, tmp_path):
    model = _fill(tmp_path / "model.h5", definition)
    with h5py.File(model, "a") as h5:
        del h5[fw.ARRIVAL_GROUP]["time"]
        del h5[fw.ARRIVAL_GROUP][fw.ARRIVAL].attrs["time_origin"]
    arrival = _status(fw.check_model_for_window(definition, model), fw.ARRIVAL)
    assert arrival["reason"] == f"`{fw.ARRIVAL_GROUP}`: lacks `time`."
    with h5py.File(model, "a") as h5:
        h5[fw.ARRIVAL_GROUP].create_dataset(
            "time", data=np.array([START.isoformat(), END.isoformat()], dtype="S32")
        )
    arrival = _status(fw.check_model_for_window(definition, model), fw.ARRIVAL)
    assert "needs `units` of a duration and a `time_origin`" in arrival["reason"]


def test_check_refuses_a_broken_definition(definition, tmp_path):
    with pytest.raises(case_module.CaseDefinitionError, match="ends before"):
        fw.check_model_for_window(
            {**definition, "period": {"start": "2026-08-23T00:00:00Z", "end": "2026-08-22T00:00:00Z"}},
            tmp_path / "model.h5",
        )
