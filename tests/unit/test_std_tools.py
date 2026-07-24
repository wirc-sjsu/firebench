import hashlib

import pytest
import h5py
from datetime import datetime, timezone

from firebench.standardize import (
    get_h5_referenced_file_integrity,
    merge_authors,
    validate_h5_requirement,
    validate_h5_referenced_files,
    validate_h5_std,
    validate_h5_weather_stations_structure,
)


def _set_standard_metadata(h5, version="1.0"):
    h5.attrs["FireBench_io_version"] = version
    h5.attrs["created_on"] = "2026-07-24T12:00:00+00:00"
    h5.attrs["created_by"] = "FireBench tests"


def _create_referenced_file_bundle(tmp_path):
    bundle_dir = tmp_path / "bundle"
    kml_dir = bundle_dir / "kml"
    kml_dir.mkdir(parents=True)
    kml_path = kml_dir / "perimeter.kml"
    kml_path.write_text("<kml>perimeter</kml>", encoding="utf-8")

    h5_path = bundle_dir / "model.h5"
    with h5py.File(h5_path, "w") as h5:
        _set_standard_metadata(h5)
        perimeter = h5.create_dataset("/polygons/perimeter", data=0)
        perimeter.attrs["rel_path"] = "kml/perimeter.kml"
        perimeter.attrs["file_size_bytes"] = kml_path.stat().st_size
        perimeter.attrs["sha256"] = hashlib.sha256(kml_path.read_bytes()).hexdigest()
        perimeter.attrs["time"] = "2021-08-20T20:20-07:00"

    return h5_path, kml_path


@pytest.mark.parametrize("version", ["1.0", "0.2"])
def test_validate_h5_std_accepts_current_and_compatible_versions(tmp_path, version):
    h5_path = tmp_path / f"standard-{version}.h5"
    with h5py.File(h5_path, "w") as h5:
        _set_standard_metadata(h5, version)
        validate_h5_std(h5)


def test_validate_h5_std_rejects_missing_version(tmp_path):
    h5_path = tmp_path / "missing-version.h5"
    with h5py.File(h5_path, "w") as h5:
        h5.attrs["created_on"] = "2026-07-24T12:00:00+00:00"
        h5.attrs["created_by"] = "FireBench tests"
        with pytest.raises(ValueError, match="FireBench_io_version.*not found"):
            validate_h5_std(h5)


@pytest.mark.parametrize("version", [1, "", "1", "1.0.0"])
def test_validate_h5_std_rejects_malformed_versions(tmp_path, version):
    h5_path = tmp_path / "malformed-version.h5"
    with h5py.File(h5_path, "w") as h5:
        _set_standard_metadata(h5, version)
        with pytest.raises(ValueError, match="major.minor"):
            validate_h5_std(h5)


@pytest.mark.parametrize("version", ["0.1", "9.9"])
def test_validate_h5_std_rejects_unsupported_and_unknown_versions(tmp_path, version):
    h5_path = tmp_path / f"unsupported-{version}.h5"
    with h5py.File(h5_path, "w") as h5:
        _set_standard_metadata(h5, version)
        with pytest.raises(ValueError, match="not compatible"):
            validate_h5_std(h5)


@pytest.mark.parametrize(
    "created_by_1, created_by_2, expected",
    [
        # 1. Simple case: same length, no overlaps
        # file1: alice, bob
        # file2: carol, dan
        # order: a1, a2, b1, b2
        (
            "alice;bob;",
            "carol;dan;",
            "alice;carol;bob;dan;",
        ),
        # 2. Different length, no overlaps (file1 longer)
        # file1: alice, bob, charlie
        # file2: dan, erin
        # positions:
        #   i=0: alice, dan
        #   i=1: bob, erin
        #   i=2: charlie (only file1)
        (
            "alice;bob;charlie;",
            "dan;erin;",
            "alice;dan;bob;erin;charlie;",
        ),
        # 3. Different length, no overlaps (file2 longer)
        # file1: alice, bob
        # file2: carol, dan, erin
        # positions:
        #   i=0: alice, carol
        #   i=1: bob, dan
        #   i=2: erin (only file2)
        (
            "alice;bob;",
            "carol;dan;erin;",
            "alice;carol;bob;dan;erin;",
        ),
        # 4. Overlap across lists
        # file1: alice, bob
        # file2: bob, carol
        # positions:
        #   i=0: alice, bob -> alice, bob
        #   i=1: bob (already seen), carol -> carol
        # merged: alice, bob, carol
        (
            "alice;bob;",
            "bob;carol;",
            "alice;bob;carol;",
        ),
        # 5. Duplicate within the same list + overlap
        # file1: alice, alice, bob
        # file2: carol, alice
        # positions:
        #   i=0: alice, carol -> alice, carol
        #   i=1: alice (seen), alice (seen) -> no new author
        #   i=2: bob -> bob
        # merged: alice, carol, bob
        (
            "alice;alice;bob;",
            "carol;alice;",
            "alice;carol;bob;",
        ),
        # 6. One side empty (no authors in file1)
        # file1: ""
        # file2: alice, bob
        (
            "",
            "alice;bob;",
            "alice;bob;",
        ),
        # 7. One side empty (no authors in file2)
        # file1: alice, bob
        # file2: ""
        (
            "alice;bob;",
            "",
            "alice;bob;",
        ),
        # 8. Both empty
        (
            "",
            "",
            "",
        ),
        # 9. Trailing semicolons with possible stray spaces
        # Expect that your function strips whitespace around names.
        # file1: " alice  ", "bob"
        # file2: "bob ", "  carol"
        # merged: alice, bob, carol (no duplicates, trimmed)
        (
            " alice  ;bob ;",
            "bob ;  carol ;",
            "alice;bob;carol;",
        ),
        # 10. Multiple overlaps and reordering
        # file1: alice, bob, charlie, dave
        # file2: bob, erin, charlie, frank
        # positions:
        #   i=0: alice, bob       -> alice, bob
        #   i=1: bob(seen), erin  -> erin
        #   i=2: charlie, charlie -> charlie
        #   i=3: dave, frank      -> dave, frank
        # merged: alice, bob, erin, charlie, dave, frank
        (
            "alice;bob;charlie;dave;",
            "bob;erin;charlie;frank;",
            "alice;bob;erin;charlie;dave;frank;",
        ),
    ],
)
def test_merge_authors(created_by_1, created_by_2, expected):
    assert merge_authors(created_by_1, created_by_2) == expected


def test_validate_h5_requirement_resolves_rel_path_from_h5_directory(tmp_path, monkeypatch):
    h5_path, _ = _create_referenced_file_bundle(tmp_path)

    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)

    with h5py.File(h5_path, "r") as h5:
        result = validate_h5_requirement(
            h5,
            {"/polygons/perimeter": ["rel_path", "time"]},
        )

    assert result == (True, None)


@pytest.mark.parametrize("missing_attribute", ["file_size_bytes", "sha256"])
def test_validate_h5_requirement_enforces_reference_integrity_attributes(tmp_path, missing_attribute):
    h5_path, _ = _create_referenced_file_bundle(tmp_path)
    with h5py.File(h5_path, "r+") as h5:
        del h5["/polygons/perimeter"].attrs[missing_attribute]

    with h5py.File(h5_path, "r") as h5:
        valid, issue = validate_h5_requirement(
            h5,
            {"/polygons/perimeter": ["rel_path", "time"]},
        )

    assert valid is False
    assert missing_attribute in issue


def test_validate_h5_referenced_files_reports_missing_file(tmp_path):
    h5_path, kml_path = _create_referenced_file_bundle(tmp_path)
    kml_path.unlink()

    with h5py.File(h5_path, "r") as h5:
        valid, issue = validate_h5_referenced_files(h5)

    assert valid is False
    assert "not found" in issue


def test_validate_h5_referenced_files_reports_moved_file(tmp_path):
    h5_path, kml_path = _create_referenced_file_bundle(tmp_path)
    kml_path.rename(kml_path.with_name("moved.kml"))

    with h5py.File(h5_path, "r") as h5:
        valid, issue = validate_h5_referenced_files(h5)

    assert valid is False
    assert "kml/perimeter.kml" in issue


def test_validate_h5_referenced_files_reports_size_mismatch(tmp_path):
    h5_path, _ = _create_referenced_file_bundle(tmp_path)
    with h5py.File(h5_path, "r+") as h5:
        h5["/polygons/perimeter"].attrs["file_size_bytes"] += 1

    with h5py.File(h5_path, "r") as h5:
        valid, issue = validate_h5_referenced_files(h5)

    assert valid is False
    assert "size mismatch" in issue


def test_validate_h5_referenced_files_reports_hash_mismatch(tmp_path):
    h5_path, _ = _create_referenced_file_bundle(tmp_path)
    with h5py.File(h5_path, "r+") as h5:
        h5["/polygons/perimeter"].attrs["sha256"] = "0" * 64

    with h5py.File(h5_path, "r") as h5:
        valid, issue = validate_h5_referenced_files(h5)

    assert valid is False
    assert "SHA-256 mismatch" in issue


def test_get_h5_referenced_file_integrity_returns_verified_metadata(tmp_path):
    h5_path, kml_path = _create_referenced_file_bundle(tmp_path)

    with h5py.File(h5_path, "r") as h5:
        integrity = get_h5_referenced_file_integrity(h5)

    assert integrity == {
        "/polygons/perimeter": {
            "rel_path": "kml/perimeter.kml",
            "file_size_bytes": kml_path.stat().st_size,
            "sha256": hashlib.sha256(kml_path.read_bytes()).hexdigest(),
        }
    }


def test_validate_h5_weather_stations_structure_reports_missing_station_details(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        time_series = obs_h5.create_group("time_series")
        station_a = time_series.create_group("station_A")
        station_a.create_dataset("time", data=[0, 1])
        station_a.create_dataset("air_temperature", data=[290, 291])
        station_b = time_series.create_group("station_B")
        station_b.create_dataset("time", data=[0, 1])
        station_b.create_dataset("air_temperature", data=[292, 293])

    with h5py.File(model_path, "w") as model_h5:
        time_series = model_h5.create_group("time_series")
        station_a = time_series.create_group("station_A")
        station_a.create_dataset("time", data=[0, 1])
        station_a.create_dataset("air_temperature", data=[290, 291])

    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        ok, missing = validate_h5_weather_stations_structure(
            model_h5, obs_h5, "air_temperature", "station_"
        )

    assert ok is False
    assert missing == [
        {
            "station": "station_B",
            "variable": "air_temperature",
            "missing": [
                "time_series/station_B/time",
                "time_series/station_B/air_temperature",
            ],
        }
    ]


def test_validate_h5_weather_stations_structure_is_scoped_to_selected_stations(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        for station_name in ("station_SELECTED", "station_EXCLUDED"):
            station = obs_h5.create_group(f"time_series/{station_name}")
            station.create_dataset("time", data=[0, 1])
            station.create_dataset("air_temperature", data=[290, 291])

    with h5py.File(model_path, "w") as model_h5:
        station = model_h5.create_group("time_series/station_SELECTED")
        station.create_dataset("time", data=[0, 1])
        station.create_dataset("air_temperature", data=[290, 291])

    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        ok, missing = validate_h5_weather_stations_structure(
            model_h5,
            obs_h5,
            "air_temperature",
            "station_",
            selected_stations={"station_SELECTED"},
        )

    assert ok is True
    assert missing is None


def test_validate_h5_weather_stations_structure_ignores_stations_outside_period(tmp_path):
    obs_path = tmp_path / "obs.h5"
    model_path = tmp_path / "model.h5"

    with h5py.File(obs_path, "w") as obs_h5:
        time_series = obs_h5.create_group("time_series")
        station_outside = time_series.create_group("station_OUTSIDE")
        station_outside.create_dataset("time", data=[0, 1])
        station_outside["time"].attrs["time_origin"] = "2021-08-20T00:00:00+00:00"
        station_outside["time"].attrs["time_units"] = "hour"
        station_outside.create_dataset("air_temperature", data=[290, 291])

        station_inside = time_series.create_group("station_INSIDE")
        station_inside.create_dataset("time", data=[24, 25])
        station_inside["time"].attrs["time_origin"] = "2021-08-20T00:00:00+00:00"
        station_inside["time"].attrs["time_units"] = "hour"
        station_inside.create_dataset("air_temperature", data=[292, 293])

    with h5py.File(model_path, "w") as model_h5:
        model_h5.create_group("time_series")

    period = (
        datetime(2021, 8, 21, 0, tzinfo=timezone.utc),
        datetime(2021, 8, 21, 1, tzinfo=timezone.utc),
    )
    with h5py.File(model_path, "r") as model_h5, h5py.File(obs_path, "r") as obs_h5:
        ok, missing = validate_h5_weather_stations_structure(
            model_h5,
            obs_h5,
            "air_temperature",
            "station_",
            periods=[period],
        )

    assert ok is False
    assert missing == [
        {
            "station": "station_INSIDE",
            "variable": "air_temperature",
            "missing": [
                "time_series/station_INSIDE/time",
                "time_series/station_INSIDE/air_temperature",
            ],
        }
    ]
