"""The radar plume family of the generic cases, on a synthetic radar and a model built from it."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest
from pyproj import Geod

from firebench.acquisition import nexrad
from firebench.benchmarks import fire_case_radar
from firebench.benchmarks import fire_case_radar_model as model_targets
from firebench.benchmarks.fire_case import load_case
from firebench.benchmarks.fire_case_definition import (
    check_case,
    edit_case,
    propose_case,
    write_case_definition,
)
from firebench.benchmarks.fire_case_template import (
    case_requirements,
    plume_targets,
    write_model_output_template,
)
from firebench.standardize import new_std_file, radar

START = datetime(2021, 8, 17, tzinfo=timezone.utc)
CALDOR = (-120.8, 38.4, -119.7, 39.0)
KDAX = nexrad.site("KDAX")
AZIMUTH = 75.25
TILTS = ((0.5, 20.0, 5.0, 10.0), (1.5, 30.0, 7.0, 20.0), (2.5, 40.0, 9.0, 30.0))
GEOD = Geod(ellps="WGS84")


def _volume(time: datetime) -> radar.RadarVolume:
    """Three tilts, each with one reflectivity, a plume correlation, and one velocity everywhere."""
    sweeps = []
    for position, (elevation, dbz, velocity, nyquist) in enumerate(TILTS):
        shape = (720, 1000)
        sweeps.append(
            radar.RadarSweep(
                time=time + timedelta(seconds=30 * position),
                elevation=elevation,
                azimuth_resolution=0.5,
                nyquist_velocity=nyquist,
                first_gate=2125.0,
                data={
                    "DBZH": np.full(shape, dbz, dtype=np.float32),
                    "RHOHV": np.full(shape, 0.5, dtype=np.float32),
                    "VRADH": np.full(shape, velocity, dtype=np.float32),
                },
                azimuth=(np.arange(720) + 0.5) * 0.5 + 0.03,
            )
        )
    return radar.RadarVolume(
        site="KDAX",
        latitude=KDAX.latitude,
        longitude=KDAX.longitude,
        altitude=43.0,
        vcp=212,
        time_start=time,
        time_end=time + timedelta(minutes=4),
        sweeps=sweeps,
    )


@pytest.fixture
def observations(tmp_path, monkeypatch):
    """A radar file of two volumes with a vertical section along the beam of KDAX, and the section."""
    made = {}

    def read(path, fields=radar.DEFAULT_FIELDS):
        return made[Path(path).name]

    monkeypatch.setattr(radar, "read_level2_volume", read)
    fetched = []
    for minute in (3, 8):
        time = START + timedelta(minutes=minute)
        key = f"{time:%Y/%m/%d}/KDAX/KDAX{time:%Y%m%d_%H%M%S}_V06"
        path = tmp_path / Path(key).name
        path.write_bytes(b"x")
        made[path.name] = _volume(time)
        fetched.append(
            nexrad.FetchedVolume(nexrad.NexradVolume(nexrad.BUCKET, key, "KDAX", time), path, "a" * 64)
        )
    obs = tmp_path / "obs.h5"
    p1 = GEOD.fwd(KDAX.longitude, KDAX.latitude, AZIMUTH, 100_000.0)
    p2 = GEOD.fwd(KDAX.longitude, KDAX.latitude, AZIMUTH, 110_000.0)
    plane = radar.RadarPlane.from_points(
        (p1[1], p1[0], 0.0), (p2[1], p2[0], 0.0), (p1[1], p1[0], 5_000.0), 500
    )
    with new_std_file(str(obs), "test") as h5:
        h5.attrs["version"] = "test"
        end = START + timedelta(hours=1)
        radar.standardize_nexrad_level2(fetched, h5, site="KDAX", bbox=CALDOR, start=START, end=end)
        radar.write_radar_sections(h5, "KDAX", [radar.radar_cross_section(h5, "KDAX", plane, name="axis")])
    return obs, radar.read_radar_section(obs, "KDAX", "axis")


def _section_fields(section: radar.RadarSection, shift_tracer: bool = False) -> dict:
    """On the nodes of the section, a tracer that is the observed linear reflectivity and a wind that
    gives the observed radial velocity at every node."""
    reflectivity = np.nan_to_num(section.values["radar_reflectivity"], nan=-30.0)
    tracer = 10.0 ** (reflectivity / 10.0)
    if shift_tracer:
        tracer = np.roll(tracer, tracer.shape[2] // 2, axis=2)
    elevation = np.radians(np.nan_to_num(section.elevation, nan=0.0))
    speed = np.nan_to_num(section.values["radar_radial_velocity"]) / np.cos(elevation)
    azimuth = np.radians(section.azimuth)[None]
    return {
        "passive_tracer": tracer,
        "wind_u": speed * np.sin(azimuth),
        "wind_v": speed * np.cos(azimuth),
        "wind_w": np.zeros_like(tracer),
    }


def _model(
    path: Path, obs: Path, section: radar.RadarSection, shift_tracer: bool = False, counts=None
) -> Path:
    """A model output that gives the radar's own section, and its plume cells over the frame of KDAX
    (``counts``, at each volume time; the radar's own gates by default)."""
    entry = {
        "sections": ["KDAX/axis"],
        "model_group": model_targets.MODEL_GROUP,
        "echo_top": ["KDAX"],
    }
    with h5py.File(obs) as h5:
        targets = model_targets.targets_from_observations(
            h5, entry, [(START, START + timedelta(hours=1))], 100.0, 0.01
        )
    (target,) = targets.sections
    (frame,) = targets.frames
    if counts is None:
        counts = np.stack(
            [
                np.histogram(radar.radar_points(obs, "KDAX", volume).height, frame.height_bins)[0]
                for volume in range(len(frame.time))
            ]
        )
    with new_std_file(str(path), "model") as h5:
        model_targets.write_plume_section(h5, target, _section_fields(section, shift_tracer))
        model_targets.write_plume_frame(h5, frame, counts)
    return path


def _scores(case, model: Path, obs: Path) -> dict:
    results = case.run_all_benchmarks(
        model, "0", case.get_list_benchmark_with_agg(case.AGGREGATION, "0"), obs
    )
    return {key: value for item in results["benchmarks"].values() for key, value in item.items()}


def test_a_case_proposes_the_radar_plume_on_every_section(observations):
    obs, _ = observations
    proposal = propose_case(obs)
    (plume,) = [item for item in proposal["definition"]["families"] if item["family"] == "radar_plume"]
    assert plume == {
        "family": "radar_plume",
        "periods": ["P01"],
        "sections": ["KDAX/axis"],
        "model_group": "/spatial_3d/plume",
        "echo_top": ["KDAX"],
    }
    assert check_case(proposal["definition"], obs) == []
    without = {key: value for key, value in plume.items() if key != "echo_top"}
    assert check_case({**proposal["definition"], "families": [without]}, obs) == []
    unknown = {**plume, "echo_top": ["KXXX"]}
    assert check_case({**proposal["definition"], "families": [unknown]}, obs) == [
        "Radar plume: not a radar site of the file: KXXX."
    ]
    bad = {**proposal["definition"], "families": [{**plume, "sections": ["KDAX/other"]}]}
    assert check_case(bad, obs) == ["Radar plume: not a cross section of the file: KDAX/other."]
    added = edit_case(proposal["definition"], obs, add_periods=[(START, START + timedelta(minutes=30))])
    assert [item for item in added["families"] if item["family"] == "radar_plume"][0]["periods"] == [
        "P01",
        "P02",
    ]


def test_a_model_that_is_the_radar_scores_every_kpi_at_its_best(observations, tmp_path):
    obs, section = observations
    definition = propose_case(obs)["definition"]
    case = load_case(definition, obs)
    groups = case.describe_composable_groups()
    assert [group["name"] for group in groups] == ["Radar Plume KDAX/axis P01", "Radar Plume Top KDAX P01"]
    assert len(groups[0]["kpis"]) == 6
    assert len(groups[1]["kpis"]) == 2
    values = _scores(case, _model(tmp_path / "model.h5", obs, section), obs)
    assert values["Plume Mask IoU KDAX/axis P01"] == pytest.approx(1.0)
    assert values["Plume Top Error KDAX/axis P01"] == pytest.approx(0.0, abs=1e-6)
    # Float32 values: within a millimetre.
    assert values["Plume Centroid Error KDAX/axis P01"] == pytest.approx(0.0, abs=1e-3)
    assert values["Concentration Rank Correlation KDAX/axis P01"] == pytest.approx(1.0)
    assert values["Radial Velocity RMSE KDAX/axis P01"] == pytest.approx(0.0, abs=1e-4)
    assert values["Radial Velocity Bias KDAX/axis P01"] == pytest.approx(0.0, abs=1e-4)
    # The model counts the radar's own gates in bins of 100 m: its 90th percentile is within a bin.
    assert values["Plume Top Series Error KDAX P01"] < 100.0
    assert abs(values["Plume Top Series Bias KDAX P01"]) < 100.0


def test_a_plume_in_the_wrong_place_scores_less(observations, tmp_path):
    obs, section = observations
    case = load_case(propose_case(obs)["definition"], obs)
    # Tracer shifted along the section: the masks still overlap entirely (the observed plume fills it),
    # but its centroid moves only when the tracer's weights move.
    values = _scores(case, _model(tmp_path / "model.h5", obs, section, shift_tracer=True), obs)
    assert values["Concentration Rank Correlation KDAX/axis P01"] < 1.0


def test_an_aliased_velocity_folds_onto_the_model_s(observations):
    nyquist = np.array([10.0, 10.0, 20.0])
    model = np.array([14.0, -12.0, 3.0])
    aliased = np.array([14.0 - 20.0, -12.0 + 20.0, 3.0])
    assert np.allclose(fire_case_radar.fold(model - aliased, nyquist), 0.0)


def test_a_kpi_with_no_volume_is_left_out_of_its_group(observations, tmp_path):
    obs, section = observations
    model = _model(tmp_path / "model.h5", obs, section)
    with h5py.File(model, "a") as h5:
        # The model's times are an hour away from the volumes.
        h5["spatial_3d/plume/sections/KDAX/axis/time"][...] += 3600.0
        h5["spatial_3d/plume/frame/KDAX/time"][...] += 3600.0
    case = load_case(propose_case(obs)["definition"], obs)
    results = case.run_all_benchmarks(
        model, "RP", case.get_list_benchmark_with_agg(case.AGGREGATION, "RP"), obs
    )
    assert results["benchmarks"] == {}


def test_a_definition_without_echo_top_keeps_its_groups_and_ids(observations, tmp_path):
    obs, section = observations
    definition = propose_case(obs)["definition"]
    (plume,) = [item for item in definition["families"] if item["family"] == "radar_plume"]
    del plume["echo_top"]
    case = load_case(definition, obs)
    (group,) = case.describe_composable_groups()
    assert group["name"] == "Radar Plume KDAX/axis P01"
    assert sorted(case.BENCHMARK_FUNCTIONS) == [f"G-RP{number:02d}" for number in range(1, 7)]
    model = _model(tmp_path / "model.h5", obs, section)
    with h5py.File(model, "a") as h5:
        del h5["spatial_3d/plume/frame"]
    assert _scores(case, model, obs)["Plume Mask IoU KDAX/axis P01"] == pytest.approx(1.0)


def test_a_top_counted_at_another_threshold_is_left_out(observations, tmp_path):
    obs, section = observations
    model = _model(tmp_path / "model.h5", obs, section)
    with h5py.File(model, "a") as h5:
        h5["spatial_3d/plume/frame/KDAX/plume_cells"].attrs["tracer_relative_threshold"] = 0.1
    case = load_case(propose_case(obs)["definition"], obs)
    values = _scores(case, model, obs)
    assert "Plume Top Series Error KDAX P01" not in values
    assert "Plume Mask IoU KDAX/axis P01" in values


def test_a_model_with_no_plume_over_the_frame_has_no_top(observations, tmp_path):
    obs, section = observations
    with h5py.File(obs) as h5:
        n_bins = int(round(h5["spatial_3d/radar/KDAX"].attrs["max_height"] / 100))
    model = _model(tmp_path / "model.h5", obs, section, counts=np.zeros((2, n_bins)))
    case = load_case(propose_case(obs)["definition"], obs)
    assert "Plume Top Series Error KDAX P01" not in _scores(case, model, obs)


def test_the_sampler_puts_a_model_grid_on_the_nodes(observations):
    _, section = observations
    plane = section.plane
    fields = _section_fields(section)
    # A grid whose columns are the nodes of the bottom row and whose levels are the rows.
    for index in range(len(section.time)):
        sampled = model_targets.sample_columns(
            plane.latitude[:1],
            plane.longitude[:1],
            plane.height[:, None, :],
            {name: values[index][:, None, :] for name, values in fields.items()},
            plane.latitude,
            plane.longitude,
            plane.height,
        )
        for name, values in fields.items():
            assert np.allclose(sampled[name], values[index], equal_nan=True)
    # A node above the top level and one off the grid are NaN.
    far = model_targets.sample_columns(
        plane.latitude[:1],
        plane.longitude[:1],
        plane.height[:, None, :],
        {"passive_tracer": np.ones((plane.height.shape[0], 1, plane.height.shape[1]))},
        np.array([plane.latitude[0, 0], plane.latitude[0, 0] + 1.0]),
        np.array([plane.longitude[0, 0], plane.longitude[0, 0]]),
        np.array([plane.height.max() + 10.0, plane.height[0, 0]]),
    )
    assert np.isnan(far["passive_tracer"]).all()


def test_plume_cells_and_their_quantile():
    heights = np.array([[[100.0, 150.0]], [[300.0, 350.0]], [[900.0, 950.0]]])
    tracer = np.array([[[1.0, 0.001]], [[0.5, 0.2]], [[np.nan, 0.05]]])
    bins = np.arange(0.0, 1100.0, 100.0)
    counts = model_targets.plume_cell_counts(heights, tracer, True, bins, 0.1)
    # 0.001 and 0.05 are under a tenth of the largest, and NaN is no cell.
    assert counts.tolist() == [0, 1, 0, 2, 0, 0, 0, 0, 0, 0]
    assert model_targets.histogram_quantile(bins, counts, 0.5) == pytest.approx(325.0)
    assert np.isnan(model_targets.histogram_quantile(bins, np.zeros(10), 0.9))
    assert not model_targets.plume_cell_mask(np.zeros(3), True, 0.1).any()
    # A column four times as large counts four times as much: its weight is its area.
    weighted = model_targets.plume_cell_counts(
        heights, tracer, True, bins, 0.1, weights=np.array([[[4.0, 1.0]]])
    )
    assert weighted.tolist() == [0, 4, 0, 5, 0, 0, 0, 0, 0, 0]
    assert model_targets.histogram_quantile(bins, weighted, 0.5) == pytest.approx(300.0 + 100.0 * 0.5 / 5)


def test_the_template_and_the_requirements_name_the_model_s_plume(observations, tmp_path):
    obs, _ = observations
    definition = propose_case(obs)["definition"]
    template = write_model_output_template(obs, definition, tmp_path / "template.h5")
    with h5py.File(template) as h5:
        section = h5["spatial_3d/plume/sections/KDAX/axis"]
        assert section["passive_tracer"].shape == (2, *section["position_lat"].shape)
        assert np.isnan(section["passive_tracer"][()]).all()
        assert h5["spatial_3d/plume/frame/KDAX/plume_cells"].attrs["tracer_relative_threshold"] == 0.01
    (requirement,) = [
        item for item in case_requirements(definition, obs)["requirements"] if item["name"] == "R_RP"
    ]
    assert requirement["family"] == "radar_plume"
    assert "/spatial_3d/plume/sections/KDAX/axis/passive_tracer" in requirement["datasets"]
    (top,) = [item for item in case_requirements(definition, obs)["requirements"] if item["name"] == "R_RT"]
    assert "/spatial_3d/plume/frame/KDAX/plume_cells" in top["datasets"]


def test_the_targets_are_the_same_from_a_template_and_from_the_observations(observations, tmp_path):
    obs, _ = observations
    definition = propose_case(obs)["definition"]
    template = write_model_output_template(obs, definition, tmp_path / "template.h5")
    write_case_definition(obs, definition)
    from_template, from_obs = plume_targets(template), plume_targets(obs)
    assert from_template.model_group == from_obs.model_group == "/spatial_3d/plume"
    for one, other in (
        (from_template.sections, from_obs.sections),
        (from_template.frames, from_obs.frames),
    ):
        assert len(one) == len(other) == 1
        assert np.array_equal(one[0].time, other[0].time)
        assert one[0].path == other[0].path
    assert np.allclose(from_template.sections[0].height, from_obs.sections[0].height)
    assert np.array_equal(from_template.frames[0].height_bins, from_obs.frames[0].height_bins)
    assert len(from_obs.times) == 2


def test_the_values_of_a_figure_are_those_the_kpis_compare(observations, tmp_path):
    obs, section = observations
    case = load_case(propose_case(obs)["definition"], obs)
    model = _model(tmp_path / "model.h5", obs, section)
    with h5py.File(model, "r") as model_h5, h5py.File(obs, "r") as obs_h5:
        values = case.radar_plume_values(model_h5, obs_h5)
    (item,) = values["sections"]
    assert item["problem"] is None
    assert item["periods"] == {"P01": [0, 1]}
    assert item["reflectivity"].shape == item["radial"].shape == (2, *item["position_lat"].shape)
    assert np.allclose(item["iou"], 1.0)
    assert np.allclose(item["top_observed"], item["top_modelled"])
    kept = np.isfinite(item["velocity"]) & item["observed"]
    assert np.allclose(item["radial"][kept], item["velocity"][kept], atol=1e-4)
    (top,) = values["tops"]
    assert top["problem"] is None
    assert np.all(np.abs(top["modelled"] - top["observed"]) < 100.0)
    assert values["points"] is None
