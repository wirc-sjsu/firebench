import io
import json
import logging
import urllib.error
from datetime import date, datetime, timezone

import pytest

from firebench.acquisition import firms, http

KEY = "fake-firms-key-0123456789"
BOX = (-120.8, 38.4, -119.7, 39.0)
START = datetime(2021, 8, 1, tzinfo=timezone.utc)
AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "MODIS_NRT,2021-08-11,2026-10-15\nMODIS_SP,2000-11-01,2021-08-10\n"
    "VIIRS_SNPP_NRT,2021-08-09,2026-10-15\nVIIRS_SNPP_SP,2012-01-20,2021-08-08\n"
    "VIIRS_NOAA20_SP,2018-04-01,2026-06-30\n"
)
VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_ti5,frp,daynight,type\n"
    "38.55845,-120.4651,327.24,0.54,0.51,2021-08-01,918,N,VIIRS,n,2,289.79,4.35,N,0\n"
)
MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,"
    "bright_t31,frp,daynight,type\n"
    "38.5828,-120.4393,313.1,3,1.6,2021-08-01,520,Terra,MODIS,86,6.03,288.8,64.7,N,0\n"
    "38.6001,-120.5664,301.7,3,1.7,2021-08-01,938,Aqua,MODIS,44,6.03,289.1,28.4,D,0\n"
)


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


class _Firms:
    """Fake FIRMS and CMR: answers by URL, records every URL, fails the products listed in `failing`."""

    def __init__(self, failing=(), availability=AVAILABILITY) -> None:
        self.failing = set(failing)
        self.availability = availability
        self.urls = []

    def __call__(self, request, timeout):
        url = request.full_url
        self.urls.append(url)
        if "cmr.earthdata.nasa.gov" in url:
            return _Response(json.dumps({"feed": {"entry": []}}).encode())
        if "/data_availability/" in url:
            if self.availability is None:
                raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b""))
            return _Response(self.availability.encode())
        product = url.split(f"/{KEY}/")[1].split("/")[0]
        if product in self.failing:
            raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b""))
        return _Response((MODIS_CSV if product.startswith("MODIS") else VIIRS_CSV).encode())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def test_plan_takes_the_standard_product_day_by_day_and_groups_five_days_at_most():
    availability = {
        "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2021, 8, 8)),
        "VIIRS_SNPP_NRT": (date(2021, 8, 9), date(2026, 1, 1)),
    }

    plan, uncovered = firms.plan_firms_requests(
        ["viirs_snpp"], START, datetime(2021, 8, 13, tzinfo=timezone.utc), availability
    )

    assert [(item.product, item.day.isoformat(), item.n_days) for item in plan] == [
        ("VIIRS_SNPP_SP", "2021-08-01", 5),
        ("VIIRS_SNPP_SP", "2021-08-06", 3),
        ("VIIRS_SNPP_NRT", "2021-08-09", 4),
    ]
    assert uncovered == {}


def test_terra_and_aqua_share_requests_and_a_day_without_product_is_reported():
    availability = {"MODIS_SP": (date(2000, 1, 1), date(2030, 1, 1))}

    plan, uncovered = firms.plan_firms_requests(
        ["modis_aqua", "viirs_noaa21", "modis_terra"],
        START,
        datetime(2021, 8, 3, tzinfo=timezone.utc),
        availability,
    )

    assert [(item.product, item.streams) for item in plan] == [("MODIS_SP", ("modis_terra", "modis_aqua"))]
    assert uncovered == {"viirs_noaa21": [date(2021, 8, 1), date(2021, 8, 2)]}


def test_a_window_ending_at_midnight_does_not_request_the_next_day():
    assert firms.request_days(START, datetime(2021, 8, 3, tzinfo=timezone.utc)) == [
        date(2021, 8, 1),
        date(2021, 8, 2),
    ]


def test_bundle_keeps_the_csv_verbatim_and_requests_modis_once():
    opener = _Firms()

    bundle = firms.download_firms_bundle(
        BOX,
        START,
        datetime(2021, 8, 3, tzinfo=timezone.utc),
        ["viirs_snpp", "modis_terra", "modis_aqua"],
        KEY,
        opener=opener,
    )

    assert bundle["format"] == firms.BUNDLE_FORMAT and bundle["streams"] == [
        "viirs_snpp",
        "modis_terra",
        "modis_aqua",
    ]
    assert [(item["product"], item["status"]) for item in bundle["requests"]] == [
        ("VIIRS_SNPP_SP", "ok"),
        ("MODIS_SP", "ok"),
    ]
    assert bundle["requests"][0]["csv"] == VIIRS_CSV
    assert sum("/area/csv/" in url for url in opener.urls) == 2
    assert "/-120.8,38.4,-119.7,39/2/2021-08-01" in [url for url in opener.urls if "MODIS_SP" in url][0]
    assert set(bundle["overpasses"]) == {"viirs_snpp", "modis_terra", "modis_aqua"}


def test_a_failed_request_is_recorded_and_the_others_are_kept():
    bundle = firms.download_firms_bundle(
        BOX,
        START,
        datetime(2021, 8, 3, tzinfo=timezone.utc),
        ["viirs_snpp", "modis_aqua"],
        KEY,
        opener=_Firms({"MODIS_SP"}),
    )

    statuses = {item["product"]: item["status"] for item in bundle["requests"]}
    assert statuses == {"VIIRS_SNPP_SP": "ok", "MODIS_SP": "failed"}
    assert "HTTP 500" in [item for item in bundle["requests"] if item["product"] == "MODIS_SP"][0]["error"]


def test_the_key_is_nowhere_in_the_bundle_the_errors_or_the_logs(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="firebench")

    bundle = firms.download_firms_bundle(
        BOX,
        START,
        datetime(2021, 8, 3, tzinfo=timezone.utc),
        ["viirs_snpp", "modis_aqua"],
        KEY,
        opener=_Firms({"MODIS_SP"}, availability=None),
    )
    path = firms.write_firms_bundle(bundle, tmp_path / "firms.json")

    assert bundle["availability"] is None and bundle["availability_error"]
    assert KEY not in path.read_text()
    assert KEY not in caplog.text
    assert "/csv/***/" in caplog.text


def test_read_refuses_a_file_of_another_format(tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"format": "something", "version": 1}))
    broken = tmp_path / "broken.json"
    broken.write_text("{")

    for path in (other, broken):
        with pytest.raises(ValueError, match="not a FIRMS bundle"):
            firms.read_firms_bundle(path)


def test_overpasses_round_trip_through_json_with_an_unknown_fraction():
    from firebench.acquisition import cmr  # pylint: disable=import-outside-toplevel

    item = cmr.Overpass(START, START.replace(minute=6), ("A", "B"), float("nan"))

    restored = firms.overpass_from_dict(json.loads(json.dumps(firms.overpass_to_dict(item))))

    assert restored.time_start == item.time_start and restored.granule_ids == ("A", "B")
    assert restored.observed_fraction != restored.observed_fraction
