"""The event catalogue file: writing, reading, validation, and its subject digest."""

import h5py
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from firebench.signing import hdf5_subject_digest_sha256
from firebench.standardize import (
    event_ids_sha256,
    read_event_catalogue,
    validate_event_catalogue,
    write_event_catalogue,
)
from firebench.standardize.event_catalogue import COUNT_DTYPE


def _events(n=3):
    rows, geometries = [], []
    for index in range(n):
        lon, lat = -121.0 + index, 38.0 + index * 0.5
        rows.append(
            {
                "event_id": f"87283082{index}ffffff_2021081{index}",
                "name": f"FIRE {index}",
                "state": "CA",
                "ignition_lat": lat,
                "ignition_lon": lon,
                "anchor_time": f"2021-08-1{index}",
                "anchor_precision": "day",
                "discovery_time": f"2021-08-1{index}T01:54:00Z" if index else "",
                "discovery_precision": "minute" if index else "",
                "containment_time": "",
                "containment_precision": "",
                "cause": "Natural",
                "source_ids": {"mtbs": f"CA{index}", "fod": [str(index)]},
            }
        )
        geometries.append(Point(lon, lat).buffer(0.05))
    # Reverse the order: the writer sorts by ID.
    return gpd.GeoDataFrame(rows[::-1], geometry=geometries[::-1], crs="EPSG:4326")


def _write(path, events=None, **kwargs):
    return write_event_catalogue(
        path,
        _events() if events is None else events,
        authors="FireBench tests",
        license="Public domain (MTBS, FPA FOD)",
        data_source="MTBS; FPA FOD",
        attrs={"id_scheme": "test"},
        **kwargs,
    )


def test_round_trip(tmp_path):
    path = _write(tmp_path / "catalogue.h5")
    catalogue = read_event_catalogue(path)
    events = catalogue.events
    assert list(events["event_id"]) == sorted(events["event_id"])
    assert catalogue.attrs["n_events"] == 3 and catalogue.attrs["id_scheme"] == "test"
    assert catalogue.attrs["event_ids_sha256"] == event_ids_sha256(events["event_id"])
    assert catalogue.attrs["area_crs"] == "EPSG:5070"
    first = events.iloc[0]
    assert first["source_ids"] == {"fod": ["0"], "mtbs": "CA0"}
    assert first["discovery_time"] == "" and first["discovery_precision"] == ""
    assert events.iloc[0]["final_area_m2"] > 1e7  # a 0.05 degree disc is tens of km2
    assert events.geometry.iloc[1].equals_exact(Point(-120.0, 38.5).buffer(0.05), 1e-9)
    assert catalogue.structures is None
    with h5py.File(path, "r") as h5:
        assert h5["events/table"].dtype.kind == "V"
        assert h5["events"].attrs["license"] and "redistribution_allowed" in h5["events"].attrs
    assert validate_event_catalogue(path) == []


def test_structures_are_counted(tmp_path):
    events = _events()
    first = sorted(events["event_id"])[0]
    structures = pd.DataFrame(
        {
            "event_id": [first, first, first],
            "lat": [38.0, 38.01, 38.02],
            "lon": [-121.0, -121.01, -121.02],
            "damage": ["Destroyed (>50%)", "No Damage", "Affected (>0-10%)"],
        }
    )
    path = _write(
        tmp_path / "catalogue.h5",
        events,
        structures=structures,
        structures_license="CC BY 4.0",
        structures_data_source="CAL FIRE DINS",
    )
    catalogue = read_event_catalogue(path)
    counts = catalogue.structure_counts.set_index("event_id")
    assert list(counts.columns) == list(COUNT_DTYPE.names[1:])
    assert counts.loc[first, "destroyed"] == 1 and counts.loc[first, "affected"] == 1
    assert counts.loc[first, "no_damage"] == 1 and counts.loc[first, "major"] == 0
    assert catalogue.attrs["structures"]["license"] == "CC BY 4.0"
    assert len(catalogue.structures) == 3


def test_structures_need_their_licence_and_known_events(tmp_path):
    structures = pd.DataFrame(
        {"event_id": ["unknown"], "lat": [0.0], "lon": [0.0], "damage": ["No Damage"]}
    )
    with pytest.raises(ValueError, match="licence"):
        _write(tmp_path / "a.h5", structures=structures)
    with pytest.raises(ValueError, match="does not hold"):
        _write(
            tmp_path / "b.h5",
            structures=structures,
            structures_license="CC BY",
            structures_data_source="DINS",
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda events: events.assign(event_id=["same"] * 3), "Duplicate"),
        (lambda events: events.assign(anchor_precision=["", "", ""]), "precision"),
        (
            lambda events: events.assign(anchor_time=["", "", ""], anchor_precision=["", "", ""]),
            "no anchor time",
        ),
        (lambda events: events.assign(anchor_time=["14/08/2021"] * 3), "not a day time"),
        (lambda events: events.assign(event_id=["x" * 41, "a", "b"]), "longer than 40"),
        (
            lambda events: events.set_geometry([Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])] * 3),
            "invalid perimeter",
        ),
        (lambda events: events.set_geometry([Polygon()] * 3), "empty perimeter"),
        (lambda events: events.set_geometry([Point(0, 0)] * 3), "not a polygon"),
    ],
)
def test_refusals(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        _write(tmp_path / "catalogue.h5", change(_events()))


def test_a_missing_licence_is_refused(tmp_path):
    path = _write(tmp_path / "catalogue.h5")
    with h5py.File(path, "a") as h5:
        del h5["events"].attrs["license"]
    with pytest.raises(ValueError, match="license"):
        validate_event_catalogue(path)


def test_a_far_ignition_is_a_warning(tmp_path):
    events = _events()
    events = events.assign(ignition_lat=events["ignition_lat"] + 0.2)
    warnings = validate_event_catalogue(_write(tmp_path / "catalogue.h5", events))
    assert len(warnings) == 3 and "outside its perimeter" in warnings[0]


def test_digest_is_stable_and_covers_perimeters(tmp_path):
    path = _write(tmp_path / "catalogue.h5")
    digest = hdf5_subject_digest_sha256(path)
    read_event_catalogue(path)
    validate_event_catalogue(path)
    assert hdf5_subject_digest_sha256(path) == digest
    # A certificate does not change what it signs.
    with h5py.File(path, "a") as h5:
        h5.create_group("certificates/abc").attrs["key_id"] = "test"
    assert hdf5_subject_digest_sha256(path) == digest
    # The same events written again give the same digest, whatever the order given.
    other = _write(tmp_path / "again.h5", _events()[::-1])
    assert _digest_without_dates(other) == _digest_without_dates(path)
    # Moving one perimeter changes the digest.
    with h5py.File(path, "a") as h5:
        value = h5["events/final_perimeter"][0].copy()
        value[-1] ^= 1
        h5["events/final_perimeter"][0] = value
    assert hdf5_subject_digest_sha256(path) != digest


def _digest_without_dates(path):
    with h5py.File(path, "a") as h5:
        h5.attrs["created_on"] = "2026-01-01T00:00"
    return hdf5_subject_digest_sha256(path)


def test_a_file_without_a_catalogue_is_refused(tmp_path):
    path = tmp_path / "empty.h5"
    with h5py.File(path, "w") as h5:
        h5.attrs["FireBench_io_version"] = "1.0"
        h5.attrs["created_on"] = "2026-01-01T00:00"
        h5.attrs["created_by"] = "tests"
    with pytest.raises(ValueError, match="no event catalogue"):
        validate_event_catalogue(path)
    with pytest.raises(ValueError, match="no event catalogue"):
        read_event_catalogue(path)


def test_ids_hash_is_order_free():
    assert event_ids_sha256(["b", "a"]) == event_ids_sha256(["a", "b"])
    assert event_ids_sha256(["a"]) != event_ids_sha256(["a", "b"])
