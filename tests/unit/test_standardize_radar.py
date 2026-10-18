import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pytest
from pyproj import Geod

from firebench.acquisition import nexrad
from firebench.standardize import merge_two_std_files, new_std_file, validate_h5_std
from firebench.standardize import radar

CALDOR = (-120.8, 38.4, -119.7, 39.0)
START = datetime(2021, 8, 17, tzinfo=timezone.utc)
END = START + timedelta(hours=2)
KDAX = nexrad.site("KDAX")
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "test" / "KDAX20210817_000309_V06_cut"
# Raw Level II encoding of each moment: value = raw * scale + offset; raw 0 and 1 carry no value.
ENCODING = {
    "DBZH": (0.5, -33.0),
    "RHOHV": (1 / 300, 0.20166666666666666),
    "ZDR": (1 / 32, -13.0625),
    "VRADH": (0.5, -64.5),
}


class _Moment:
    """Stands for an xradar variable opened without scaling."""

    def __init__(self, name: str, values: np.ndarray) -> None:
        scale, offset = ENCODING[name]
        raw = np.where(np.isnan(values), 0, np.round((np.nan_to_num(values) - offset) / scale))
        self.values = raw.astype(np.uint16)
        self.attrs = {"scale_factor": scale, "add_offset": offset}


def _cut(time, elevation, moments: dict, n_rays=720, n_gates=40, first_gate=2125.0, nyquist=26.0):
    azimuth = (np.arange(n_rays) + 0.5) * 360.0 / n_rays + 0.04
    return {
        "time": time,
        "time_end": time + timedelta(seconds=20),
        "elevation": elevation,
        "azimuth": azimuth,
        "first_gate": first_gate,
        "gate_spacing": 250.0,
        "nyquist": nyquist,
        "moments": {
            name: _Moment(name, np.broadcast_to(value, (n_rays, n_gates)).astype(float))
            for name, value in moments.items()
        },
    }


def test_beam_geometry_follows_the_four_thirds_earth():
    assert radar.beam_height(0.0, 0.0, 43.0) == pytest.approx(43.0)
    # At 0 degree the beam rises by r^2 / (2 ke a): 589 m at 100 km.
    assert radar.beam_height(100_000.0, 0.0) == pytest.approx(
        100_000.0**2 / (2 * radar.EFFECTIVE_RADIUS), rel=1e-3
    )
    assert radar.beam_height(100_000.0, 6.0) > 100_000.0 * np.sin(np.radians(6.0))
    assert radar.beam_ground_distance(50_000.0, 0.5) == pytest.approx(50_000.0, rel=2e-4)
    assert radar.beam_ground_distance(50_000.0, 19.5) < 50_000.0 * np.cos(np.radians(19.4))


def test_frame_axes_of_a_radar_west_of_the_box():
    bins, gates = radar.frame_axes(KDAX.latitude, KDAX.longitude, 43.0, CALDOR, first_gate=2125.0)
    centres = radar.azimuth_bins()[bins]
    assert 50 < centres[0] < 60 and 95 < centres[-1] < 100
    assert np.all(np.diff(centres) == 0.5)
    assert 70_000 < gates[0] < 80_000 and 175_000 < gates[-1] < 190_000
    assert np.allclose(np.diff(gates), 250.0) and (gates[0] - 2125.0) % 250.0 == 0
    # A lower ceiling keeps fewer far gates: the beam rises above it sooner.
    _, low = radar.frame_axes(KDAX.latitude, KDAX.longitude, 43.0, CALDOR, max_height=3000.0)
    assert low[-1] < gates[-1]


def test_frame_axes_keep_the_whole_circle_for_a_radar_inside_the_box():
    box = (KDAX.longitude - 0.3, KDAX.latitude - 0.3, KDAX.longitude + 0.3, KDAX.latitude + 0.3)
    bins, gates = radar.frame_axes(KDAX.latitude, KDAX.longitude, 43.0, box, first_gate=2125.0)
    assert len(bins) == radar.N_AZIMUTH and gates[0] == 2125.0


def test_frame_axes_of_an_arc_across_north_wrap_around():
    box = (KDAX.longitude - 0.2, KDAX.latitude + 0.5, KDAX.longitude + 0.2, KDAX.latitude + 0.8)
    bins, _ = radar.frame_axes(KDAX.latitude, KDAX.longitude, 43.0, box)
    centres = radar.azimuth_bins()[bins]
    assert centres[0] > 300 and centres[-1] < 60
    assert np.all((np.diff(centres) % 360.0) == 0.5)


def test_frame_axes_refuse_a_box_out_of_reach():
    with pytest.raises(ValueError, match="never pass over the box"):
        radar.frame_axes(KDAX.latitude, KDAX.longitude, 43.0, (-80.0, 30.0, -79.0, 31.0))


def test_merge_cuts_joins_a_split_cut_and_keeps_a_sails_repeat_apart():
    surveillance = {"DBZH": 20.0, "RHOHV": 0.5, "ZDR": 1.0}
    doppler = {"DBZH": 18.0, "VRADH": 7.5}
    full = {"DBZH": 12.0, "RHOHV": 0.95, "ZDR": 0.5, "VRADH": -3.0}
    cuts = [
        _cut(START, 0.48, surveillance, n_gates=60),
        _cut(START + timedelta(seconds=20), 0.48, doppler, n_gates=40, nyquist=28.49),
        _cut(START + timedelta(seconds=40), 1.8, full, n_rays=360),
        _cut(START + timedelta(seconds=60), 0.48, surveillance, n_gates=60),
        _cut(START + timedelta(seconds=80), 0.48, doppler, n_gates=40, nyquist=28.49),
    ]
    sweeps = radar.merge_cuts(cuts)
    assert [round(sweep.elevation, 2) for sweep in sweeps] == [0.48, 1.8, 0.48]
    assert [sweep.time for sweep in sweeps] == [cuts[0]["time"], cuts[2]["time"], cuts[3]["time"]]
    first = sweeps[0]
    assert np.allclose(first.data["DBZH"], 20.0) and np.allclose(first.data["RHOHV"], 0.5, atol=2e-3)
    assert first.data["VRADH"].shape == (720, 40) and np.allclose(first.data["VRADH"], 7.5)
    assert first.nyquist_velocity == 28.49 and first.azimuth_resolution == 0.5
    assert sweeps[1].azimuth_resolution == 1.0 and np.allclose(sweeps[1].data["VRADH"], -3.0)
    only_reflectivity = radar.merge_cuts(cuts[:2], fields=("DBZH",))
    assert list(only_reflectivity[0].data) == ["DBZH"] and np.isnan(only_reflectivity[0].nyquist_velocity)


def test_codes_below_threshold_and_range_folded_are_nan():
    values = np.array([[np.nan, 10.0, 20.0]])
    moment = _Moment("DBZH", values)
    moment.values[0, 1] = 1
    decoded = radar._decode(moment)
    assert np.isnan(decoded[0, 0]) and np.isnan(decoded[0, 1]) and decoded[0, 2] == 20.0


def test_merge_cuts_refuses_gates_other_than_250_m():
    cut = _cut(START, 0.5, {"DBZH": 10.0})
    cut["gate_spacing"] = 1000.0
    with pytest.raises(ValueError, match="only 250 m gates"):
        radar.merge_cuts([cut])


# Writing, with volumes made in the test --------------------------------------------------------------

PLUME_AZIMUTH = 75.25
PLUME_RANGE = 120_125.0
PLUME_ELEVATION = 3.1


def _volume(time: datetime, plume: bool = True, site="KDAX") -> radar.RadarVolume:
    """Two sweeps over the whole circle: a plume gate on the second when ``plume``."""
    n_gates = 1000
    sweeps = []
    for position, elevation in enumerate((0.5, PLUME_ELEVATION)):
        azimuth = (np.arange(720) + 0.5) * 0.5 + 0.03
        reflectivity = np.full((720, n_gates), np.nan, dtype=np.float32)
        correlation = np.full((720, n_gates), np.nan, dtype=np.float32)
        velocity = np.full((720, n_gates), 5.0, dtype=np.float32)
        if plume and position == 1:
            ray = int(PLUME_AZIMUTH // 0.5)
            gate = int((PLUME_RANGE - 2125.0) // 250.0)
            reflectivity[ray, gate], correlation[ray, gate] = 25.0, 0.5
            # Same echo with a weather correlation, one gate further: not a plume gate.
            reflectivity[ray, gate + 1], correlation[ray, gate + 1] = 30.0, 0.97
        sweeps.append(
            radar.RadarSweep(
                time=time + timedelta(seconds=30 * position),
                elevation=elevation,
                azimuth_resolution=0.5,
                nyquist_velocity=26.4,
                first_gate=2125.0,
                data={"DBZH": reflectivity, "RHOHV": correlation, "VRADH": velocity},
                azimuth=azimuth,
            )
        )
    return radar.RadarVolume(
        site=site,
        latitude=KDAX.latitude,
        longitude=KDAX.longitude,
        altitude=43.0,
        vcp=212,
        time_start=time,
        time_end=time + timedelta(minutes=4),
        sweeps=sweeps,
    )


@pytest.fixture
def fake_reader(monkeypatch):
    """``read_level2_volume`` returns the volume a test made, keyed by file name."""
    made = {}

    def read(path, fields=radar.DEFAULT_FIELDS):
        volume = made[Path(path).name]
        if isinstance(volume, Exception):
            raise volume
        for sweep in volume.sweeps:
            sweep.data = {name: values for name, values in sweep.data.items() if name in fields}
        return volume

    monkeypatch.setattr(radar, "read_level2_volume", read)
    return made


def _fetched(tmp_path, made, minute: int, volume=None, site="KDAX", fetched=True):
    time = START + timedelta(minutes=minute)
    key = f"{time:%Y/%m/%d}/{site}/{site}{time:%Y%m%d_%H%M%S}_V06"
    ref = nexrad.NexradVolume(nexrad.BUCKET, key, site, time)
    if not fetched:
        return nexrad.FetchedVolume(ref, None, None, "HTTP 503")
    path = tmp_path / Path(key).name
    path.write_bytes(b"x")
    made[path.name] = volume if volume is not None else _volume(time, site=site)
    return nexrad.FetchedVolume(ref, path, "a" * 64)


def _write(tmp_path, name, fetched, **kwargs):
    with new_std_file(str(tmp_path / name), "test") as h5:
        options = {"site": "KDAX", "bbox": CALDOR, "start": START, "end": END}
        group = radar.standardize_nexrad_level2(fetched, h5, **(options | kwargs))
        return group.name


def test_a_site_is_written_as_sweeps_cropped_to_the_frame(tmp_path, fake_reader):
    fetched = [
        _fetched(tmp_path, fake_reader, 3),
        _fetched(tmp_path, fake_reader, 8, fetched=False),
        _fetched(tmp_path, fake_reader, 13, volume=ValueError("bad block")),
        _fetched(tmp_path, fake_reader, 18, volume=_volume(START + timedelta(minutes=18), plume=False)),
        _fetched(tmp_path, fake_reader, 125),
    ]
    _write(tmp_path, "radar.h5", fetched, fields=("DBZH", "RHOHV", "VRADH"), time_step_min=5)
    with h5py.File(tmp_path / "radar.h5") as h5:
        group = h5["/spatial_3d/radar/KDAX"]
        assert dict(h5["/spatial_3d"].attrs) == {} and dict(h5["/spatial_3d/radar"].attrs) == {}
        assert group.attrs["site"] == "KDAX" and group.attrs["crs"] == "EPSG:4326"
        assert (
            group.attrs["position_origin_alt"] == 43.0 and group.attrs["position_origin_alt_units"] == "m"
        )
        assert group.attrs["time_step"] == 5 and group.attrs["volumes_complete"] == np.False_
        failed = json.loads(group.attrs["failed"])
        assert [item["key"].rsplit("_", 2)[-2] for item in failed] == ["000800", "001300"]
        assert failed[0]["reason"] == "HTTP 503" and "bad block" in failed[1]["reason"]
        assert json.loads(group.attrs["fields"]) == [
            "radar_reflectivity",
            "radar_correlation_coefficient",
            "radar_radial_velocity",
        ]
        n_az, n_gate = len(group["azimuth"]), len(group["range"])
        assert n_az < radar.N_AZIMUTH and group["radar_reflectivity"].shape == (4, n_az, n_gate)
        assert "radar_differential_reflectivity" not in group
        assert group["radar_reflectivity"].attrs["units"] == "dBZ"
        assert list(group["volume_index"][()]) == [0, 0, 1, 1]
        assert np.allclose(group["elevation"][()], [0.5, PLUME_ELEVATION] * 2)
        assert group["time"].attrs["time_origin"] == START.isoformat()
        assert list(group["time"][()]) == [180.0, 210.0, 1080.0, 1110.0]
        assert np.allclose(group["nyquist_velocity"][()], 26.4)
        volumes = group["volumes"]
        assert list(volumes["time"][()]) == [180.0, 1080.0]
        assert [key.decode().rsplit("/", 1)[-1] for key in volumes["source_key"][()]] == [
            "KDAX20210817_000300_V06",
            "KDAX20210817_001800_V06",
        ]
        assert list(volumes["vcp"][()]) == [212, 212] and list(volumes["n_sweeps"][()]) == [2, 2]
        # The value of the bin and gate of the plume, and the velocity everywhere observed
        column = int(np.argmin(np.abs(group["azimuth"][()] - PLUME_AZIMUTH)))
        gate = int(np.argmin(np.abs(group["range"][()] - PLUME_RANGE)))
        assert group["radar_reflectivity"][1, column, gate] == 25.0
        assert np.isnan(group["radar_reflectivity"][0]).all()
        assert np.allclose(group["radar_radial_velocity"][0], 5.0)
        validate_h5_std(h5)


def test_writing_refuses_another_site_an_existing_group_and_nothing_readable(tmp_path, fake_reader):
    with pytest.raises(ValueError, match="cannot be written to the group of KDAX"):
        _write(tmp_path, "a.h5", [_fetched(tmp_path, fake_reader, 3, site="KRGX")])
    with pytest.raises(ValueError, match="no NEXRAD volume of KDAX could be read"):
        _write(tmp_path, "b.h5", [_fetched(tmp_path, fake_reader, 3, volume=ValueError("bad"))])
    with h5py.File(tmp_path / "b.h5") as h5:
        assert "/spatial_3d/radar/KDAX" not in h5
    with pytest.raises(ValueError, match="unknown or missing radar fields"):
        _write(tmp_path, "c.h5", [_fetched(tmp_path, fake_reader, 3)], fields=("KDP",))
    with h5py.File(tmp_path / "d.h5", "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-10-15T00:00+00:00"
        h5.attrs["created_by"] = "test"
        radar.standardize_nexrad_level2(
            [_fetched(tmp_path, fake_reader, 3)], h5, site="KDAX", bbox=CALDOR, start=START, end=END
        )
        with pytest.raises(ValueError, match="already exists"):
            radar.standardize_nexrad_level2(
                [_fetched(tmp_path, fake_reader, 8)], h5, site="KDAX", bbox=CALDOR, start=START, end=END
            )
        group = radar.standardize_nexrad_level2(
            [_fetched(tmp_path, fake_reader, 8)],
            h5,
            site="KDAX",
            bbox=CALDOR,
            start=START,
            end=END,
            overwrite=True,
        )
        assert list(group["volumes"]["time"][()]) == [480.0]


def test_echo_top_series_and_composite_count_plume_gates_over_the_frame(tmp_path, fake_reader):
    fetched = [
        _fetched(tmp_path, fake_reader, 3),
        _fetched(tmp_path, fake_reader, 18, volume=_volume(START + timedelta(minutes=18), plume=False)),
    ]
    _write(tmp_path, "radar.h5", fetched)
    with h5py.File(tmp_path / "radar.h5") as h5:
        assert radar.list_radar_sites(h5) == ["KDAX"]
        group = h5["/spatial_3d/radar/KDAX"]
        column = int(np.argmin(np.abs(group["azimuth"][()] - PLUME_AZIMUTH)))
        gate = int(np.argmin(np.abs(group["range"][()] - PLUME_RANGE)))
        expected = radar.beam_height(group["range"][gate], PLUME_ELEVATION, 43.0)
        distance = radar.beam_ground_distance(group["range"][gate], PLUME_ELEVATION)
        lon, lat, _ = Geod(ellps="WGS84").fwd(
            KDAX.longitude, KDAX.latitude, group["azimuth"][column], distance
        )
        assert CALDOR[0] < lon < CALDOR[2] and CALDOR[1] < lat < CALDOR[3]

    series = radar.radar_echo_top_series(tmp_path / "radar.h5", "KDAX")
    assert list(series.time) == [np.datetime64("2021-08-17T00:03"), np.datetime64("2021-08-17T00:18")]
    assert list(series.n_gates) == [1, 0]
    assert series.height_max[0] == pytest.approx(expected) and np.isnan(series.height_max[1])
    assert series.height_quantiles[0.9][0] == pytest.approx(expected)
    # Without the correlation test, the weather echo next to it counts too.
    assert list(radar.radar_echo_top_series(tmp_path / "radar.h5", "KDAX", rhohv_range=None).n_gates) == [
        2,
        0,
    ]
    # A box that leaves the plume out
    outside = radar.radar_echo_top_series(
        tmp_path / "radar.h5", "KDAX", corners=((38.4, -120.8), (38.5, -120.7))
    )
    assert list(outside.n_gates) == [0, 0]

    composite = radar.radar_composite(tmp_path / "radar.h5", "KDAX", 0, resolution=0.02)
    assert composite.bounds[0] == CALDOR[0] and composite.bounds[3] == CALDOR[3]
    assert composite.values.shape == (30, 55)
    assert np.nansum(np.isfinite(composite.values)) == 1 and np.nanmax(composite.values) == 25.0
    row, col = np.argwhere(np.isfinite(composite.values))[0]
    assert composite.bounds[3] - (row + 1) * 0.02 <= lat <= composite.bounds[3] - row * 0.02
    assert composite.bounds[0] + col * 0.02 <= lon <= composite.bounds[0] + (col + 1) * 0.02
    assert np.isnan(radar.radar_composite(tmp_path / "radar.h5", "KDAX", 1).values).all()
    with pytest.raises(ValueError, match="volume 2 is not one of the 2 volumes"):
        radar.radar_composite(tmp_path / "radar.h5", "KDAX", 2)
    with pytest.raises(ValueError, match="no radar site 'KRGX'"):
        radar.radar_echo_top_series(tmp_path / "radar.h5", "KRGX")


def test_the_signing_digest_of_a_radar_file_is_stable_and_ignores_a_certificate(tmp_path, fake_reader):
    # pylint: disable-next=import-outside-toplevel
    from firebench.signing import hdf5_subject_digest_sha256

    _write(tmp_path, "radar.h5", [_fetched(tmp_path, fake_reader, minute) for minute in (3, 8, 13)])
    first = hdf5_subject_digest_sha256(str(tmp_path / "radar.h5"))
    assert hdf5_subject_digest_sha256(str(tmp_path / "radar.h5")) == first
    with h5py.File(tmp_path / "radar.h5", "a") as h5:
        h5.require_group("certificates").attrs["test"] = "x"
    assert hdf5_subject_digest_sha256(str(tmp_path / "radar.h5")) == first


def test_two_site_fragments_merge_without_conflict(tmp_path, fake_reader):
    _write(tmp_path, "kdax.h5", [_fetched(tmp_path, fake_reader, 3)])
    krgx = _volume(START + timedelta(minutes=3), site="KRGX")
    _write(tmp_path, "krgx.h5", [_fetched(tmp_path, fake_reader, 3, volume=krgx, site="KRGX")], site="KRGX")
    merge_two_std_files(str(tmp_path / "kdax.h5"), str(tmp_path / "krgx.h5"), str(tmp_path / "both.h5"))
    with h5py.File(tmp_path / "both.h5") as h5:
        assert radar.list_radar_sites(h5) == ["KDAX", "KRGX"]


def test_points_are_the_plume_gates_at_their_beam_centre(tmp_path, fake_reader):
    fetched = [
        _fetched(tmp_path, fake_reader, 3),
        _fetched(tmp_path, fake_reader, 18, volume=_volume(START + timedelta(minutes=18), plume=False)),
    ]
    _write(tmp_path, "radar.h5", fetched)
    points = radar.radar_points(tmp_path / "radar.h5", "KDAX", 0)
    tops = radar.radar_echo_top_series(tmp_path / "radar.h5", "KDAX")
    assert len(points.height) == 1 and points.height[0] == pytest.approx(tops.height_max[0])
    assert points.values["radar_reflectivity"][0] == 25.0
    assert points.values["radar_radial_velocity"][0] == 5.0
    assert points.values["radar_correlation_coefficient"][0] == pytest.approx(0.5, abs=2e-3)
    # Both echoes over the box have a reflectivity; one passes the mask.
    assert points.n_gates == 2 and points.time == tops.time[0]
    assert CALDOR[0] < points.longitude[0] < CALDOR[2] and CALDOR[1] < points.latitude[0] < CALDOR[3]
    empty = radar.radar_points(tmp_path / "radar.h5", "KDAX", 1)
    assert len(empty.longitude) == 0 and empty.n_gates == 0
    with pytest.raises(ValueError, match="volume 2 is not one of the 2 volumes"):
        radar.radar_points(tmp_path / "radar.h5", "KDAX", 2)


def test_the_parameters_file_gives_the_plume_mask_and_section_limits():
    parameters = radar.radar_parameters()
    assert (parameters.min_dbz, parameters.rhohv_range) == (
        radar.DEFAULT_MIN_DBZ,
        radar.DEFAULT_RHOHV_RANGE,
    )
    assert parameters.version and len(parameters.sha256) == 64
    assert parameters.min_spacing < 250.0 < parameters.max_spacing


def test_the_beam_through_a_point_inverts_the_beam_geometry():
    ranges = np.array([2_125.0, 50_000.0, 120_125.0, 230_000.0])
    for elevation in (0.0, 0.5, 3.1, 19.5):
        height = radar.beam_height(ranges, elevation)
        ground = radar.beam_ground_distance(ranges, elevation)
        back, slant = radar.beam_elevation_range(ground, height)
        assert np.allclose(back, elevation, atol=1e-9) and np.allclose(slant, ranges, rtol=1e-9)


GEOD = Geod(ellps="WGS84")
SECTION_AZIMUTH = 75.25


def _ground(distance: float, alt: float) -> tuple[float, float, float]:
    """A point at ``distance`` from KDAX along the section azimuth, as (lat, lon, alt)."""
    lon, lat, _ = GEOD.fwd(KDAX.longitude, KDAX.latitude, SECTION_AZIMUTH, distance)
    return (lat, lon, alt)


def test_a_vertical_plane_has_its_nodes_above_its_ground_line():
    p1, p2 = _ground(100_000.0, 0.0), _ground(140_000.0, 0.0)
    plane = radar.RadarPlane.from_points(p1, p2, (p1[0], p1[1], 8_000.0), spacing=500.0)
    assert plane.u[-1] == 40_000.0 and len(plane.u) == 81
    assert plane.v[-1] == 8_000.0 and len(plane.v) == 17
    assert plane.latitude.shape == (17, 81)
    # A vertical plane: altitude is v, and every row stands over the same ground line.
    assert np.allclose(plane.height, plane.v[:, None])
    assert np.allclose(plane.latitude[0], plane.latitude[-1]) and np.allclose(
        plane.longitude[0], plane.longitude[-1]
    )
    assert plane.latitude[0, 0] == pytest.approx(p1[0]) and plane.longitude[0, -1] == pytest.approx(
        p2[1], abs=1e-6
    )
    _, _, distance = GEOD.inv(p1[1], p1[0], plane.longitude[0, -1], plane.latitude[0, -1])
    assert distance == pytest.approx(40_000.0, rel=1e-3)


def test_a_plane_refuses_three_points_on_a_line_and_a_grid_too_large():
    p1, p2 = _ground(100_000.0, 1_000.0), _ground(140_000.0, 1_000.0)
    with pytest.raises(ValueError, match="on one line"):
        radar.RadarPlane.from_points(p1, p2, _ground(120_000.0, 1_000.0))
    with pytest.raises(ValueError, match="closer than its spacing"):
        radar.RadarPlane.from_points(p1, p1, (p1[0], p1[1], 9_000.0))
    with pytest.raises(ValueError, match="spacing is"):
        radar.RadarPlane.from_points(p1, p2, (p1[0], p1[1], 9_000.0), spacing=10.0)
    with pytest.raises(ValueError, match="cells"):
        radar.RadarPlane.from_points(
            p1, _ground(400_000.0, 1_000.0), (p1[0], p1[1], 20_000.0), spacing=100.0
        )
    with pytest.raises(ValueError, match="longest allowed"):
        radar.RadarPlane.from_points(
            p1, _ground(450_000.0, 1_000.0), (p1[0], p1[1], 9_000.0), spacing=2000.0
        )
    with pytest.raises(ValueError, match="altitude"):
        radar.RadarPlane.from_points(p1, p2, (p1[0], p1[1], 30_000.0), spacing=1000.0)


TILTS = (0.5, 1.5, 6.0)
TILT_DBZ = (20.0, 30.0, 40.0)
TILT_VELOCITY = (5.0, 7.0, 9.0)
TILT_NYQUIST = (10.0, 20.0, 30.0)


def _layered_volume(time: datetime) -> radar.RadarVolume:
    """Three tilts, each with one value of every field everywhere, and a SAILS repeat of the first."""
    sweeps = []
    tilts = [*zip(TILTS, TILT_DBZ, TILT_VELOCITY, TILT_NYQUIST), (0.5, 60.0, -1.0, 99.0)]
    for position, (elevation, dbz, velocity, nyquist) in enumerate(tilts):
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


def _expected(elevation: np.ndarray):
    """Reflectivity, velocity, and Nyquist velocity of a node at a beam elevation, by the rules."""
    half = radar.BEAM_WIDTH / 2
    dbz = np.full(elevation.shape, np.nan)
    velocity = np.full(elevation.shape, np.nan)
    nyquist = np.full(elevation.shape, np.nan)
    for index, value in np.ndenumerate(elevation):
        if TILTS[0] - half <= value <= TILTS[0]:
            dbz[index], velocity[index], nyquist[index] = TILT_DBZ[0], TILT_VELOCITY[0], TILT_NYQUIST[0]
        elif TILTS[0] < value <= TILTS[1]:
            share = (value - TILTS[0]) / (TILTS[1] - TILTS[0])
            linear = (1 - share) * 10 ** (TILT_DBZ[0] / 10) + share * 10 ** (TILT_DBZ[1] / 10)
            dbz[index] = 10 * np.log10(linear)
            pick = 0 if share <= 0.5 else 1
            velocity[index], nyquist[index] = TILT_VELOCITY[pick], TILT_NYQUIST[pick]
        elif TILTS[2] <= value <= TILTS[2] + half:
            dbz[index], velocity[index], nyquist[index] = TILT_DBZ[2], TILT_VELOCITY[2], TILT_NYQUIST[2]
    return dbz, velocity, nyquist


def test_a_section_reads_between_tilts_and_never_interpolates_velocity(tmp_path, fake_reader):
    fetched = [
        _fetched(tmp_path, fake_reader, minute, volume=_layered_volume(START + timedelta(minutes=minute)))
        for minute in (3, 8)
    ]
    _write(tmp_path, "radar.h5", fetched)
    p1, p2 = _ground(100_000.0, 0.0), _ground(140_000.0, 0.0)
    plane = radar.RadarPlane.from_points(p1, p2, (p1[0], p1[1], 12_000.0), spacing=250.0)
    section = radar.radar_cross_section(tmp_path / "radar.h5", "KDAX", plane, name="axis")
    assert section.values["radar_reflectivity"].shape == (2, len(plane.v), len(plane.u))
    assert list(section.time) == [np.datetime64("2021-08-17T00:03"), np.datetime64("2021-08-17T00:08")]
    assert np.allclose(section.azimuth, SECTION_AZIMUTH, atol=0.01)
    dbz, velocity, nyquist = _expected(section.beam_elevation.astype(np.float64))
    for volume in range(2):
        assert np.allclose(section.values["radar_reflectivity"][volume], dbz, equal_nan=True, atol=1e-3)
        assert np.allclose(section.values["radar_radial_velocity"][volume], velocity, equal_nan=True)
        assert np.allclose(section.nyquist_velocity[volume], nyquist, equal_nan=True)
    # Velocity takes a tilt's own value, never one between; the SAILS repeat (60 dBZ) is never read.
    observed = section.values["radar_radial_velocity"]
    assert set(np.unique(observed[np.isfinite(observed)])) <= {5.0, 7.0, 9.0}
    assert np.nanmax(section.values["radar_reflectivity"]) <= 40.0 + 1e-3
    # The gap from 1.5 to 6 degree is wider than max_elevation_gap: no value there.
    gap = (section.beam_elevation > 1.6) & (section.beam_elevation < 5.9)
    assert gap.any() and np.isnan(section.values["radar_reflectivity"][0][gap]).all()
    assert np.isfinite(dbz).any() and np.isnan(dbz).any()
    with pytest.raises(ValueError, match="lower-case"):
        radar.radar_cross_section(tmp_path / "radar.h5", "KDAX", plane, name="Axis 1")
    with pytest.raises(ValueError, match="has no field"):
        radar.radar_cross_section(
            tmp_path / "radar.h5", "KDAX", plane, name="axis", fields=["radar_spectrum_width"]
        )


def test_sections_are_stored_beside_the_sweeps_and_read_back(tmp_path, fake_reader):
    # pylint: disable-next=import-outside-toplevel
    from firebench.signing import hdf5_subject_digest_sha256

    fetched = [_fetched(tmp_path, fake_reader, 3, volume=_layered_volume(START + timedelta(minutes=3)))]
    _write(tmp_path, "radar.h5", fetched)
    p1, p2 = _ground(100_000.0, 0.0), _ground(120_000.0, 0.0)
    plane = radar.RadarPlane.from_points(p1, p2, (p1[0], p1[1], 6_000.0), spacing=500.0)
    with h5py.File(tmp_path / "radar.h5", "a") as h5:
        cut = radar.radar_cross_section(h5, "KDAX", plane, name="axis")
        radar.write_radar_sections(h5, "KDAX", [cut])
        # Writing it again replaces it.
        radar.write_radar_sections(h5, "KDAX", [cut])
        assert radar.list_radar_sections(h5, "KDAX") == ["axis"]
        assert dict(h5["/spatial_3d/radar/KDAX/sections"].attrs) == {}
        assert radar.list_radar_sites(h5) == ["KDAX"]
        validate_h5_std(h5)
    back = radar.read_radar_section(tmp_path / "radar.h5", "KDAX", "axis")
    assert back.plane.points == plane.points and back.plane.spacing == 500.0
    assert np.array_equal(back.plane.height, plane.height) and list(back.time) == list(cut.time)
    for field, values in cut.values.items():
        assert np.array_equal(back.values[field], values, equal_nan=True)
    assert np.array_equal(back.elevation, cut.elevation, equal_nan=True)
    assert np.array_equal(back.azimuth, cut.azimuth)
    first = hdf5_subject_digest_sha256(str(tmp_path / "radar.h5"))
    assert hdf5_subject_digest_sha256(str(tmp_path / "radar.h5")) == first
    with pytest.raises(ValueError, match="no radar section KDAX/other"):
        radar.read_radar_section(tmp_path / "radar.h5", "KDAX", "other")


# A real volume ------------------------------------------------------------------------------------------


def test_a_real_level2_volume_cut_to_two_sweeps():
    pytest.importorskip("xradar")
    from xradar.io import open_nexradlevel2_datatree

    volume = radar.read_level2_volume(SAMPLE)
    assert volume.site == "KDAX" and volume.vcp == 212
    assert volume.latitude == pytest.approx(KDAX.latitude, abs=1e-3)
    assert [round(sweep.elevation, 1) for sweep in volume.sweeps] == [5.1, 6.4]
    assert [sweep.azimuth_resolution for sweep in volume.sweeps] == [1.0, 1.0]
    assert volume.sweeps[0].nyquist_velocity == pytest.approx(26.38)
    assert set(volume.sweeps[0].data) == {"DBZH", "RHOHV", "ZDR", "VRADH"}
    tree = open_nexradlevel2_datatree(str(SAMPLE), mask_and_scale=False)
    for index, sweep in enumerate(volume.sweeps):
        source = tree[f"sweep_{index}"].ds
        # xradar sorts the rays by azimuth; the volume keeps them in the order scanned.
        order = np.argsort(sweep.azimuth)
        assert np.allclose(sweep.azimuth[order], source["azimuth"].values)
        for name in ("DBZH", "RHOHV", "VRADH"):
            raw = source[name].values
            scaled = raw * source[name].attrs["scale_factor"] + source[name].attrs["add_offset"]
            scaled = np.where(raw > 1, scaled, np.nan)
            assert np.allclose(sweep.data[name][order], scaled, equal_nan=True, atol=1e-5)
    assert volume.time_start < volume.sweeps[1].time < volume.time_end


def test_a_real_level2_volume_standardized(tmp_path):
    pytest.importorskip("xradar")
    time = nexrad.volume_time(SAMPLE.name.removesuffix("_cut"))
    ref = nexrad.NexradVolume(nexrad.BUCKET, f"2021/08/17/KDAX/{SAMPLE.name}", "KDAX", time)
    fetched = nexrad.FetchedVolume(ref, SAMPLE, nexrad.sha256_file(SAMPLE))
    _write(tmp_path, "real.h5", [fetched])
    with h5py.File(tmp_path / "real.h5") as h5:
        group = h5["/spatial_3d/radar/KDAX"]
        assert group["radar_reflectivity"].shape[0] == 2
        assert np.isfinite(group["radar_reflectivity"][()]).any()
        assert group["volumes"]["source_sha256"][0].decode() == fetched.sha256
    series = radar.radar_echo_top_series(tmp_path / "real.h5", "KDAX")
    assert series.n_gates[0] > 0 and series.height_max[0] > 10_000.0
