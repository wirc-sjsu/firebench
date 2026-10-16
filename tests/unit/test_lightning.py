import gzip
import json
from datetime import datetime, timezone

import h5py
import numpy as np
import pytest

from firebench.acquisition import nldn_tiles
from firebench.standardize import (
    lightning_time_series,
    list_lightning_streams,
    new_std_file,
    standardize_lightning_strokes,
    standardize_nldn_tiles,
)

BBOX = (-121.0, 38.0, -120.0, 39.0)
START = datetime(2021, 8, 12, 18, tzinfo=timezone.utc)
END = datetime(2021, 8, 14, 0, tzinfo=timezone.utc)

ROWS_2021 = [
    "20210811,-120.5,38.5,7",  # the day before the window
    "20210812,-120.5,38.5,2",  # overlaps the window, which starts at 18 UTC
    "20210812,-119.5,38.5,9",  # outside the box
    "20210813,-120.2,38.9,1",
    "20210813,-120.5,38.5,4",
    "20210814,-120.5,38.5,5",  # the end is at midnight: no part of the 14th
]


def _tile_file(directory, name, rows):
    body = "#This file contains the count of Vaisala NLDN lightning strikes.\n#ZDAY,CENTERLON,CENTERLAT,TOTAL_COUNT\n"
    (directory / name).write_bytes(gzip.compress((body + "\n".join(rows) + "\n").encode()))


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.status = 200

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def std_file(tmp_path):
    file = new_std_file(tmp_path / "data.h5", "tester")
    yield file
    file.close()


@pytest.fixture
def tiles_dir(tmp_path):
    directory = tmp_path / "ncei"
    directory.mkdir()
    _tile_file(directory, "nldn-tiles-2021.csv.gz", ROWS_2021)
    _tile_file(directory, "nldn-tiles-2020.csv.gz", ["20200812,-120.5,38.5,3"])
    (directory / "README.txt").write_text("not a tile file")
    return directory


def test_window_days_overlap_and_an_end_at_midnight_takes_no_day():
    assert nldn_tiles.window_days(START, END) == (START.date(), datetime(2021, 8, 13).date())
    instant = datetime(2021, 8, 13, tzinfo=timezone.utc)
    assert nldn_tiles.window_days(instant, instant) == (instant.date(), instant.date())
    with pytest.raises(ValueError, match="no time zone"):
        nldn_tiles.window_days(datetime(2021, 8, 1), END)


def test_annual_files_are_preferred_and_missing_months_are_named():
    available = ["nldn-tiles-2025.csv.gz", "nldn-tiles-202601.csv.gz", "nldn-tiles-202602.csv.gz"]
    names, missing = nldn_tiles.tile_files(
        datetime(2025, 12, 30, tzinfo=timezone.utc), datetime(2026, 3, 2, tzinfo=timezone.utc), available
    )
    assert names == ["nldn-tiles-2025.csv.gz", "nldn-tiles-202601.csv.gz", "nldn-tiles-202602.csv.gz"]
    assert missing == ["2026-03"]


def test_fetch_keeps_the_cells_of_the_box_on_the_days_of_the_window(tiles_dir):
    tiles = nldn_tiles.fetch_nldn_tiles(BBOX, START, END, local_dir=tiles_dir)
    assert [str(day) for day in tiles.day] == ["2021-08-12", "2021-08-13", "2021-08-13"]
    assert tiles.count.tolist() == [2, 4, 1]
    assert tiles.lat.tolist() == [38.5, 38.5, 38.9]
    assert tiles.files[0]["name"] == "nldn-tiles-2021.csv.gz"
    assert tiles.files[0]["rows"] == 3
    assert tiles.missing == []


def test_fetch_lists_ncei_and_downloads_the_files_it_needs(tiles_dir):
    urls = []

    def opener(request, timeout):
        urls.append(request.full_url)
        if request.full_url == nldn_tiles.BASE_URL:
            return _Response(
                b'<a href="nldn-tiles-2020.csv.gz">x</a> <a href="nldn-tiles-2021.csv.gz">y</a>'
            )
        return _Response((tiles_dir / request.full_url.rsplit("/", 1)[1]).read_bytes())

    tiles = nldn_tiles.fetch_nldn_tiles(BBOX, START, END, opener=opener)
    assert urls == [nldn_tiles.BASE_URL, nldn_tiles.BASE_URL + "nldn-tiles-2021.csv.gz"]
    assert int(tiles.count.sum()) == 7


def test_a_window_no_file_covers_is_refused(tiles_dir):
    with pytest.raises(ValueError, match="2022-08"):
        nldn_tiles.fetch_nldn_tiles(
            BBOX,
            datetime(2022, 8, 1, tzinfo=timezone.utc),
            datetime(2022, 8, 2, tzinfo=timezone.utc),
            local_dir=tiles_dir,
        )


def test_tiles_stream_holds_one_row_per_cell_day_and_its_counts(std_file, tiles_dir):
    tiles = nldn_tiles.fetch_nldn_tiles(BBOX, START, END, local_dir=tiles_dir)
    group = standardize_nldn_tiles(tiles, std_file)
    assert list_lightning_streams(std_file) == ["nldn_tiles"]
    assert dict(std_file["/unstructured"].attrs) == {}
    assert group.attrs["discharge"] == "cloud_to_ground"
    assert group.attrs["aggregation"] == "cell_day"
    assert group.attrs["period"] == 86400
    assert json.loads(group.attrs["source_files"])[0]["rows"] == 3
    strikes = group["strikes"]
    assert strikes["time"].attrs["time_origin"] == "2021-08-12T00:00:00+00:00"
    assert strikes["time"][()].tolist() == [0.0, 86400.0, 86400.0]
    assert strikes["time_end"][()].tolist() == [86400.0, 172800.0, 172800.0]
    assert strikes["lightning_stroke_count"][()].tolist() == [2, 4, 1]

    series = lightning_time_series(std_file, "nldn_tiles")
    assert series.step_s == 86400
    assert [str(value) for value in series.time.astype("datetime64[D]")] == ["2021-08-12", "2021-08-13"]
    assert series.count.tolist() == [2, 5]
    with pytest.raises(ValueError, match="shorter"):
        lightning_time_series(std_file, "nldn_tiles", 3600)


def test_a_window_without_strike_still_writes_the_stream(std_file, tiles_dir):
    tiles = nldn_tiles.fetch_nldn_tiles(BBOX, START, END, local_dir=tiles_dir)
    empty = nldn_tiles.NldnTiles(
        tiles.bbox, tiles.start, tiles.end, tiles.day[:0], tiles.lat[:0], tiles.lon[:0], tiles.count[:0]
    )
    group = standardize_nldn_tiles(empty, std_file)
    assert group["strikes/time"].shape == (0,)
    assert lightning_time_series(std_file, "nldn_tiles").count.tolist() == [0, 0]
    with pytest.raises(ValueError, match="already exists"):
        standardize_nldn_tiles(empty, std_file)


def test_strokes_keep_the_ground_strokes_of_the_box_and_window(std_file, tmp_path):
    csv = tmp_path / "strokes.csv"
    csv.write_text(
        "Timestamp, Latitude, Longitude, Peak_Current, Type\n"
        "2021-08-12T19:05:00Z, 38.5, -120.5, -21.4, G\n"
        "2021-08-12T19:06:00Z, 38.5, -120.5, 8.0, C\n"
        "2021-08-12T18:30:00Z, 38.6, -120.4, , CG\n"
        "2021-08-12T19:10:00Z, 39.5, -120.5, -15.0, G\n"
        "2021-08-12T17:00:00Z, 38.5, -120.5, -15.0, G\n"
    )
    group = standardize_lightning_strokes(csv, std_file, bbox=BBOX, start=START, end=END, network="ENTLN")
    assert group.attrs["aggregation"] == "stroke"
    assert group.attrs["network"] == "ENTLN"
    assert json.loads(group.attrs["source_files"])["cloud_rows_dropped"] == 1
    strikes = group["strikes"]
    assert strikes["time"][()].tolist() == [1800.0, 3900.0]
    assert strikes["time_end"][()].tolist() == [1800.0, 3900.0]
    assert np.isnan(strikes["lightning_peak_current"][0])
    assert strikes["lightning_peak_current"][1] == -21.4

    series = lightning_time_series(std_file, "strokes")
    assert series.step_s == 3600
    assert len(series.count) == 30
    assert series.count[:2].tolist() == [1, 1]


def test_a_stroke_file_without_type_or_with_unknown_types_is_refused(std_file, tmp_path):
    csv = tmp_path / "strokes.csv"
    csv.write_text("time,lat,lon\n2021-08-12T19:05:00Z,38.5,-120.5\n")
    with pytest.raises(ValueError, match="cloud flashes"):
        standardize_lightning_strokes(csv, std_file, bbox=BBOX, start=START, end=END)
    csv.write_text("date,time,lat,lon,type\n2021-08-12,19:05:00,38.5,-120.5,X\n")
    with pytest.raises(ValueError, match="unknown stroke types"):
        standardize_lightning_strokes(csv, std_file, bbox=BBOX, start=START, end=END)
    csv.write_text("date,time,lat,lon,type\n2021-08-12,19:05:00,38.5,-120.5,0\n")
    group = standardize_lightning_strokes(csv, std_file, bbox=BBOX, start=START, end=END, overwrite=True)
    assert group["strikes/time"][()].tolist() == [3900.0]


def test_an_unknown_stream_is_refused(tmp_path):
    with h5py.File(tmp_path / "empty.h5", "w") as file:
        with pytest.raises(ValueError, match="no lightning stream"):
            lightning_time_series(file, "nldn_tiles")
