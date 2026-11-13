"""
Readers of the sources of a fire event catalogue: MTBS burned area boundaries, the FPA FOD wildfire
records, and the WFIGS interagency perimeters.

Each reader only reads: it returns one row per source record, in EPSG:4326, with documented
columns, and filters by state, year, smallest area, and box. Joining the sources, and naming the
events, is the caller's job.

Times
-----
A time is given with its precision in a column beside it (`<name>_precision`), one of
`TIME_PRECISIONS`:

- a date-only time stays a date, `YYYY-MM-DD`, with precision `day`. It is the calendar day as the
  source records it: local for MTBS and FPA FOD;
- any other time is ISO 8601 in UTC ending in `Z`. FPA FOD's local times are converted with the
  time zone of the fire's state (`STATE_TIME_ZONES`), which is named in `time_zone`;
- a missing time is an empty string with an empty precision, never a guessed value.
"""

import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

TIME_PRECISIONS = ("day", "hour", "minute", "second")
ACRE_M2 = 4046.8564224

# The time zone of most of each state's land. A state that spans two zones gets the one most of its
# fires burn in; the reader names the zone it used in a column, so a caller can correct it.
STATE_TIME_ZONES = {
    "AL": "America/Chicago",
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DE": "America/New_York",
    "DC": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "MT": "America/Denver",
    "NE": "America/Chicago",
    "NV": "America/Los_Angeles",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "PR": "America/Puerto_Rico",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WA": "America/Los_Angeles",
    "WV": "America/New_York",
    "WI": "America/Chicago",
    "WY": "America/Denver",
}

MTBS_COLUMNS = [
    "mtbs_id",
    "name",
    "type",
    "state",
    "year",
    "ignition_date",
    "ignition_date_precision",
    "ignition_lat",
    "ignition_lon",
    "centroid_lat",
    "centroid_lon",
    "area_acres",
    "irwin_id",
    "geometry",
]
# An MTBS event ID: state, the ignition latitude and west longitude in thousandths of a degree, date.
_MTBS_ID = re.compile(r"^[A-Z]{2}(\d{5})(\d{6})\d{8}$")
FOD_COLUMNS = [
    "fod_id",
    "mtbs_id",
    "irwin_id",
    "name",
    "state",
    "year",
    "time_zone",
    "discovery_time",
    "discovery_time_precision",
    "containment_time",
    "containment_time_precision",
    "cause",
    "area_acres",
    "discovery_lat",
    "discovery_lon",
    "geometry",
]
WFIGS_COLUMNS = [
    "irwin_id",
    "unique_fire_id",
    "name",
    "state",
    "year",
    "discovery_time",
    "discovery_time_precision",
    "origin_lat",
    "origin_lon",
    "area_acres",
    "geometry",
]

_UUID = re.compile(r"^\{?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\}?$")
# Day 0 of the Julian dates of FPA FOD up to its 5th edition.
_JULIAN_EPOCH = 2440587.5


def _pick(frame: pd.DataFrame, source: str, *names: str, required: bool = True) -> str | None:
    """The first of `names` that is a column of `frame`, ignoring case."""
    columns = {str(column).casefold(): column for column in frame.columns}
    for name in names:
        if name.casefold() in columns:
            return columns[name.casefold()]
    if required:
        raise ValueError(f"The {source} table has no column {' or '.join(f'`{name}`' for name in names)}.")
    return None


def _text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return ""
    return str(value).strip()


def _number(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _irwin(value) -> str:
    """An IRWIN ID as a plain lower-case UUID, or an empty string."""
    match = _UUID.match(_text(value))
    return match.group(1).lower() if match else ""


def _date(value) -> date | None:
    """A calendar date from what a source writes: a date, a timestamp, text, or a Julian day number."""
    if isinstance(value, datetime):
        return None if value is pd.NaT else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        # A Julian day number (FPA FOD up to its 5th edition); any other number is no date.
        if math.isfinite(number) and number > 1e6:
            return (datetime(1970, 1, 1) + timedelta(days=number - _JULIAN_EPOCH)).date()
        return None
    text = _text(value).split(" ", maxsplit=1)[0].split("T", maxsplit=1)[0]
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y%m%d") if text else ():
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    if text:
        raise ValueError(f"`{text}` is not a date.")
    return None


def _hhmm(value) -> tuple[int, int] | None:
    """A local time of day written `HHMM` (FPA FOD), or None when absent."""
    text = _text(value)
    if not text:
        return None
    text = text.split(".", maxsplit=1)[0].zfill(4)
    if not text.isdigit() or len(text) != 4:
        return None
    hour, minute = int(text[:2]), int(text[2:])
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_time(day: date | None, clock: tuple[int, int] | None, zone: str) -> tuple[str, str]:
    """A local date and time of day as (time, precision): UTC to the minute, or the date alone."""
    if day is None:
        return "", ""
    if clock is None or not zone:
        return day.isoformat(), "day"
    local = datetime(day.year, day.month, day.day, clock[0], clock[1], tzinfo=ZoneInfo(zone))
    return _iso_utc(local), "minute"


def _utc_time(value) -> tuple[str, str]:
    """A UTC time from an ArcGIS field (epoch milliseconds or ISO text) as (time, precision)."""
    if value is None or value is pd.NaT or _text(value) == "":
        return "", ""
    if isinstance(value, (int, float, np.integer, np.floating)):
        moment = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    elif isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        text = _text(value).replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            # The GeoJSON export of an ArcGIS service writes RFC 1123: `Wed, 18 Mar 2026 12:06:00 GMT`.
            try:
                moment = parsedate_to_datetime(_text(value))
            except (TypeError, ValueError) as error:
                raise ValueError(f"`{value}` is not a time.") from error
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    precision = "minute" if moment.second == 0 and moment.microsecond == 0 else "second"
    return _iso_utc(moment), precision


def _filter(
    frame: gpd.GeoDataFrame,
    states: list[str] | None,
    years: tuple[int, int] | None,
    min_acres: float | None,
    bbox: tuple[float, float, float, float] | None,
) -> gpd.GeoDataFrame:
    """Keep the rows in `states`, in the years `years` (first and last, included), at least
    `min_acres` large, and whose geometry meets `bbox` (west, south, east, north)."""
    keep = np.ones(len(frame), dtype=bool)
    if states:
        keep &= frame["state"].isin([state.upper() for state in states]).to_numpy()
    if years is not None:
        first, last = years
        keep &= frame["year"].between(first, last).to_numpy()
    if min_acres is not None:
        keep &= (frame["area_acres"] >= min_acres).to_numpy()
    if bbox is not None:
        keep &= frame.geometry.intersects(box(*bbox)).to_numpy()
    return frame[keep].reset_index(drop=True)


def mtbs_ignition_point(mtbs_id: str) -> tuple[float, float]:
    """The ignition point an MTBS event ID holds, as (lat, lon) to 0.001 degree; NaN when it holds none."""
    match = _MTBS_ID.match(mtbs_id.strip().upper())
    if match is None:
        return math.nan, math.nan
    return int(match.group(1)) / 1000.0, -int(match.group(2)) / 1000.0


def read_mtbs_boundaries(
    path: Path,
    states: list[str] | None = None,
    years: tuple[int, int] | None = None,
    min_acres: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    incident_types: tuple[str, ...] | None = ("Wildfire",),
) -> gpd.GeoDataFrame:
    """
    Read the MTBS burned area boundaries (`mtbs_perims_DD.shp`, or any format GeoPandas reads).

    Parameters
    ----------
    path : Path
        The boundaries. Columns used: `Event_ID`, `Incid_Name`, `Incid_Type`, `Ig_Date`,
        `BurnBndAc`, `BurnBndLat`, `BurnBndLon`, and `irwinID` when present.
    states : list of str, optional
        Two-letter states to keep. An MTBS event's state is the first two letters of its ID.
    years : (int, int), optional
        First and last ignition year to keep.
    min_acres : float, optional
        Smallest burned area to keep, in acres.
    bbox : (west, south, east, north), optional
        Keep the boundaries that meet this box, in degrees.
    incident_types : tuple of str, optional
        `Incid_Type` values to keep (`Wildfire` by default; None keeps all, prescribed fires too).

    Returns
    -------
    GeoDataFrame
        In EPSG:4326, sorted by `mtbs_id`, with the columns of `MTBS_COLUMNS`. The ignition date
        is a date (`ignition_date_precision` is `day`), as MTBS records no time; the ignition
        point is the one the event ID holds (`mtbs_ignition_point`), to 0.001 degree: the source
        fire occurrence record's. `centroid_lat` and `centroid_lon` are `BurnBndLat` and
        `BurnBndLon`, the centroid of the perimeter, which is not where the fire started.

    Raises
    ------
    ValueError
        If the file cannot be read or a column is missing.
    """  # pylint: disable=line-too-long
    try:
        raw = gpd.read_file(path)
    except Exception as error:  # pylint: disable=broad-exception-caught
        raise ValueError(f"The MTBS boundaries cannot be read: {error}") from error
    if raw.crs is None:
        raise ValueError("The MTBS boundaries have no coordinate reference system.")
    raw = raw.to_crs("EPSG:4326")
    names = {
        "event": _pick(raw, "MTBS", "Event_ID"),
        "name": _pick(raw, "MTBS", "Incid_Name"),
        "type": _pick(raw, "MTBS", "Incid_Type"),
        "ignition": _pick(raw, "MTBS", "Ig_Date"),
        "lat": _pick(raw, "MTBS", "BurnBndLat"),
        "lon": _pick(raw, "MTBS", "BurnBndLon"),
        "area_acres": _pick(raw, "MTBS", "BurnBndAc"),
        "irwin_id": _pick(raw, "MTBS", "irwinID", "IRWIN_ID", required=False),
    }

    rows = []
    for row in raw.to_dict("records"):
        mtbs_id = _text(row[names["event"]])
        day = _date(row[names["ignition"]])
        point = mtbs_ignition_point(mtbs_id)
        rows.append(
            {
                "mtbs_id": mtbs_id,
                "name": _text(row[names["name"]]),
                "type": _text(row[names["type"]]),
                "state": mtbs_id[:2].upper(),
                "year": day.year if day else -1,
                "ignition_date": day.isoformat() if day else "",
                "ignition_date_precision": "day" if day else "",
                "ignition_lat": point[0],
                "ignition_lon": point[1],
                "centroid_lat": _number(row[names["lat"]]),
                "centroid_lon": _number(row[names["lon"]]),
                "area_acres": _number(row[names["area_acres"]]),
                "irwin_id": _irwin(row[names["irwin_id"]]) if names["irwin_id"] else "",
                "geometry": row["geometry"],
            }
        )
    frame = gpd.GeoDataFrame(rows, columns=MTBS_COLUMNS, geometry="geometry", crs="EPSG:4326")
    if incident_types is not None:
        frame = frame[frame["type"].isin(incident_types)]
    frame = _filter(frame, states, years, min_acres, bbox)
    return frame.sort_values("mtbs_id", kind="stable").reset_index(drop=True)


def read_fpa_fod(
    path: Path,
    states: list[str] | None = None,
    years: tuple[int, int] | None = None,
    min_acres: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    mtbs_only: bool = False,
) -> gpd.GeoDataFrame:
    """
    Read the FPA FOD wildfire records (Short, 6th edition, SQLite table `Fires`).

    Parameters
    ----------
    path : Path
        The SQLite database. Columns used: `FOD_ID`, `MTBS_ID`, `FIRE_NAME`, `STATE`, `FIRE_YEAR`,
        `DISCOVERY_DATE`, `DISCOVERY_TIME`, `CONT_DATE`, `CONT_TIME`, `NWCG_GENERAL_CAUSE` (or
        `STAT_CAUSE_DESCR`), `FIRE_SIZE`, `LATITUDE`, `LONGITUDE`, and an IRWIN ID column
        (`IRWIN_ID`, `IRWINID`) when present. A date may be text or a Julian day number.
    states, years, min_acres, bbox
        As for `read_mtbs_boundaries`; the box is met by the discovery point.
    mtbs_only : bool
        Keep only the records with an MTBS ID.

    Returns
    -------
    GeoDataFrame
        In EPSG:4326 (discovery points), sorted by `fod_id`, with the columns of `FOD_COLUMNS`.
        Discovery and containment times are UTC to the minute when the record has a time of day,
        converted from the local time of the state's zone (`time_zone`); otherwise the local date.

    Raises
    ------
    ValueError
        If the database cannot be read or a column is missing.
    """  # pylint: disable=line-too-long
    try:
        with sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True) as connection:
            raw = pd.read_sql_query("SELECT * FROM Fires", connection)
    except Exception as error:  # pylint: disable=broad-exception-caught
        raise ValueError(f"The FPA FOD database cannot be read: {error}") from error
    names = {
        "fod_id": _pick(raw, "FPA FOD", "FOD_ID"),
        "mtbs_id": _pick(raw, "FPA FOD", "MTBS_ID", required=False),
        "irwin_id": _pick(raw, "FPA FOD", "IRWIN_ID", "IRWINID", required=False),
        "name": _pick(raw, "FPA FOD", "FIRE_NAME"),
        "state": _pick(raw, "FPA FOD", "STATE"),
        "year": _pick(raw, "FPA FOD", "FIRE_YEAR"),
        "discovery_date": _pick(raw, "FPA FOD", "DISCOVERY_DATE"),
        "discovery_clock": _pick(raw, "FPA FOD", "DISCOVERY_TIME", required=False),
        "containment_date": _pick(raw, "FPA FOD", "CONT_DATE", required=False),
        "containment_clock": _pick(raw, "FPA FOD", "CONT_TIME", required=False),
        "cause": _pick(raw, "FPA FOD", "NWCG_GENERAL_CAUSE", "STAT_CAUSE_DESCR", required=False),
        "area_acres": _pick(raw, "FPA FOD", "FIRE_SIZE"),
        "lat": _pick(raw, "FPA FOD", "LATITUDE"),
        "lon": _pick(raw, "FPA FOD", "LONGITUDE"),
    }

    def column(key: str, row: dict):
        return row[names[key]] if names[key] is not None else None

    rows = []
    for row in raw.to_dict("records"):
        state = _text(column("state", row)).upper()
        zone = STATE_TIME_ZONES.get(state, "")
        discovery = _local_time(
            _date(column("discovery_date", row)), _hhmm(column("discovery_clock", row)), zone
        )
        containment = _local_time(
            _date(column("containment_date", row)), _hhmm(column("containment_clock", row)), zone
        )
        lat, lon = _number(column("lat", row)), _number(column("lon", row))
        year = _number(column("year", row))
        rows.append(
            {
                "fod_id": _text(column("fod_id", row)),
                "mtbs_id": _text(column("mtbs_id", row)),
                "irwin_id": _irwin(column("irwin_id", row)),
                "name": _text(column("name", row)),
                "state": state,
                "year": int(year) if math.isfinite(year) else -1,
                "time_zone": zone,
                "discovery_time": discovery[0],
                "discovery_time_precision": discovery[1],
                "containment_time": containment[0],
                "containment_time_precision": containment[1],
                "cause": _text(column("cause", row)),
                "area_acres": _number(column("area_acres", row)),
                "discovery_lat": lat,
                "discovery_lon": lon,
                "geometry": Point(lon, lat) if math.isfinite(lat) and math.isfinite(lon) else None,
            }
        )
    frame = gpd.GeoDataFrame(rows, columns=FOD_COLUMNS, geometry="geometry", crs="EPSG:4326")
    if mtbs_only:
        frame = frame[frame["mtbs_id"] != ""]
    frame = _filter(frame, states, years, min_acres, bbox)
    return frame.sort_values("fod_id", kind="stable").reset_index(drop=True)


def read_wfigs_perimeters(
    path: Path,
    states: list[str] | None = None,
    years: tuple[int, int] | None = None,
    min_acres: float | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """
    Read the WFIGS interagency perimeters (GeoJSON of the NIFC layer, perimeter and incident fields).

    Parameters
    ----------
    path : Path
        The perimeters. Columns used: `poly_IRWINID` (or `attr_IrwinID`), `attr_UniqueFireIdentifier`,
        `poly_IncidentName` (or `attr_IncidentName`), `attr_POOState`, `attr_FireDiscoveryDateTime`,
        `attr_InitialLatitude`, `attr_InitialLongitude`, `poly_GISAcres`.
    states, years, min_acres, bbox
        As for `read_mtbs_boundaries`; the year is the discovery's.

    Returns
    -------
    GeoDataFrame
        In EPSG:4326, sorted by `irwin_id`, with the columns of `WFIGS_COLUMNS`. A perimeter without
        an IRWIN ID is left out. The discovery time is UTC, as the layer stores it.

    Raises
    ------
    ValueError
        If the file cannot be read or a column is missing.
    """  # pylint: disable=line-too-long
    try:
        raw = gpd.read_file(path)
    except Exception as error:  # pylint: disable=broad-exception-caught
        raise ValueError(f"The WFIGS perimeters cannot be read: {error}") from error
    raw = raw.set_crs("EPSG:4326") if raw.crs is None else raw.to_crs("EPSG:4326")
    names = {
        "irwin_id": _pick(raw, "WFIGS", "poly_IRWINID", "attr_IrwinID"),
        "unique_fire_id": _pick(raw, "WFIGS", "attr_UniqueFireIdentifier", required=False),
        "name": _pick(raw, "WFIGS", "poly_IncidentName", "attr_IncidentName"),
        "state": _pick(raw, "WFIGS", "attr_POOState", required=False),
        "discovery": _pick(raw, "WFIGS", "attr_FireDiscoveryDateTime"),
        "lat": _pick(raw, "WFIGS", "attr_InitialLatitude", required=False),
        "lon": _pick(raw, "WFIGS", "attr_InitialLongitude", required=False),
        "area_acres": _pick(raw, "WFIGS", "poly_GISAcres", "attr_IncidentSize"),
    }

    rows = []
    for row in raw.to_dict("records"):
        irwin = _irwin(row[names["irwin_id"]])
        if not irwin:
            continue
        discovery = _utc_time(row[names["discovery"]])
        state = _text(row[names["state"]]) if names["state"] else ""
        rows.append(
            {
                "irwin_id": irwin,
                "unique_fire_id": _text(row[names["unique_fire_id"]]) if names["unique_fire_id"] else "",
                "name": _text(row[names["name"]]),
                "state": state.rsplit("-", maxsplit=1)[-1].upper(),
                "year": int(discovery[0][:4]) if discovery[0] else -1,
                "discovery_time": discovery[0],
                "discovery_time_precision": discovery[1],
                "origin_lat": _number(row[names["lat"]]) if names["lat"] else math.nan,
                "origin_lon": _number(row[names["lon"]]) if names["lon"] else math.nan,
                "area_acres": _number(row[names["area_acres"]]),
                "geometry": row["geometry"],
            }
        )
    frame = gpd.GeoDataFrame(rows, columns=WFIGS_COLUMNS, geometry="geometry", crs="EPSG:4326")
    frame = _filter(frame, states, years, min_acres, bbox)
    return frame.sort_values("irwin_id", kind="stable").reset_index(drop=True)
