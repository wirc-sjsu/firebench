"""Readers of the sources of an event catalogue: MTBS, FPA FOD, and WFIGS, on files the tests write."""

import json
import math
import sqlite3

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from firebench.standardize import read_fpa_fod, read_mtbs_boundaries, read_wfigs_perimeters

CALDOR_IRWIN = "{9A1B2C3D-0000-4000-8000-00000000CAFE}"


def _square(lon, lat, half=0.05):
    return box(lon - half, lat - half, lon + half, lat + half)


@pytest.fixture
def mtbs_file(tmp_path):
    frame = gpd.GeoDataFrame(
        {
            "Event_ID": [
                "CA3858612053820210814",
                "CA3900012100020200901",
                "OR4400012100020210701",
                "CA3800012000020190601",
            ],
            "Incid_Name": ["CALDOR", "SMALL", "OREGON", "PRESCRIBED"],
            "Incid_Type": ["Wildfire", "Wildfire", "Wildfire", "Prescribed Fire"],
            "Ig_Date": ["2021-08-14", "2020-09-01", "2021-07-01", "2019-06-01"],
            "BurnBndAc": [221835.0, 1200.0, 5000.0, 900.0],
            "BurnBndLat": ["38.586", "39.000", "44.000", "38.000"],
            "BurnBndLon": ["-120.538", "-121.000", "-121.000", "-120.000"],
            "irwinID": [CALDOR_IRWIN, "", None, ""],
        },
        geometry=[_square(-120.538, 38.586), _square(-121, 39), _square(-121, 44), _square(-120, 38)],
        crs="EPSG:4326",
    ).to_crs("EPSG:5070")
    path = tmp_path / "mtbs_perims_DD.shp"
    frame.to_file(path)
    return path


def test_mtbs_reads_and_filters(mtbs_file):
    frame = read_mtbs_boundaries(mtbs_file)
    assert list(frame["mtbs_id"]) == [
        "CA3858612053820210814",
        "CA3900012100020200901",
        "OR4400012100020210701",
    ]
    caldor = frame.iloc[0]
    assert caldor["state"] == "CA" and caldor["year"] == 2021
    assert caldor["ignition_date"] == "2021-08-14" and caldor["ignition_date_precision"] == "day"
    assert caldor["ignition_lat"] == pytest.approx(38.586)
    assert caldor["irwin_id"] == "9a1b2c3d-0000-4000-8000-00000000cafe"
    assert frame.crs.to_epsg() == 4326
    assert caldor.geometry.contains(Point(-120.538, 38.586))

    assert list(read_mtbs_boundaries(mtbs_file, states=["ca"], years=(2021, 2021))["name"]) == ["CALDOR"]
    assert list(read_mtbs_boundaries(mtbs_file, min_acres=4000)["name"]) == ["CALDOR", "OREGON"]
    assert list(read_mtbs_boundaries(mtbs_file, bbox=(-121.2, 38.9, -120.8, 39.1))["name"]) == ["SMALL"]
    assert len(read_mtbs_boundaries(mtbs_file, incident_types=None)) == 4


def test_mtbs_refuses_a_missing_column(tmp_path):
    path = tmp_path / "bad.geojson"
    gpd.GeoDataFrame({"Event_ID": ["X"]}, geometry=[_square(0, 0)], crs="EPSG:4326").to_file(path)
    with pytest.raises(ValueError, match="no column `Incid_Name`"):
        read_mtbs_boundaries(path)


@pytest.fixture
def fod_file(tmp_path):
    rows = pd.DataFrame(
        {
            "FOD_ID": [1, 2, 3],
            "MTBS_ID": ["CA3858612053820210814", None, ""],
            "FIRE_NAME": ["CALDOR", "NO TIME", "OREGON"],
            "STATE": ["CA", "CA", "OR"],
            "FIRE_YEAR": [2021, 2020, 2021],
            "DISCOVERY_DATE": ["8/14/2021 0:00", "2020-06-02", "2021-07-01"],
            "DISCOVERY_TIME": ["1854", None, "0905"],
            "CONT_DATE": ["10/21/2021", None, "2021-07-03"],
            "CONT_TIME": ["1800", None, ""],
            "NWCG_GENERAL_CAUSE": [
                "Missing data/not specified/undetermined",
                "Debris and open burning",
                "Natural",
            ],
            "FIRE_SIZE": [221835.0, 3.0, 5000.0],
            "LATITUDE": [38.586, 39.1, 44.0],
            "LONGITUDE": [-120.538, -121.2, -121.0],
        }
    )
    path = tmp_path / "FPA_FOD.sqlite"
    with sqlite3.connect(path) as connection:
        rows.to_sql("Fires", connection, index=False)
    return path


def test_fpa_fod_reads_local_times_as_utc(fod_file):
    frame = read_fpa_fod(fod_file)
    assert list(frame["fod_id"]) == ["1", "2", "3"]
    caldor = frame.iloc[0]
    assert caldor["time_zone"] == "America/Los_Angeles"
    # 18:54 PDT on 2021-08-14 is 01:54 UTC the next day.
    assert caldor["discovery_time"] == "2021-08-15T01:54:00Z"
    assert caldor["discovery_time_precision"] == "minute"
    assert caldor["containment_time"] == "2021-10-22T01:00:00Z"
    assert caldor["mtbs_id"] == "CA3858612053820210814" and caldor["irwin_id"] == ""
    # A record without a time of day keeps its date, never a guessed midnight.
    no_time = frame.iloc[1]
    assert (no_time["discovery_time"], no_time["discovery_time_precision"]) == ("2020-06-02", "day")
    assert (no_time["containment_time"], no_time["containment_time_precision"]) == ("", "")
    # A containment date without a time keeps its date.
    oregon = frame.iloc[2]
    assert (oregon["containment_time"], oregon["containment_time_precision"]) == ("2021-07-03", "day")
    assert oregon["discovery_time"] == "2021-07-01T16:05:00Z"

    assert list(read_fpa_fod(fod_file, mtbs_only=True)["name"]) == ["CALDOR"]
    assert list(read_fpa_fod(fod_file, states=["OR"])["name"]) == ["OREGON"]
    assert list(read_fpa_fod(fod_file, min_acres=10)["name"]) == ["CALDOR", "OREGON"]


def test_fpa_fod_reads_julian_dates(tmp_path):
    path = tmp_path / "fod5.sqlite"
    rows = pd.DataFrame(
        {
            "FOD_ID": [7],
            "FIRE_NAME": ["OLD"],
            "STATE": ["CA"],
            "FIRE_YEAR": [2005],
            "DISCOVERY_DATE": [2453403.5],  # 2005-02-02
            "FIRE_SIZE": [1.0],
            "LATITUDE": [38.0],
            "LONGITUDE": [-120.0],
        }
    )
    with sqlite3.connect(path) as connection:
        rows.to_sql("Fires", connection, index=False)
    frame = read_fpa_fod(path)
    assert frame.iloc[0]["discovery_time"] == "2005-02-02"
    assert frame.iloc[0]["mtbs_id"] == "" and frame.iloc[0]["cause"] == ""


def test_fpa_fod_refuses_what_is_not_a_database(tmp_path):
    path = tmp_path / "not.sqlite"
    path.write_text("nothing")
    with pytest.raises(ValueError, match="cannot be read"):
        read_fpa_fod(path)


def test_wfigs_reads_perimeters(tmp_path):
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(gpd.GeoSeries([_square(-120.5, 38.6)]).to_json())["features"][0][
                "geometry"
            ],
            "properties": {
                "poly_IRWINID": CALDOR_IRWIN,
                "attr_UniqueFireIdentifier": "2021-CAENF-024030",
                "poly_IncidentName": "Caldor",
                "attr_POOState": "US-CA",
                "attr_FireDiscoveryDateTime": "2021-08-15T01:54:00Z",
                "attr_InitialLatitude": 38.586,
                "attr_InitialLongitude": -120.538,
                "poly_GISAcres": 221835.0,
            },
        },
        {
            "type": "Feature",
            "geometry": json.loads(gpd.GeoSeries([_square(-110, 40)]).to_json())["features"][0]["geometry"],
            "properties": {
                "poly_IRWINID": None,
                "attr_UniqueFireIdentifier": "2021-UT-1",
                "poly_IncidentName": "No IRWIN",
                "attr_POOState": "US-UT",
                "attr_FireDiscoveryDateTime": 1625097600000,
                "attr_InitialLatitude": None,
                "attr_InitialLongitude": None,
                "poly_GISAcres": 10.0,
            },
        },
    ]
    path = tmp_path / "wfigs.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    frame = read_wfigs_perimeters(path)
    assert len(frame) == 1
    caldor = frame.iloc[0]
    assert caldor["irwin_id"] == "9a1b2c3d-0000-4000-8000-00000000cafe"
    assert caldor["unique_fire_id"] == "2021-CAENF-024030" and caldor["state"] == "CA"
    assert caldor["discovery_time"] == "2021-08-15T01:54:00Z"
    assert caldor["discovery_time_precision"] == "minute" and caldor["year"] == 2021
    assert read_wfigs_perimeters(path, states=["OR"]).empty
    assert not math.isnan(caldor["origin_lat"])
