import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pytest

from firebench.acquisition import forecast_models
from firebench.acquisition.hrrr import inventory
from firebench.acquisition.hrrr.grid import HRRRGrid
from firebench.acquisition.lambert import LambertParameters
from firebench.acquisition.rrfs import forecast, grid, read

# Trimmed from rrfs.20260828/00/rrfs.t00z.2dfld.3km.f006.conus.grib2.idx (NOAA Open Data on AWS)
IDX_2026082800_F006 = """\
31:27768976:d=2026082800:PRES:surface:6 hour fcst:
32:29844939:d=2026082800:HGT:surface:6 hour fcst:
74:79742860:d=2026082800:TMP:2 m above ground:6 hour fcst:
75:81460042:d=2026082800:SPFH:2 m above ground:6 hour fcst:
76:83097716:d=2026082800:DPT:2 m above ground:6 hour fcst:
78:86072559:d=2026082800:RH:2 m above ground:6 hour fcst:
79:87628801:d=2026082800:TMAX:2 m above ground:5-6 hour max fcst:
88:97185598:d=2026082800:UGRD:10 m above ground:6 hour fcst:
89:99070367:d=2026082800:VGRD:10 m above ground:6 hour fcst:
92:103574536:d=2026082800:WIND:10 m above ground:5-6 hour max fcst:
127:115412115:d=2026082800:SFCR:surface:6 hour fcst:
128:116641703:d=2026082800:FRICV:surface:6 hour fcst:
"""

CYCLE = datetime(2026, 8, 28, 0, tzinfo=timezone.utc)


def test_url_and_cache_path_of_a_forecast_hour(tmp_path):
    assert forecast.grib_url(CYCLE, 6) == (
        "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.20260828/00/rrfs.t00z.2dfld.3km.f006.conus.grib2"
    )
    path = forecast.cached_file_path(CYCLE, 6, tmp_path)
    assert path == tmp_path / "rrfs" / "20260828" / "t00z" / "rrfs.t00z.2dfld.3km.f006.conus.fb.grib2"


def test_long_cycles_from_the_first_cycle_with_every_index_are_read():
    assert forecast.rrfs_version(CYCLE) == "1"
    assert forecast.max_forecast_hour(datetime(2026, 8, 13, 6, tzinfo=timezone.utc)) == 84
    assert forecast.output_hours(CYCLE) == tuple(range(85))
    with pytest.raises(
        ValueError, match=r"older than the first cycle of its archive FireBench reads \(2026-08-13 06Z\)"
    ):
        forecast.validate_cycle(datetime(2026, 8, 13, 0, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="00, 06, 12 or 18 UTC"):
        forecast.validate_cycle(datetime(2026, 8, 28, 3, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="no time zone"):
        forecast.validate_cycle(datetime(2026, 8, 28, 0))


def test_horizon_beyond_f084_is_refused():
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ValueError, match="RRFS forecast range"):
            forecast.submit_cycle(CYCLE, 85, executor)


def test_fields_are_instantaneous_messages_of_their_own():
    messages = inventory.select_messages(
        inventory.parse_index(IDX_2026082800_F006), forecast.fields_for_hour(0)
    )

    assert [message.number for message in messages] == ["32", "74", "78", "88", "89", "127"]
    # The hourly maximum wind and temperature are never taken for the instantaneous fields.
    assert all(message.instantaneous for message in messages)


def test_u_and_v_packed_in_one_message_would_be_refused():
    packed = IDX_2026082800_F006.replace("89:99070367:", "88.2:97185598:").replace(
        "88:97185598:", "88.1:97185598:"
    )

    with pytest.raises(ValueError, match="share a GRIB message"):
        inventory.select_messages(inventory.parse_index(packed), forecast.FIELDS)


def test_fetch_file_downloads_the_byte_ranges_of_the_fields(tmp_path, monkeypatch):
    ranges = []

    monkeypatch.setattr(forecast, "fetch_text", lambda url, **kwargs: IDX_2026082800_F006)

    def fake_http_get(url, byte_range=None, **kwargs):
        ranges.append(byte_range)
        start, end = byte_range
        return b"g" * (end - start + 1)

    monkeypatch.setattr("firebench.acquisition.http.http_get", fake_http_get)

    path = forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)

    # U and V are adjacent: one range for both.
    assert ranges == [
        (79742860, 81460041),
        (86072559, 87628800),
        (97185598, 103574535),
        (115412115, 116641702),
    ]
    sidecar = json.loads(path.with_suffix(".json").read_text())
    assert sidecar["fields"] == list(forecast.FIELDS)
    assert path.stat().st_size == sidecar["size"] == sum(end - start + 1 for start, end in ranges)


def test_missing_index_is_a_file_not_found_error(tmp_path, monkeypatch):
    def not_found(url, **kwargs):
        raise FileNotFoundError("HTTP 404")

    monkeypatch.setattr(forecast, "fetch_text", not_found)

    with pytest.raises(FileNotFoundError, match="RRFS file not available for cycle 2026-08-28 00Z f006"):
        forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)


def test_the_conus_grid_is_hrrrs():
    assert grid.RRFS_PARAMETERS.mismatch(HRRRGrid().parameters) is None
    lat, lon = grid.RRFSGrid().latlon_from_ij(0, 0)
    assert (lat, lon) == pytest.approx((21.138123, -122.719528), abs=1e-9)
    u, v = grid.earth_winds(np.array([0.0]), np.array([5.0]), np.array([-118.2]))
    hrrr_u, hrrr_v = HRRRGrid().rotate_winds_to_earth(np.array([0.0]), np.array([5.0]), np.array([-118.2]))
    assert (u, v) == (pytest.approx(hrrr_u), pytest.approx(hrrr_v))


def test_registry_names_rrfs():
    model = forecast_models.get_model("rrfs")

    assert model.forecast is forecast
    assert model.adapter_module == "firebench.adapters.rrfs_weather"
    assert model.version(CYCLE) == "1"
    assert forecast_models.download_mb_per_cycle("RRFS", 48) == pytest.approx(10.0 + 8.3 * 48, abs=0.1)
    assert model.domain_problem((-121.0, 38.0, -120.0, 39.0)) is None
    assert "RRFS CONUS grid" in model.domain_problem((-150.0, 64.0, -149.0, 65.0))


# ------------------------------------------------------------------ decoding (needs eccodes)

# A 4 x 3 grid with RRFS's projection, standing for the CONUS grid in the reader's checks.
SMALL = LambertParameters(
    nx=4,
    ny=3,
    dx=3000.0,
    dy=3000.0,
    lat_1=38.5,
    lat_2=38.5,
    lon_0=-97.5,
    lat_first=21.138123,
    lon_first=-122.719528,
    radius=6371229.0,
)


def _small_lambert(eccodes, short_name, type_of_level, level, values, *, lon_first=237.280472):
    """One GRIB2 message on the small grid, as RRFS writes it (LoV and longitudes in 0..360)."""
    gid = eccodes.codes_grib_new_from_samples("GRIB2")
    eccodes.codes_set(gid, "gridDefinitionTemplateNumber", 30)
    for key, value in (
        ("shapeOfTheEarth", 6),
        ("Nx", SMALL.nx),
        ("Ny", SMALL.ny),
        ("DxInMetres", SMALL.dx),
        ("DyInMetres", SMALL.dy),
        ("Latin1InDegrees", 38.5),
        ("Latin2InDegrees", 38.5),
        ("LaDInDegrees", 38.5),
        ("LoVInDegrees", 262.5),
        ("latitudeOfFirstGridPointInDegrees", 21.138123),
        ("longitudeOfFirstGridPointInDegrees", lon_first),
        ("iScansNegatively", 0),
        ("jScansPositively", 1),
        ("jPointsAreConsecutive", 0),
        ("typeOfLevel", type_of_level),
        ("level", level),
        ("resolutionAndComponentFlags", 8),  # grid-relative winds
        ("shortName", short_name),
    ):
        eccodes.codes_set(gid, key, value)
    eccodes.codes_set_values(gid, np.asarray(values, dtype=np.float64))
    message = eccodes.codes_get_message(gid)
    eccodes.codes_release(gid)
    return message


@pytest.fixture
def small_grid(monkeypatch):
    eccodes = pytest.importorskip("eccodes")
    monkeypatch.setattr(read, "RRFS_PARAMETERS", SMALL)
    return eccodes


def _write_subset(eccodes, path, fields):
    size = SMALL.nx * SMALL.ny
    path.write_bytes(
        _small_lambert(eccodes, "2t", "heightAboveGround", 2, 280.0 + np.arange(size))
        + _small_lambert(eccodes, "10u", "heightAboveGround", 10, np.arange(size))
        + _small_lambert(eccodes, "10v", "heightAboveGround", 10, 100.0 + np.arange(size))
    )
    path.with_suffix(".json").write_text(json.dumps({"fields": fields}))


def test_fields_of_their_own_messages_are_decoded(small_grid, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    _write_subset(
        small_grid, path, ["TMP:2 m above ground", "UGRD:10 m above ground", "VGRD:10 m above ground"]
    )

    fields = read.read_fields(path)

    assert fields["TMP:2 m above ground"].ravel() == pytest.approx(280.0 + np.arange(12), abs=0.01)
    assert fields["UGRD:10 m above ground"].ravel() == pytest.approx(np.arange(12), abs=0.01)
    assert fields["VGRD:10 m above ground"].ravel() == pytest.approx(100.0 + np.arange(12), abs=0.01)


def test_a_swapped_sidecar_is_refused(small_grid, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    _write_subset(
        small_grid, path, ["TMP:2 m above ground", "VGRD:10 m above ground", "UGRD:10 m above ground"]
    )

    with pytest.raises(ValueError, match="field for VGRD:10 m above ground is '10u', expected '10v'"):
        read.read_fields(path)


def test_a_message_off_the_grid_is_refused(small_grid, tmp_path):
    # 0.001 degree is within NAM's tolerance, not within RRFS's.
    path = tmp_path / "sample.fb.grib2"
    path.write_bytes(
        _small_lambert(small_grid, "2t", "heightAboveGround", 2, np.zeros(12), lon_first=237.281472)
    )
    path.with_suffix(".json").write_text(json.dumps({"fields": ["TMP:2 m above ground"]}))

    with pytest.raises(ValueError, match="unexpected grid: lon_first"):
        read.read_fields(path)
