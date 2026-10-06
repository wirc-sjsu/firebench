import io
import json
import logging
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from firebench.acquisition import http, synoptic
from firebench.standardize.synoptic_data import VARIABLE_CONVERSION

TOKEN = "tok-SECRET-1234"
UTC = timezone.utc
START = datetime(2021, 8, 20, 0, tzinfo=UTC)
END = datetime(2021, 8, 22, 0, tzinfo=UTC)
BBOX = (-120.8, 38.4, -119.7, 39.0)


def _station(stid, times, *, lat=38.7, lon=-120.3, **overrides):
    station = {
        "STID": stid,
        "NAME": f"Station {stid}",
        "STATE": "CA",
        "TIMEZONE": "America/Los_Angeles",
        "LATITUDE": str(lat),
        "LONGITUDE": str(lon),
        "ELEVATION": "5000",
        "ID": "1",
        "MNET_ID": "2",
        "UNITS": {"position": "m", "elevation": "ft"},
        "SENSOR_VARIABLES": {"air_temp": {"air_temp_set_1": {"position": "2.0"}}},
        "OBSERVATIONS": {
            "date_time": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times],
            "air_temp_set_1": [20.0 + index for index, _ in enumerate(times)],
        },
    }
    station.update(overrides)
    return station


class _Response:
    def __init__(self, payload) -> None:
        self.body = json.dumps(payload).encode()
        self.status = 200

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeSynoptic:
    """Serves metadata and time series for stations observed every 10 minutes."""

    def __init__(self, stations=("A", "B")) -> None:
        self.stations = stations
        self.requests = []

    def __call__(self, request, timeout):
        url = urllib.parse.urlparse(request.full_url)
        params = dict(urllib.parse.parse_qsl(url.query))
        self.requests.append((url.path, params))
        if params.get("token") != TOKEN:
            body = {"SUMMARY": {"RESPONSE_CODE": 2, "RESPONSE_MESSAGE": "Invalid token."}}
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", {}, io.BytesIO(json.dumps(body).encode())
            )
        if url.path.endswith("/metadata"):
            return _Response({"SUMMARY": {"RESPONSE_CODE": 1, "NUMBER_OF_OBJECTS": len(self.stations)}})
        start = datetime.strptime(params["start"], "%Y%m%d%H%M").replace(tzinfo=UTC)
        end = datetime.strptime(params["end"], "%Y%m%d%H%M").replace(tzinfo=UTC)
        times = []
        current = start
        while current <= end:
            if current.minute % 10 == 0:
                times.append(current)
            current += timedelta(minutes=1)
        return _Response(
            {
                "SUMMARY": {"RESPONSE_CODE": 1, "NUMBER_OF_OBJECTS": len(self.stations)},
                "UNITS": {"air_temp": "Celsius", "wind_speed": "m/s"},
                "STATION": [_station(stid, times) for stid in self.stations],
            }
        )

    def timeseries_requests(self):
        return [params for path, params in self.requests if path.endswith("/timeseries")]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def test_default_variables_match_the_standardizer_variable_map():
    assert {f"{name}_set_1" for name in synoptic.DEFAULT_VARIABLES} == set(VARIABLE_CONVERSION)


def test_timeseries_request_carries_the_parameters_the_pipeline_needs(tmp_path):
    fake = _FakeSynoptic()
    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=fake)

    client.fetch(BBOX, START, END, cache_root=tmp_path, now=END + timedelta(days=30))

    params = fake.timeseries_requests()[0]
    assert params["bbox"] == "-120.8,38.4,-119.7,39"
    assert params["obtimezone"] == "UTC"
    assert params["units"] == "metric"
    assert params["sensorvars"] == "1"
    assert params["complete"] == "1"
    assert params["showemptystations"] == "0"
    assert params["vars"].split(",") == list(synoptic.DEFAULT_VARIABLES)
    metadata = [params for path, params in fake.requests if path.endswith("/metadata")][0]
    assert metadata["obrange"] == "202108200000,202108220000"


@pytest.mark.parametrize(
    ("n_stations", "hours"), ((1, 168), (126, 168), (600, 72), (4029, 12), (80_000, 1))
)
def test_chunk_length_keeps_requests_under_the_station_hour_cap(n_stations, hours):
    assert synoptic.chunk_hours_for(n_stations) == hours
    assert n_stations * hours <= synoptic.MAX_STATION_HOURS


def test_too_many_stations_for_a_one_hour_request_is_explained():
    with pytest.raises(ValueError, match="smaller bounding box"):
        synoptic.chunk_hours_for(200_000)


def test_chunks_are_aligned_contiguous_and_do_not_overlap():
    chunks = synoptic.plan_chunks(
        datetime(2021, 8, 20, 5, tzinfo=UTC), datetime(2021, 8, 22, 7, tzinfo=UTC), 24
    )

    assert chunks == [
        (datetime(2021, 8, 20, 5, tzinfo=UTC), datetime(2021, 8, 20, 23, 59, tzinfo=UTC)),
        (datetime(2021, 8, 21, 0, tzinfo=UTC), datetime(2021, 8, 21, 23, 59, tzinfo=UTC)),
        (datetime(2021, 8, 22, 0, tzinfo=UTC), datetime(2021, 8, 22, 7, tzinfo=UTC)),
    ]


def test_chunked_download_equals_a_single_request(tmp_path):
    fake = _FakeSynoptic()
    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=fake)
    later = END + timedelta(days=30)

    chunked = client.fetch(BBOX, START, END, max_chunk_days=0.5, cache_root=tmp_path / "a", now=later)
    single = client.fetch(BBOX, START, END, cache_root=tmp_path / "b", now=later)

    assert len(fake.timeseries_requests()) == 4 + 1
    assert [station["STID"] for station in chunked["STATION"]] == ["A", "B"]
    for merged, whole in zip(chunked["STATION"], single["STATION"]):
        assert merged["OBSERVATIONS"]["date_time"] == whole["OBSERVATIONS"]["date_time"]
        assert len(merged["OBSERVATIONS"]["air_temp_set_1"]) == len(whole["OBSERVATIONS"]["date_time"])
    assert chunked["STATION"][0]["OBSERVATIONS"]["date_time"][0] == "2021-08-20T00:00:00Z"
    assert chunked["STATION"][0]["OBSERVATIONS"]["date_time"][-1] == "2021-08-22T00:00:00Z"


def test_finished_chunks_are_served_from_the_cache(tmp_path):
    fake = _FakeSynoptic()
    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=fake)
    later = END + timedelta(days=30)

    first = client.fetch(BBOX, START, END, cache_root=tmp_path, now=later)
    second = client.fetch(BBOX, START, END, cache_root=tmp_path, now=later)

    assert len(fake.timeseries_requests()) == 1
    assert first == second


def test_recent_chunks_are_fetched_again_because_late_data_arrives(tmp_path):
    fake = _FakeSynoptic()
    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=fake)
    just_after = END + timedelta(hours=2)

    client.fetch(BBOX, START, END, cache_root=tmp_path, now=just_after)
    client.fetch(BBOX, START, END, cache_root=tmp_path, now=just_after)

    assert len(fake.timeseries_requests()) == 2


def test_cache_metadata_never_contains_the_token(tmp_path):
    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=_FakeSynoptic())

    client.fetch(BBOX, START, END, cache_root=tmp_path, now=END + timedelta(days=30))

    for path in tmp_path.rglob("*.json"):
        assert TOKEN not in path.read_text()


def test_bad_token_gives_a_clean_error_without_the_token(caplog, tmp_path):
    client = synoptic.SynopticTimeseriesClient("wrong-token", opener=_FakeSynoptic())

    with caplog.at_level(logging.DEBUG), pytest.raises(synoptic.SynopticError) as excinfo:
        client.fetch(BBOX, START, END, cache_root=tmp_path)

    assert "Invalid token." in str(excinfo.value)
    assert "HTTP 401" in str(excinfo.value)
    assert "wrong-token" not in str(excinfo.value)
    assert "wrong-token" not in caplog.text


def test_rejected_request_reports_the_synoptic_message():
    def opener(request, timeout):
        return _Response(
            {"SUMMARY": {"RESPONSE_CODE": -1, "RESPONSE_MESSAGE": "Querying too many station hours."}}
        )

    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=opener)

    with pytest.raises(synoptic.SynopticError, match="too many station hours") as excinfo:
        client.count_stations(BBOX, START, END)
    assert TOKEN not in str(excinfo.value)


def test_no_station_found_is_an_empty_result_not_an_error(tmp_path):
    def opener(request, timeout):
        return _Response(
            {"SUMMARY": {"RESPONSE_CODE": 2, "RESPONSE_MESSAGE": "No stations found for this request."}}
        )

    client = synoptic.SynopticTimeseriesClient(TOKEN, opener=opener)

    assert client.fetch(BBOX, START, END, cache_root=tmp_path)["STATION"] == []


def test_merge_pads_columns_missing_from_a_chunk_and_unites_sensor_variables():
    t0 = datetime(2021, 8, 20, 0, tzinfo=UTC)
    first = _station("A", [t0, t0 + timedelta(minutes=10)])
    second = _station("A", [t0 + timedelta(minutes=10), t0 + timedelta(minutes=20)])
    second["OBSERVATIONS"]["wind_speed_set_1"] = [1.0, 2.0]
    second["SENSOR_VARIABLES"] = {"wind_speed": {"wind_speed_set_1": {"position": "6.1"}}}

    merged = synoptic.merge_payloads([{"STATION": [first]}, {"STATION": [second]}])["STATION"][0]

    assert merged["OBSERVATIONS"]["date_time"] == [
        "2021-08-20T00:00:00Z",
        "2021-08-20T00:10:00Z",
        "2021-08-20T00:20:00Z",
    ]
    assert merged["OBSERVATIONS"]["air_temp_set_1"] == [20.0, 21.0, 21.0]
    assert merged["OBSERVATIONS"]["wind_speed_set_1"] == [None, None, 2.0]
    assert set(merged["SENSOR_VARIABLES"]) == {"air_temp", "wind_speed"}


def test_validate_payload_drops_stations_the_standardizer_would_crash_on():
    t0 = datetime(2021, 8, 20, 0, tzinfo=UTC)
    payload = {
        "STATION": [
            _station("OK", [t0]),
            _station("NOELEV", [t0], ELEVATION=None),
            _station("NOSTATE", [t0], STATE=None),
            _station("NOUNITS", [t0], UNITS={"position": "m"}),
            _station("NOTIMES", [], OBSERVATIONS={"date_time": []}),
        ]
    }

    cleaned, dropped = synoptic.validate_payload(payload)

    assert [station["STID"] for station in cleaned["STATION"]] == ["OK"]
    assert {item["station"]: item["reason"] for item in dropped} == {
        "NOELEV": "missing or non-numeric ELEVATION",
        "NOSTATE": "missing STATE",
        "NOUNITS": "missing UNITS.elevation",
        "NOTIMES": "no observation timestamps",
    }


def test_validate_payload_rejects_english_units():
    with pytest.raises(synoptic.SynopticError, match="metric"):
        synoptic.validate_payload({"UNITS": {"air_temp": "Fahrenheit"}, "STATION": []})


def test_clip_payload_keeps_the_window_and_the_bbox():
    t0 = datetime(2021, 8, 19, 23, 50, tzinfo=UTC)
    times = [t0 + timedelta(minutes=10 * index) for index in range(4)]
    payload = {
        "STATION": [
            _station("IN", times),
            _station("OUT", times, lon=-118.0),
            _station("EARLY", times[:1]),
        ]
    }

    clipped = synoptic.clip_payload(payload, START, START + timedelta(minutes=20), BBOX)

    assert [station["STID"] for station in clipped["STATION"]] == ["IN"]
    observations = clipped["STATION"][0]["OBSERVATIONS"]
    assert observations["date_time"] == [
        "2021-08-20T00:00:00Z",
        "2021-08-20T00:10:00Z",
        "2021-08-20T00:20:00Z",
    ]
    assert observations["air_temp_set_1"] == [21.0, 22.0, 23.0]


def test_client_requires_a_token():
    with pytest.raises(ValueError, match="firebench keys set synoptic"):
        synoptic.SynopticTimeseriesClient("")


@pytest.mark.parametrize("http_status", [True, False])
def test_origins_fallback_and_reuse_for_metadata_and_timeseries(tmp_path, http_status):
    attempts = []
    fake = _FakeSynoptic()

    def opener(request, timeout):
        origin = request.get_header("Origin")
        attempts.append((urllib.parse.urlsplit(request.full_url).path, origin))
        if origin == "https://first.example":
            body = {"SUMMARY": {"RESPONSE_CODE": 403, "RESPONSE_MESSAGE": "Origin rejected"}}
            if http_status:
                raise urllib.error.HTTPError(
                    request.full_url, 403, "Forbidden", {}, io.BytesIO(json.dumps(body).encode())
                )
            return _Response(body)
        return fake(request, timeout)

    client = synoptic.SynopticTimeseriesClient(
        TOKEN, origins=["https://first.example", "https://second.example"], opener=opener
    )
    client.check_token()
    client.fetch(BBOX, START, END, cache_root=tmp_path)
    assert [origin for _, origin in attempts] == [
        "https://first.example",
        "https://second.example",
        "https://second.example",
        "https://second.example",
    ]
    assert attempts[-1][0].endswith("/timeseries")


def test_all_origins_rejected_reports_attempts():
    attempts = []

    def opener(request, timeout):
        attempts.append(request.get_header("Origin"))
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b""))

    client = synoptic.SynopticTimeseriesClient(
        TOKEN, origins=["https://one.example", "https://two.example"], opener=opener
    )
    with pytest.raises(synoptic.SynopticError, match="attempted origins") as error:
        client.check_token()
    assert attempts == ["https://one.example", "https://two.example"]
    assert TOKEN not in str(error.value)


def test_other_errors_do_not_try_next_origin():
    attempts = []

    def opener(request, timeout):
        attempts.append(request.get_header("Origin"))
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    client = synoptic.SynopticTimeseriesClient(
        TOKEN, origins=["https://one.example", "https://two.example"], opener=opener
    )
    with pytest.raises(synoptic.SynopticError):
        client.check_token()
    assert attempts == ["https://one.example"]


def test_no_origin_header_and_cache_identity():
    captured = []

    def opener(request, timeout):
        captured.append(request.get_header("Origin"))
        return _Response({"SUMMARY": {"RESPONSE_CODE": 1}})

    plain = synoptic.SynopticTimeseriesClient(TOKEN, origins=[], opener=opener)
    plain.check_token()
    assert captured == [None]
    restricted = synoptic.SynopticTimeseriesClient(TOKEN, origins=["https://one.example"])
    assert restricted._request_key({}) != plain._request_key({})


def test_preferred_origin_can_fail_and_fallback_again():
    attempts = []
    accepted = "https://two.example"

    def opener(request, timeout):
        origin = request.get_header("Origin")
        attempts.append(origin)
        if origin != accepted:
            # The HTTP status must take precedence over a different API summary code.
            body = {"SUMMARY": {"RESPONSE_CODE": 2, "RESPONSE_MESSAGE": "no stations found"}}
            raise urllib.error.HTTPError(
                request.full_url, 403, "Forbidden", {}, io.BytesIO(json.dumps(body).encode())
            )
        return _Response({"SUMMARY": {"RESPONSE_CODE": 1}})

    client = synoptic.SynopticTimeseriesClient(
        TOKEN, origins=["https://one.example", "https://two.example"], opener=opener
    )
    client.check_token()
    accepted = "https://one.example"
    client.check_token()
    assert attempts == [
        "https://one.example",
        "https://two.example",
        "https://two.example",
        "https://one.example",
    ]
