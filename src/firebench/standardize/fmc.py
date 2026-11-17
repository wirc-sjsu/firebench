"""NFMDB CSV adapter, based on the converter contributed by Abtin Olaee.

Raw observations are preserved; time assumptions are explicit sample metadata.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import hdf5plugin
import numpy as np

from ..tools import calculate_sha256
from .tools import check_std_version

import h5py

# nfmdb SCHEMA
REQUIRED_COLUMNS = {
    "STID",
    "DATE",
    "FUEL_TYPE",
    "FUEL_VARIATION",
    "PERCENT",
    "NAME",
    "GACC",
    "GROUP",
    "LAT",
    "LON",
    "ELE",
}

# Translation from NFMDB dead time-lag labels to FireBench standard names.
FUEL_DATASETS = {
    "1-Hour": "fuel_moisture_content_1h",
    "10-Hour": "fuel_moisture_content_10h",
    "100-Hour": "fuel_moisture_content_100h",
    "1000-Hour": "fuel_moisture_content_1000h",
}


def fail(message: str) -> None:
    raise ValueError(message)


def text(value: str | None) -> str:
    return (value or "").strip()


def number(value: str) -> float:
    """Return a float, using NaN for missing or nonnumeric measurements."""
    try:
        return float(text(value))
    except ValueError:
        return math.nan


def required_number(value: str, row_number: int, field: str) -> float:
    result = number(value)
    if not math.isfinite(result):
        fail(f"row {row_number}: {field} must be numeric")
    return result


def parse_date(value: str, row_number: int) -> date | datetime:
    value = text(value)
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp needs a timezone")
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"row {row_number}: DATE must be YYYY-MM-DD or a timezone-aware ISO timestamp"
        ) from exc


def read_rows(path: Path) -> list[dict[str, object]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            fail("CSV has no header row")

        headers = {text(value) for value in reader.fieldnames}
        missing = REQUIRED_COLUMNS - headers
        if missing:
            fail(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        rows = []
        for row_number, source in enumerate(reader, start=2):
            if None in source or any(v is None for v in source.values()):
                fail(f"row {row_number}: number of fields does not match CSV header")
            row = {text(key): text(value) for key, value in source.items() if key}
            fuel_type = row["FUEL_TYPE"]
            fuel_variation = row["FUEL_VARIATION"]
            if fuel_variation.lower() == "none":
                fuel_variation = ""
            if not fuel_type:
                fail(f"row {row_number}: FUEL_TYPE is empty")
            if "/" in row["STID"]:
                fail(f"row {row_number}: STID cannot contain slash")
            if not row["STID"]:
                fail(f"row {row_number}: STID is empty")
            if "/" in fuel_type or "/" in fuel_variation:
                fail(f"row {row_number}: fuel labels cannot contain '/'")

            rows.append(
                {
                    "row_number": row_number,
                    "stid": row["STID"],
                    "date": parse_date(row["DATE"], row_number),
                    "fuel_type": fuel_type,
                    "fuel_variation": fuel_variation,
                    "percent": number(row["PERCENT"]),
                    "name": row["NAME"],
                    "gacc": row["GACC"],
                    "group": row["GROUP"],
                    "lat": required_number(row["LAT"], row_number, "LAT"),
                    "lon": required_number(row["LON"], row_number, "LON"),
                    "ele": required_number(row["ELE"], row_number, "ELE"),
                }
            )

    if not rows:
        fail("CSV contains no data rows")
    return rows


def validate_stations(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_station: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_station[str(row["stid"])].append(row)

    stations = {}
    for stid, station_rows in by_station.items():
        station = station_rows[0]

        stations[stid] = {
            "station_id": stid,
            "station_name": station["name"],
            "source_gacc": station["gacc"],
            "source_group": station["group"],
            "position_lat": station["lat"],
            "position_lat_units": "degree",
            "position_lon": station["lon"],
            "position_lon_units": "degree",
            "position_alt": station["ele"],
            "position_alt_units": "ft",
            "crs": "EPSG:4326",
        }
    return stations


def series_label(fuel_type: str, fuel_variation: str) -> str:
    return fuel_type if not fuel_variation else f"{fuel_type}_{fuel_variation}"


def station_groups(
    rows: list[dict[str, object]],
) -> dict[str, list[tuple[tuple[str, list[dict[str, object]]], ...]]]:
    """Group a fully synchronized station together; otherwise keep each series separate."""
    by_series: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_series[(str(row["stid"]), str(row["fuel_type"]), str(row["fuel_variation"]))].append(row)

    by_station: dict[str, list[tuple[str, list[dict[str, object]]]]] = defaultdict(list)
    for (stid, fuel_type, variation), series_rows in by_series.items():
        series_rows.sort(key=lambda row: (row["date"], row["row_number"]))
        by_station[stid].append((series_label(fuel_type, variation), series_rows))

    result = {}
    for stid, series in by_station.items():
        series = sorted(series, key=lambda item: item[0])
        time_coordinates = {tuple(row["date"] for row in series_rows) for _, series_rows in series}
        if len(series) == 1 or len(time_coordinates) == 1:
            result[stid] = [tuple(series)]
        else:
            result[stid] = [(item,) for item in series]
    return result


def common_fuel_type(series_group: tuple[tuple[str, list[dict[str, object]]], ...]) -> str | None:
    """Return the fuel type when every series in a time group has the same one."""
    fuel_types = {str(series_rows[0]["fuel_type"]) for _, series_rows in series_group}
    return fuel_types.pop() if len(fuel_types) == 1 else None


def group_name(
    stid: str,
    series_group: tuple[tuple[str, list[dict[str, object]]], ...],
    has_out_of_sync_series: bool,
) -> str:
    """Only add the fuel label when a station has out-of-sync series."""
    if not has_out_of_sync_series:
        return f"station_{stid}"
    return f"station_{stid}_{series_group[0][0]}"


def dataset_name(
    fuel_type: str,
    fuel_variation: str,
    series_group: tuple[tuple[str, list[dict[str, object]]], ...],
) -> str:
    """Use standard dead-FMC names where possible and unique names otherwise."""
    if fuel_type in FUEL_DATASETS and not fuel_variation:
        return FUEL_DATASETS[fuel_type]

    if common_fuel_type(series_group):
        return "fuel_moisture_content" if not fuel_variation else f"fuel_moisture_content_{fuel_variation}"

    return f"fuel_moisture_content_{series_label(fuel_type, fuel_variation)}"


def standardize_nfmdb_csv(
    csv_path: Path, h5file: h5py.File, *, timezone: str | None = None, overwrite: bool = False
):
    """Append raw NFMDB series to a standard file. Date-only live fuels require an IANA timezone.

    All non-time-lag fuel types are live, following the NFMDB classification. Date-only live
    samples are placed at local noon; date-only dead samples at UTC midnight. No QC is applied.
    Existing conflicting groups are replaced only with ``overwrite=True``.
    """
    # Alias avoids shadowing datetime.timezone with the public keyword.
    from datetime import timezone as dt_timezone

    check_std_version(h5file)
    rows = read_rows(Path(csv_path))
    zone = ZoneInfo(timezone) if timezone else None
    for row in rows:
        original = row["date"]
        date_only = not isinstance(original, datetime)
        live = row["fuel_type"] not in FUEL_DATASETS
        if date_only and live and zone is None:
            fail(f"row {row['row_number']}: date-only live fuel requires --timezone")
        row["date_only"] = date_only
        row["assumed"] = date_only and live
        row["date"] = (
            datetime.combine(
                original, time(12) if live else time(), tzinfo=zone if live else dt_timezone.utc
            ).astimezone(dt_timezone.utc)
            if date_only
            else original
        )
    stations = validate_stations(rows)
    grouped = station_groups(rows)
    planned = []
    names = set()
    for stid, groups in grouped.items():
        for series in groups:
            name = group_name(stid, series, len(groups) > 1)
            if name in names:
                fail(f"group name collision: {name}")
            names.add(name)
            datasets = [
                dataset_name(str(r[0]["fuel_type"]), str(r[0]["fuel_variation"]), series) for _, r in series
            ]
            if len(set(datasets)) != len(datasets):
                fail(f"station {stid}: dataset name collision")
            path = f"time_series/{name}"
            if path in h5file and not overwrite:
                fail(f"group {path} already exists; use overwrite=True")
            planned.append((stid, path, series, datasets))
    source_hash = calculate_sha256(Path(csv_path))
    for stid, path, series, datasets in planned:
        if path in h5file:
            del h5file[path]
        group = h5file.create_group(path)
        group.attrs.update(stations[stid])
        group.attrs["source_data_hash"] = source_hash
        times = [r["date"] for r in series[0][1]]
        time_ds = group.create_dataset("time", data=[(t - times[0]).total_seconds() for t in times])
        time_ds.attrs.update(time_origin=times[0].isoformat(), time_units="s")
        for (_, records), name in zip(series, datasets):
            ds = group.create_dataset(
                name, data=[r["percent"] for r in records], **hdf5plugin.Zstd(clevel=3)
            )
            ds.attrs.update(
                units="percent",
                source_fuel_type=records[0]["fuel_type"],
                source_fuel_variation=records[0]["fuel_variation"],
                fuel_category="dead" if records[0]["fuel_type"] in FUEL_DATASETS else "live",
            )
            for suffix, key in (("date_only", "date_only"), ("time_assumed", "assumed")):
                group.create_dataset(
                    f"{name}_{suffix}", data=np.array([r[key] for r in records], dtype=bool)
                )
            if timezone:
                ds.attrs["source_timezone"] = timezone
    return [path for _, path, _, _ in planned]
