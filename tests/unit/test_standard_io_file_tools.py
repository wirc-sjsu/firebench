import re
import os
import pytest
from datetime import tzinfo, timezone, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import h5py
import numpy as np

# Replace 'your_module' with the actual module name that defines _resolve_tz
from firebench.standardize.time import _resolve_tz, datetime_to_iso8601, current_datetime_iso8601
from firebench.standardize.tools import read_quantity_from_fb_dataset
from firebench.tools import get_firebench_data_directory


# _resolve_tz
# -----------
def test_resolve_tz_returns_none_for_none():
    result = _resolve_tz(None)
    assert result is None


def test_resolve_tz_converts_string_to_zoneinfo():
    result = _resolve_tz("UTC")
    assert isinstance(result, ZoneInfo)
    # Ensure it specifically represents the UTC zone
    assert getattr(result, "key", None) == "UTC"
    # And it's a tzinfo
    assert isinstance(result, tzinfo)


def test_resolve_tz_passthrough_zoneinfo_object():
    paris = ZoneInfo("Europe/Paris")
    result = _resolve_tz(paris)
    # Should be the exact same object (identity)
    assert result is paris


def test_resolve_tz_passthrough_datetime_timezone_object():
    result = _resolve_tz(timezone.utc)
    # Should be the exact same object (identity)
    assert result is timezone.utc
    assert isinstance(result, tzinfo)


def test_resolve_tz_invalid_string_raises():
    with pytest.raises(ZoneInfoNotFoundError):
        _resolve_tz("Not/A_Real_TZ")


# datetime_to_iso8601
# -------------------


def test_naive_dt_with_tz_string_attaches_no_shift_with_seconds():
    # Naive datetime; tz provided as string -> attach tz (no time shift)
    dt = datetime(2025, 8, 8, 12, 34, 56)  # naive
    result = datetime_to_iso8601(dt, include_seconds=True, tz="UTC")
    assert result == "2025-08-08T12:34:56+00:00"


def test_naive_dt_with_tzinfo_attaches_no_shift_without_seconds():
    # Naive datetime; tz provided as tzinfo -> attach tz (no shift), minutes precision
    dt = datetime(2025, 8, 8, 12, 34, 56)  # naive
    paris = ZoneInfo("Europe/Paris")  # DST in August -> +02:00
    result = datetime_to_iso8601(dt, include_seconds=False, tz=paris)
    # Expect no seconds in the string and +02:00 offset
    assert result == "2025-08-08T12:34+02:00"
    # Quick format sanity check: no seconds chunk before the offset
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}", result)


def test_aware_dt_with_tz_converts_timezone_with_seconds():
    # Aware UTC datetime; convert to Europe/Paris (DST +02:00 in August)
    dt_utc = datetime(2025, 8, 8, 10, 0, 0, tzinfo=timezone.utc)
    result = datetime_to_iso8601(dt_utc, include_seconds=True, tz="Europe/Paris")
    # 10:00 UTC -> 12:00 in Paris during DST, seconds included
    assert result.startswith("2025-08-08T12:00:00")
    assert result.endswith("+02:00")


def test_aware_dt_without_tz_keeps_existing_timezone():
    # Aware datetime; tz not provided -> keep dt's timezone
    dt_utc = datetime(2025, 8, 8, 7, 8, 9, tzinfo=timezone.utc)
    result = datetime_to_iso8601(dt_utc, include_seconds=True, tz=None)
    assert result == "2025-08-08T07:08:09+00:00"


def test_naive_dt_without_tz_raises_value_error():
    # Naive datetime; tz not provided -> must raise
    dt = datetime(2025, 8, 8, 12, 34, 56)  # naive
    with pytest.raises(ValueError):
        datetime_to_iso8601(dt, include_seconds=True, tz=None)


# current_datetime_iso8601
# ------------------------


class FixedOffsetTZ(tzinfo):
    """UTC+03:00 fixed offset."""

    def utcoffset(self, dt):
        return timedelta(hours=3)

    def tzname(self, dt):
        return "+03:00"

    def dst(self, dt):
        return timedelta(0)


class DummyNow:
    def astimezone(self):
        return datetime(2030, 1, 2, 3, 4, 5, tzinfo=FixedOffsetTZ())


class FakeDateTime:
    @classmethod
    def now(cls):
        return DummyNow()


def test_current_datetime_iso8601_local_with_seconds(monkeypatch):
    import firebench.standardize.time as std_utils

    monkeypatch.setattr(std_utils, "datetime", FakeDateTime)

    result = current_datetime_iso8601(include_seconds=True, tz=None)
    assert result == "2030-01-02T03:04:05+03:00"


def test_current_datetime_iso8601_local_without_seconds(monkeypatch):
    import firebench.standardize.time as std_utils

    monkeypatch.setattr(std_utils, "datetime", FakeDateTime)

    result = current_datetime_iso8601(include_seconds=False, tz=None)
    assert result == "2030-01-02T03:04+03:00"


def test_current_datetime_iso8601_with_utc(monkeypatch):
    import firebench.standardize.time as std_utils

    monkeypatch.setattr(std_utils, "datetime", FakeDateTime)

    result = current_datetime_iso8601(include_seconds=True, tz="UTC")
    # +03:00 local → UTC subtracts 3 hours
    assert result == "2030-01-02T00:04:05+00:00"


def test_current_datetime_iso8601_with_zoneinfo_without_seconds(monkeypatch):
    import firebench.standardize.time as std_utils

    monkeypatch.setattr(std_utils, "datetime", FakeDateTime)

    # Paris in January is UTC+01:00 → from +03:00 local, subtract 2 hours
    result = current_datetime_iso8601(include_seconds=False, tz=ZoneInfo("Europe/Paris"))
    assert result == "2030-01-02T01:04+01:00"


# read_quantity_from_fb_dataset
# -----------------------------
def test_read_quantity_from_fb_dataset():
    # Assuming these files exist in the package
    h5_file_path = os.path.join(get_firebench_data_directory(), "test", "file_test_1.h5")

    # Ensure the files exist
    assert os.path.isfile(h5_file_path), f"Missing h5 file: {h5_file_path}"

    with h5py.File(h5_file_path, mode="r") as f:
        q = read_quantity_from_fb_dataset("valid_data", f)
    assert hasattr(q, "magnitude") and hasattr(q, "units")
    np.testing.assert_allclose(q.magnitude, np.array([1.0, 2.0, 3.0]))
    assert str(q.units) == "meter"

    with h5py.File(h5_file_path, "r") as f:
        q = read_quantity_from_fb_dataset("valid_data_2d", f)
    np.testing.assert_allclose(q.magnitude, np.array([[1, 2], [3, 4]], dtype=float))
    assert str(q.units) == "second"

    with h5py.File(h5_file_path, "r") as f:
        with pytest.raises(ValueError, match="missing a valid `units` attribute"):
            read_quantity_from_fb_dataset("missing_units", f)

    with h5py.File(h5_file_path, "r") as f:
        with pytest.raises(ValueError):
            read_quantity_from_fb_dataset("non_string_units", f)
