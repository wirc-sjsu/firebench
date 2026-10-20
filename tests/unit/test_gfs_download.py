import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pytest

from firebench.acquisition import forecast_models
from firebench.acquisition.gfs import forecast, grid
from firebench.acquisition.hrrr import inventory

# Trimmed from gfs.20210820/00/atmos/gfs.t00z.pgrb2.0p25.f006.idx (NOAA Open Data on AWS)
IDX_2021082000_F006 = """\
14:6967905:d=2021082000:GUST:surface:6 hour fcst:
15:7926310:d=2021082000:UGRD:planetary boundary layer:6 hour fcst:
562:416127173:d=2021082000:HGT:surface:6 hour fcst:
563:416620022:d=2021082000:TMP:surface:6 hour fcst:
581:423569365:d=2021082000:TMP:2 m above ground:6 hour fcst:
582:424080000:d=2021082000:SPFH:2 m above ground:6 hour fcst:
583:425312692:d=2021082000:DPT:2 m above ground:6 hour fcst:
584:425850225:d=2021082000:RH:2 m above ground:6 hour fcst:
585:426650000:d=2021082000:TMAX:2 m above ground:0-6 hour max fcst:
588:428563692:d=2021082000:UGRD:10 m above ground:6 hour fcst:
589:429536849:d=2021082000:VGRD:10 m above ground:6 hour fcst:
590:430500000:d=2021082000:CPOFP:surface:6 hour fcst:
614:439331556:d=2021082000:SFCR:surface:6 hour fcst:
615:439830000:d=2021082000:FRICV:surface:6 hour fcst:
"""

CYCLE = datetime(2021, 8, 20, 0, tzinfo=timezone.utc)


def test_url_and_cache_path_of_a_forecast_hour(tmp_path):
    assert forecast.grib_url(CYCLE, 6) == (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20210820/00/atmos/gfs.t00z.pgrb2.0p25.f006"
    )
    path = forecast.cached_file_path(CYCLE, 6, tmp_path)
    assert path == tmp_path / "gfs" / "20210820" / "t00z" / "gfs.t00z.pgrb2.0p25.f006.fb.grib2"
    assert path.with_suffix(".json").name == "gfs.t00z.pgrb2.0p25.f006.fb.json"


def test_only_gfs_v16_cycles_at_synoptic_hours_are_read():
    assert forecast.gfs_version(CYCLE) == "16"
    assert forecast.max_forecast_hour(datetime(2021, 3, 22, 12, tzinfo=timezone.utc)) == 120
    with pytest.raises(ValueError, match="older than GFS v16"):
        forecast.validate_cycle(datetime(2021, 3, 22, 6, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="00, 06, 12 or 18 UTC"):
        forecast.validate_cycle(datetime(2021, 8, 20, 3, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="no time zone"):
        forecast.validate_cycle(datetime(2021, 8, 20, 0))


def test_horizon_beyond_the_hourly_output_is_refused():
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ValueError, match="hourly GFS forecast range"):
            forecast.submit_cycle(CYCLE, 121, executor)


def test_selection_keeps_the_instantaneous_fields_in_byte_order():
    messages = inventory.select_messages(
        inventory.parse_index(IDX_2021082000_F006), forecast.fields_for_hour(0)
    )

    assert [message.field for message in messages] == [
        "HGT:surface",
        "TMP:2 m above ground",
        "RH:2 m above ground",
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "SFCR:surface",
    ]
    assert (messages[1].byte_start, messages[1].byte_end) == (423569365, 424079999)
    assert forecast.fields_for_hour(1) == forecast.FIELDS


def test_fetch_file_downloads_the_subset_once_and_writes_its_sidecar(tmp_path, monkeypatch):
    calls = []

    def fake_fetch_text(url, **kwargs):
        calls.append(url)
        return IDX_2021082000_F006

    def fake_download_subset(url, messages, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"g" * 12)
        return 12

    monkeypatch.setattr(forecast, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(forecast, "download_subset", fake_download_subset)

    path = forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)
    again = forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)

    assert path == again
    assert calls == [forecast.grib_url(CYCLE, 6) + ".idx"]
    assert json.loads(path.with_suffix(".json").read_text())["fields"] == list(forecast.FIELDS)


def test_missing_forecast_hour_is_a_file_not_found_error(tmp_path, monkeypatch):
    def not_found(url, **kwargs):
        raise FileNotFoundError("HTTP 404")

    monkeypatch.setattr(forecast, "fetch_text", not_found)

    with pytest.raises(FileNotFoundError, match="GFS file not available for cycle 2021-08-20 00Z f006"):
        forecast.fetch_file(CYCLE, 6, cache_root=tmp_path)


def test_grid_indices_wrap_in_longitude_and_count_rows_from_the_north():
    i, j = grid.GFSGrid.ij_arrays_from_latlon([38.7, 90.0, -90.0, 0.0], [-120.3, 0.0, 359.9, -0.1])

    np.testing.assert_allclose(i, [(360 - 120.3) / 0.25, 0.0, 359.9 / 0.25, 359.9 / 0.25])
    np.testing.assert_allclose(j, [(90 - 38.7) / 0.25, 0.0, 720.0, 360.0])
    assert grid.GFSGrid.contains(i, j).all()
    assert not grid.GFSGrid.contains([0.0], [721.0]).any()


def test_registry_names_the_models_of_the_workflow():
    assert forecast_models.get_model("gfs").forecast is forecast
    assert forecast_models.get_model("HRRR").version(CYCLE) == "4"
    assert forecast_models.download_mb_per_cycle("GFS", 48) == pytest.approx(4.6 + 3.7 * 48, abs=0.1)
    assert forecast_models.get_model("GFS").domain_problem((-150.0, 64.0, -149.0, 65.0)) is None
    with pytest.raises(ValueError, match="unknown forecast model 'NAM'"):
        forecast_models.get_model("NAM")
