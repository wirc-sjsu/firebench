import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from firebench.acquisition import goes_fdc, http


def _key(satellite: int, start: datetime) -> str:
    end = start + timedelta(minutes=2, seconds=37)
    stamp = lambda moment: moment.strftime("%Y%j%H%M%S") + "0"  # noqa: E731
    return (
        f"ABI-L2-FDCC/{start:%Y}/{start:%j}/{start:%H}/OR_ABI-L2-FDCC-M6_G{satellite}_s{stamp(start)}"
        f"_e{stamp(end)}_c{stamp(end)}.nc"
    )


def _listing(keys: list[str], token: str | None = None) -> bytes:
    contents = "".join(
        f"<Contents><Key>{key}</Key><Size>{100 + i}</Size></Contents>" for i, key in enumerate(keys)
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


DAY = datetime(2021, 8, 20, tzinfo=timezone.utc)


def test_west_across_the_switch_gives_two_segments_meeting_on_the_switch_day():
    segments = goes_fdc.goes_segments(DAY.replace(2022, 12, 30), DAY.replace(2023, 1, 10), ["west"])

    assert [
        (segment.bucket, segment.start.date().isoformat(), segment.end.date().isoformat())
        for segment in segments
    ] == [
        ("noaa-goes17", "2022-12-30", "2023-01-04"),
        ("noaa-goes18", "2023-01-04", "2023-01-10"),
    ]


def test_scan_times_come_from_the_stamps_of_the_key_to_the_second():
    start, end = goes_fdc.scan_times(
        "OR_ABI-L2-FDCC-M6_G17_s20212320901177_e20212320903550_c20212320904154.nc"
    )

    assert start == datetime(2021, 8, 20, 9, 1, 17, tzinfo=timezone.utc)
    assert end == datetime(2021, 8, 20, 9, 3, 55, tzinfo=timezone.utc)


def test_listing_reads_both_pages_and_keeps_the_scans_of_the_segment():
    keys = [_key(17, DAY + timedelta(minutes=5 * index + 1)) for index in range(-3, 6)]
    keys = [key for key in keys if "/2021/232/" in key] + [_key(17, DAY - timedelta(minutes=4))]
    segment = goes_fdc.GoesSegment("west", 17, "noaa-goes17", DAY, DAY + timedelta(minutes=20))

    scans = goes_fdc.list_fdc_scans(segment, opener=_Bucket(keys))

    assert [scan.time_start.minute for scan in scans] == [1, 6, 11, 16]
    assert all(scan.size and scan.size >= 100 for scan in scans)


def test_selection_keeps_the_first_scan_of_each_bin():
    scans = [
        goes_fdc.FdcScan(
            "noaa-goes16",
            _key(16, DAY + timedelta(minutes=5 * i + 1)),
            DAY + timedelta(minutes=5 * i + 1),
            DAY,
        )
        for i in range(12)
    ]

    assert [scan.time_start.minute for scan in goes_fdc.select_scans(reversed(scans), 10)] == [
        1,
        11,
        21,
        31,
        41,
        51,
    ]
    assert [scan.time_start.minute for scan in goes_fdc.select_scans(scans, 30)] == [1, 31]
    assert len(goes_fdc.select_scans(scans, 5)) == 12
    with pytest.raises(ValueError, match="time step"):
        goes_fdc.select_scans(scans, 20)


def test_fetch_yields_in_order_with_checksums_and_deletes_files_once_passed(tmp_path):
    keys = [_key(16, DAY + timedelta(minutes=10 * i + 1)) for i in range(5)]
    scans = [goes_fdc.FdcScan("noaa-goes16", key, *goes_fdc.scan_times(key)) for key in keys]
    seen = []

    for fetched in goes_fdc.fetch_fdc_scans(
        scans, tmp_path, workers=2, opener=_Bucket(keys, failing={keys[2]})
    ):
        seen.append(fetched)
        on_disk = sorted(path.name for path in tmp_path.rglob("*.nc"))
        if fetched.path is not None:
            assert fetched.path.name in on_disk
            assert fetched.sha256 == hashlib.sha256(f"body of {fetched.scan.key}".encode()).hexdigest()
            assert len(on_disk) <= 3

    assert [fetched.scan.key for fetched in seen] == keys
    assert seen[2].path is None and seen[2].sha256 is None and keys[2] in seen[2].error
    assert list(tmp_path.rglob("*.nc")) == []


def test_fetch_with_keep_leaves_the_files_in_the_bucket_layout(tmp_path):
    keys = [_key(16, DAY + timedelta(minutes=1))]
    scans = [goes_fdc.FdcScan("noaa-goes16", keys[0], *goes_fdc.scan_times(keys[0]))]

    list(goes_fdc.fetch_fdc_scans(scans, tmp_path, keep=True, opener=_Bucket(keys)))

    assert (tmp_path / "noaa-goes16" / keys[0]).read_bytes() == f"body of {keys[0]}".encode()


def test_local_scans_are_listed_from_a_directory_in_the_bucket_layout(tmp_path):
    keys = [_key(17, DAY + timedelta(minutes=30 * i + 1)) for i in range(3)]
    for key in keys:
        (tmp_path / "noaa-goes17" / key).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "noaa-goes17" / key).write_bytes(b"x")
    segment = goes_fdc.GoesSegment("west", 17, "noaa-goes17", DAY, DAY + timedelta(hours=1))

    scans = goes_fdc.local_fdc_scans(tmp_path, segment)
    fetched = list(goes_fdc.local_fetched_scans(scans, tmp_path))

    assert [scan.key for scan in scans] == keys[:2]
    assert [item.sha256 for item in fetched] == [hashlib.sha256(b"x").hexdigest()] * 2
    assert all(item.path.exists() for item in fetched)
