import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from firebench.acquisition import http, nexrad

CALDOR = (-120.8, 38.4, -119.7, 39.0)
DAY = datetime(2021, 8, 17, tzinfo=timezone.utc)


def _key(site: str, start: datetime) -> str:
    return f"{start:%Y/%m/%d}/{site}/{site}{start:%Y%m%d_%H%M%S}_V06"


def _listing(keys: list[str], token: str | None = None) -> bytes:
    contents = "".join(
        f"<Contents><Key>{key}</Key><Size>{1000 + i}</Size></Contents>" for i, key in enumerate(keys)
    )
    more = (
        f"<IsTruncated>true</IsTruncated><NextContinuationToken>{token}</NextContinuationToken>"
        if token
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{contents}{more}</ListBucketResult>'
    ).encode()


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


class _Bucket:
    """A fake anonymous S3 bucket: two-page listings per prefix, and file bodies by key."""

    def __init__(self, keys: list[str], failing=()) -> None:
        self.keys = keys
        self.failing = set(failing)
        self.urls = []

    def __call__(self, request, timeout):
        url = request.full_url
        self.urls.append(url)
        parts = urllib.parse.urlsplit(url)
        if parts.query:
            query = dict(urllib.parse.parse_qsl(parts.query))
            found = [key for key in self.keys if key.startswith(query["prefix"])]
            half = len(found) // 2
            if "continuation-token" in query:
                return _Response(_listing(found[half:]))
            return _Response(_listing(found[:half], token="next") if half else _listing(found))
        key = parts.path.lstrip("/")
        if key in self.failing:
            raise FileNotFoundError(key)
        return _Response(f"body of {key}".encode())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def test_site_table_holds_the_wsr88d_sites_with_metric_elevations():
    sites = nexrad.nexrad_sites()
    assert len(sites) >= 155
    kdax = sites["KDAX"]
    assert kdax.name == "Sacramento" and kdax.state == "CA"
    assert kdax.latitude == pytest.approx(38.5011, abs=1e-3)
    assert kdax.longitude == pytest.approx(-121.6778, abs=1e-3)
    assert kdax.elevation_m == pytest.approx(144 * 0.3048, abs=0.1)
    with pytest.raises(ValueError, match="unknown NEXRAD site"):
        nexrad.site("KXXX")


def test_sites_in_range_of_the_caldor_frame_nearest_first():
    found = nexrad.sites_in_range(CALDOR)
    names = [site.icao for site, _ in found]
    assert names[:3] == ["KDAX", "KRGX", "KBBX"]
    assert all(distance <= nexrad.DEFAULT_MAX_RANGE_KM for _, distance in found)
    assert [distance for _, distance in found] == sorted(distance for _, distance in found)
    assert [site.icao for site, _ in nexrad.sites_in_range(CALDOR, max_km=80)] == ["KDAX"]


def test_a_site_inside_the_box_is_at_distance_zero():
    kdax = nexrad.site("KDAX")
    box = (kdax.longitude - 0.5, kdax.latitude - 0.5, kdax.longitude + 0.5, kdax.latitude + 0.5)
    assert nexrad.distance_to_box_km(kdax.latitude, kdax.longitude, box) == 0.0
    assert nexrad.sites_in_range(box, max_km=1)[0][0].icao == "KDAX"


def test_volume_keys_and_their_times():
    assert nexrad.volume_time("2021/08/17/KDAX/KDAX20210817_000309_V06") == datetime(
        2021, 8, 17, 0, 3, 9, tzinfo=timezone.utc
    )
    assert nexrad.is_volume_key("2010/08/17/KDAX/KDAX20100817_000309_V03.gz")
    assert nexrad.is_volume_key("1995/08/17/KDAX/KDAX19950817_000309.gz")
    assert not nexrad.is_volume_key("2021/08/17/KDAX/KDAX20210817_000309_V06_MDM")
    with pytest.raises(ValueError, match="not a NEXRAD Level II volume key"):
        nexrad.volume_time("2021/08/17/KDAX/notes.txt")


def test_list_volumes_reads_each_day_in_pages_and_keeps_the_window():
    times = [DAY + timedelta(hours=23, minutes=50), DAY + timedelta(days=1, minutes=1)]
    times += [DAY + timedelta(days=1, minutes=5 * index) for index in range(1, 5)]
    keys = [_key("KDAX", moment) for moment in times]
    keys += [_key("KDAX", times[1]) + "_MDM", _key("KRGX", times[1])]
    bucket = _Bucket(keys)
    volumes = nexrad.list_volumes(
        "KDAX", DAY + timedelta(hours=23, minutes=55), DAY + timedelta(days=1, minutes=15), opener=bucket
    )
    assert [volume.time_start for volume in volumes] == times[1:4]
    assert all(volume.site == "KDAX" and volume.bucket == nexrad.BUCKET for volume in volumes)
    assert all(volume.size is not None for volume in volumes)
    prefixes = {
        dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["prefix"] for url in bucket.urls
    }
    assert prefixes == {"2021/08/17/KDAX/", "2021/08/18/KDAX/"}
    assert any("continuation-token" in url for url in bucket.urls)


def test_list_volumes_refuses_an_empty_window_and_an_unknown_site():
    with pytest.raises(ValueError, match="before it starts"):
        nexrad.list_volumes("KDAX", DAY, DAY, opener=_Bucket([]))
    with pytest.raises(ValueError, match="unknown NEXRAD site"):
        nexrad.list_volumes("KXXX", DAY, DAY + timedelta(hours=1), opener=_Bucket([]))


def _volumes(site="KDAX", minutes=(0, 4, 9, 13, 18, 22)):
    return [
        nexrad.NexradVolume(
            nexrad.BUCKET, _key(site, DAY + timedelta(minutes=m)), site, DAY + timedelta(minutes=m)
        )
        for m in minutes
    ]


def test_select_volumes_keeps_the_first_of_each_bin_or_every_volume():
    volumes = _volumes()
    assert nexrad.select_volumes(volumes, 0) == volumes
    kept = nexrad.select_volumes(list(reversed(volumes)), 10)
    assert [volume.time_start.minute for volume in kept] == [0, 13, 22]
    assert [v.time_start.minute for v in nexrad.select_volumes(volumes, 5)] == [0, 9, 13, 18, 22]
    with pytest.raises(ValueError, match="time step"):
        nexrad.select_volumes(volumes, 7)


def test_fetch_volumes_keeps_order_checks_sums_and_deletes_behind(tmp_path):
    volumes = _volumes()
    bucket = _Bucket([volume.key for volume in volumes], failing={volumes[2].key})
    seen = []
    for fetched in nexrad.fetch_volumes(volumes, tmp_path, workers=2, opener=bucket):
        seen.append(fetched)
        if fetched.path is not None:
            assert fetched.path.read_bytes() == f"body of {fetched.volume.key}".encode()
            assert fetched.sha256 == hashlib.sha256(fetched.path.read_bytes()).hexdigest()
            earlier = [item.path for item in seen[:-1] if item.path is not None]
            assert not any(path.exists() for path in earlier)
    assert [item.volume for item in seen] == volumes
    assert seen[2].path is None and "download failed" in seen[2].error
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_fetch_volumes_with_keep_leaves_the_bucket_layout(tmp_path):
    volumes = _volumes(minutes=(0, 4))
    list(nexrad.fetch_volumes(volumes, tmp_path, keep=True, opener=_Bucket([v.key for v in volumes])))
    found = nexrad.local_volumes(tmp_path, "KDAX", DAY, DAY + timedelta(hours=1))
    assert [volume.key for volume in found] == [volume.key for volume in volumes]
    fetched = list(nexrad.local_fetched_volumes([*found, _volumes(minutes=(30,))[0]], tmp_path))
    assert [item.sha256 is not None for item in fetched] == [True, True, False]
    assert fetched[0].sha256 == nexrad.sha256_file(fetched[0].path)
    assert all(path.exists() for path in (item.path for item in fetched[:2]))
