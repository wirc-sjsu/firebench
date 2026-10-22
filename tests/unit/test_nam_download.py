import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pytest

from firebench.acquisition import forecast_models
from firebench.acquisition.hrrr import inventory
from firebench.acquisition.hrrr.grid import HRRRGrid
from firebench.acquisition.lambert import LambertGrid, LambertParameters
from firebench.acquisition.nam import forecast, grid, read

# Trimmed from nam.20260828/nam.t00z.conusnest.hiresf06.tm00.grib2.idx (NOAA Open Data on AWS)
IDX_2026082800_F06 = """\
593:663105245:d=2026082800:PRES:surface:6 hour fcst:
594:664620555:d=2026082800:HGT:surface:6 hour fcst:
616:695673235:d=2026082800:TMP:2 m above ground:6 hour fcst:
617:697777000:d=2026082800:SPFH:2 m above ground:6 hour fcst:
618:699814019:d=2026082800:DPT:2 m above ground:6 hour fcst:
619:701881379:d=2026082800:RH:2 m above ground:6 hour fcst:
624.1:711347173:d=2026082800:UGRD:10 m above ground:6 hour fcst:
624.2:711347173:d=2026082800:VGRD:10 m above ground:6 hour fcst:
625:714800000:d=2026082800:TMAX:2 m above ground:5-6 hour max fcst:
648:739405125:d=2026082800:SFCR:surface:6 hour fcst:
649:740500000:d=2026082800:FRICV:surface:6 hour fcst:
"""

CYCLE = datetime(2026, 8, 28, 0, tzinfo=timezone.utc)


def test_url_and_cache_path_of_a_forecast_hour(tmp_path):
    assert forecast.grib_url(CYCLE, 6) == (
        "https://noaa-nam-pds.s3.amazonaws.com/nam.20260828/nam.t00z.conusnest.hiresf06.tm00.grib2"
    )
    path = forecast.cached_file_path(CYCLE, 6, tmp_path)
    assert path == tmp_path / "nam" / "20260828" / "t00z" / "nam.t00z.conusnest.hiresf06.tm00.fb.grib2"


def test_cycles_at_synoptic_hours_from_the_first_cycle_of_the_archive_are_read():
    assert forecast.nam_version(CYCLE) == "4"
    assert forecast.max_forecast_hour(datetime(2021, 9, 16, 0, tzinfo=timezone.utc)) == 60
    assert forecast.output_hours(CYCLE) == tuple(range(61))
    with pytest.raises(ValueError, match="older than the first cycle of its archive FireBench reads"):
        forecast.validate_cycle(datetime(2021, 9, 15, 18, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="00, 06, 12 or 18 UTC"):
        forecast.validate_cycle(datetime(2026, 8, 28, 3, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="no time zone"):
        forecast.validate_cycle(datetime(2026, 8, 28, 0))


def test_horizon_beyond_f60_is_refused():
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ValueError, match="NAM nest forecast range"):
            forecast.submit_cycle(CYCLE, 61, executor)


def test_u_and_v_of_one_message_are_selected_in_sub_message_order():
    messages = inventory.select_messages(
        inventory.parse_index(IDX_2026082800_F06), forecast.fields_for_hour(0), shared=True
    )

    assert [message.field for message in messages] == [
        "HGT:surface",
        "TMP:2 m above ground",
        "RH:2 m above ground",
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "SFCR:surface",
    ]
    u, v = messages[3], messages[4]
    assert (u.byte_start, u.byte_end) == (v.byte_start, v.byte_end) == (711347173, 714799999)
    # Listed V first, the sub-messages still come in their order in the message.
    reversed_wind = inventory.select_messages(
        inventory.parse_index(IDX_2026082800_F06),
        ["VGRD:10 m above ground", "UGRD:10 m above ground"],
        shared=True,
    )
    assert [message.number for message in reversed_wind] == ["624.1", "624.2"]


def test_fetch_file_downloads_the_shared_message_once_and_lists_both_fields(tmp_path, monkeypatch):
    ranges = []

    monkeypatch.setattr(forecast, "fetch_text", lambda url, **kwargs: IDX_2026082800_F06)

    def fake_http_get(url, byte_range=None, **kwargs):
        ranges.append(byte_range)
        start, end = byte_range
        return b"g" * (end - start + 1)

    monkeypatch.setattr("firebench.acquisition.http.http_get", fake_http_get)

    path = forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)

    # RH ends where the message of U and V starts: one range, and that message is fetched once.
    assert ranges == [(695673235, 697776999), (701881379, 714799999), (739405125, 740499999)]
    sidecar = json.loads(path.with_suffix(".json").read_text())
    assert sidecar["fields"] == list(forecast.FIELDS)
    assert [message["number"] for message in sidecar["messages"]] == ["616", "619", "624.1", "624.2", "648"]
    assert path.stat().st_size == sidecar["size"] == sum(end - start + 1 for start, end in ranges)


def test_missing_forecast_hour_is_a_file_not_found_error(tmp_path, monkeypatch):
    def not_found(url, **kwargs):
        raise FileNotFoundError("HTTP 404")

    monkeypatch.setattr(forecast, "fetch_text", not_found)

    with pytest.raises(FileNotFoundError, match="NAM file not available for cycle 2026-08-28 00Z f06"):
        forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)


def test_the_nest_is_hrrrs_grid_with_the_first_point_its_messages_give():
    assert grid.NAM_PARAMETERS.mismatch(HRRRGrid().parameters, tolerance_deg=grid.TOLERANCE_DEG) is None
    nam = grid.NAMGrid()
    lat, lon = nam.latlon_from_ij(0, 0)
    assert (lat, lon) == pytest.approx((21.138, -122.72), abs=1e-9)
    i, j = nam.ij_arrays_from_latlon([44.85], [-118.2])
    hrrr_i, hrrr_j = HRRRGrid().ij_arrays_from_latlon([44.85], [-118.2])
    assert abs(i[0] - hrrr_i[0]) < 0.02 and abs(j[0] - hrrr_j[0]) < 0.02


def test_registry_names_nam():
    model = forecast_models.get_model("nam")

    assert model.forecast is forecast
    assert model.adapter_module == "firebench.adapters.nam_weather"
    assert model.version(CYCLE) == "4"
    assert forecast_models.download_mb_per_cycle("NAM", 48) == pytest.approx(10.5 + 8.9 * 48, abs=0.1)
    assert model.domain_problem((-121.0, 38.0, -120.0, 39.0)) is None
    assert "NAM CONUS nest grid" in model.domain_problem((-150.0, 64.0, -149.0, 65.0))


# ------------------------------------------------------------------ decoding (needs eccodes)

# A 4 x 3 grid with the nest's projection, standing for the nest in the reader's checks.
SMALL = LambertParameters(
    nx=4,
    ny=3,
    dx=3000.0,
    dy=3000.0,
    lat_1=38.5,
    lat_2=38.5,
    lon_0=-97.5,
    lat_first=21.138,
    lon_first=-122.72,
    radius=6371229.0,
)


def _small_lambert(eccodes, short_name, type_of_level, level, values, *, lon_first=237.28):
    """One GRIB2 message on the small grid, as the nest writes it (LoV and longitudes in 0..360)."""
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
        ("latitudeOfFirstGridPointInDegrees", 21.138),
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


def _sections(message: bytes) -> list[tuple[int, bytes]]:
    sections, position = [], 16
    while message[position : position + 4] != b"7777":
        length = int.from_bytes(message[position : position + 4], "big")
        sections.append((message[position + 4], message[position : position + length]))
        position += length
    return sections


def _one_message(first: bytes, second: bytes) -> bytes:
    """Two fields of one GRIB2 message, as NAM packs U and V: sections 4 to 7 of ``second`` repeated."""
    body = b"".join(section for _, section in _sections(first))
    body += b"".join(section for number, section in _sections(second) if number >= 4) + b"7777"
    return first[:8] + (16 + len(body)).to_bytes(8, "big") + body


def _write_subset(eccodes, path, fields):
    size = SMALL.nx * SMALL.ny
    temperature = _small_lambert(eccodes, "2t", "heightAboveGround", 2, 280.0 + np.arange(size))
    u = _small_lambert(eccodes, "10u", "heightAboveGround", 10, np.arange(size))
    v = _small_lambert(eccodes, "10v", "heightAboveGround", 10, 100.0 + np.arange(size))
    path.write_bytes(temperature + _one_message(u, v))
    path.with_suffix(".json").write_text(json.dumps({"fields": fields}))


@pytest.fixture
def small_nest(monkeypatch):
    eccodes = pytest.importorskip("eccodes")
    monkeypatch.setattr(read, "NAM_PARAMETERS", SMALL)
    return eccodes


def test_u_and_v_of_one_message_are_both_decoded(small_nest, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    _write_subset(
        small_nest, path, ["TMP:2 m above ground", "UGRD:10 m above ground", "VGRD:10 m above ground"]
    )

    fields = read.read_fields(path)

    assert fields["TMP:2 m above ground"].shape == (3, 4)
    assert fields["UGRD:10 m above ground"].ravel() == pytest.approx(np.arange(12), abs=0.01)
    assert fields["VGRD:10 m above ground"].ravel() == pytest.approx(100.0 + np.arange(12), abs=0.01)


def test_a_sidecar_listing_v_before_u_is_refused(small_nest, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    _write_subset(
        small_nest, path, ["TMP:2 m above ground", "VGRD:10 m above ground", "UGRD:10 m above ground"]
    )

    with pytest.raises(ValueError, match="field for VGRD:10 m above ground is '10u', expected '10v'"):
        read.read_fields(path)


def test_a_message_on_another_grid_is_refused(small_nest, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    path.write_bytes(
        _small_lambert(small_nest, "2t", "heightAboveGround", 2, np.zeros(12), lon_first=237.3)
    )
    path.with_suffix(".json").write_text(json.dumps({"fields": ["TMP:2 m above ground"]}))

    with pytest.raises(ValueError, match="unexpected grid: lon_first"):
        read.read_fields(path)


def test_multi_field_support_is_off_after_a_read(small_nest, tmp_path):
    path = tmp_path / "sample.fb.grib2"
    _write_subset(
        small_nest, path, ["TMP:2 m above ground", "UGRD:10 m above ground", "VGRD:10 m above ground"]
    )
    read.read_fields(path)

    # Without multi-field support, eccodes returns the message of U and V once, as U.
    with open(path, "rb") as f:
        count = 0
        while (gid := small_nest.codes_grib_new_from_file(f)) is not None:
            small_nest.codes_release(gid)
            count += 1
    assert count == 2
