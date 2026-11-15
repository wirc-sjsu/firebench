"""
The per-event template of an event catalogue: what an adapter reads to run a model on one fire.

``write_event_template`` writes, for one event of the catalogue, a standard file marked by the root
attribute ``firebench_template = "catalogue_event"`` (a bundle refuses one submitted unchanged), with:

- ``/event``: the ignition point, the anchor time and its precision, the box (a square around the
  ignition point, never from the observed perimeter), and the window (from the anchor time to the
  containment time, or ``default_window_days`` later when the catalogue has none);
- ``/polygons/final_perimeter``: a group whose ``time`` is the window's end and that holds no file
  reference and no geometry: the model writes its KML file, ``rel_path``, ``file_size_bytes`` and
  ``sha256`` there;
- ``/points/building_damaged``: when the catalogue has structures for the event, their positions in
  the catalogue's order and a blank damage, but ``Inaccessible``, in ``building_damage``: the model
  writes one DINS damage label per structure.

A kit holds no observed value but the containment time (deviation 70 of the site). Licence attributes
of the catalogue are on each group.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pyproj

from .. import __version__ as fb_version
from .. import standardize as fs
from ..standardize.event_catalogue import EventCatalogue, damage_class, read_event_catalogue
from .catalogue_case import SCHEMA
from .catalogue_parameters import load_parameters
from .catalogue_scoring import BUILDING_DAMAGE_PATH, FINAL_PERIMETER_PATH
from .fire_case_definition import TEMPLATE_ATTRIBUTE, canonical_json, definition_sha256, iso_utc

TEMPLATE_KIND = "catalogue_event"
EVENT_GROUP = "/event"


def _time(text: str, precision: str, end_of_day: bool = False) -> datetime:
    """A time of the catalogue (UTC); a date is the start of its UTC day, or its end."""
    if precision == "day":
        start = datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc)
        return start + timedelta(days=1) if end_of_day else start
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _box(lat: float, lon: float, half_width_km: float) -> tuple[float, float, float, float]:
    """West, south, east, north of the square of half width ``half_width_km`` around a point."""
    geod = pyproj.Geod(ellps="WGS84")
    distance = half_width_km * 1000.0
    west, _, _ = geod.fwd(lon, lat, 270.0, distance)
    east, _, _ = geod.fwd(lon, lat, 90.0, distance)
    _, north, _ = geod.fwd(lon, lat, 0.0, distance)
    _, south, _ = geod.fwd(lon, lat, 180.0, distance)
    return float(west), float(south), float(east), float(north)


def _licence(group, attrs: dict) -> None:
    for key in ("license", "redistribution_allowed", "data_source"):
        if key in attrs:
            group.attrs[key] = attrs[key]


def _write_template(  # pylint: disable=too-many-locals
    catalogue: EventCatalogue, event_id: str, path, definition: dict | None, window_days, overwrite: bool
) -> Path:
    parameters = load_parameters()
    window_days = parameters.template.default_window_days if window_days is None else window_days
    if not window_days > 0:
        raise ValueError("`window_days` must be above 0.")
    rows = catalogue.events[catalogue.events["event_id"] == event_id]
    if rows.empty:
        raise ValueError(f"The catalogue does not hold the event `{event_id}`.")
    row = rows.iloc[0]
    if definition is not None and definition.get("schema") != SCHEMA:
        raise ValueError(f"The definition is not a `{SCHEMA}` document.")

    start = _time(row["anchor_time"], row["anchor_precision"])
    end = start + timedelta(days=window_days)
    if row["containment_time"]:
        containment = _time(row["containment_time"], row["containment_precision"], end_of_day=True)
        if containment > start:
            end = containment
    box = _box(
        float(row["ignition_lat"]), float(row["ignition_lon"]), parameters.template.box_half_width_km
    )
    licence = {key: catalogue.attrs[key] for key in ("license", "redistribution_allowed", "data_source")}

    out = fs.new_std_file(Path(path), authors=f"FireBench {fb_version}", overwrite=overwrite)
    try:
        out.attrs[TEMPLATE_ATTRIBUTE] = TEMPLATE_KIND
        out.attrs["description"] = f"Model-output template of the event {event_id} of an event catalogue."
        out.attrs["event_id"] = event_id
        if definition is not None:
            out.attrs["catalogue_case_sha256"] = definition_sha256(definition)
            out.attrs["catalogue_case_definition"] = canonical_json(definition).decode("utf-8")
        event = out.create_group(EVENT_GROUP)
        _licence(event, licence)
        event.attrs["event_id"] = event_id
        event.attrs["ignition_lat"] = float(row["ignition_lat"])
        event.attrs["ignition_lon"] = float(row["ignition_lon"])
        event.attrs["anchor_time"] = row["anchor_time"]
        event.attrs["anchor_precision"] = row["anchor_precision"]
        if row["containment_time"]:
            event.attrs["containment_time"] = row["containment_time"]
            event.attrs["containment_precision"] = row["containment_precision"]
        for name, value in zip(("box_west", "box_south", "box_east", "box_north"), box):
            event.attrs[name] = value
        event.attrs["box_units"] = "degree"
        event.attrs["window_start"] = iso_utc(start)
        event.attrs["window_end"] = iso_utc(end)
        perimeter = out.create_group(FINAL_PERIMETER_PATH)
        _licence(perimeter, licence)
        perimeter.attrs["time"] = iso_utc(end)
        _write_structures(out, catalogue, event_id)
    finally:
        out.close()
    return Path(path)


def _write_structures(out, catalogue: EventCatalogue, event_id: str) -> None:
    if catalogue.structures is None:
        return
    records = catalogue.structures[catalogue.structures["event_id"] == event_id]
    if records.empty:
        return
    group = out.create_group(BUILDING_DAMAGE_PATH.rsplit("/", 1)[0])
    _licence(group, catalogue.attrs["structures"])
    for name, column in (("position_lat", "lat"), ("position_lon", "lon")):
        group.create_dataset(name, data=records[column].to_numpy(dtype=float)).attrs["units"] = "degree"
    # Whether a structure was surveyed is not what happened to it: "Inaccessible" stays.
    blank = [label if damage_class(label) == "inaccessible" else "" for label in records["damage"]]
    group.create_dataset("building_damage", data=np.array(blank, dtype="S16")).attrs["units"] = (
        "dimensionless"
    )


def write_event_template(
    catalogue_path, event_id: str, path, definition: dict | None = None, window_days=None, overwrite=False
) -> Path:
    """
    Write the template of the event ``event_id`` of the catalogue at ``catalogue_path`` to ``path``.

    ``definition`` (an ``fb-catalogue-case-v1`` document) is recorded in the file with its hash;
    ``window_days`` replaces ``default_window_days`` of the parameters when the catalogue has no
    containment time. Raises ``ValueError`` for an event the catalogue does not hold, and
    ``FileExistsError`` for an existing file without ``overwrite``.
    """
    return _write_template(
        read_event_catalogue(catalogue_path), event_id, path, definition, window_days, overwrite
    )


def write_event_templates(
    catalogue_path,
    out_dir,
    event_ids=None,
    definition: dict | None = None,
    window_days=None,
    overwrite=False,
) -> list[Path]:
    """The templates of ``event_ids`` (all by default), each at ``<out_dir>/<event_id>/template.h5``."""
    catalogue = read_event_catalogue(catalogue_path)
    known = set(catalogue.events["event_id"])
    ids = sorted(known) if event_ids is None else list(event_ids)
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ValueError(f"The catalogue does not hold the events: {', '.join(unknown[:5])}.")
    unsafe = [event for event in ids if "/" in event or "\\" in event or event.startswith(".")]
    if unsafe:
        raise ValueError(f"The event IDs cannot name a directory: {', '.join(unsafe[:5])}.")
    return [
        _write_template(
            catalogue, event, Path(out_dir) / event / "template.h5", definition, window_days, overwrite
        )
        for event in ids
    ]
