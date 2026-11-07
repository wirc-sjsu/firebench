"""
The event catalogue: many fire events in one standard file, under the root group `events`.

| Path | Content |
|---|---|
| `/events/table` | One row per event, sorted by `event_id`, fixed-length fields (`TABLE_DTYPE`) |
| `/events/final_perimeter` | Final perimeters, WKB in EPSG:4326, variable-length `uint8`, table order |
| `/events/structures/records` | Optional: one row per inspected structure (`STRUCTURE_DTYPE`) |
| `/events/structures/counts` | Optional: per-event counts by damage class (`COUNT_DTYPE`) |

Event IDs are opaque strings given by the caller (at most `EVENT_ID_LENGTH` bytes); FireBench never
makes one. Every field of the table is fixed-length so that the subject digest of the file, which
hashes a compound dataset by its raw bytes, covers its content. A missing text is an empty string
and a missing number NaN, never zero.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import shapely

from .building_damage import DAMAGE_SEVERITY
from .catalogues import TIME_PRECISIONS
from .files import new_std_file
from .tools import validate_h5_std

EVENTS = "events"
EVENT_ID_LENGTH = 40
DEFAULT_AREA_CRS = "EPSG:5070"
DEFAULT_MAX_IGNITION_DISTANCE_M = 5000.0

TABLE_DTYPE = np.dtype(
    [
        ("event_id", f"S{EVENT_ID_LENGTH}"),
        ("name", "S128"),
        ("state", "S8"),
        ("ignition_lat", "f8"),
        ("ignition_lon", "f8"),
        ("anchor_time", "S25"),
        ("anchor_precision", "S8"),
        ("discovery_time", "S25"),
        ("discovery_precision", "S8"),
        ("containment_time", "S25"),
        ("containment_precision", "S8"),
        ("final_area_m2", "f8"),
        ("cause", "S64"),
        ("source_ids", "S1024"),
    ]
)
STRUCTURE_DTYPE = np.dtype(
    [
        ("event_id", f"S{EVENT_ID_LENGTH}"),
        ("lat", "f8"),
        ("lon", "f8"),
        ("damage", "S32"),
        ("structure_type", "S64"),
    ]
)
DAMAGE_CLASSES = ("destroyed", "major", "minor", "affected", "inaccessible", "no_damage", "other")
COUNT_DTYPE = np.dtype([("event_id", f"S{EVENT_ID_LENGTH}")] + [(name, "i4") for name in DAMAGE_CLASSES])
_CLASS_OF_SEVERITY = {
    5: "destroyed",
    4: "major",
    3: "minor",
    2: "affected",
    1: "inaccessible",
    0: "no_damage",
}
_TIMES = (
    ("anchor_time", "anchor_precision"),
    ("discovery_time", "discovery_precision"),
    ("containment_time", "containment_precision"),
)
_TEXT_FIELDS = [name for name in TABLE_DTYPE.names if TABLE_DTYPE[name].kind == "S"]


@dataclass
class EventCatalogue:
    """What `read_event_catalogue` returns."""

    events: gpd.GeoDataFrame
    structures: pd.DataFrame | None = None
    structure_counts: pd.DataFrame | None = None
    attrs: dict = field(default_factory=dict)


def event_ids_sha256(event_ids) -> str:
    """The SHA-256 of a set of event IDs: of the sorted IDs joined by a line feed, in UTF-8."""
    return hashlib.sha256("\n".join(sorted(event_ids)).encode("utf-8")).hexdigest()


def damage_class(label: str) -> str:
    """The class of `DAMAGE_CLASSES` a DINS damage label counts in."""
    severity = DAMAGE_SEVERITY.get(str(label).strip())
    return _CLASS_OF_SEVERITY.get(severity, "other")


def _fixed(value, name: str, length: int) -> bytes:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return b""
    text = value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    encoded = text.strip().encode("utf-8")
    if len(encoded) > length:
        raise ValueError(f"`{name}` is longer than {length} bytes: `{text[:60]}`.")
    return encoded


def _canonical(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "{}"
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else {}
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _table(events: gpd.GeoDataFrame, area_crs: str) -> np.ndarray:
    areas = events["final_area_m2"] if "final_area_m2" in events else None
    if areas is None:
        areas = events.geometry.to_crs(area_crs).area.where(~events.geometry.is_empty)
    table = np.zeros(len(events), dtype=TABLE_DTYPE)
    for position, (_, row) in enumerate(events.iterrows()):
        record = table[position]
        for name in _TEXT_FIELDS:
            if name == "source_ids":
                value = _canonical(row.get("source_ids"))
            else:
                value = row.get(name, "")
            record[name] = _fixed(value, name, TABLE_DTYPE[name].itemsize)
        for name in ("ignition_lat", "ignition_lon"):
            record[name] = float(row.get(name, math.nan))
        area = areas.iloc[position]
        record["final_area_m2"] = float(area) if area is not None and not pd.isna(area) else math.nan
    return table


def _structure_tables(structures: pd.DataFrame, known: set[str]) -> tuple[np.ndarray, np.ndarray]:
    for column in ("event_id", "lat", "lon", "damage"):
        if column not in structures:
            raise ValueError(f"The structures have no column `{column}`.")
    unknown = sorted(set(structures["event_id"].astype(str)) - known)
    if unknown:
        raise ValueError(f"Structures name events the catalogue does not hold: {', '.join(unknown[:5])}.")
    ordered = structures.sort_values(["event_id", "lat", "lon"], kind="stable")
    records = np.zeros(len(ordered), dtype=STRUCTURE_DTYPE)
    for position, (_, row) in enumerate(ordered.iterrows()):
        records[position]["event_id"] = _fixed(row["event_id"], "event_id", EVENT_ID_LENGTH)
        records[position]["lat"] = float(row["lat"])
        records[position]["lon"] = float(row["lon"])
        records[position]["damage"] = _fixed(row["damage"], "damage", STRUCTURE_DTYPE["damage"].itemsize)
        records[position]["structure_type"] = _fixed(
            row.get("structure_type", ""), "structure_type", STRUCTURE_DTYPE["structure_type"].itemsize
        )
    classes = ordered.assign(damage_class=ordered["damage"].map(damage_class))
    per_event = classes.groupby(["event_id", "damage_class"]).size().unstack(fill_value=0)
    counts = np.zeros(len(per_event), dtype=COUNT_DTYPE)
    for position, (event, row) in enumerate(per_event.sort_index().iterrows()):
        counts[position]["event_id"] = _fixed(event, "event_id", EVENT_ID_LENGTH)
        for name in DAMAGE_CLASSES:
            counts[position][name] = int(row.get(name, 0))
    return records, counts


def _licence(group: h5py.Group, licence: str, redistribution_allowed: bool, data_source: str):
    group.attrs["license"] = licence
    group.attrs["redistribution_allowed"] = redistribution_allowed
    group.attrs["data_source"] = data_source


def write_event_catalogue(
    path: Path,
    events: gpd.GeoDataFrame,
    authors: str,
    license: str,  # pylint: disable=redefined-builtin
    data_source: str,
    structures: pd.DataFrame | None = None,
    structures_license: str | None = None,
    structures_data_source: str | None = None,
    area_crs: str = DEFAULT_AREA_CRS,
    redistribution_allowed: bool = True,
    attrs: dict | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Write an event catalogue as a new standard file.

    Parameters
    ----------
    path : Path
        The file to write.
    events : GeoDataFrame
        One row per event; its geometry is the event's final perimeter (any CRS, written in
        EPSG:4326). Required columns: `event_id`, `ignition_lat`, `ignition_lon`, `anchor_time`,
        `anchor_precision`. Optional: `name`, `state`, `discovery_time`, `discovery_precision`,
        `containment_time`, `containment_precision`, `cause`, `final_area_m2` (computed in
        `area_crs` when absent), `source_ids` (a dict or JSON text, written as canonical JSON).
        Times are ISO 8601 text (a date for precision `day`), precisions one of `TIME_PRECISIONS`.
    authors : str
        The `created_by` attribute of the file.
    license, data_source : str
        Licence and source of the events, written on the `events` group with
        `redistribution_allowed`.
    structures : DataFrame, optional
        Inspected structures (CAL FIRE DINS records): `event_id`, `lat`, `lon`, `damage` (a DINS
        label), and optionally `structure_type`. The counts per damage class are computed from them.
    structures_license, structures_data_source : str, optional
        Licence and source of the structures; required with `structures`.
    area_crs : str
        The equal-area projection of `final_area_m2`, written in the attribute `area_crs`.
    attrs : dict, optional
        Other attributes of the `events` group, such as the caller's ID scheme.
    overwrite : bool
        Replace an existing file.

    Returns
    -------
    Path
        The file, validated by `validate_event_catalogue`.
    """  # pylint: disable=line-too-long
    for column in ("event_id", "ignition_lat", "ignition_lon", "anchor_time", "anchor_precision"):
        if column not in events:
            raise ValueError(f"The events have no column `{column}`.")
    if events.crs is None:
        raise ValueError("The events' perimeters have no coordinate reference system.")
    if structures is not None and (not structures_license or not structures_data_source):
        raise ValueError("Structures need their own licence and data source.")
    duplicates = sorted(events["event_id"][events["event_id"].duplicated()].astype(str).unique())
    if duplicates:
        raise ValueError(f"Duplicate event IDs: {', '.join(duplicates[:5])}.")

    ordered = events.to_crs("EPSG:4326").sort_values("event_id", kind="stable").reset_index(drop=True)
    table = _table(ordered, area_crs)
    ids = [str(value) for value in ordered["event_id"]]
    wkb = [np.frombuffer(shapely.to_wkb(geometry), dtype=np.uint8) for geometry in ordered.geometry]

    with new_std_file(path, authors, overwrite=overwrite) as h5:
        group = h5.create_group(EVENTS)
        _licence(group, license, redistribution_allowed, data_source)
        group.attrs["n_events"] = len(ids)
        group.attrs["event_ids_sha256"] = event_ids_sha256(ids)
        for key, value in (attrs or {}).items():
            group.attrs[key] = value
        group.create_dataset("table", data=table)
        perimeters = group.create_dataset(
            "final_perimeter", shape=(len(wkb),), dtype=h5py.vlen_dtype(np.dtype("uint8"))
        )
        for position, value in enumerate(wkb):
            perimeters[position] = value
        perimeters.attrs["crs"] = "EPSG:4326"
        perimeters.attrs["encoding"] = "WKB"
        perimeters.attrs["area_crs"] = area_crs
        if structures is not None:
            records, counts = _structure_tables(structures, set(ids))
            sub = group.create_group("structures")
            _licence(sub, structures_license, redistribution_allowed, structures_data_source)
            sub.create_dataset("records", data=records)
            sub.create_dataset("counts", data=counts)
    validate_event_catalogue(path)
    return Path(path)


def _decode(array: np.ndarray, dtype: np.dtype) -> pd.DataFrame:
    frame = pd.DataFrame({name: array[name] for name in dtype.names})
    for name in dtype.names:
        if dtype[name].kind == "S":
            frame[name] = frame[name].map(lambda value: value.decode("utf-8"))
    return frame


def read_event_catalogue(path: Path) -> EventCatalogue:
    """
    Read an event catalogue. The events' geometry is their final perimeter in EPSG:4326 and
    `source_ids` is parsed from JSON. Raises `ValueError` if the file holds no catalogue.
    """
    with h5py.File(path, "r") as h5:
        if EVENTS not in h5 or "table" not in h5[EVENTS]:
            raise ValueError("The file holds no event catalogue (no `/events/table`).")
        group = h5[EVENTS]
        attrs = {key: _attr(value) for key, value in group.attrs.items()}
        table = _decode(group["table"][()], TABLE_DTYPE)
        geometries = [shapely.from_wkb(bytes(value)) for value in group["final_perimeter"][()]]
        structures = counts = None
        if "structures" in group:
            structures = _decode(group["structures/records"][()], STRUCTURE_DTYPE)
            counts = _decode(group["structures/counts"][()], COUNT_DTYPE)
            attrs["structures"] = {key: _attr(value) for key, value in group["structures"].attrs.items()}
        attrs["area_crs"] = _attr(group["final_perimeter"].attrs.get("area_crs", ""))
    table["source_ids"] = table["source_ids"].map(lambda text: json.loads(text) if text else {})
    events = gpd.GeoDataFrame(table, geometry=geometries, crs="EPSG:4326")
    return EventCatalogue(events=events, structures=structures, structure_counts=counts, attrs=attrs)


def _attr(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.generic):
        return value.item()
    return value


def _time_problems(event: str, row: pd.Series) -> list[str]:
    problems = []
    for time_name, precision_name in _TIMES:
        value, precision = row[time_name], row[precision_name]
        if not value and not precision:
            if time_name == "anchor_time":
                problems.append(f"Event `{event}` has no anchor time.")
            continue
        if precision not in TIME_PRECISIONS:
            problems.append(f"Event `{event}`: `{time_name}` has no precision (`{precision}`).")
            continue
        try:
            if precision == "day":
                date.fromisoformat(value)
            elif not value.endswith("Z"):
                raise ValueError(value)
            else:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            problems.append(f"Event `{event}`: `{time_name}` is not a {precision} time (`{value}`).")
    return problems


def _file_problems(path: Path) -> list[str]:
    """Problems of the file's layout. Raises when the catalogue cannot be read at all."""
    problems = []
    with h5py.File(path, "r") as h5:
        validate_h5_std(h5)
        if EVENTS not in h5:
            raise ValueError("The file holds no event catalogue (no `/events`).")
        group = h5[EVENTS]
        for name in [EVENTS] + ([f"{EVENTS}/structures"] if "structures" in group else []):
            for key in ("license", "redistribution_allowed", "data_source"):
                if key not in h5[name].attrs:
                    problems.append(f"`/{name}` has no `{key}` attribute.")
        if "table" not in group or "final_perimeter" not in group:
            raise ValueError("The event catalogue needs `/events/table` and `/events/final_perimeter`.")
        n_rows, n_perimeters = len(group["table"]), len(group["final_perimeter"])
        if n_rows != n_perimeters:
            raise ValueError(f"The table has {n_rows} events but there are {n_perimeters} perimeters.")
        if group.attrs.get("n_events") != n_rows:
            problems.append(f"`n_events` is {group.attrs.get('n_events')}, the table has {n_rows} events.")
    return problems


def _id_problems(catalogue: EventCatalogue) -> list[str]:
    events = catalogue.events
    ids = list(events["event_id"])
    problems = []
    if catalogue.attrs.get("event_ids_sha256") != event_ids_sha256(ids):
        problems.append("`event_ids_sha256` does not match the table's IDs.")
    if any(not value for value in ids):
        problems.append("An event has an empty ID.")
    duplicates = sorted(events["event_id"][events["event_id"].duplicated()].unique())
    if duplicates:
        problems.append(f"Duplicate event IDs: {', '.join(duplicates[:5])}.")
    elif ids != sorted(ids):
        problems.append("The table is not sorted by event ID.")
    if catalogue.structures is not None:
        unknown = sorted(set(catalogue.structures["event_id"]) - set(ids))
        if unknown:
            problems.append(
                f"Structures name events the catalogue does not hold: {', '.join(unknown[:5])}."
            )
    return problems


def _geometry_problem(event: str, geometry) -> str | None:
    if geometry is None or geometry.is_empty:
        return f"Event `{event}` has an empty perimeter."
    if geometry.geom_type not in ("Polygon", "MultiPolygon"):
        return f"Event `{event}`: the perimeter is a {geometry.geom_type}, not a polygon."
    if not geometry.is_valid:
        return f"Event `{event}` has an invalid perimeter ({shapely.is_valid_reason(geometry)})."
    return None


def validate_event_catalogue(
    path: Path, max_ignition_distance_m: float = DEFAULT_MAX_IGNITION_DISTANCE_M
) -> list[str]:
    """
    Check an event catalogue.

    Refuses (`ValueError`, every problem listed): a file that is not a standard file; duplicate,
    empty, or unsorted IDs; counts or hashes that disagree with the table; an empty, invalid, or
    non-polygonal perimeter; a time without a valid precision; an event without an anchor time or
    ignition point; a group without its licence attributes; structures of unknown events.

    Returns warnings: an ignition point farther than `max_ignition_distance_m` outside its perimeter.
    """
    problems = _file_problems(path)
    catalogue = read_event_catalogue(path)
    problems.extend(_id_problems(catalogue))

    events = catalogue.events
    area_crs = catalogue.attrs.get("area_crs") or DEFAULT_AREA_CRS
    ignitions = gpd.GeoSeries(
        gpd.points_from_xy(events["ignition_lon"], events["ignition_lat"]), crs="EPSG:4326"
    ).to_crs(area_crs)
    distances = events.geometry.to_crs(area_crs).distance(ignitions, align=False)
    warnings = []
    for position, row in events.iterrows():
        event = row["event_id"]
        problems.extend(_time_problems(event, row))
        geometry_problem = _geometry_problem(event, row.geometry)
        if geometry_problem:
            problems.append(geometry_problem)
        if not (math.isfinite(row["ignition_lat"]) and math.isfinite(row["ignition_lon"])):
            problems.append(f"Event `{event}` has no ignition point.")
        elif not geometry_problem and distances.iloc[position] > max_ignition_distance_m:
            distance = distances.iloc[position]
            warnings.append(
                f"Event `{event}`: the ignition point is {distance:.0f} m outside its perimeter."
            )
    if problems:
        raise ValueError(" ".join(problems))
    return warnings
