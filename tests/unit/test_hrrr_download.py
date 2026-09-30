import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from firebench.acquisition.hrrr import forecast, grid, inventory, read

# Trimmed from hrrr.20210820/conus/hrrr.t00z.wrfsfcf01.grib2.idx (NOAA Open Data on AWS)
IDX_2021082000_F01 = """\
8:3152171:d=2021082000:REFD:263 K level:1 hour fcst:
9:3341423:d=2021082000:GUST:surface:1 hour fcst:
10:4483027:d=2021082000:UGRD:250 mb:1 hour fcst:
62:37388796:d=2021082000:PRES:surface:1 hour fcst:
63:38885285:d=2021082000:HGT:surface:1 hour fcst:
64:41043753:d=2021082000:TMP:surface:1 hour fcst:
70:43910976:d=2021082000:SNOD:surface:1 hour fcst:
71:43912124:d=2021082000:TMP:2 m above ground:1 hour fcst:
72:45130573:d=2021082000:POT:2 m above ground:1 hour fcst:
74:47840095:d=2021082000:DPT:2 m above ground:1 hour fcst:
75:48981668:d=2021082000:RH:2 m above ground:1 hour fcst:
76:50517460:d=2021082000:MASSDEN:8 m above ground:1 hour fcst:
77:51271891:d=2021082000:UGRD:10 m above ground:1 hour fcst:
78:53653506:d=2021082000:VGRD:10 m above ground:1 hour fcst:
79:56035121:d=2021082000:WIND:10 m above ground:0-1 hour max fcst:
80:57175065:d=2021082000:MAXUW:10 m above ground:0-1 hour max fcst:
93:60213124:d=2021082000:CRAIN:surface:1 hour fcst:
94:60280092:d=2021082000:SFCR:surface:1 hour fcst:
95:62178879:d=2021082000:FRICV:surface:1 hour fcst:
170:153023287:d=2021082000:SBT114:top of atmosphere:1 hour fcst:
"""

CYCLE = datetime(2021, 8, 20, 0, tzinfo=timezone.utc)


def test_parse_index_derives_inclusive_ranges_and_open_last_message():
    messages = inventory.parse_index(IDX_2021082000_F01)

    tmp_2m = next(message for message in messages if message.field == "TMP:2 m above ground")
    assert (tmp_2m.byte_start, tmp_2m.byte_end) == (43912124, 45130572)
    assert messages[-1].byte_end is None
    assert tmp_2m.instantaneous


def test_parse_index_tolerates_sub_message_numbers_sharing_an_offset():
    text = "600:100:d=x:UGRD:10 m above ground:anl:\n600.2:100:d=x:VGRD:10 m above ground:anl:\n601:250:d=x:A:b:anl:\n"

    messages = inventory.parse_index(text)

    assert [message.number for message in messages] == ["600", "600.2", "601"]
    assert messages[0].byte_end == messages[1].byte_end == 249


def test_selection_ignores_time_statistics_of_the_same_variable_and_level():
    text = "1:0:d=x:WIND:10 m above ground:0-1 hour max fcst:\n2:50:d=x:WIND:10 m above ground:1 hour fcst:\n3:90:d=x:Z:s:anl:\n"

    selected = inventory.select_messages(inventory.parse_index(text), ["WIND:10 m above ground"])

    assert [(message.byte_start, message.forecast) for message in selected] == [(50, "1 hour fcst")]


def test_selection_of_hrrr_surface_fields_is_in_byte_order():
    messages = inventory.parse_index(IDX_2021082000_F01)

    selected = inventory.select_messages(messages, forecast.fields_for_hour(0))

    assert [message.field for message in selected] == [
        "HGT:surface",
        "TMP:2 m above ground",
        "RH:2 m above ground",
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "SFCR:surface",
    ]


def test_selection_reports_every_missing_field():
    with pytest.raises(ValueError, match="GUST:10 m above ground"):
        inventory.select_messages(inventory.parse_index(IDX_2021082000_F01), ["GUST:10 m above ground"])


def test_selection_rejects_fields_packed_in_one_message():
    text = "600:100:d=x:UGRD:10 m above ground:anl:\n600.2:100:d=x:VGRD:10 m above ground:anl:\n601:250:d=x:A:b:anl:\n"

    with pytest.raises(ValueError, match="share a GRIB message"):
        inventory.select_messages(
            inventory.parse_index(text), ["UGRD:10 m above ground", "VGRD:10 m above ground"]
        )


@pytest.mark.parametrize(
    ("cycle", "version", "horizon"),
    (
        (datetime(2021, 8, 20, 0, tzinfo=timezone.utc), 4, 48),
        (datetime(2021, 8, 20, 1, tzinfo=timezone.utc), 4, 18),
        (datetime(2020, 12, 2, 12, tzinfo=timezone.utc), 4, 48),
        (datetime(2020, 12, 2, 6, tzinfo=timezone.utc), 3, 36),
        (datetime(2020, 9, 15, 0, tzinfo=timezone.utc), 3, 36),
        (datetime(2018, 7, 12, 6, tzinfo=timezone.utc), 2, 18),
    ),
)
def test_forecast_horizon_follows_the_hrrr_version(cycle, version, horizon):
    assert forecast.hrrr_version(cycle) == version
    assert forecast.max_forecast_hour(cycle) == horizon


@pytest.mark.parametrize(
    "cycle",
    (datetime(2021, 8, 20, 0), datetime(2021, 8, 20, 0, 30, tzinfo=timezone.utc)),
)
def test_cycles_must_be_aware_and_on_the_hour(cycle):
    with pytest.raises(ValueError):
        forecast.validate_cycle(cycle)


def test_cycle_in_another_time_zone_is_normalized_to_utc():
    pacific = timezone(timedelta(hours=-7))

    assert forecast.validate_cycle(datetime(2021, 8, 19, 17, tzinfo=pacific)) == CYCLE


def test_grib_url_points_to_the_surface_product():
    assert forecast.grib_url(CYCLE, 1) == (
        "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20210820/conus/hrrr.t00z.wrfsfcf01.grib2"
    )


class _FakeArchive:
    """Serves the trimmed idx and byte ranges, counting requests."""

    def __init__(self, missing_hours=()) -> None:
        self.missing_hours = set(missing_hours)
        self.idx_requests = 0
        self.range_requests = []

    def fetch_text(self, url, **kwargs):
        self.idx_requests += 1
        if any(f"wrfsfcf{fxx:02d}" in url for fxx in self.missing_hours):
            raise FileNotFoundError(f"remote file not found: {url} (HTTP 404)")
        return IDX_2021082000_F01

    def http_get(self, url, byte_range=None, **kwargs):
        self.range_requests.append(byte_range)
        start, end = byte_range
        return b"x" * (end - start + 1)


@pytest.fixture
def archive(monkeypatch):
    fake = _FakeArchive()
    monkeypatch.setattr(forecast, "fetch_text", fake.fetch_text)
    monkeypatch.setattr("firebench.acquisition.http.http_get", fake.http_get)
    return fake


def test_fetch_file_downloads_the_subset_and_writes_a_sidecar(archive, tmp_path):
    path = forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)

    sidecar = json.loads(path.with_suffix(".json").read_text())
    assert path == tmp_path / "hrrr" / "20210820" / "t00z" / "hrrr.t00z.wrfsfcf01.fb.grib2"
    assert sidecar["fields"] == [
        "TMP:2 m above ground",
        "RH:2 m above ground",
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "SFCR:surface",
    ]
    assert sidecar["size"] == path.stat().st_size
    assert sidecar["source_url"].endswith("hrrr.t00z.wrfsfcf01.grib2")
    # UGRD and VGRD are adjacent in the file, so they share one range request
    assert len(archive.range_requests) == 4


def test_second_fetch_is_a_cache_hit_without_network(archive, tmp_path):
    forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)
    forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)

    assert archive.idx_requests == 1


def test_truncated_cached_file_is_downloaded_again(archive, tmp_path):
    path = forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)
    path.write_bytes(b"truncated")

    forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)

    assert archive.idx_requests == 2
    assert forecast.is_cached(path, forecast.FIELDS)


def test_static_terrain_is_downloaded_at_f00_only(archive, tmp_path):
    f00 = forecast.fetch_file(CYCLE, 0, cache_root=tmp_path)
    f01 = forecast.fetch_file(CYCLE, 1, cache_root=tmp_path)

    assert "HGT:surface" in forecast.read_sidecar(f00)["fields"]
    assert "HGT:surface" not in forecast.read_sidecar(f01)["fields"]


def test_fetch_cycle_reports_hours_missing_from_the_archive(monkeypatch, tmp_path):
    fake = _FakeArchive(missing_hours={2})
    monkeypatch.setattr(forecast, "fetch_text", fake.fetch_text)
    monkeypatch.setattr("firebench.acquisition.http.http_get", fake.http_get)

    cycle_files = forecast.fetch_cycle(CYCLE, 3, workers=2, cache_root=tmp_path)

    assert sorted(cycle_files.files) == [0, 1, 3]
    assert cycle_files.missing == [2]
    assert not cycle_files.complete


def test_horizon_beyond_the_cycle_forecast_range_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="0-36 h"):
        forecast.fetch_cycle(datetime(2020, 9, 15, 0, tzinfo=timezone.utc), 48, cache_root=tmp_path)


def test_grid_south_west_corner_round_trips():
    hrrr_grid = grid.HRRRGrid()

    i, j = hrrr_grid.ij_arrays_from_latlon(grid.LAT_FIRST, grid.LON_FIRST)
    lat, lon = hrrr_grid.latlon_from_ij(0, 0)

    assert abs(float(i)) < 1e-6 and abs(float(j)) < 1e-6
    assert lat == pytest.approx(grid.LAT_FIRST, abs=1e-6)
    assert lon == pytest.approx(grid.LON_FIRST, abs=1e-6)


def test_grid_cell_near_caldor_matches_the_decoded_hrrr_file():
    # cell (246, 618) of the operational HRRR file is centred at 38.7032 N, 120.3133 W
    hrrr_grid = grid.HRRRGrid()

    assert hrrr_grid.ij_from_latlon(38.7, -120.3) == (246, 618)
    lat, lon = hrrr_grid.latlon_from_ij(246, 618)
    assert (lat, lon) == pytest.approx((38.70319, -120.31328), abs=1e-4)
    assert bool(hrrr_grid.contains(246, 618))
    assert not bool(hrrr_grid.contains(-1, 618))


def test_winds_need_no_rotation_on_the_central_meridian():
    u, v = grid.rotate_winds_to_earth(np.array([3.0]), np.array([4.0]), grid.LON_0)

    assert (float(u[0]), float(v[0])) == pytest.approx((3.0, 4.0))


def test_winds_west_of_the_central_meridian_are_rotated_to_earth():
    # Meridians converge towards the pole, so west of lon_0 the grid y axis points west of true
    # north: a pure grid-northward wind has a westward earth component, angle sin(38.5)(lon - lon_0).
    lon = -120.3
    u, v = grid.rotate_winds_to_earth(np.array([0.0]), np.array([1.0]), lon)
    angle = np.sin(np.radians(38.5)) * np.radians(lon + 97.5)

    assert float(u[0]) == pytest.approx(np.sin(angle))
    assert float(u[0]) < 0
    assert float(np.hypot(u[0], v[0])) == pytest.approx(1.0)


def test_expected_levels_of_hrrr_fields():
    assert read.expected_level("TMP:2 m above ground") == ("heightAboveGround", 2.0)
    assert read.expected_level("SFCR:surface") == ("surface", None)
    with pytest.raises(ValueError):
        read.expected_level("UGRD:250 mb")


def _hrrr_like_sample(eccodes):
    """GRIB2 sample message re-oriented to scan south to north, like HRRR."""
    gid = eccodes.codes_grib_new_from_samples("GRIB2")
    lat_a = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees")
    lat_b = eccodes.codes_get(gid, "latitudeOfLastGridPointInDegrees")
    eccodes.codes_set(gid, "jScansPositively", 1)
    eccodes.codes_set(gid, "latitudeOfFirstGridPointInDegrees", min(lat_a, lat_b))
    eccodes.codes_set(gid, "latitudeOfLastGridPointInDegrees", max(lat_a, lat_b))
    return gid


def _patch_grid_to_sample(eccodes, monkeypatch):
    gid = _hrrr_like_sample(eccodes)
    ni, nj = eccodes.codes_get(gid, "Ni"), eccodes.codes_get(gid, "Nj")
    monkeypatch.setattr(read, "NX", ni)
    monkeypatch.setattr(read, "NY", nj)
    monkeypatch.setattr(read, "LAT_FIRST", eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees"))
    monkeypatch.setattr(read, "LON_FIRST", eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees"))
    eccodes.codes_release(gid)
    return ni, nj


def _write_sample_grib(eccodes, path, messages):
    with open(path, "wb") as f:
        for type_of_level, level, flags, values in messages:
            gid = _hrrr_like_sample(eccodes)
            eccodes.codes_set(gid, "typeOfLevel", type_of_level)
            eccodes.codes_set(gid, "level", level)
            eccodes.codes_set(gid, "resolutionAndComponentFlags", flags)
            if np.isnan(values).any():
                eccodes.codes_set(gid, "bitmapPresent", 1)
                values = np.where(np.isnan(values), eccodes.codes_get(gid, "missingValue"), values)
            eccodes.codes_set_values(gid, values)
            eccodes.codes_write(gid, f)
            eccodes.codes_release(gid)


def test_read_fields_decodes_messages_in_sidecar_order(monkeypatch, tmp_path):
    eccodes = pytest.importorskip("eccodes")
    ni, nj = _patch_grid_to_sample(eccodes, monkeypatch)

    temperature = np.linspace(280.0, 300.0, ni * nj)
    wind = np.full(ni * nj, 2.0)
    wind[3] = np.nan
    path = tmp_path / "sample.fb.grib2"
    _write_sample_grib(
        eccodes, path, [("heightAboveGround", 2, 0, temperature), ("heightAboveGround", 10, 8, wind)]
    )
    path.with_suffix(".json").write_text(
        json.dumps({"fields": ["TMP:2 m above ground", "UGRD:10 m above ground"]})
    )

    fields = read.read_fields(path)

    assert fields["TMP:2 m above ground"].shape == (nj, ni)
    assert fields["TMP:2 m above ground"].ravel() == pytest.approx(temperature, abs=0.01)
    assert np.isnan(fields["UGRD:10 m above ground"].ravel()[3])


def test_read_fields_refuses_earth_relative_wind(monkeypatch, tmp_path):
    eccodes = pytest.importorskip("eccodes")
    ni, nj = _patch_grid_to_sample(eccodes, monkeypatch)
    path = tmp_path / "sample.fb.grib2"
    _write_sample_grib(eccodes, path, [("heightAboveGround", 10, 0, np.ones(ni * nj))])
    path.with_suffix(".json").write_text(json.dumps({"fields": ["UGRD:10 m above ground"]}))

    with pytest.raises(ValueError, match="not grid-relative"):
        read.read_fields(path)
