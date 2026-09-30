import io
import urllib.error
from dataclasses import dataclass
from pathlib import Path

import pytest

from firebench.acquisition import http


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url: str, code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(body))


class _Opener:
    """Replays a scripted sequence of responses or exceptions and records the requests."""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http.time, "sleep", sleeps.append)
    return sleeps


def test_http_get_sends_inclusive_byte_range_and_user_agent():
    opener = _Opener(_Response(b"abcd", status=206))

    assert http.http_get("https://x/f", byte_range=(10, 13), opener=opener) == b"abcd"
    assert opener.requests[0].get_header("Range") == "bytes=10-13"
    assert opener.requests[0].get_header("User-agent") == http.USER_AGENT


def test_http_get_open_ended_range_reads_to_end_of_file():
    opener = _Opener(_Response(b"tail", status=206))

    http.http_get("https://x/f", byte_range=(10, None), opener=opener)

    assert opener.requests[0].get_header("Range") == "bytes=10-"


def test_server_ignoring_the_range_fails_instead_of_returning_the_whole_file():
    opener = _Opener(_Response(b"whole file", status=200))

    with pytest.raises(http.RangeNotHonoredError, match="expected 206"):
        http.http_get("https://x/f", byte_range=(0, 3), opener=opener)
    assert len(opener.requests) == 1


def test_short_range_read_is_retried(_no_sleep):
    opener = _Opener(_Response(b"ab", status=206), _Response(b"abcd", status=206))

    assert http.http_get("https://x/f", byte_range=(0, 3), opener=opener) == b"abcd"
    assert _no_sleep == [2]


@pytest.mark.parametrize("code", (403, 404))
def test_missing_remote_file_raises_file_not_found_without_retry(code):
    opener = _Opener(_http_error("https://x/f", code))

    with pytest.raises(FileNotFoundError, match=f"HTTP {code}"):
        http.http_get("https://x/f", opener=opener)
    assert len(opener.requests) == 1


def test_transient_server_error_is_retried_with_backoff_and_no_final_sleep(_no_sleep):
    opener = _Opener(
        _http_error("https://x/f", 503),
        urllib.error.URLError("reset"),
        _Response(b"ok"),
    )

    assert http.http_get("https://x/f", opener=opener) == b"ok"
    assert _no_sleep == [2, 4]


def test_exhausted_retries_raise_connection_error_without_sleeping_after_last_attempt(_no_sleep):
    opener = _Opener(*(TimeoutError("slow") for _ in range(http.RETRIES)))

    with pytest.raises(ConnectionError, match="failed after 3 attempts"):
        http.http_get("https://x/f", opener=opener)
    assert _no_sleep == [2, 4]


def test_client_error_is_not_retried_and_keeps_the_response_body():
    opener = _Opener(_http_error("https://x/f", 401, b'{"SUMMARY": {"RESPONSE_CODE": 2}}'))

    with pytest.raises(http.HTTPStatusError) as excinfo:
        http.http_get("https://x/f", opener=opener, not_found_codes=())
    assert excinfo.value.code == 401
    assert b"RESPONSE_CODE" in excinfo.value.body
    assert len(opener.requests) == 1


def test_display_url_hides_the_real_url_in_errors():
    opener = _Opener(_http_error("https://x/f?token=SECRET", 404))

    with pytest.raises(FileNotFoundError) as excinfo:
        http.http_get("https://x/f?token=SECRET", opener=opener, display_url="https://x/f?token=***")
    assert "SECRET" not in str(excinfo.value)


@dataclass
class _Message:
    byte_start: int
    byte_end: int | None


def test_adjacent_messages_are_coalesced_into_one_range():
    messages = [_Message(0, 9), _Message(10, 19), _Message(30, 39), _Message(40, None)]

    assert http.coalesce_ranges(messages) == [(0, 19), (30, None)]


def test_download_subset_writes_concatenated_ranges_atomically(tmp_path):
    opener = _Opener(_Response(b"0123456789", status=206), _Response(b"XYZ", status=206))
    dest = tmp_path / "sub" / "file.grib2"

    size = http.download_subset("https://x/f", [_Message(0, 9), _Message(20, 22)], dest, opener=opener)

    assert size == 13
    assert dest.read_bytes() == b"0123456789XYZ"
    assert sorted(path.name for path in dest.parent.iterdir()) == ["file.grib2"]


def test_failed_subset_download_leaves_neither_destination_nor_temporary_file(tmp_path):
    opener = _Opener(_Response(b"0123456789", status=206), _http_error("https://x/f", 404))
    dest = tmp_path / "file.grib2"

    with pytest.raises(FileNotFoundError):
        http.download_subset("https://x/f", [_Message(0, 9), _Message(20, 22)], dest, opener=opener)
    assert list(Path(tmp_path).iterdir()) == []
