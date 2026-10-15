import json
import math
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from firebench.acquisition import cmr, http

BOX = (-120.8, 38.4, -119.7, 39.0)


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


class _Cmr:
    """Answers CMR granule searches from a list of entries per collection, one page at a time."""

    def __init__(self, entries: dict[tuple[str, str], list[dict]], page_size: int = cmr.PAGE_SIZE) -> None:
        self.entries = entries
        self.page_size = page_size
        self.queries = []

    def __call__(self, request, timeout):
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(request.full_url).query))
        self.queries.append(query)
        found = self.entries.get((query["short_name"], query["version"]), [])
        start, end = (cmr._parse_time(value) for value in query["temporal"].split(","))
        found = [entry for entry in found if cmr._parse_time(entry["time_start"]) <= end]
        found = [entry for entry in found if cmr._parse_time(entry["time_end"]) >= start]
        page = int(query["page_num"])
        chunk = found[(page - 1) * self.page_size : page * self.page_size]
        return _Response(json.dumps({"feed": {"entry": chunk}}).encode())


def _entry(granule_id: str, start: datetime, minutes: int = 6, ring=None) -> dict:
    ring = ring or [(-121, 38), (-119, 38), (-119, 40), (-121, 40)]
    closed = [*ring, ring[0]]
    entry = {
        "producer_granule_id": granule_id,
        "time_start": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "time_end": (start + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "links": [],
    }
    if ring != "none":
        entry["polygons"] = [[" ".join(f"{lat} {lon}" for lon, lat in closed)]]
    return entry


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


T0 = datetime(2021, 8, 20, 9, 18, tzinfo=timezone.utc)
DAY = (datetime(2021, 8, 20, tzinfo=timezone.utc), datetime(2021, 8, 21, tzinfo=timezone.utc))


def test_search_reads_every_page_in_time_order(monkeypatch):
    entries = [_entry(f"G{index:03d}", T0 + timedelta(minutes=7 * index)) for index in range(5)]
    opener = _Cmr({("VNP14IMG", "002"): list(reversed(entries))}, page_size=2)
    monkeypatch.setattr(cmr, "PAGE_SIZE", 2)

    granules = cmr.search_granules("VNP14IMG", "002", BOX, *DAY, opener=opener)

    assert [granule.granule_id for granule in granules] == [f"G{index:03d}" for index in range(5)]
    assert [query["page_num"] for query in opener.queries] == ["1", "2", "3"]
    assert opener.queries[0]["bounding_box"] == "-120.8,38.4,-119.7,39.0"
    assert opener.queries[0]["temporal"] == "2021-08-20T00:00:00Z,2021-08-21T00:00:00Z"
    assert granules[0].time_start == T0 and granules[0].polygon[0] == (-121.0, 38.0)


def test_granule_whose_outline_misses_the_box_is_dropped_and_one_without_outline_kept():
    away = _entry("AWAY", T0, ring=[(-100, 38), (-99, 38), (-99, 39), (-100, 39)])
    bare = _entry("BARE", T0 + timedelta(minutes=10), ring="none")
    opener = _Cmr({("VNP14IMG", "002"): [away, bare, bare]})

    granules = cmr.search_granules("VNP14IMG", "002", BOX, *DAY, opener=opener)

    assert [granule.granule_id for granule in granules] == ["BARE"]
    assert granules[0].polygon == ()


def test_consecutive_granules_merge_into_one_overpass():
    granules = [
        cmr.Granule("X", "1", name, T0 + timedelta(minutes=offset), T0 + timedelta(minutes=offset + 6), ())
        for name, offset in (("A", 0), ("B", 6), ("C", 12), ("D", 52))
    ]

    passes = cmr.overpasses(list(reversed(granules)), BOX)

    assert [item.granule_ids for item in passes] == [("A", "B", "C"), ("D",)]
    assert passes[0].time_start == T0 and passes[0].time_end == T0 + timedelta(minutes=18)
    assert math.isnan(passes[0].observed_fraction)


def test_observed_fraction_of_a_swath_over_the_west_half_of_the_box():
    middle = (BOX[0] + BOX[2]) / 2
    west_half = ((-125.0, 37.0), (middle, 37.0), (middle, 40.0), (-125.0, 40.0))
    whole = ((-125.0, 37.0), (-115.0, 37.0), (-115.0, 40.0), (-125.0, 40.0))
    granule = lambda ring: cmr.Granule("X", "1", "G", T0, T0 + timedelta(minutes=6), ring)  # noqa: E731

    assert cmr.overpasses([granule(west_half)], BOX)[0].observed_fraction == pytest.approx(0.5, abs=2e-3)
    assert cmr.overpasses([granule(whole)], BOX)[0].observed_fraction == pytest.approx(1.0)


def test_near_real_time_collection_takes_over_after_the_last_standard_granule():
    standard = [_entry(f"SP{day}", T0 + timedelta(days=day)) for day in range(3)]
    recent = [_entry(f"NRT{day}", T0 + timedelta(days=day)) for day in range(2, 5)]
    opener = _Cmr({("VNP14IMG", "002"): standard, ("VNP14IMG_NRT", "2"): recent})
    end = T0 + timedelta(days=6)

    passes, used = cmr.stream_overpasses("viirs_snpp", BOX, T0 - timedelta(hours=1), end, opener=opener)

    assert used == ["VNP14IMG 002", "VNP14IMG_NRT 2"]
    assert [item.granule_ids[0] for item in passes] == ["SP0", "SP1", "SP2", "NRT3", "NRT4"]


def test_a_stream_without_any_granule_gives_no_overpass_and_no_collection():
    passes, used = cmr.stream_overpasses("viirs_noaa21", BOX, *DAY, opener=_Cmr({}))

    assert passes == [] and used == []


def test_a_box_across_the_antimeridian_or_an_unknown_stream_is_refused():
    with pytest.raises(ValueError, match="antimeridian"):
        cmr.check_bbox((170, 10, -170, 20))
    with pytest.raises(ValueError, match="unknown stream"):
        cmr.stream_overpasses("goes16", BOX, *DAY, opener=_Cmr({}))
