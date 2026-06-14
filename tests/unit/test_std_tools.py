import pytest
import h5py
from datetime import datetime, timezone

from firebench.standardize import merge_authors, validate_h5_weather_stations_structure


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
