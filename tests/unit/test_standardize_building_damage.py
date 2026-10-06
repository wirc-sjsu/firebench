import hashlib
import json

import h5py
import numpy as np
import pytest
from pyproj import Transformer

import firebench.standardize as fs

# Footprints and DINS rows are laid out in metres in this projection, which is also the one the
# function is asked to measure distances in, so a row placed 49 m from a centroid is at 49 m.
PROJECTED_CRS = "EPSG:32610"
TO_LONLAT = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
X0, Y0 = 700_000.0, 4_290_000.0
SPACING = 1_000.0
NUMBER_COLUMN = "Incident Number (e.g. CAAEU 123456)"
HEADER = [
    "OBJECTID",
    "Damage",
    "Incident Name",
    NUMBER_COLUMN,
    "Incident Start Date",
    "Latitude",
    "Longitude",
]

# incident name, incident number, start date, footprint, metres east of its centroid, metres north, damage
DINS_ROWS = [
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 0, 5, 0, "Affected (1-9%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 1, 10, 0, "Minor (10-25%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 1, 20, 0, "Destroyed (>50%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 2, 49, 0, "Major (26-50%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 3, 51, 0, "Destroyed (>50%)"),
    ("test fire", "N-1", "8/15/2021 12:00:00 AM", 0, 8, 0, "No Damage"),
    ("Other Fire", "N-9", "7/1/2019 12:00:00 AM", 4, 5, 0, "Destroyed (>50%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 2, 0, 5_000, "Destroyed (>50%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", None, 0, 0, "Destroyed (>50%)"),
    ("Test Fire", "N-1", "8/14/2021 12:00:00 AM", 2, 30, 0, "Under review"),
    ("Twin", "N-2", "9/4/2020 12:00:00 AM", 0, 3, 0, "Destroyed (>50%)"),
    ("Twin ", "N-2", "9/5/2020 12:00:00 AM", 1, 3, 0, "Minor (10-25%)"),
    ("Twin", "N-3", "6/1/2022 12:00:00 AM", 2, 3, 0, "Major (26-50%)"),
    ("", "N-0", "1/1/2018 12:00:00 AM", 4, 3, 0, "Destroyed (>50%)"),
]


def _lonlat(footprint, east=0.0, north=0.0):
    return TO_LONLAT.transform(X0 + footprint * SPACING + east, Y0 + north)


def _write_dins(path, rows=DINS_ROWS, header=HEADER):
    lines = [",".join(f'"{name}"' for name in header)]
    for object_id, (name, number, start, footprint, east, north, damage) in enumerate(rows, start=1):
        lon, lat = ("", "") if footprint is None else _lonlat(footprint, east, north)
        values = {
            "OBJECTID": object_id,
            "Damage": damage,
            "Incident Name": name,
            NUMBER_COLUMN: number,
            "Incident Start Date": start,
            "Latitude": repr(lat) if lat != "" else "",
            "Longitude": repr(lon) if lon != "" else "",
        }
        lines.append(",".join(f'"{values[name]}"' for name in header if name in values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def _write_footprints(path, footprints=(0, 1, 2, 3, 4, 60)):
    """Squares of 10 m, one per line. Footprint 60 is 60 km east, outside the box."""
    lines = []
    for footprint in footprints:
        corners = [(-5, -5), (5, -5), (5, 5), (-5, 5), (-5, -5)]
        ring = [list(_lonlat(footprint, east, north)) for east, north in corners]
        feature = {
            "type": "Feature",
            "properties": {"height": -1.0, "confidence": -1.0},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
        lines.append(json.dumps(feature, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n\n", encoding="utf-8")
    return path


def _corners():
    lon_min, lat_min = _lonlat(0, -500, -500)
    lon_max, lat_max = _lonlat(4, 500, 500)
    return (lat_min, lon_min), (lat_max, lon_max)


@pytest.fixture
def inputs(tmp_path):
    h5 = fs.new_std_file(str(tmp_path / "bundle" / "damage.h5"), "FireBench tests")
    yield _write_dins(tmp_path / "dins.csv"), _write_footprints(tmp_path / "footprints.geojsonl"), h5
    h5.close()


def _standardize(inputs, incident_name="Test Fire", **arguments):
    dins_csv, footprints, h5 = inputs
    arguments = {"projected_crs": PROJECTED_CRS, **arguments}
    return fs.standardize_dins_building_damage(
        dins_csv, footprints, h5, incident_name, *_corners(), **arguments
    )


def _text(dataset):
    return [value.decode("utf-8") for value in dataset[:]]


def test_list_dins_incidents_gives_one_record_per_name_and_number(inputs):
    dins_csv, _, _ = inputs

    incidents = fs.list_dins_incidents(dins_csv)

    assert [(item["incident_name"], item["incident_number"]) for item in incidents] == [
        ("Other Fire", "N-9"),
        ("Test Fire", "N-1"),
        ("Twin", "N-2"),
        ("Twin", "N-3"),
    ]
    assert [item["n_records"] for item in incidents] == [1, 9, 2, 1]
    assert [item["start_date_min"] for item in incidents] == [
        "2019-07-01",
        "2021-08-14",
        "2020-09-04",
        "2022-06-01",
    ]
    assert incidents[1]["start_date_max"] == "2021-08-15"
    assert incidents[2]["start_date_max"] == "2020-09-05"


def test_list_dins_incidents_gives_the_box_of_each_incident(inputs):
    dins_csv, _, _ = inputs

    twin = fs.list_dins_incidents(dins_csv)[2]

    first, second = _lonlat(0, 3), _lonlat(1, 3)
    assert twin["lon_min"] == pytest.approx(min(first[0], second[0]), abs=1e-12)
    assert twin["lon_max"] == pytest.approx(max(first[0], second[0]), abs=1e-12)
    assert twin["lat_min"] == pytest.approx(min(first[1], second[1]), abs=1e-12)
    assert twin["lat_max"] == pytest.approx(max(first[1], second[1]), abs=1e-12)
    assert json.loads(json.dumps(twin)) == twin


def test_footprint_takes_the_most_severe_damage_of_its_rows(inputs):
    group = _standardize(inputs)

    assert _text(group["building_damage"])[:5] == [
        "Affected (1-9%)",
        "Destroyed (>50%)",
        "Major (26-50%)",
        "No Damage",
        "No Damage",
    ]
    assert list(group["dins_match_count"][:5]) == [2, 2, 2, 0, 0]
    assert list(group["dins_matched"][:5]) == [True, True, True, False, False]
    assert group["dins_match_distance_m"][:3] == pytest.approx([5.0, 10.0, 30.0], abs=1e-3)
    assert np.isnan(group["dins_match_distance_m"][3:5]).all()


def test_row_beyond_the_match_distance_becomes_a_building_of_its_own(inputs):
    group = _standardize(inputs)

    # the row at 49 m is matched to footprint 2, the row at 51 m of footprint 3 is not
    assert group["dins_match_count"][2] == 2
    assert group["dins_match_count"][3] == 0
    assert len(group["position_lat"]) == 6
    lon, lat = _lonlat(3, 51)
    assert group["position_lat"][5] == pytest.approx(lat, abs=1e-12)
    assert group["position_lon"][5] == pytest.approx(lon, abs=1e-12)
    assert _text(group["building_damage"])[5] == "Destroyed (>50%)"
    assert _text(group["building_source"])[5] == "DINS"
    assert group["dins_matched"][5]
    assert group["dins_match_count"][5] == 1
    assert group["dins_match_distance_m"][5] == 0.0

    assert len(_standardize(inputs, max_match_distance_m=52.0, overwrite=True)["position_lat"]) == 5


def test_rows_of_another_incident_are_ignored_and_the_name_has_no_case(inputs):
    group = _standardize(inputs, incident_name="  TEST fire ")

    # footprint 4 only has a row of `Other Fire`; footprint 0 has a row written `test fire`
    assert _text(group["building_damage"])[4] == "No Damage"
    assert group["dins_match_count"][0] == 2
    assert group.attrs["dins_record_count"] == 7
    assert group.attrs["dins_incident_name"] == "Test Fire"


def test_rows_outside_the_box_are_dropped_and_counted_when_clipping(inputs):
    clipped = _standardize(inputs)
    assert clipped.attrs["dins_records_outside_box"] == 1
    assert clipped.attrs["dins_record_count"] == 7
    assert _text(clipped["building_source"]) == ["MBF"] * 5 + ["DINS"]

    kept = _standardize(inputs, clip_to_box=False, overwrite=True)
    assert kept.attrs["dins_records_outside_box"] == 0
    assert kept.attrs["dins_record_count"] == 8
    # DINS-only buildings follow the footprints, in table order
    assert _text(kept["building_source"]) == ["MBF"] * 5 + ["DINS", "DINS"]
    assert kept["position_lat"][5] == pytest.approx(_lonlat(3, 51)[1], abs=1e-12)
    assert kept["position_lat"][6] == pytest.approx(_lonlat(2, 0, 5_000)[1], abs=1e-12)


def test_datasets_and_attributes(inputs):
    dins_csv, footprints, _ = inputs

    group = _standardize(inputs, footprints_source="test source")

    assert group.name == "/points/building_damaged"
    datasets = {name: (group[name].dtype.kind, group[name].attrs["units"]) for name in group}
    assert datasets == {
        "position_lat": ("f", "degree"),
        "position_lon": ("f", "degree"),
        "building_damage": ("S", "dimensionless"),
        "dins_matched": ("b", "dimensionless"),
        "dins_match_count": ("i", "dimensionless"),
        "building_source": ("S", "dimensionless"),
        "dins_match_distance_m": ("f", "m"),
    }
    assert group["position_lat"].dtype == np.float64
    assert group["dins_match_count"].dtype == np.int32
    assert group["dins_match_distance_m"].dtype == np.float64
    assert dict(group.attrs) == {
        "source_data_hash": hashlib.sha256(dins_csv.read_bytes()).hexdigest(),
        "mbf_source": "test source",
        "mbf_source_data_hash": hashlib.sha256(footprints.read_bytes()).hexdigest(),
        "default_damage_for_unmatched_mbf": "No Damage",
        "dins_only_fallback_distance_m": 50.0,
        "dins_only_synthetic_building_radius_m": 5.0,
        "dins_record_count": 7,
        "dins_records_outside_box": 1,
        "dins_incident_name": "Test Fire",
        "dins_incident_numbers": '["N-1"]',
        "dins_incident_start_date": "2021-08-14",
    }
    # footprints in file order, at their centroids
    for footprint in range(5):
        lon, lat = _lonlat(footprint)
        assert group["position_lat"][footprint] == pytest.approx(lat, abs=1e-9)
        assert group["position_lon"][footprint] == pytest.approx(lon, abs=1e-9)


def test_default_projection_is_the_utm_zone_of_the_box(inputs):
    group = _standardize(inputs, projected_crs=None)

    assert _text(group["building_source"]) == ["MBF"] * 5 + ["DINS"]
    assert group["dins_match_distance_m"][:3] == pytest.approx([5.0, 10.0, 30.0], abs=1e-3)


def test_name_that_covers_several_incident_numbers_is_refused(inputs):
    with pytest.raises(ValueError) as error:
        _standardize(inputs, incident_name="Twin")

    message = str(error.value)
    assert "Give `incident_numbers`" in message
    assert "'N-2' (start 2020-09-04, 2 rows)" in message
    assert "'N-3' (start 2022-06-01, 1 rows)" in message
    assert "points" not in inputs[2]


def test_incident_numbers_select_the_rows(inputs):
    one = _standardize(inputs, incident_name="Twin", incident_numbers=["N-2"])
    assert _text(one["building_damage"])[:3] == ["Destroyed (>50%)", "Minor (10-25%)", "No Damage"]
    assert one.attrs["dins_record_count"] == 2
    assert one.attrs["dins_incident_numbers"] == '["N-2"]'
    assert one.attrs["dins_incident_start_date"] == "2020-09-04"

    other = _standardize(inputs, incident_name="Twin", incident_numbers="N-3", overwrite=True)
    assert _text(other["building_damage"])[:3] == ["No Damage", "No Damage", "Major (26-50%)"]

    both = _standardize(inputs, incident_name="Twin", incident_numbers=["N-3", "N-2"], overwrite=True)
    assert _text(both["building_damage"])[:3] == ["Destroyed (>50%)", "Minor (10-25%)", "Major (26-50%)"]
    assert json.loads(both.attrs["dins_incident_numbers"]) == ["N-2", "N-3"]


@pytest.mark.parametrize("incident_numbers", [["N-9"], ["N-2", "N-4"], []])
def test_unknown_incident_number_is_refused(inputs, incident_numbers):
    with pytest.raises(ValueError, match="Its incident numbers: 'N-2'"):
        _standardize(inputs, incident_name="Twin", incident_numbers=incident_numbers)


def test_refusals(inputs, tmp_path):
    dins_csv, footprints, h5 = inputs

    with pytest.raises(ValueError, match="no row of .* has the incident name 'Missing Fire'"):
        _standardize(inputs, incident_name="Missing Fire")
    with pytest.raises(ValueError, match="no footprint of .* intersects the box"):
        _standardize((dins_csv, _write_footprints(tmp_path / "far.geojsonl", footprints=(60,)), h5))
    with pytest.raises(ValueError, match="1 rows are outside"):
        _standardize((_write_dins(tmp_path / "outside.csv", rows=[DINS_ROWS[7]]), footprints, h5))
    with pytest.raises(ValueError, match="projected CRS in metres"):
        _standardize(inputs, projected_crs="EPSG:4326")
    assert "points" not in h5

    _standardize(inputs)
    with pytest.raises(ValueError, match="already exists"):
        _standardize(inputs)


def test_unreadable_inputs_are_refused(inputs, tmp_path):
    dins_csv, footprints, h5 = inputs
    no_number = [name for name in HEADER if name != NUMBER_COLUMN]
    broken = tmp_path / "broken.geojsonl"
    broken.write_text(footprints.read_text(encoding="utf-8").splitlines()[0] + '\n{"type": "Feature"}\n')

    with pytest.raises(ValueError, match="column `Incident Number` not found"):
        fs.list_dins_incidents(_write_dins(tmp_path / "no_number.csv", header=no_number))
    with pytest.raises(ValueError, match="could not be read"):
        fs.list_dins_incidents(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="line 2 is not a GeoJSON feature"):
        _standardize((dins_csv, broken, h5))
    with pytest.raises(ValueError, match="could not be read"):
        _standardize((dins_csv, tmp_path / "missing.geojsonl", h5))
    assert "points" not in h5


def test_written_file_reads_back(inputs):
    _, _, h5 = inputs
    _standardize(inputs)
    path = h5.filename
    h5.flush()

    with h5py.File(path, "r") as written:
        assert written["points/building_damaged/position_lat"].shape == (6,)
