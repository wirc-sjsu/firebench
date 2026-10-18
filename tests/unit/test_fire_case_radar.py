"""The radar plume family of the generic cases, on a synthetic radar and a model built from it."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest
from pyproj import Geod

from firebench.acquisition import nexrad
from firebench.benchmarks import fire_case_radar
from firebench.benchmarks.fire_case import load_case
from firebench.benchmarks.fire_case_definition import check_case, edit_case, propose_case
from firebench.benchmarks.fire_case_template import case_requirements, write_model_output_template
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


def _model(path: Path, section: radar.RadarSection, shift_tracer: bool = False) -> Path:
    """A model whose columns are the nodes of the bottom row and whose levels are the rows: its tracer is
    the observed linear reflectivity and its wind gives the observed radial velocity at every node."""
    plane = section.plane
    n_time, n_v, n_u = section.values["radar_reflectivity"].shape
    reflectivity = np.nan_to_num(section.values["radar_reflectivity"], nan=-30.0)
    tracer = 10.0 ** (reflectivity / 10.0)
    if shift_tracer:
        tracer = np.roll(tracer, n_u // 2, axis=2)
    elevation = np.radians(np.nan_to_num(section.elevation, nan=0.0))
    speed = np.nan_to_num(section.values["radar_radial_velocity"]) / np.cos(elevation)
    azimuth = np.radians(section.azimuth)[None]
    seconds = (section.time - np.datetime64("2021-08-17T00:00")) / np.timedelta64(1, "s")
    with new_std_file(str(path), "model") as h5:
        group = h5.create_group("spatial_3d/plume")
        time = group.create_dataset("time", data=seconds.astype(np.float64))
        time.attrs.update({"time_origin": START.isoformat(), "time_units": "s", "units": "s"})
        for name, data, units in (
            ("position_lat", plane.latitude[:1], "degree"),
            ("position_lon", plane.longitude[:1], "degree"),
            ("position_z", plane.height[:, None, :], "m"),
            ("passive_tracer", tracer[:, :, None, :], "1"),
            ("wind_u", (speed * np.sin(azimuth))[:, :, None, :], "m/s"),
            ("wind_v", (speed * np.cos(azimuth))[:, :, None, :], "m/s"),
            ("wind_w", np.zeros((n_time, n_v, 1, n_u)), "m/s"),
        ):
            dataset = group.create_dataset(name, data=data)
            dataset.attrs["units"] = units
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
    }
    assert check_case(proposal["definition"], obs) == []
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
    assert [group["name"] for group in groups] == ["Radar Plume KDAX/axis P01"]
    assert len(groups[0]["kpis"]) == 6
    values = _scores(case, _model(tmp_path / "model.h5", section), obs)
    assert values["Plume Mask IoU KDAX/axis P01"] == pytest.approx(1.0)
    assert values["Plume Top Error KDAX/axis P01"] == pytest.approx(0.0, abs=1e-6)
    # Float32 values: within a millimetre.
    assert values["Plume Centroid Error KDAX/axis P01"] == pytest.approx(0.0, abs=1e-3)
    assert values["Concentration Rank Correlation KDAX/axis P01"] == pytest.approx(1.0)
    assert values["Radial Velocity RMSE KDAX/axis P01"] == pytest.approx(0.0, abs=1e-4)
    assert values["Radial Velocity Bias KDAX/axis P01"] == pytest.approx(0.0, abs=1e-4)


def test_a_plume_in_the_wrong_place_scores_less(observations, tmp_path):
    obs, section = observations
    case = load_case(propose_case(obs)["definition"], obs)
    # Tracer shifted along the section: the masks still overlap entirely (the observed plume fills it),
    # but its centroid moves only when the tracer's weights move.
    values = _scores(case, _model(tmp_path / "model.h5", section, shift_tracer=True), obs)
    assert values["Concentration Rank Correlation KDAX/axis P01"] < 1.0


def test_an_aliased_velocity_folds_onto_the_model_s(observations):
    nyquist = np.array([10.0, 10.0, 20.0])
    model = np.array([14.0, -12.0, 3.0])
    aliased = np.array([14.0 - 20.0, -12.0 + 20.0, 3.0])
    assert np.allclose(fire_case_radar.fold(model - aliased, nyquist), 0.0)


def test_a_kpi_with_no_volume_is_left_out_of_its_group(observations, tmp_path):
    obs, section = observations
    model = _model(tmp_path / "model.h5", section)
    with h5py.File(model, "a") as h5:
        # The model's times are an hour away from the volumes.
        h5["spatial_3d/plume/time"][...] += 3600.0
    case = load_case(propose_case(obs)["definition"], obs)
    results = case.run_all_benchmarks(
        model, "RP", case.get_list_benchmark_with_agg(case.AGGREGATION, "RP"), obs
    )
    assert results["benchmarks"] == {}


def test_the_template_and_the_requirements_name_the_model_s_plume(observations, tmp_path):
    obs, _ = observations
    definition = propose_case(obs)["definition"]
    template = write_model_output_template(obs, definition, tmp_path / "template.h5")
    with h5py.File(template) as h5:
        assert "passive_tracer" in h5["spatial_3d/plume"].attrs["required_datasets"]
    (requirement,) = [
        item for item in case_requirements(definition, obs)["requirements"] if item["name"] == "R_RP"
    ]
    assert requirement["family"] == "radar_plume"
    assert "/spatial_3d/plume/passive_tracer" in requirement["datasets"]
