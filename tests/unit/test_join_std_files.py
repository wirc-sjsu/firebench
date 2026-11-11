import json
from datetime import datetime, timedelta, timezone
from itertools import permutations

import h5py
import numpy as np
import pytest

from firebench.signing.std_files import hdf5_subject_digest_sha256
from firebench.standardize import join_std_files, merge_std_files, new_std_file

STREAM = "unstructured/fire_detections/viirs_snpp"
T0 = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def _fragment(tmp_path, name, authors="Alice;", created_on="2026-08-22T12:00+00:00"):
    file = new_std_file(str(tmp_path / f"{name}.h5"), authors)
    file.attrs["created_on"] = created_on
    return file


def _station_fragment(tmp_path, name, minutes, wind, relative=True, station="station_A", **kwargs):
    """A station with `time` (minutes from 12:00 UTC, relative or ISO strings) and a wind series."""
    with _fragment(tmp_path, name, **kwargs) as file:
        group = file.create_group(f"time_series/{station}")
        group.attrs["name"] = "Test station"
        if relative:
            time = group.create_dataset("time", data=np.array(minutes, dtype=float))
            time.attrs["time_origin"], time.attrs["time_units"] = T0.isoformat(), "min"
        else:
            times = [(T0 + timedelta(minutes=m)).isoformat() for m in minutes]
            group.create_dataset("time", data=times, dtype=h5py.string_dtype())
        speed = group.create_dataset("wind_speed", data=np.array(wind, dtype=float))
        speed.attrs["units"] = "m/s"
        speed.attrs["sensor_height"] = 7.0
        speed.attrs["sensor_height_source_confidence_lvl"] = 2
    return str(tmp_path / f"{name}.h5")


def _stream_fragment(tmp_path, name, start_hour, detections, passes, attrs=None, **kwargs):
    """`passes` are minutes after the origin of observations; `detections` are (minute, pass row)."""
    origin = T0 + timedelta(hours=start_hour)
    stream_attrs = {
        "satellite": "Suomi NPP",
        "product": json.dumps(["VIIRS_SNPP_SP"]),
        "product_version": "2",
        "time_start": origin.isoformat(),
        "time_end": (origin + timedelta(hours=1)).isoformat(),
        "failed": "[]",
        "observations_complete": True,
        "observation_source": "cmr",
    }
    stream_attrs.update(attrs or {})
    with _fragment(tmp_path, name, **kwargs) as file:
        group = file.create_group(STREAM)
        group.attrs.update(stream_attrs)
        tables = {
            "observations": {
                "time": [m * 60.0 for m in passes],
                "time_end": [m * 60.0 + 360 for m in passes],
            },
            "detections": {
                "time": [m * 60.0 for m, _ in detections],
                "fire_radiative_power": [float(m) for m, _ in detections],
                "observation_index": [row for _, row in detections],
            },
        }
        for table, datasets in tables.items():
            for key, values in datasets.items():
                dtype = np.int64 if key == "observation_index" else float
                dataset = group.create_dataset(f"{table}/{key}", data=np.array(values, dtype=dtype))
                if key.startswith("time"):
                    dataset.attrs["time_origin"], dataset.attrs["time_units"] = origin.isoformat(), "s"
    return str(tmp_path / f"{name}.h5")


def _perimeter_fragment(tmp_path, name, group_name, **kwargs):
    with _fragment(tmp_path, name, **kwargs) as file:
        group = file.create_group(f"polygons/{group_name}")
        group.attrs["rel_path"] = f"kml/{group_name}.kml"
        group.attrs["time"] = T0.isoformat()
    return str(tmp_path / f"{name}.h5")


def test_stations_are_appended_in_time_order_whatever_the_order_given(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0, 10, 20], [1.0, 2.0, 3.0])
    second = _station_fragment(tmp_path, "h13", [60, 70], [4.0, 5.0])
    join_std_files([second, first], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        group = file["time_series/station_A"]
        assert list(group["time"][()]) == [0, 600, 1200, 3600, 4200]
        assert (
            group["time"].attrs["time_origin"] == T0.isoformat()
            and group["time"].attrs["time_units"] == "s"
        )
        assert list(group["wind_speed"][()]) == [1.0, 2.0, 3.0, 4.0, 5.0]
        assert group["wind_speed"].attrs["units"] == "m/s" and group.attrs["name"] == "Test station"


def test_absolute_times_are_written_relative_to_the_first_sample(tmp_path):
    first = _station_fragment(tmp_path, "h12", [10, 20], [1.0, 2.0], relative=False)
    second = _station_fragment(tmp_path, "h13", [60], [3.0])  # one fragment relative, one absolute
    join_std_files([first, second], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        time = file["time_series/station_A/time"]
        assert list(time[()]) == [0, 600, 3000]
        assert time.attrs["time_origin"] == (T0 + timedelta(minutes=10)).isoformat()


def test_a_time_present_twice_is_kept_once_when_the_values_agree(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0, 10], [1.0, np.nan])
    second = _station_fragment(tmp_path, "h13", [10, 20], [np.nan, 3.0])
    join_std_files([first, second], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        assert file["time_series/station_A/time"].shape == (3,)
        assert np.allclose(file["time_series/station_A/wind_speed"][()], [1.0, np.nan, 3.0], equal_nan=True)


def test_a_time_present_twice_with_different_values_is_refused_naming_station_and_time(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0, 10], [1.0, 2.0])
    second = _station_fragment(tmp_path, "h13", [10, 20], [2.5, 3.0])
    with pytest.raises(ValueError, match=r"station /time_series/station_A.*2026-08-22T12:10:00\+00:00"):
        join_std_files([first, second], str(tmp_path / "joined.h5"))
    assert not (tmp_path / "joined.h5").exists()


def test_an_attribute_that_differs_is_refused_naming_station_dataset_and_attribute(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    with h5py.File(second, "r+") as file:
        file["time_series/station_A/wind_speed"].attrs["sensor_height"] = 10.0
    with pytest.raises(ValueError, match="station_A, dataset 'wind_speed': attribute 'sensor_height'"):
        join_std_files([first, second], str(tmp_path / "joined.h5"))

    with h5py.File(second, "r+") as file:
        file["time_series/station_A/wind_speed"].attrs["sensor_height"] = 7.0
        file["time_series/station_A"].attrs["name"] = "Other"
    with pytest.raises(ValueError, match="station /time_series/station_A: attribute 'name'"):
        join_std_files([first, second], str(tmp_path / "joined.h5"))


def test_a_series_held_by_some_fragments_only_is_filled_with_nan(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0, 10], [1.0, 2.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    with h5py.File(second, "r+") as file:
        del file["time_series/station_A/wind_speed"]
    join_std_files([second, first], str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        speed = file["time_series/station_A/wind_speed"]
        assert np.allclose(speed[()], [1.0, 2.0, np.nan], equal_nan=True)
        assert speed.attrs["units"] == "m/s"  # from the fragment that holds it


def test_a_missing_series_takes_the_fill_value_and_a_non_float_one_without_it_is_refused(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    with h5py.File(first, "r+") as file:
        flag = file["time_series/station_A"].create_dataset("flag", data=np.array([3], dtype=np.int16))
        flag.attrs["_FillValue"] = np.int16(-1)
    join_std_files([first, second], str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        assert list(file["time_series/station_A/flag"][()]) == [3, -1]
    with h5py.File(first, "r+") as file:
        del file["time_series/station_A/flag"].attrs["_FillValue"]
    with pytest.raises(ValueError, match="station_A, dataset 'flag': missing in some fragments"):
        join_std_files([first, second], str(tmp_path / "other.h5"))


def test_a_dataset_that_is_not_a_series_must_be_in_every_fragment(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    with h5py.File(first, "r+") as file:
        file["time_series/station_A"].create_dataset("calibration", data=np.array([1.0, 2.0, 3.0]))
    with pytest.raises(
        ValueError, match="dataset 'calibration': missing in some fragments and not a series"
    ):
        join_std_files([first, second], str(tmp_path / "joined.h5"))


def test_detections_follow_their_observation_after_the_join_and_the_sort(tmp_path):
    # Hour 0: passes at 5 and 40 min; hour 1: a pass at 10 min. Detections point to a pass.
    early = _stream_fragment(tmp_path, "h12", 0, [(5, 0), (41, 1), (42, 1)], [5, 40])
    late = _stream_fragment(tmp_path, "h13", 1, [(10, 0)], [10])
    join_std_files([late, early], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        group = file[STREAM]
        assert group["observations/time"].attrs["time_origin"] == T0.isoformat()
        assert list(group["observations/time"][()]) == [300, 2400, 4200]
        assert list(group["observations/time_end"][()]) == [660, 2760, 4560]
        assert list(group["detections/time"][()]) == [300, 2460, 2520, 4200]
        assert list(group["detections/observation_index"][()]) == [0, 1, 1, 2]
        assert group["detections/observation_index"].dtype == np.int64
        assert list(group["detections/fire_radiative_power"][()]) == [5.0, 41.0, 42.0, 10.0]


def test_an_observation_sorted_before_another_fragment_shifts_the_index_of_its_detections(tmp_path):
    # The fragments overlap in time: the second one's pass comes between the first one's.
    first = _stream_fragment(tmp_path, "h12", 0, [(1, 0), (50, 1)], [1, 50])
    second = _stream_fragment(tmp_path, "h12b", 0, [(20, 0)], [20])
    join_std_files([first, second], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        group = file[STREAM]
        assert list(group["observations/time"][()]) == [60, 1200, 3000]
        assert list(group["detections/time"][()]) == [60, 1200, 3000]
        assert list(group["detections/observation_index"][()]) == [0, 1, 2]


def test_stream_attributes_are_joined(tmp_path):
    first = _stream_fragment(
        tmp_path,
        "h12",
        0,
        [(5, 0)],
        [5],
        {"product": json.dumps(["VIIRS_SNPP_SP"]), "failed": json.dumps([{"day": "d1", "reason": "x"}])},
    )
    second = _stream_fragment(
        tmp_path,
        "h13",
        1,
        [(10, 0)],
        [10],
        {
            "product": json.dumps(["VIIRS_SNPP_NRT", "VIIRS_SNPP_SP"]),
            "product_version": "2;1",
            "failed": json.dumps([{"day": "d1", "reason": "x"}, {"day": "d2", "reason": "y"}]),
            "observations_complete": False,
        },
    )
    join_std_files([second, first], str(tmp_path / "joined.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        attrs = file[STREAM].attrs
        assert attrs["time_start"] == T0.isoformat()
        assert attrs["time_end"] == (T0 + timedelta(hours=2)).isoformat()
        assert json.loads(attrs["product"]) == ["VIIRS_SNPP_NRT", "VIIRS_SNPP_SP"]
        assert attrs["product_version"] == "1;2"
        assert json.loads(attrs["failed"]) == [{"day": "d1", "reason": "x"}, {"day": "d2", "reason": "y"}]
        assert not attrs["observations_complete"]
        assert attrs["satellite"] == "Suomi NPP"


def test_observation_source_lists_the_distinct_values_and_another_attribute_must_agree(tmp_path):
    first = _stream_fragment(tmp_path, "h12", 0, [(5, 0)], [5])
    same = _stream_fragment(tmp_path, "h13", 1, [(10, 0)], [10])
    mixed = _stream_fragment(tmp_path, "h14", 2, [(10, 0)], [10], {"observation_source": "detections"})
    join_std_files([first, same], str(tmp_path / "same.h5"))
    join_std_files([mixed, first, same], str(tmp_path / "mixed.h5"))
    with h5py.File(tmp_path / "same.h5") as file:
        assert file[STREAM].attrs["observation_source"] == "cmr"
    with h5py.File(tmp_path / "mixed.h5") as file:
        assert file[STREAM].attrs["observation_source"] == "cmr;detections"

    other = _stream_fragment(tmp_path, "h15", 3, [(10, 0)], [10], {"satellite": "NOAA-20"})
    with pytest.raises(
        ValueError, match="stream /unstructured/fire_detections/viirs_snpp: attribute 'satellite'"
    ):
        join_std_files([first, other], str(tmp_path / "joined.h5"))


def test_perimeters_go_side_by_side_and_the_same_one_twice_is_refused(tmp_path):
    first = _perimeter_fragment(tmp_path, "p1", "perimeter_1")
    second = _perimeter_fragment(tmp_path, "p2", "perimeter_2")
    join_std_files([second, first], str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        assert list(file["polygons"]) == ["perimeter_1", "perimeter_2"]
        assert file["polygons/perimeter_2"].attrs["rel_path"] == "kml/perimeter_2.kml"

    again = _perimeter_fragment(tmp_path, "p3", "perimeter_1")
    with pytest.raises(ValueError, match="/polygons/perimeter_1 is in two fragments"):
        join_std_files([first, again], str(tmp_path / "other.h5"))


def test_stations_streams_and_perimeters_join_in_one_file(tmp_path):
    parts = [
        _station_fragment(tmp_path, "w", [0, 10], [1.0, 2.0]),
        _stream_fragment(tmp_path, "s", 0, [(5, 0)], [5]),
        _perimeter_fragment(tmp_path, "p", "perimeter_1"),
    ]
    join_std_files(parts, str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        assert "time_series/station_A" in file and STREAM in file and "polygons/perimeter_1" in file


def test_the_same_fragments_in_any_order_give_the_same_file(tmp_path):
    parts = [
        _station_fragment(tmp_path, "h12", [0, 10], [1.0, 2.0], created_on="2026-08-22T13:00+00:00"),
        _station_fragment(
            tmp_path, "h13", [60, 70], [3.0, 4.0], authors="Bob;", created_on="2026-08-22T14:00+00:00"
        ),
        _station_fragment(tmp_path, "h14", [120], [5.0], authors="Alice;Carol;"),
    ]
    digests, contents = set(), set()
    for number, order in enumerate(permutations(parts)):
        target = tmp_path / f"joined_{number}.h5"
        join_std_files(list(order), str(target), description="joined")
        digests.add(hdf5_subject_digest_sha256(str(target)))
        contents.add(target.read_bytes())
    assert len(digests) == 1
    assert len(contents) == 1
    with h5py.File(tmp_path / "joined_0.h5") as file:
        assert file.attrs["created_on"] == "2026-08-22T14:00+00:00"
        assert file.attrs["created_by"] == "Alice;Bob;Carol;"
        assert file.attrs["description"] == "joined"


def test_fragments_with_the_same_first_sample_are_ordered_by_their_content(tmp_path):
    first = _station_fragment(tmp_path, "a", [0], [1.0], station="station_A")
    second = _station_fragment(tmp_path, "b", [0], [1.0], station="station_B")
    join_std_files([first, second], str(tmp_path / "ab.h5"))
    join_std_files([second, first], str(tmp_path / "ba.h5"))
    assert (tmp_path / "ab.h5").read_bytes() == (tmp_path / "ba.h5").read_bytes()


def test_one_fragment_is_normalised_and_a_repeated_time_inside_it_is_dropped(tmp_path):
    single = _station_fragment(tmp_path, "h12", [10, 0, 10], [2.0, 1.0, 2.0], relative=False)
    join_std_files([single], str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        assert list(file["time_series/station_A/time"][()]) == [0, 600]


def test_a_root_attribute_that_differs_is_refused(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    for path, value in ((first, "one"), (second, "two")):
        with h5py.File(path, "r+") as file:
            file.attrs["wx_qc_policy_sha256"] = value
    with pytest.raises(ValueError, match="root: attribute 'wx_qc_policy_sha256'"):
        join_std_files([first, second], str(tmp_path / "joined.h5"))


def test_a_root_attribute_held_by_some_fragments_only_is_compared_among_them(tmp_path):
    station = _station_fragment(tmp_path, "h12", [0], [1.0])
    stream = _stream_fragment(tmp_path, "s1", 0, [(5, 0)], [5])
    with h5py.File(station, "r+") as file:
        file.attrs["wx_qc_policy_sha256"] = "policy"
    join_std_files([stream, station], str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as file:
        assert file.attrs["wx_qc_policy_sha256"] == "policy"


def test_provenance_attributes_are_left_out_when_they_differ_and_kept_when_they_agree(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    for number, path in enumerate((first, second)):
        with h5py.File(path, "r+") as file:
            station = file["time_series/station_A"]
            file.attrs["wx_qc_run_id"] = f"run{number}"
            file.attrs["wx_qc_source_sha256"] = "same"
            station.attrs["source_file_sha256"] = f"hash{number}"
            station["wind_speed"].attrs["sensor_height_source_reference"] = f"ref{number}"
            station["wind_speed"].attrs["sensor_height_verification_date"] = "2026-08-22"
    third = _stream_fragment(tmp_path, "s1", 0, [(5, 0)], [5], {"source_files": '{"a": 1}'})
    fourth = _stream_fragment(tmp_path, "s2", 1, [(5, 0)], [5], {"source_files": '{"a": 2}'})
    join_std_files([first, second], str(tmp_path / "joined.h5"))
    join_std_files([third, fourth], str(tmp_path / "streams.h5"))

    with h5py.File(tmp_path / "joined.h5") as file:
        station = file["time_series/station_A"]
        assert "wx_qc_run_id" not in file.attrs and file.attrs["wx_qc_source_sha256"] == "same"
        assert "source_file_sha256" not in station.attrs
        assert "sensor_height_source_reference" not in station["wind_speed"].attrs
        assert station["wind_speed"].attrs["sensor_height_verification_date"] == "2026-08-22"
        assert station["wind_speed"].attrs["sensor_height"] == 7.0  # any other attribute is kept
    with h5py.File(tmp_path / "streams.h5") as file:
        assert "source_files" not in file[STREAM].attrs


def test_no_path_and_an_existing_target_are_refused(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        join_std_files([], str(tmp_path / "joined.h5"))
    single = _station_fragment(tmp_path, "h12", [0], [1.0])
    join_std_files([single], str(tmp_path / "joined.h5"))
    with pytest.raises(FileExistsError):
        join_std_files([single], str(tmp_path / "joined.h5"))
    join_std_files([single], str(tmp_path / "joined.h5"), overwrite=True)


def test_merge_std_files_still_refuses_what_join_std_files_joins(tmp_path):
    first = _station_fragment(tmp_path, "h12", [0], [1.0])
    second = _station_fragment(tmp_path, "h13", [60], [2.0])
    with pytest.raises(ValueError, match="onflict"):
        merge_std_files([first, second], str(tmp_path / "merged.h5"))


def test_the_trusted_station_selection_and_the_window_readers_accept_a_joined_file(tmp_path):
    from firebench.benchmarks import fire_case_definition as fcd  # pylint: disable=import-outside-toplevel
    from firebench.benchmarks import wx_common  # pylint: disable=import-outside-toplevel
    from firebench.benchmarks.fire_case_parameters import (
        load_parameters,
    )  # pylint: disable=import-outside-toplevel
    from firebench.benchmarks.wx_cadence import station_times_utc  # pylint: disable=import-outside-toplevel
    from firebench.standardize import WeatherStationSet  # pylint: disable=import-outside-toplevel

    first = _station_fragment(tmp_path, "h12", [0, 10], [1.0, 2.0])
    second = _station_fragment(tmp_path, "h13", [60, 70], [3.0, 4.0])
    for number, path in enumerate((first, second)):
        with h5py.File(path, "r+") as file:  # what differs from hour to hour is not read by the selection
            file["time_series/station_A/wind_speed"].attrs[
                "sensor_height_source_reference"
            ] = f"ref{number}"
            file["time_series/station_A/wind_speed"].attrs["sensor_height_verification_date"] = f"d{number}"
    perimeter = _perimeter_fragment(tmp_path, "p1", "perimeter_1")
    join_std_files([second, first, perimeter], str(tmp_path / "joined.h5"))

    period = (T0, T0 + timedelta(hours=3))
    with h5py.File(first) as fragment, h5py.File(tmp_path / "joined.h5") as joined:
        for station_set in WeatherStationSet:
            expected = wx_common.select_weather_stations(fragment, "wind_speed", period, station_set)
            assert wx_common.select_weather_stations(joined, "wind_speed", period, station_set) == expected
        assert expected["included"] == [{"station": "station_A", "confidence": 2}]
        assert list(station_times_utc(joined, "/time_series/station_A")) == [
            np.datetime64((T0 + timedelta(minutes=m)).replace(tzinfo=None), "s") for m in (0, 10, 60, 70)
        ]
        assert list(fcd.perimeter_times(joined)) == ["/polygons/perimeter_1"]
        assert fcd.data_span(joined, load_parameters()) is not None


def test_an_attribute_that_holds_several_values_is_compared_whole(tmp_path):
    paths = [_station_fragment(tmp_path, "a", [0], [1.0]), _station_fragment(tmp_path, "b", [10], [2.0])]
    for path, corner in zip(paths, ([1.0, 2.0], [1.0, 2.0])):
        with h5py.File(path, "a") as file:
            file["time_series/station_A"].attrs["position"] = np.array(corner)
    join_std_files(paths, str(tmp_path / "joined.h5"))
    with h5py.File(tmp_path / "joined.h5") as joined:
        assert joined["time_series/station_A"].attrs["position"].tolist() == [1.0, 2.0]
    with h5py.File(paths[1], "a") as file:
        file["time_series/station_A"].attrs["position"] = np.array([1.0, 3.0])
    with pytest.raises(ValueError, match="attribute 'position' differs"):
        join_std_files(paths, str(tmp_path / "other.h5"))
