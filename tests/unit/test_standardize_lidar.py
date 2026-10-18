import json
from datetime import datetime, timezone

import h5py
import numpy as np
import pytest

from firebench.standardize import (
    halo_file_kind,
    lidar_parameters,
    lidar_points,
    lidar_scans,
    list_lidar_instruments,
    merge_two_std_files,
    new_std_file,
    read_halo_hpl,
    read_halo_time_sync,
    standardize_halo_lidar,
)

BBOX = (-119.25, 40.77, -119.17, 40.81)
START = datetime(2023, 9, 6, 2, tzinfo=timezone.utc)
END = datetime(2023, 9, 6, 5, tzinfo=timezone.utc)
# The longitude of a made-up lidar inside the box, and the fix that gives it.
LON = -119.2
SYNC_LINE = (
    "Time before: *06/09/2023 03:00:03.712*Time after: *06/09/2023 03:00:03.800*Satellites in view: "
    "*08*Synchronisid? Yes*Lat: 40 47' 27.96\"N*Long: 119 12' 0.00\"W*Height (m): *01183.9"
)


def _hpl(
    directory,
    name="User1_7_20230906_030000.hpl",
    *,
    system=7,
    start="20230906 03:00:00.00",
    rays=((3.0, 60.0, 10.0),),
    n_gates=4,
    gate_length=18.0,
    points=12,
    scan_type="User file 1 - csm - overlapping",
    doppler=-2.5,
    intensity=1.8,
    beta=2.0e-5,
    cut=0,
):
    """A raw Halo scan: rays of (decimal hour, azimuth, elevation), every gate with the same values."""
    lines = [
        f"Filename:\t{name}",
        f"System ID:\t{system}",
        f"Number of gates:\t{n_gates}",
        f"Range gate length (m):\t{gate_length}",
        f"Gate length (pts):\t{points}",
        "Pulses/ray:\t30000",
        f"No. of waypoints in file:\t{len(rays)}",
        f"Scan type:\t{scan_type}",
        "Focus range:\t65535",
        f"Start time:\t{start}",
        "Resolution (m/s):\t0.0760",
        "Altitude of measurement (center of gate) = (range gate + 0.5) * Gate length",
        "Data line 1: Decimal time (hours)  Azimuth (degrees)  Elevation (degrees) Pitch (degrees) Roll (degrees)",
        "f9.6,1x,f6.2,1x,f6.2",
        "Data line 2: Range Gate  Doppler (m/s)  Intensity (SNR + 1)  Beta (m-1 sr-1)",
        "i3,1x,f6.4,1x,f8.6,1x,e12.6 - repeat for no. gates",
        "**** Instrument spectral width = 0.607721",
    ]
    for hour, azimuth, elevation in rays:
        lines.append(f"{hour:.8f} {azimuth:6.2f} {elevation:6.2f} -0.11 0.09")
        for gate in range(n_gates):
            lines.append(f"{gate:3d} {doppler:.4f} {intensity:.6f} {beta:.6E} 0.0760 ")
    text = "\r\n".join(lines[: len(lines) - cut]) + "\r\n"
    path = directory / name
    path.write_text(text)
    return path


def _sync(directory, lines=(SYNC_LINE,)):
    path = directory / "Time_Sync_7_202309.txt"
    path.write_text("\r\n".join(lines) + "\r\n")
    return path


@pytest.fixture
def std_file(tmp_path):
    file = new_std_file(tmp_path / "data.h5", "tester")
    yield file
    file.close()


# Reading the raw files ------------------------------------------------------------------------------------


def test_the_kind_of_a_file_is_told_from_its_first_bytes(tmp_path):
    assert halo_file_kind(_hpl(tmp_path)) == "scan"
    assert halo_file_kind(_sync(tmp_path)) == "time_sync"
    (tmp_path / "profile.hpl").write_text("2040\r\n   6 133.44   2.92\r\n")
    assert halo_file_kind(tmp_path / "profile.hpl") is None


def test_an_overlapping_scan_has_a_gate_every_point(tmp_path):
    scan = read_halo_hpl(_hpl(tmp_path, rays=((3.0, 60.0, 10.0), (3.01, 62.0, 12.0))))
    assert scan.system_id == 7
    assert scan.gate_spacing == pytest.approx(1.5)
    np.testing.assert_allclose(scan.range, [0.75, 2.25, 3.75, 5.25])
    assert scan.radial_velocity.shape == (2, 4)
    np.testing.assert_allclose(scan.azimuth, [60.0, 62.0])
    assert scan.time[0] == datetime(2023, 9, 6, 3, tzinfo=timezone.utc)
    assert scan.velocity_resolution == pytest.approx(0.076)
    assert not scan.truncated


def test_a_scan_without_overlap_has_a_gate_every_gate_length(tmp_path):
    scan = read_halo_hpl(_hpl(tmp_path, scan_type="User file 1 - csm"))
    np.testing.assert_allclose(scan.range, [9.0, 27.0, 45.0, 63.0])


def test_ray_times_roll_over_midnight(tmp_path):
    scan = read_halo_hpl(
        _hpl(tmp_path, start="20230905 23:59:50.00", rays=((23.9990, 60.0, 5.0), (0.0010, 61.0, 5.0)))
    )
    assert scan.time[0].day == 5
    assert scan.time[1] == datetime(2023, 9, 6, 0, 0, 3, 600000, tzinfo=timezone.utc)


def test_a_last_ray_cut_short_is_left_out(tmp_path):
    scan = read_halo_hpl(_hpl(tmp_path, rays=((3.0, 60.0, 10.0), (3.01, 62.0, 12.0)), cut=2))
    assert len(scan.time) == 1
    assert scan.truncated


@pytest.mark.parametrize(
    "text, message",
    [
        ("2040\r\n   6 133.44   2.92\r\n", "not a raw Halo scan"),
        ("Filename:\tx.hpl\r\nSystem ID:\t7\r\n", "has no end"),
    ],
)
def test_a_file_that_is_no_raw_scan_is_refused(tmp_path, text, message):
    (tmp_path / "bad.hpl").write_text(text)
    with pytest.raises(ValueError, match=message):
        read_halo_hpl(tmp_path / "bad.hpl")


def test_the_gps_fixes_are_read_in_degrees(tmp_path):
    (fix,) = read_halo_time_sync(_sync(tmp_path, [SYNC_LINE, "garbage"]))
    assert fix.time == datetime(2023, 9, 6, 3, 0, 3, 712000, tzinfo=timezone.utc)
    assert fix.latitude == pytest.approx(40 + 47 / 60 + 27.96 / 3600)
    assert fix.longitude == pytest.approx(-119.2)
    assert fix.altitude == pytest.approx(1183.9)
    assert fix.satellites == 8
    (tmp_path / "empty.txt").write_text("nothing\n")
    with pytest.raises(ValueError, match="no GPS fix"):
        read_halo_time_sync(tmp_path / "empty.txt")


# Writing ----------------------------------------------------------------------------------------------------


def _write(h5, scans, **options):
    options = {"bbox": BBOX, "start": START, "end": END, "heading_deg": 30.0} | options
    return standardize_halo_lidar(scans, h5, **options)


def test_the_scans_of_a_lidar_are_one_group_with_a_row_per_ray(tmp_path, std_file):
    first = _hpl(tmp_path, rays=((3.0, 60.0, 10.0), (3.01, 62.0, 12.0)))
    second = _hpl(
        tmp_path, "User1_7_20230906_031000.hpl", start="20230906 03:10:00.00", rays=((3.17, 64.0, 5.0),)
    )
    (group,) = _write(std_file, [second, first], time_sync=[_sync(tmp_path)])
    assert group.name == "/spatial_3d/lidar/HALO_7"
    assert dict(std_file["/spatial_3d"].attrs) == {} and dict(std_file["/spatial_3d/lidar"].attrs) == {}
    assert group["lidar_radial_velocity"].shape == (3, 4)
    np.testing.assert_array_equal(group["scan_index"][()], [0, 0, 1])
    np.testing.assert_allclose(group["azimuth"][()], [60.0, 62.0, 64.0])
    assert group.attrs["azimuth_offset"] == 30.0
    assert group.attrs["gate_spacing"] == pytest.approx(1.5)
    assert group["time"].attrs["time_origin"] == START.isoformat()
    table = group["scans"]
    np.testing.assert_array_equal(table["first_ray"][()], [0, 2])
    assert table["source_file"][0] == b"User1_7_20230906_030000.hpl"
    assert table["position_source"][0] == b"gps"
    assert table["position_origin_lon"][0] == pytest.approx(LON)
    assert json.loads(group.attrs["failed"]) == []
    assert list_lidar_instruments(std_file) == ["HALO_7"]


def test_an_entered_position_and_altitude_are_used_instead_of_the_gps(tmp_path, std_file):
    (group,) = _write(
        std_file,
        [_hpl(tmp_path)],
        time_sync=[_sync(tmp_path)],
        position=(40.78, -119.21),
        altitude=1193.0,
        altitude_source="LANDFIRE",
    )
    assert group["scans/position_origin_lat"][0] == pytest.approx(40.78)
    assert group["scans/position_origin_alt"][0] == pytest.approx(1193.0)
    assert group["scans/position_source"][0] == b"entered"
    assert (group.attrs["position_source"], group.attrs["altitude_source"]) == ("entered", "LANDFIRE")


def test_the_altitude_can_come_from_an_elevation_model_at_the_position(tmp_path, std_file):
    asked = []

    def ground(lat, lon):
        asked.append((round(lat, 4), round(lon, 4)))
        return 1191.0, "LANDFIRE"

    (group,) = _write(std_file, [_hpl(tmp_path)], time_sync=[_sync(tmp_path)], altitude_of=ground)
    assert asked == [(40.7911, -119.2)]
    assert group.attrs["position_origin_alt"] == pytest.approx(1191.0)
    assert (group.attrs["position_source"], group.attrs["altitude_source"]) == ("gps", "LANDFIRE")
    # An altitude given wins, and a model with no value leaves the GPS height.
    (group,) = _write(
        std_file,
        [_hpl(tmp_path)],
        time_sync=[_sync(tmp_path)],
        altitude=1193.0,
        altitude_of=ground,
        overwrite=True,
    )
    assert group.attrs["altitude_source"] == "entered" and len(asked) == 1
    (group,) = _write(
        std_file,
        [_hpl(tmp_path)],
        time_sync=[_sync(tmp_path)],
        altitude_of=lambda lat, lon: None,
        overwrite=True,
    )
    assert group.attrs["altitude_source"] == "gps" and group.attrs["position_origin_alt"] == pytest.approx(
        1183.9
    )


def test_a_static_lidar_takes_the_median_of_the_fixes_near_its_scans(tmp_path, std_file):
    fixes = [
        SYNC_LINE,
        SYNC_LINE.replace("03:00:03", "04:00:03").replace("27.96", "28.06").replace("01183.9", "01187.5"),
        # Days before: the lidar was elsewhere.
        SYNC_LINE.replace("06/09/2023", "01/09/2023").replace("119 12' 0.00", "119 12' 50.00"),
    ]
    late = _hpl(
        tmp_path, "User1_7_20230906_033000.hpl", start="20230906 03:30:00.00", rays=((3.5, 60.0, 5.0),)
    )
    (group,) = _write(std_file, [_hpl(tmp_path), late], time_sync=[_sync(tmp_path, fixes)])
    lats = group["scans/position_origin_lat"][()]
    assert lats[0] == lats[1] == pytest.approx(40 + 47 / 60 + 28.01 / 3600)
    assert group["scans/position_origin_alt"][0] == pytest.approx(1185.7)
    assert (group.attrs["position_fixes"], group.attrs["altitude_source"]) == (2, "gps")
    assert group.attrs["position_spread"] == pytest.approx(1.5, abs=0.2)


def test_scans_out_of_the_window_are_skipped_and_a_lidar_without_position_or_out_of_the_frame_refused(
    tmp_path, std_file
):
    kept = _hpl(tmp_path)
    late = _hpl(
        tmp_path, "User1_7_20230906_053000.hpl", start="20230906 05:30:00.00", rays=((5.5, 60.0, 5.0),)
    )
    (group,) = _write(std_file, [kept, late], time_sync=[_sync(tmp_path)])
    assert group["scans/n_rays"].shape == (1,)

    far = _sync(tmp_path, [SYNC_LINE.replace("03:00:03", "23:30:00").replace("06/09/2023", "05/09/2023")])
    with pytest.raises(ValueError, match="no position"):
        _write(std_file, [kept], time_sync=[far], overwrite=True)
    with pytest.raises(ValueError, match="no altitude"):
        _write(std_file, [kept], position=(40.79, -119.2), overwrite=True)
    with pytest.raises(ValueError, match="outside the frame"):
        _write(std_file, [kept], position=(41.5, -119.2), altitude=1190.0, overwrite=True)


def test_a_file_given_twice_or_with_other_gates_is_not_written(tmp_path, std_file):
    first = _hpl(tmp_path)
    copy = tmp_path / "copy"
    copy.mkdir()
    twice = _hpl(copy)
    other = _hpl(
        tmp_path,
        "User1_7_20230906_031000.hpl",
        start="20230906 03:10:00.00",
        rays=((3.17, 60.0, 5.0),),
        n_gates=6,
    )
    (group,) = _write(std_file, [first, twice, other], time_sync=[_sync(tmp_path)])
    reasons = [item["reason"] for item in json.loads(group.attrs["failed"])]
    assert reasons == [
        "the same file was given twice",
        "its gates differ from the first scan of the same lidar",
    ]


def test_nothing_to_write_and_bad_settings_are_refused(tmp_path, std_file):
    with pytest.raises(ValueError, match="no lidar scan"):
        _write(std_file, [_hpl(tmp_path)], end=datetime(2023, 9, 6, 2, 30, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="heading"):
        _write(std_file, [_hpl(tmp_path)], heading_deg=360)
    _write(std_file, [_hpl(tmp_path)], time_sync=[_sync(tmp_path)])
    with pytest.raises(ValueError, match="already exists"):
        _write(std_file, [_hpl(tmp_path)], time_sync=[_sync(tmp_path)])


def test_two_lidars_in_two_fragments_merge_without_conflict(tmp_path):
    for system in (7, 8):
        h5 = new_std_file(tmp_path / f"lidar{system}.h5", "tester")
        _write(h5, [_hpl(tmp_path, f"User1_{system}.hpl", system=system)], time_sync=[_sync(tmp_path)])
        h5.close()
    merge_two_std_files(str(tmp_path / "lidar7.h5"), str(tmp_path / "lidar8.h5"), str(tmp_path / "both.h5"))
    with h5py.File(tmp_path / "both.h5") as h5:
        assert list_lidar_instruments(h5) == ["HALO_7", "HALO_8"]


def test_the_signing_digest_of_a_lidar_file_is_stable(tmp_path):
    # pylint: disable-next=import-outside-toplevel
    from firebench.signing import hdf5_subject_digest_sha256

    h5 = new_std_file(tmp_path / "lidar.h5", "tester")
    _write(h5, [_hpl(tmp_path)], time_sync=[_sync(tmp_path)])
    h5.close()
    first = hdf5_subject_digest_sha256(str(tmp_path / "lidar.h5"))
    assert hdf5_subject_digest_sha256(str(tmp_path / "lidar.h5")) == first


# Reading the standard file ------------------------------------------------------------------------------------


def test_the_points_of_a_scan_take_the_heading_and_the_thresholds(tmp_path, std_file):
    rays = ((3.0, 60.0, 0.0), (3.01, 330.0, 30.0))
    _write(
        std_file, [_hpl(tmp_path, rays=rays, scan_type="User file 1 - csm")], time_sync=[_sync(tmp_path)]
    )
    (scan,) = lidar_scans(std_file, "HALO_7")
    assert not scan.is_stare and scan.n_rays == 2
    points = lidar_points(std_file, "HALO_7", 0)
    assert points.n_gates == 8 and len(points.east) == 8
    # 60 + 30: east. 330 + 30: north, raised by 30 degree.
    np.testing.assert_allclose(points.east[:4], [9.0, 27.0, 45.0, 63.0], atol=1e-9)
    np.testing.assert_allclose(points.north[:4], 0, atol=1e-9)
    np.testing.assert_allclose(points.east[4:], 0, atol=1e-9)
    np.testing.assert_allclose(points.north[4:], np.array([9.0, 27.0, 45.0, 63.0]) * np.cos(np.pi / 6))
    np.testing.assert_allclose(points.up[4:], np.array([9.0, 27.0, 45.0, 63.0]) / 2)


def test_gates_below_a_threshold_are_dropped_by_the_reader_and_kept_in_the_file(tmp_path, std_file):
    parameters = lidar_parameters()
    weak = 1 + 10 ** ((parameters.snr_min_db - 1) / 10)
    _write(std_file, [_hpl(tmp_path, intensity=weak)], time_sync=[_sync(tmp_path)])
    assert len(lidar_points(std_file, "HALO_7", 0).east) == 0
    assert len(lidar_points(std_file, "HALO_7", 0, qc=False).east) == 4
    assert np.isfinite(std_file["/spatial_3d/lidar/HALO_7/lidar_intensity"][()]).all()


def test_a_stare_is_told_from_a_scan(tmp_path, std_file):
    rays = ((3.0, 45.0, 89.99), (3.01, 45.0, 90.0))
    _write(
        std_file, [_hpl(tmp_path, rays=rays, scan_type="Stare - overlapping")], time_sync=[_sync(tmp_path)]
    )
    assert lidar_scans(std_file, "HALO_7")[0].is_stare
