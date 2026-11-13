import hashlib
import json
from datetime import datetime, timedelta, timezone

import geopandas as gpd
import h5py
import numpy as np
import pytest
from shapely.geometry import Point

from firebench import standardize as fs
from firebench import tools as ft
from firebench.benchmarks import fire_case_definition as case_module
from firebench.benchmarks import fire_window as fw
from firebench.benchmarks import fire_window_scoring as fws
from firebench.benchmarks import wx_common as wxc

START = datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=48)
AFTER = START + timedelta(hours=6)
FRAME = [-120.6, 38.4, -120.2, 38.8]
FIRE_FRAME = [-120.41, 38.59, -120.39, 38.61]
CENTRE = (-120.4, 38.6)
SPEED = 0.02 / (12 * 3600)  # the fire's radius, in degrees per second
STATIONS = {
    "station_A": ["air_temperature", "wind_direction", "wind_speed"],
    "station_B": ["air_temperature", "wind_direction"],
}


def _hours(time):
    return (time - START).total_seconds() / 3600


def _temperature(hours):
    return 10.0 + hours


def _direction(hours):
    return (350.0 + 20.0 * hours) % 360.0


def _observation(path, hours, perimeter_hours=(), absolute=False):
    """Observations until ``hours`` after the opening: two stations at uneven times, perimeters of discs."""
    h5 = fs.new_std_file(path, authors="test")
    for number, (name, variables) in enumerate(STATIONS.items()):
        group = h5.create_group(f"time_series/{name}")
        group.attrs["position_lat"] = 38.6
        group.attrs["position_lon"] = -120.4 + 0.01 * number
        minutes = np.arange(-17, hours * 60 + 1, 17.0) if number == 0 else np.arange(0, hours * 60, 23.0)
        if absolute:
            stamps = [(START + timedelta(minutes=float(item))).isoformat() for item in minutes]
            group.create_dataset("time", data=np.array(stamps, dtype="S32"))
        else:
            time = group.create_dataset("time", data=minutes)
            time.attrs["time_origin"] = START.isoformat()
            time.attrs["time_units"] = "min"
        for variable in variables:
            function = {"wind_direction": _direction, "wind_speed": lambda hours: 5.0 + 0 * hours}.get(
                variable, _temperature
            )
            unit = {"wind_direction": "degree", "wind_speed": "m/s"}.get(variable, "degC")
            dataset = group.create_dataset(variable, data=function(minutes / 60))
            dataset.attrs["units"] = unit
            dataset.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = 2.0
            dataset.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
            dataset.attrs[fs.SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = 2
    for hour in perimeter_hours:
        disc = Point(*CENTRE).buffer(SPEED * hour * 3600, 32)
        kml = path.parent / f"perimeter_{hour}h.kml"
        gpd.GeoDataFrame(geometry=[disc], crs="EPSG:4326").to_file(
            kml, driver="KML", layer="fire_perimeter"
        )
        group = h5.create_group(f"polygons/perimeter_{hour}h")
        group.attrs["rel_path"] = kml.name
        group.attrs["sha256"] = ft.calculate_sha256(kml)
        group.attrs["file_size_bytes"] = kml.stat().st_size
        group.attrs["time"] = (START + timedelta(hours=hour)).isoformat()
    h5.close()
    return path


@pytest.fixture(name="observed_24h")
def fixture_observed_24h(tmp_path):
    """Observations until 24 h: perimeters at 2 h (before the reception), 12 h and 24 h."""
    return _observation(tmp_path / "obs24" / "obs24.h5", 24, (2, 12, 24))


@pytest.fixture(name="observed_6h")
def fixture_observed_6h(tmp_path):
    return _observation(tmp_path / "obs6" / "obs6.h5", 6)


@pytest.fixture(name="definition")
def fixture_definition(observed_24h):
    proposal = fw.propose_window(
        "FW48-1", START, END, FRAME, fire_frame=FIRE_FRAME, std_files=[observed_24h]
    )
    assert proposal["left_out"] == []
    return proposal["definition"]


def _model(path, definition, delay_hours=0.0, lon=(-120.5, -120.3), without=()):
    """A model output: the template filled with series that are linear in time, and a cone of fire."""
    template = fw.write_window_template(definition, path)
    with h5py.File(template, "a") as h5:
        del h5.attrs[case_module.TEMPLATE_ATTRIBUTE]
        for name in without:
            del h5["time_series"][name]
        for station in h5["time_series"].values():
            hours = station["time"][()] / 60
            for name, dataset in station.items():
                if name != "time":
                    dataset[...] = {"wind_direction": _direction, "wind_speed": lambda x: 5.0 + 0 * x}.get(
                        name, _temperature
                    )(hours)
        group = h5[fw.ARRIVAL_GROUP]
        lat, lons = np.linspace(38.5, 38.7, 201), np.linspace(*lon, 201)
        group.create_dataset("position_lat", data=lat)
        group.create_dataset("position_lon", data=lons)
        radius = np.hypot(lons[None, :] - CENTRE[0], lat[:, None] - CENTRE[1])
        field = group.create_dataset(fw.ARRIVAL, data=radius / SPEED + delay_hours * 3600)
        field.attrs["units"] = "s"
        field.attrs["time_origin"] = START.isoformat()
        group.create_dataset("time", data=np.array([START.isoformat(), END.isoformat()], dtype="S32"))
    return template


@pytest.fixture(name="model")
def fixture_model(tmp_path, definition):
    return _model(tmp_path / "model.h5", definition)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _family(report, name):
    return next(item for item in report["families"] if item["family"] == name)


def _kpi(result, name):
    return next((item for item in result["benchmarks"].values() if name in item), None)


def _score(tmp_path, definition, model, observed, after=AFTER, tag="run"):
    prepared = tmp_path / f"{tag}.h5"
    report = fws.prepare_window_model(definition, model, observed, prepared, after=after)
    result = fws.score_window(
        definition,
        prepared,
        observed,
        after=after,
        output_json=tmp_path / f"{tag}.json",
        score_card_report=tmp_path / f"{tag}.pdf",
    )
    return report, result, prepared


# ---------------------------
# The burnt area
# ---------------------------
def test_burnt_area_of_a_cone_is_the_disc():
    lon, lat = np.linspace(-1, 1, 401), np.linspace(-1, 1, 401)
    field = np.hypot(lon[None, :], lat[:, None]) * 100.0  # arrival time grows with the distance
    polygons = fws.burnt_area_polygons(field, lon, lat, 50.0)
    assert str(polygons.crs) == "EPSG:4326"
    area = sum(polygon.area for polygon in polygons.geometry)
    assert area == pytest.approx(np.pi * 0.5**2, rel=0.01)


def test_burnt_area_has_holes_and_leaves_out_what_is_not_burnt():
    lon, lat = np.linspace(-1, 1, 101), np.linspace(-1, 1, 101)
    radius = np.hypot(lon[None, :], lat[:, None])
    field = np.where(radius < 0.2, np.nan, radius)  # the fire did not arrive inside 0.2
    polygons = fws.burnt_area_polygons(field, lon, lat, 0.6)
    assert len(polygons) == 1
    assert len(polygons.geometry[0].interiors) == 1
    assert polygons.geometry[0].area == pytest.approx(np.pi * (0.6**2 - 0.2**2), rel=0.05)
    assert fws.burnt_area_polygons(field, lon, lat, -1.0).empty


def test_burnt_area_takes_grids_of_positions():
    lon, lat = np.meshgrid(np.linspace(-1, 1, 51), np.linspace(-1, 1, 51))
    field = np.hypot(lon, lat)
    assert len(fws.burnt_area_polygons(field, lon, lat, 0.5)) == 1
    with pytest.raises(ValueError, match="same shape"):
        fws.burnt_area_polygons(field, lon[:10], lat[:10], 0.5)


# ---------------------------
# Prepare
# ---------------------------
def test_station_series_are_interpolated_to_the_observed_times(tmp_path, definition, model, observed_24h):
    prepared = tmp_path / "prepared.h5"
    report = fws.prepare_window_model(definition, model, observed_24h, prepared, after=AFTER)
    assert report["schema"] == "fb-window-prepared-v1"
    assert report["after"] == "2026-08-22T06:00:00Z"
    assert report["observed_until"] == "2026-08-23T00:00:00Z"
    stations = _family(report, fw.STATIONS)
    assert stations["status"] == "made"
    assert [(part["name"], part["stations"], part["made"]) for part in stations["parts"]] == [
        ("air_temperature", 2, 2),
        ("wind_speed", 1, 1),
        ("wind_direction", 2, 2),
    ]
    with h5py.File(observed_24h, "r") as obs, h5py.File(prepared, "r") as made:
        # The sample 17 min before the opening is not in the window so far.
        assert made["time_series/station_A/time"].shape[0] == obs["time_series/station_A/time"].shape[0] - 1
        minutes = made["time_series/station_A/time"][()]
        assert minutes[0] == 0.0 and made["time_series/station_A/time"].attrs["time_units"] == "min"
        hours = minutes / 60
        np.testing.assert_allclose(made["time_series/station_A/air_temperature"][()], _temperature(hours))
        # Along the shortest arc (350 to 10 degrees goes through 0, not 180), in [0, 360).
        direction = made["time_series/station_B/wind_direction"][()]
        np.testing.assert_allclose(direction, _direction(made["time_series/station_B/time"][()] / 60))
        assert direction.min() >= 0 and direction.max() < 360
        assert made["time_series/station_A/air_temperature"].attrs["units"] == "degC"
        assert made["time_series/station_A/air_temperature"].attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] == 2.0


def test_absolute_observed_times_are_kept_as_they_are(tmp_path):
    observed = _observation(tmp_path / "abs" / "obs.h5", 24, (12,), absolute=True)
    proposal = fw.propose_window("FW48-1", START, END, FRAME, fire_frame=FIRE_FRAME, std_files=[observed])
    model = _model(tmp_path / "model.h5", proposal["definition"])
    prepared = tmp_path / "prepared.h5"
    fws.prepare_window_model(proposal["definition"], model, observed, prepared, after=AFTER)
    with h5py.File(observed, "r") as obs, h5py.File(prepared, "r") as made:
        assert made["time_series/station_B/time"][0] == obs["time_series/station_B/time"][0]
        assert made["time_series/station_B/time"].dtype == obs["time_series/station_B/time"].dtype


def test_nothing_is_extrapolated_and_no_nan_is_written(tmp_path, definition, model, observed_24h):
    with h5py.File(model, "a") as h5:
        station = h5["time_series/station_B"]
        station["air_temperature"][10:] = np.nan  # the model stops at 09:00 for this variable
    report = fws.prepare_window_model(definition, model, observed_24h, tmp_path / "prepared.h5")
    part = _family(report, fw.STATIONS)["parts"][0]
    assert (part["name"], part["made"]) == ("air_temperature", 1)
    assert part["left_out"][0]["station"] == "station_B"
    assert "not the observed times" in part["left_out"][0]["reason"]
    assert _family(report, fw.STATIONS)["status"] == "partial"
    with h5py.File(tmp_path / "prepared.h5", "r") as made:
        assert "air_temperature" not in made["time_series/station_B"]
        assert "wind_direction" in made["time_series/station_B"]
        for station in made["time_series"].values():
            for name, dataset in station.items():
                assert not np.isnan(dataset[()]).any(), name


def test_a_step_over_the_limit_where_the_observations_need_it_is_left_out(
    tmp_path, definition, model, observed_24h
):
    with h5py.File(model, "a") as h5:
        h5["time_series/station_A/wind_speed"][10:12] = np.nan  # a step of 3 h, from 09:00 to 12:00
    report = fws.prepare_window_model(definition, model, observed_24h, tmp_path / "prepared.h5")
    part = next(item for item in _family(report, fw.STATIONS)["parts"] if item["name"] == "wind_speed")
    assert part["made"] == 0
    assert "has a step of 180 min where the observations need it, over the 60 min allowed" in (
        part["left_out"][0]["reason"]
    )


def test_perimeters_are_cut_after_the_reception_and_the_starting_state_is_named(
    tmp_path, definition, model, observed_24h
):
    prepared = tmp_path / "prepared.h5"
    report = fws.prepare_window_model(definition, model, observed_24h, prepared, after=AFTER)
    perimeters = _family(report, fw.ARRIVAL)
    assert perimeters["status"] == "made" and perimeters["made"] == 2
    assert [item["time"] for item in perimeters["target"]] == [
        "2026-08-22T12:00:00Z",
        "2026-08-23T00:00:00Z",
    ]
    assert perimeters["starting_state"] == {
        "path": "/polygons/perimeter_2h",
        "time": "2026-08-22T02:00:00Z",
    }
    with h5py.File(prepared, "r") as made:
        assert sorted(made["polygons"]) == ["perimeter_12h", "perimeter_24h"]
        assert fs.validate_h5_referenced_files(made) == (True, None)
        assert made["polygons/perimeter_12h"].attrs["time"] == "2026-08-22T12:00:00+00:00"
    burnt = gpd.read_file(tmp_path / "prepared_perimeters" / "perimeter_24h.kml", driver="KML")
    assert burnt.to_crs(epsg=5070).area.sum() > 0


def test_perimeters_are_not_made_without_enough_of_them(tmp_path, definition, observed_6h):
    model = _model(tmp_path / "model.h5", definition)
    report = fws.prepare_window_model(definition, model, observed_6h, tmp_path / "prepared.h5", after=AFTER)
    perimeters = _family(report, fw.ARRIVAL)
    assert perimeters["status"] == "not_made"
    assert "0 perimeter(s) after 2026-08-22T06:00:00Z; a window needs at least 1" in perimeters["reason"]
    assert perimeters["starting_state"] is None
    assert not (tmp_path / "prepared_perimeters").exists()


def test_a_perimeter_outside_the_grid_discards_the_family(tmp_path, definition, observed_24h):
    model = _model(tmp_path / "model.h5", definition, lon=(-120.42, -120.3))
    report = fws.prepare_window_model(
        definition, model, observed_24h, tmp_path / "prepared.h5", after=AFTER
    )
    perimeters = _family(report, fw.ARRIVAL)
    assert perimeters["status"] == "not_made"
    assert "perimeter of 2026-08-23T00:00:00Z is outside the model's grid" in perimeters["reason"]
    assert _family(report, fw.STATIONS)["status"] == "made"


def test_same_inputs_give_the_same_report_and_perimeters(tmp_path, definition, model, observed_24h):
    reports = [
        fws.prepare_window_model(
            definition, model, observed_24h, tmp_path / name / "prepared.h5", after=AFTER
        )
        for name in ("one", "two")
    ]
    assert reports[0] == reports[1]
    for hour in (12, 24):
        files = [
            tmp_path / name / "prepared_perimeters" / f"perimeter_{hour}h.kml" for name in ("one", "two")
        ]
        assert files[0].read_bytes() == files[1].read_bytes()


def test_the_files_given_are_not_changed(tmp_path, definition, model, observed_24h):
    before = [_sha(model), _sha(observed_24h)]
    _score(tmp_path, definition, model, observed_24h)
    assert [_sha(model), _sha(observed_24h)] == before


def test_files_that_cannot_be_prepared_from_are_refused(tmp_path, definition, model, observed_24h):
    template = fw.write_window_template(definition, tmp_path / "template.h5")
    with pytest.raises(case_module.CaseDefinitionError, match="window template"):
        fws.prepare_window_model(definition, template, observed_24h, tmp_path / "a.h5")
    with pytest.raises(case_module.CaseDefinitionError, match="model-output template"):
        fws.prepare_window_model(definition, model, template, tmp_path / "b.h5")
    text = tmp_path / "text.h5"
    text.write_text("not hdf5")
    with pytest.raises(ValueError, match="not a readable HDF5"):
        fws.prepare_window_model(definition, model, text, tmp_path / "c.h5")
    with pytest.raises(ValueError, match="`after` is outside"):
        fws.prepare_window_model(
            definition, model, observed_24h, tmp_path / "d.h5", after=START - timedelta(1)
        )
    with pytest.raises(ValueError, match="UTC offset"):
        fws.prepare_window_model(
            definition, model, observed_24h, tmp_path / "e.h5", after=datetime(2026, 8, 22, 6)
        )


def test_observations_that_end_before_the_opening_are_refused(tmp_path, definition, model):
    early = _observation(tmp_path / "early" / "obs.h5", 6)
    late = {**definition, "period": {"start": "2026-08-30T00:00:00Z", "end": "2026-08-31T00:00:00Z"}}
    with pytest.raises(ValueError, match="no observation after the window opens"):
        fws.prepare_window_model(late, model, early, tmp_path / "prepared.h5")


# ---------------------------
# Score
# ---------------------------
def test_six_hours_score_the_stations_and_leave_the_perimeters_null(
    tmp_path, definition, model, observed_6h
):
    report, result, _ = _score(tmp_path, definition, model, observed_6h)
    assert _family(report, fw.ARRIVAL)["status"] == "not_made"
    block = result["window"]
    assert block["observed_until"] == "2026-08-22T05:57:00Z"
    assert block["observed_share"] == round(5.95 / 48, 4)
    assert block["families"][0]["status"] == "null"
    assert "0 observed perimeter(s)" in block["families"][0]["reason"]
    stations = block["families"][1]
    assert stations["status"] == "scored"
    assert stations["stations"]["air_temperature"] == {"asked": 2, "given": 2}
    assert stations["stations"]["wind_speed"] == {"asked": 1, "given": 1}
    assert stations["observations"]["air_temperature"]["P01"] == {"stations": 2, "samples": 22 + 16}
    assert "P02" not in stations["observations"]["air_temperature"]
    # The model is linear in time, so the interpolated series is the observed one.
    mae = _kpi(result, "Air temp MAE mean P01 TSO")
    assert mae["Air temp MAE mean P01 TSO"] == pytest.approx(0.0, abs=1e-9)
    assert mae["Score"] == pytest.approx(100.0)
    assert not any("Fire Perimeters" in key for key in result["score_card"])
    assert (tmp_path / "run.pdf").exists() and (tmp_path / "run.json").exists()


def test_a_day_scores_the_perimeters_after_the_reception(tmp_path, definition, model, observed_24h):
    _, result, _ = _score(tmp_path, definition, model, observed_24h)
    block = result["window"]
    assert block["after"] == "2026-08-22T06:00:00Z"
    assert [item["time"] for item in block["target"]] == ["2026-08-22T12:00:00Z", "2026-08-23T00:00:00Z"]
    assert block["starting_state"]["path"] == "/polygons/perimeter_2h"
    assert block["families"][0] == {
        "family": "fire_arrival_time",
        "label": "Fire arrival time",
        "status": "scored",
        "reason": None,
        "perimeters": 2,
        "groups": {"P01": ["Fire Perimeters P01"]},
        "scores": {"P01": result["score_card"]["Score Fire Perimeters P01"]},
    }
    jaccard = _kpi(result, "Average Jaccard Index P01")["Average Jaccard Index P01"]
    assert 0.9 < jaccard <= 1.0
    assert "Score Fire Perimeters P01" in result["score_card"]
    # The perimeter KPIs of this group read the two perimeters after the reception, not the third.
    group = result["score_card"]["Scheme"]["Fire Perimeters P01"]
    assert len(group["benchmarks"]) == 8
    assert result["certificates_input"] is not None
    assert result["case_schema"] == "fb-case-v1"


def test_after_adds_the_period_of_the_ahead_score(tmp_path, definition, model, observed_24h):
    _, result, _ = _score(tmp_path, definition, model, observed_24h)
    card = result["score_card"]
    assert "Score Air Temp P01" in card and "Score Air Temp P02" in card
    observed = result["window"]["families"][1]["observations"]["air_temperature"]
    assert observed["P02"]["samples"] < observed["P01"]["samples"]
    assert _kpi(result, "Air temp MAE mean P02 TSO")["Score"] == pytest.approx(100.0)
    _, without, _ = _score(tmp_path, definition, model, observed_24h, after=None, tag="plain")
    assert "Score Air Temp P02" not in without["score_card"]
    assert without["window"]["after"] is None
    assert [item["time"] for item in without["window"]["target"]][0] == "2026-08-22T02:00:00Z"
    assert without["window"]["starting_state"] is None


def _weighted(card, names):
    scheme = card["Scheme"]
    return sum(card[f"Score {n}"] * scheme[n]["weight"] for n in names) / sum(
        scheme[n]["weight"] for n in names
    )


def test_each_family_has_its_groups_and_scores_by_period(tmp_path, definition, model, observed_24h):
    _, result, _ = _score(tmp_path, definition, model, observed_24h)
    card = result["score_card"]
    stations = _family(result["window"], fw.STATIONS)
    assert set(stations["groups"]) == {"P01", "P02"}
    for period, names in stations["groups"].items():
        assert names and all(n.endswith(period) and f"Score {n}" in card for n in names)
        assert "Air Temp " + period in names
        assert stations["scores"][period] == _weighted(card, names)
    arrival = _family(result["window"], fw.ARRIVAL)
    assert arrival["groups"] == {"P01": ["Fire Perimeters P01"]}
    assert arrival["scores"] == {"P01": card["Score Fire Perimeters P01"]}
    saved = json.loads((tmp_path / "run.json").read_text())
    assert _family(saved["window"], fw.STATIONS)["scores"] == stations["scores"]


def test_a_null_family_has_no_groups_and_p02_needs_after(tmp_path, definition, model, observed_6h):
    _, result, _ = _score(tmp_path, definition, model, observed_6h, after=None)
    window = result["window"]
    arrival = _family(window, fw.ARRIVAL)
    assert arrival["status"] == "null" and arrival["groups"] == {} and arrival["scores"] == {}
    stations = _family(window, fw.STATIONS)
    assert set(stations["groups"]) == {"P01"} and set(stations["scores"]) == {"P01"}


def test_one_perimeter_is_enough(tmp_path):
    observed = _observation(tmp_path / "one" / "obs.h5", 24, (2, 12))
    definition = fw.propose_window("FW48-1", START, END, FRAME, fire_frame=FIRE_FRAME, std_files=[observed])
    model = _model(tmp_path / "model.h5", definition["definition"])
    _, result, _ = _score(tmp_path, definition["definition"], model, observed)
    assert result["window"]["families"][0]["perimeters"] == 1
    assert "Score Fire Perimeters P01" in result["score_card"]


def test_a_station_the_model_lacks_is_left_out_and_the_rest_scored(tmp_path, definition, observed_24h):
    model = _model(tmp_path / "model.h5", definition, without=("station_B",))
    report, result, _ = _score(tmp_path, definition, model, observed_24h)
    part = _family(report, fw.STATIONS)["parts"][0]
    assert part["left_out"] == [{"station": "station_B", "reason": "is not in the model output"}]
    assert result["window"]["families"][1]["stations"]["air_temperature"] == {"asked": 2, "given": 1}
    assert "Score Air Temp P01" in result["score_card"]


def test_a_model_that_burns_nothing_scores_zero_overlap(tmp_path, definition, observed_24h):
    model = _model(tmp_path / "model.h5", definition, delay_hours=40)
    _, result, _ = _score(tmp_path, definition, model, observed_24h)
    burnt = gpd.read_file(tmp_path / "run_perimeters" / "perimeter_12h.kml", driver="KML")
    assert burnt.empty
    jaccard = _kpi(result, "Average Jaccard Index P01")
    assert jaccard["Average Jaccard Index P01"] == 0.0 and jaccard["Score"] == 0.0
    bias = _kpi(result, "Final Burn Area Bias P01")
    assert bias["Final Burn Area Bias P01"] < 0
    assert result["window"]["families"][0]["status"] == "scored"


def test_nothing_to_score_is_refused_with_every_reason(tmp_path, definition, observed_6h):
    model = _model(tmp_path / "model.h5", definition, without=("station_A", "station_B"))
    prepared = tmp_path / "prepared.h5"
    fws.prepare_window_model(definition, model, observed_6h, prepared)
    with pytest.raises(ValueError, match="Nothing can be scored") as error:
        fws.score_window(
            definition,
            prepared,
            observed_6h,
            output_json=tmp_path / "r.json",
            score_card_report=tmp_path / "r.pdf",
        )
    assert "Fire arrival time: 0 observed perimeter(s)" in str(error.value)
    assert "Weather at stations: The prepared file holds no station series." in str(error.value)


def test_a_file_prepared_for_another_window_is_refused(tmp_path, definition, model, observed_24h):
    prepared = tmp_path / "prepared.h5"
    fws.prepare_window_model(definition, model, observed_24h, prepared)
    other = {**definition, "name": "FW48-2"}
    with pytest.raises(case_module.CaseDefinitionError, match="not made for this window"):
        fws.score_window(
            other,
            prepared,
            observed_24h,
            output_json=tmp_path / "r.json",
            score_card_report=tmp_path / "r.pdf",
        )


# ---------------------------
# The stations a model gives
# ---------------------------
def test_stations_the_model_does_not_give_are_excluded(observed_24h):
    period = (START, START + timedelta(hours=24))
    with h5py.File(observed_24h, "r") as obs:
        ctx = {"weather_stations_given": {"air_temperature": {"station_A"}}}
        chosen = wxc.select_weather_stations(obs, "air_temperature", period, fs.WeatherStationSet.TSO, ctx)
        assert [item["station"] for item in chosen["included"]] == ["station_A"]
        assert chosen["excluded"] == [
            {"station": "station_B", "confidence": None, "reason": "not in the model output"}
        ]
        everything = wxc.select_weather_stations(
            obs, "air_temperature", period, fs.WeatherStationSet.TSO, {}
        )
        assert [item["station"] for item in everything["included"]] == ["station_A", "station_B"]


def test_a_file_prepared_for_another_reception_is_refused(tmp_path, definition, model, observed_24h):
    prepared = tmp_path / "prepared.h5"
    fws.prepare_window_model(definition, model, observed_24h, prepared, after=AFTER)
    fws.prepare_window_model(definition, model, observed_24h, prepared, after=AFTER, overwrite=True)
    with pytest.raises(case_module.CaseDefinitionError, match="reception time"):
        fws.score_window(
            definition,
            prepared,
            observed_24h,
            output_json=tmp_path / "result.json",
            score_card_report=tmp_path / "card.pdf",
        )


def test_a_relative_path_can_be_prepared_to(tmp_path, definition, model, observed_24h, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = fws.prepare_window_model(definition, model, observed_24h, "prepared.h5", after=AFTER)
    assert _family(report, fw.ARRIVAL)["status"] == fws.MADE
