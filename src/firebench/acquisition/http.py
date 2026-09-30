"""
Stdlib HTTP primitives shared by every FireBench data provider.

Ported from spear ``backends/hrrr/download.py``: GET/POST with retries and exponential backoff,
inclusive byte ranges, and atomic subset downloads that coalesce adjacent ranges. No third-party
HTTP client is used.
"""

import logging
import os
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

USER_AGENT = "firebench"
TIMEOUT = 60  # s
RETRIES = 3
RETRY_WAIT = 2  # s, doubled after each attempt
NOT_FOUND_CODES = (403, 404)
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class HTTPStatusError(ConnectionError):
    """An HTTP error response, carrying the status code and the response body."""

    def __init__(self, url: str, code: int, body: bytes = b"") -> None:
        super().__init__(f"HTTP {code} for {url}")
        self.url = url
        self.code = code
        self.body = body


class RangeNotHonoredError(ValueError):
    """The server answered a byte-range request with something other than 206 Partial Content."""


class ByteRanged(Protocol):  # pylint: disable=too-few-public-methods
    """Anything with an inclusive ``byte_start``/``byte_end`` range, such as a GRIB message."""

    byte_start: int
    byte_end: int | None


def http_get(
    url: str,
    byte_range: tuple[int, int | None] | None = None,
    extra_headers: dict[str, str] | None = None,
    data: bytes | None = None,
    *,
    opener: Callable = urllib.request.urlopen,
    timeout: float = TIMEOUT,
    retries: int = RETRIES,
    not_found_codes: Sequence[int] = NOT_FOUND_CODES,
    display_url: str | None = None,
) -> bytes:
    """
    GET a URL, or POST it when ``data`` is given, with retries and exponential backoff.

    ``byte_range`` is an inclusive ``(start, end)`` range; ``end=None`` reads to the end of the file.
    A ranged read must come back as ``206 Partial Content`` (``RangeNotHonoredError`` otherwise, instead
    of silently returning the whole file) with the requested length (a short read is retried).

    Status codes in ``not_found_codes`` raise ``FileNotFoundError`` immediately. Transient statuses
    (408, 429, 5xx) and network errors are retried. Any other status raises ``HTTPStatusError`` at
    once, with the response body attached. ``display_url`` replaces ``url`` in log lines and error
    messages, so callers can redact secrets carried in the query string.
    """
    shown_url = display_url or url
    headers = {"User-Agent": USER_AGENT}
    if byte_range is not None:
        start, end = byte_range
        headers["Range"] = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
    if extra_headers:
        headers.update(extra_headers)

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with opener(request, timeout=timeout) as response:
                payload = response.read()
                if byte_range is not None:
                    _check_ranged_response(shown_url, byte_range, _status(response), len(payload))
                return payload
        except urllib.error.HTTPError as error:
            if error.code in not_found_codes:
                raise FileNotFoundError(f"remote file not found: {shown_url} (HTTP {error.code})") from None
            status_error = HTTPStatusError(shown_url, error.code, _read_error_body(error))
            if error.code not in RETRYABLE_STATUS_CODES:
                raise status_error from None
            last_error = status_error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last_error = error

        if attempt + 1 < retries:
            wait = RETRY_WAIT * 2**attempt
            logger.warning(
                "[http] attempt %d/%d failed for %s (%s), retry in %ds",
                attempt + 1,
                retries,
                shown_url,
                last_error,
                wait,
            )
            time.sleep(wait)

    if isinstance(last_error, HTTPStatusError):
        raise last_error
    raise ConnectionError(f"download failed after {retries} attempts: {shown_url} ({last_error})") from None


def fetch_text(url: str, **kwargs) -> str:
    """GET a URL and decode the body as UTF-8."""
    return http_get(url, **kwargs).decode()


def coalesce_ranges(messages: Sequence[ByteRanged]) -> list[tuple[int, int | None]]:
    """Merge the inclusive byte ranges of adjacent messages to reduce the number of requests."""
    ranges: list[list[int | None]] = []
    for message in messages:
        if ranges and ranges[-1][1] is not None and ranges[-1][1] + 1 == message.byte_start:
            ranges[-1][1] = message.byte_end
        else:
            ranges.append([message.byte_start, message.byte_end])
    return [tuple(byte_range) for byte_range in ranges]


def download_subset(url: str, messages: Sequence[ByteRanged], dest: Path, **http_kwargs) -> int:
    """
    Download the byte ranges of ``messages`` from ``url`` and concatenate them into ``dest``.

    The data is written to a unique temporary file next to ``dest`` and moved into place with
    ``os.replace``, so an interrupted or concurrent download never leaves a truncated ``dest``.
    Returns the number of bytes written.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ranges = coalesce_ranges(messages)
    logger.debug("[http] %s: %d messages in %d range requests", dest.name, len(messages), len(ranges))

    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".part", dir=dest.parent)
    size = 0
    try:
        with os.fdopen(fd, "wb") as f:
            for byte_range in ranges:
                size += f.write(http_get(url, byte_range=byte_range, **http_kwargs))
        os.replace(tmp_name, dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return size


def _status(response) -> int | None:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    return status


def _check_ranged_response(
    url: str, byte_range: tuple[int, int | None], status: int | None, size: int
) -> None:
    if status is not None and status != 206:
        raise RangeNotHonoredError(f"server ignored the byte range for {url} (HTTP {status}, expected 206)")
    start, end = byte_range
    if end is not None and size != end - start + 1:
        raise ConnectionError(
            f"short byte-range read for {url}: got {size} bytes, expected {end - start + 1}"
        )


def _read_error_body(error: urllib.error.HTTPError) -> bytes:
    try:
        return error.read() or b""
    except OSError:
        return b""
