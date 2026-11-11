"""
Forecast windows: what a model output must hold before the observations exist (schema ``fb-window-v1``).

A benchmark case (``fire_case_definition``) is proposed from a finished observation file and checked
against it. A forecast window is the reverse: the definition exists first, the model output second,
and the observations arrive afterwards. A window definition says, from itself alone, what a model
gives: one period, the frame it is scored on, and per family the fields and the times asked.

- ``propose_window`` proposes a definition, with the stations of the observation files known so far;
- ``check_window`` lists the problems of a definition;
- ``check_model_for_window`` reports which families of a window a model output can enter;
- ``write_window_template`` writes the layout a model output is written on;
- ``write_window_definition`` and ``read_window_definition`` keep the definition inside a file.

Two families so far. ``fire_arrival_time``: the fire's arrival time on the model's own grid, scored
against satellite detections and perimeters. ``weather_stations``: station series at a fixed cadence,
on round times, so that they can be brought to observation times nobody knows yet.

Nothing is scored here, and no observed value is read: only the names, positions, variables, and
sensor heights of the stations. Like a case definition, a window names its parameters by reference
to ``fire_case.toml`` and its canonical JSON is hashed with SHA-256.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pint

from .. import __version__ as fb_version
from .. import standardize as fs
from ..tools.units import ureg
from .fire_case_definition import (
    STATION_PREFIX,
    TEMPLATE_ATTRIBUTE,
    CaseDefinitionError,
    canonical_json,
    definition_sha256,
    iso_utc,
    parse_time,
)
from .fire_case_parameters import (
    FireCaseParameterError,
    FireCaseParameters,
    load_parameters,
    parameters_for,
)
from .fire_case_template import _firebench_commit

SCHEMA = "fb-window-v1"
CHECK_SCHEMA = "fb-window-check-v1"
DEFINITION_PATH = "/benchmark_window/definition"
TEMPLATE_KIND = "window-model-output"
ARRIVAL = "fire_arrival_time"
STATIONS = "weather_stations"
FAMILIES = (ARRIVAL, STATIONS)
FAMILY_LABELS = {ARRIVAL: "Fire arrival time", STATIONS: "Weather at stations"}
FAMILY_KEYS = {
    ARRIVAL: {"family", "model_group"},
    STATIONS: {"family", "cadence_minutes", "stations"},
}
STATION_KEYS = {"station", "lat", "lon", "variables", "sensor_heights"}
# Where a model writes its arrival time when the definition is proposed here.
ARRIVAL_GROUP = f"/{fs.SPATIAL_2D}/fire_window"
ARRIVAL_DATASETS = ("time", "position_lat", "position_lon", ARRIVAL)
FRAME_KEYS = ("frame_west", "frame_south", "frame_east", "frame_north")
DEFAULT_CADENCE_MINUTES = 60
# How far a model time may be from a time of the grid and still be it.
TIME_TOLERANCE_SECONDS = 1.0
ELIGIBLE, PARTIAL, UNAVAILABLE = "eligible", "partial", "unavailable"
NOT_HDF5 = "The file is not a readable HDF5 file."
EMPTY_TEMPLATE = "This file is a window template: it holds no model value."


# ---------------------------
# The document
# ---------------------------
def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _frame_problem(frame, label: str) -> str | None:
    if not isinstance(frame, list) or len(frame) != 4 or not all(_is_number(edge) for edge in frame):
        return f"`{label}` must be four numbers: west, south, east, north."
    west, south, east, north = frame
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return f"`{label}` is not a box in degrees: west, south, east, north."
    return None


def _inside(inner, outer) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def window_period(definition: dict) -> tuple[datetime, datetime]:
    """The period of a window. The definition must have been checked."""
    return parse_time(definition["period"]["start"]), parse_time(definition["period"]["end"])


def family(definition: dict, name: str) -> dict | None:
    """The entry of a family in a window definition, or None."""
    return next((item for item in definition.get("families", []) if item.get("family") == name), None)


def window_times(definition: dict) -> list[datetime]:
    """
    The times a station series of the window must hold: every round edge of the cadence (counted
    from 00:00 UTC), from the last one at or before the start to the first one at or after the end,
    so that the series can be interpolated to any time of the period.
    """
    entry = family(definition, STATIONS)
    if entry is None:
        return []
    start, end = window_period(definition)
    step = entry["cadence_minutes"] * 60
    first = math.floor(start.timestamp() / step) * step
    last = math.ceil(end.timestamp() / step) * step
    return [datetime.fromtimestamp(stamp, timezone.utc) for stamp in range(first, last + step, step)]


def _check_station(item, index: int, variables: set[str]) -> list[str]:
    where = f"Station {index + 1} of `{STATIONS}`"
    if not isinstance(item, dict) or set(item) != STATION_KEYS:
        return [f"{where} must have exactly the keys {', '.join(sorted(STATION_KEYS))}."]
    problems = []
    name = item["station"]
    if not isinstance(name, str) or not name.startswith(STATION_PREFIX) or "/" in name:
        problems.append(f"{where} must be named `{STATION_PREFIX}<id>`.")
    if not (_is_number(item["lat"]) and _is_number(item["lon"])):
        problems.append(f"{where} has no position (`lat`, `lon`).")
    elif not (-90 <= item["lat"] <= 90 and -180 <= item["lon"] <= 180):
        problems.append(f"{where} is not on the globe.")
    asked = item["variables"]
    if not isinstance(asked, list) or not asked or len(set(map(str, asked))) != len(asked):
        problems.append(f"{where} must list its variables once each.")
    elif unknown := sorted(set(map(str, asked)) - variables):
        problems.append(f"{where} asks variables the parameter set does not score: {', '.join(unknown)}.")
    heights = item["sensor_heights"]
    if not isinstance(heights, dict) or not all(
        _is_number(value) and value >= 0 for value in heights.values()
    ):
        problems.append(f"{where}: `sensor_heights` must give metres per variable.")
    elif isinstance(asked, list) and set(heights) - set(map(str, asked)):
        problems.append(f"{where}: `sensor_heights` names a variable the station is not asked.")
    return problems


def _check_families(definition: dict, parameters: FireCaseParameters | None) -> list[str]:
    families = definition["families"]
    if not isinstance(families, list) or not families:
        return ["The window asks no family."]
    problems, seen = [], set()
    for entry in families:
        name = entry.get("family") if isinstance(entry, dict) else None
        if name not in FAMILIES:
            problems.append(f"Unknown family `{name}`; a window has {', '.join(FAMILIES)}.")
            continue
        if name in seen:
            problems.append(f"The family `{name}` is given twice.")
            continue
        seen.add(name)
        if set(entry) != FAMILY_KEYS[name]:
            problems.append(
                f"The family `{name}` must have exactly the keys {', '.join(sorted(FAMILY_KEYS[name]))}."
            )
            continue
        if name == ARRIVAL:
            group = entry["model_group"]
            if not isinstance(group, str) or not group.startswith(f"/{fs.SPATIAL_2D}/"):
                problems.append(f"`model_group` of `{name}` must be a group under `/{fs.SPATIAL_2D}`.")
            continue
        cadence = entry["cadence_minutes"]
        if not isinstance(cadence, int) or isinstance(cadence, bool) or cadence <= 0 or 1440 % cadence:
            problems.append("`cadence_minutes` must be a whole number of minutes that divides a day.")
        stations = entry["stations"]
        if not isinstance(stations, list) or not stations:
            problems.append(f"`{name}` names no station.")
            continue
        variables = {spec.variable for spec in parameters.variables} if parameters else set()
        for index, item in enumerate(stations):
            problems += _check_station(item, index, variables) if parameters else []
        names = [item.get("station") for item in stations if isinstance(item, dict)]
        if len(set(names)) != len(names):
            problems.append(f"A station of `{name}` is given twice.")
    return problems


def check_window(definition) -> list[str]:
    """The problems of a window definition, from the document alone. An empty list: it can be used."""
    if not isinstance(definition, dict):
        return ["The definition is not a JSON object."]
    if definition.get("schema") != SCHEMA:
        return [f"Unknown schema `{definition.get('schema')}`; this FireBench reads `{SCHEMA}`."]
    expected = {"schema", "name", "parameters", "period", "frame", "fire_frame", "families"}
    if set(definition) != expected:
        missing = sorted(expected - set(definition))
        unknown = sorted(set(definition) - expected)
        return [
            "The definition must have exactly the keys "
            f"{', '.join(sorted(expected))}"
            + (f"; missing {', '.join(missing)}" if missing else "")
            + (f"; unknown {', '.join(unknown)}" if unknown else "")
            + "."
        ]
    problems = []
    if not isinstance(definition["name"], str) or not definition["name"].strip():
        problems.append("The window has no name.")
    try:
        parameters = parameters_for(definition["parameters"])
    except FireCaseParameterError as error:
        problems.append(str(error))
        parameters = None
    period = definition["period"]
    if not isinstance(period, dict) or set(period) != {"start", "end"}:
        problems.append("`period` must have a `start` and an `end`.")
    else:
        try:
            start, end = parse_time(period["start"]), parse_time(period["end"])
        except (CaseDefinitionError, ValueError, TypeError):
            problems.append("The period's times must be ISO 8601 with a UTC offset.")
        else:
            if end <= start:
                problems.append("The period ends before it starts.")
    frames = [_frame_problem(definition[key], key) for key in ("frame", "fire_frame")]
    problems += [problem for problem in frames if problem]
    if not any(frames) and not _inside(definition["fire_frame"], definition["frame"]):
        problems.append("`fire_frame` must lie inside `frame`.")
    return problems + _check_families(definition, parameters)


def _checked(definition) -> FireCaseParameters:
    problems = check_window(definition)
    if problems:
        raise CaseDefinitionError(" ".join(problems))
    return parameters_for(definition["parameters"])


# ---------------------------
# Proposal
# ---------------------------
def _stations_of(std_file, variables: tuple[str, ...], frame, found: dict[str, dict]) -> None:
    """Add the stations of one observation file that lie in the frame: names, places, heights."""
    with h5py.File(std_file, "r") as h5:
        series = h5.get(fs.TIME_SERIES)
        if not isinstance(series, h5py.Group):
            return
        for name, group in series.items():
            if not name.startswith(STATION_PREFIX) or not isinstance(group, h5py.Group):
                continue
            try:
                lat, lon = float(group.attrs["position_lat"]), float(group.attrs["position_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (frame[0] <= lon <= frame[2] and frame[1] <= lat <= frame[3]):
                continue
            held = [variable for variable in variables if variable in group]
            if not held:
                continue
            station = found.setdefault(
                name, {"station": name, "lat": lat, "lon": lon, "variables": set(), "sensor_heights": {}}
            )
            station["variables"].update(held)
            for variable in held:
                path = f"/{fs.TIME_SERIES}/{name}/{variable}"
                try:
                    height = fs.read_sensor_height(
                        group[variable], dataset_path=path, allow_legacy_text=True
                    )
                except (KeyError, ValueError, TypeError):
                    continue
                station["sensor_heights"].setdefault(variable, round(float(height.to("m").magnitude), 2))


def propose_window(  # pylint: disable=too-many-arguments
    name: str,
    start: datetime,
    end: datetime,
    frame,
    *,
    fire_frame=None,
    std_files=(),
    cadence_minutes: int = DEFAULT_CADENCE_MINUTES,
    families=FAMILIES,
) -> dict:
    """
    Propose the definition of a forecast window from ``start`` to ``end`` over ``frame`` (west,
    south, east, north), where the fire holds ``fire_frame`` at the start (the frame when not given).

    ``std_files`` are the observation files known when the window opens, whole or in pieces. Only
    their stations are read: each station inside the frame that holds a variable of the parameter
    set is asked, with those variables and the sensor heights the files give. No observed value is
    read. ``families`` limits what is asked.

    Returns ``{"definition": ..., "left_out": [{"family": ..., "reason": ...}]}``.
    """
    parameters = load_parameters()
    frame = [float(edge) for edge in frame]
    variables = tuple(spec.variable for spec in parameters.variables)
    asked, left_out = [], []
    if ARRIVAL in families:
        asked.append({"family": ARRIVAL, "model_group": ARRIVAL_GROUP})
    if STATIONS in families:
        found: dict[str, dict] = {}
        for std_file in std_files:
            _stations_of(std_file, variables, frame, found)
        if found:
            stations = [
                {
                    **station,
                    "variables": [variable for variable in variables if variable in station["variables"]],
                }
                for _, station in sorted(found.items())
            ]
            asked.append({"family": STATIONS, "cadence_minutes": cadence_minutes, "stations": stations})
        else:
            left_out.append({"family": STATIONS, "reason": "no station is known in the frame"})
    definition = {
        "schema": SCHEMA,
        "name": name,
        "parameters": parameters.reference(),
        "period": {"start": iso_utc(start), "end": iso_utc(end)},
        "frame": frame,
        "fire_frame": [float(edge) for edge in (fire_frame if fire_frame is not None else frame)],
        "families": asked,
    }
    _checked(definition)
    return {"definition": definition, "left_out": left_out}


# ---------------------------
# The definition inside a file
# ---------------------------
def write_window_definition(std_file, definition: dict) -> str:
    """Write ``definition`` into the file at ``/benchmark_window/definition`` and return its hash."""
    content = canonical_json(definition)
    digest = hashlib.sha256(content).hexdigest()
    with h5py.File(std_file, "a") as h5:
        if DEFINITION_PATH in h5:
            del h5[DEFINITION_PATH]
        dataset = h5.create_dataset(DEFINITION_PATH, data=np.array(content, dtype=f"S{len(content)}"))
        dataset.attrs["schema"] = np.bytes_(definition.get("schema", ""))
        dataset.attrs["sha256"] = np.bytes_(digest)
    return digest


def read_window_definition(std_file) -> dict | None:
    """The window definition kept in a file, or None when it holds none. Its hash is checked."""
    with h5py.File(std_file, "r") as h5:
        dataset = h5.get(DEFINITION_PATH)
        if dataset is None:
            return None
        content = bytes(dataset[()])
        stated = _text(dataset.attrs.get("sha256", b""))
    if hashlib.sha256(content).hexdigest() != stated:
        raise CaseDefinitionError("The window definition in the file does not match its recorded SHA-256.")
    return json.loads(content.decode("utf-8"))


# ---------------------------
# Template
# ---------------------------
def write_window_template(definition: dict, out_path, *, overwrite: bool = False) -> Path:
    """
    Write the model-output template of a window: the layout a model output is written on.

    Each station asked has its group under ``/time_series`` with its position, ``time`` (the times
    of ``window_times``, minutes from the first), and each variable asked, NaN, in the unit of the
    parameter set with the sensor height the definition gives. The group of the arrival time is
    empty and says what the model writes there, on its own grid. The definition is written in too.
    The file is marked by the root attribute ``firebench_template``: a case refuses it as an
    observation file, and ``check_model_for_window`` as a model output.
    """
    parameters = _checked(definition)
    units = {spec.variable: spec.unit for spec in parameters.variables}
    out_path = Path(out_path)
    out = fs.new_std_file(out_path, authors=f"FireBench {fb_version}", overwrite=overwrite)
    try:
        out.attrs[TEMPLATE_ATTRIBUTE] = TEMPLATE_KIND
        out.attrs["window_definition_sha256"] = definition_sha256(definition)
        arrival = family(definition, ARRIVAL)
        if arrival is not None:
            group = out.require_group(arrival["model_group"])
            for key, value in zip(FRAME_KEYS, definition["frame"]):
                group.attrs[key] = float(value)
                group.attrs[f"{key}_units"] = "degree"
            group.attrs["description"] = (
                "The fire's arrival time on the model's own grid: position_lat and position_lon "
                "(degree; each one-dimensional, or the shape of the field), fire_arrival_time "
                "(n_y, n_x), a duration (units) after its time_origin (ISO 8601 with a UTC offset), "
                "NaN where the fire did not arrive, and time, the times the simulation covers, "
                "which must hold the window's period. The grid must hold the frame of the fire at "
                "the opening (fire_frame of the definition); beyond the grid the model says nothing."
            )
            group.attrs["required_datasets"] = json.dumps(list(ARRIVAL_DATASETS))
        times = window_times(definition)
        minutes = np.array([(time - times[0]).total_seconds() / 60 for time in times], dtype=np.float64)
        for station in (family(definition, STATIONS) or {}).get("stations", []):
            group = out.require_group(f"/{fs.TIME_SERIES}/{station['station']}")
            group.attrs["position_lat"] = float(station["lat"])
            group.attrs["position_lon"] = float(station["lon"])
            group.attrs["position_lat_units"] = "degree"
            group.attrs["position_lon_units"] = "degree"
            time = group.create_dataset("time", data=minutes)
            time.attrs["time_origin"] = times[0].isoformat()
            time.attrs["time_units"] = "min"
            for variable in station["variables"]:
                dataset = group.create_dataset(variable, data=np.full(minutes.shape, np.nan))
                dataset.attrs["units"] = units[variable]
                if variable in station["sensor_heights"]:
                    dataset.attrs[fs.SENSOR_HEIGHT_ATTRIBUTE] = float(station["sensor_heights"][variable])
                    dataset.attrs[fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE] = "m"
    finally:
        out.close()
    write_window_definition(out_path, definition)
    return out_path


# ---------------------------
# The check of a model output
# ---------------------------
def _seconds(dataset: h5py.Dataset) -> np.ndarray:
    """The times of a ``time`` dataset in seconds since the epoch, in either encoding of the standard.

    Raises ValueError when they cannot be placed (no UTC offset, units that are not a duration).
    """
    attrs = dataset.attrs
    try:
        if "time_origin" in attrs and "time_units" in attrs:
            origin = parse_time(_text(attrs["time_origin"]))
            values = np.asarray(dataset[()], dtype=np.float64).reshape(-1)
            seconds = ureg.Quantity(values, _text(attrs["time_units"])).to("s").magnitude
            return origin.timestamp() + np.asarray(seconds, dtype=np.float64)
        values = np.asarray(dataset[()]).reshape(-1)
        return np.array([parse_time(value).timestamp() for value in values], dtype=np.float64)
    except (CaseDefinitionError, TypeError, AttributeError, pint.errors.PintError) as error:
        raise ValueError(str(error)) from error


def _utc_text(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _convertible(dataset: h5py.Dataset, unit: str) -> bool:
    try:
        return bool(ureg.Quantity(1.0, _text(dataset.attrs["units"])).is_compatible_with(unit))
    except (KeyError, AttributeError, TypeError, ValueError, pint.errors.PintError):
        return False


# pylint: disable-next=too-many-return-statements
def _station_problem(group, variable: str, unit: str, grid: np.ndarray) -> str | None:
    """Why a station series does not give a variable on the grid, or None when it does."""
    if not isinstance(group, h5py.Group) or variable not in group or "time" not in group:
        return "is not in the file"
    dataset = group[variable]
    if not _convertible(dataset, unit):
        return f"has no `units` that convert to `{unit}`"
    try:
        times = _seconds(group["time"])
        values = np.asarray(dataset[()], dtype=np.float64).reshape(-1)
    except (ValueError, TypeError):
        return "has times or values that cannot be read"
    if times.shape != values.shape:
        return "has a `time` of another length than its values"
    finite = np.sort(times[np.isfinite(times) & np.isfinite(values)])
    if finite.size == 0:
        return "holds no value"
    at = (
        np.clip(np.searchsorted(finite, grid), 1, finite.size - 1)
        if finite.size > 1
        else np.zeros(grid.size, int)
    )
    nearest = np.minimum(np.abs(finite[at] - grid), np.abs(finite[at - 1] - grid))
    missing = int(np.sum(nearest > TIME_TOLERANCE_SECONDS))
    if missing:
        return f"lacks a value at {missing} of the {grid.size} times asked"
    return None


def _check_stations(model: h5py.File, definition: dict, parameters: FireCaseParameters) -> dict:
    entry = family(definition, STATIONS)
    grid = np.array([time.timestamp() for time in window_times(definition)], dtype=np.float64)
    parts = []
    for spec in parameters.variables:
        asked = [
            station["station"] for station in entry["stations"] if spec.variable in station["variables"]
        ]
        if not asked:
            continue
        problems = {}
        for station in asked:
            problem = _station_problem(
                model.get(f"/{fs.TIME_SERIES}/{station}"), spec.variable, spec.unit, grid
            )
            if problem:
                problems[station] = problem
        first = next(iter(problems), None)
        parts.append(
            {
                "name": spec.variable,
                "label": spec.label,
                "status": UNAVAILABLE if problems else ELIGIBLE,
                "stations": len(asked),
                "covered": len(asked) - len(problems),
                "reason": (
                    f"`{spec.variable}` is not given on the window's times for {len(problems)} of the "
                    f"{len(asked)} stations asked (first: {first} {problems[first]})."
                    if problems
                    else None
                ),
            }
        )
    eligible = sum(part["status"] == ELIGIBLE for part in parts)
    status = ELIGIBLE if eligible == len(parts) else PARTIAL if eligible else UNAVAILABLE
    return {
        "family": STATIONS,
        "label": FAMILY_LABELS[STATIONS],
        "status": status,
        "reason": None if eligible else "No variable is given for every station asked.",
        "notes": [
            f"Asked every {entry['cadence_minutes']} min from {_utc_text(grid[0])} to "
            f"{_utc_text(grid[-1])}: {grid.size} times."
        ],
        "parts": parts,
    }


def _grid_box(group: h5py.Group, shape: tuple[int, ...]) -> list[float]:
    """The box of the cell centres of an arrival-time grid: west, south, east, north."""
    lat = np.asarray(group["position_lat"][()], dtype=np.float64)
    lon = np.asarray(group["position_lon"][()], dtype=np.float64)
    if not (lat.shape == shape and lon.shape == shape) and not (
        lat.shape == shape[:1] and lon.shape == shape[1:]
    ):
        raise ValueError(
            "`position_lat` and `position_lon` must each have the shape of the field, or be its "
            "two axes (n_y and n_x)"
        )
    lat, lon = lat[np.isfinite(lat)], lon[np.isfinite(lon)]
    if not lat.size or not lon.size:
        raise ValueError("the grid has no position")
    if lat.min() < -90 or lat.max() > 90 or lon.min() < -180 or lon.max() > 180:
        raise ValueError("`position_lat` and `position_lon` are not degrees on the globe")
    return [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())]


def _share(box, frame) -> float:
    """The share of a frame's box, in degrees, that a grid's box holds."""
    width = max(0.0, min(box[2], frame[2]) - max(box[0], frame[0]))
    height = max(0.0, min(box[3], frame[3]) - max(box[1], frame[1]))
    return width * height / ((frame[2] - frame[0]) * (frame[3] - frame[1]))


# pylint: disable-next=too-many-return-statements
def _arrival_problem(group, definition: dict) -> tuple[str | None, dict]:
    """Why the arrival-time group cannot enter the window (None: it can), and what was read of it."""
    if not isinstance(group, h5py.Group):
        return "is not in the file", {}
    missing = [name for name in ARRIVAL_DATASETS if not isinstance(group.get(name), h5py.Dataset)]
    if missing:
        return f"lacks {', '.join(f'`{name}`' for name in missing)}", {}
    field = group[ARRIVAL]
    if field.ndim != 2 or not field.size or not np.issubdtype(field.dtype, np.number):
        return f"`{ARRIVAL}` must be a field of numbers (n_y, n_x)", {}
    try:
        ureg.Quantity(1.0, _text(field.attrs["units"])).to("s")
        parse_time(_text(field.attrs["time_origin"]))
    except (KeyError, CaseDefinitionError, AttributeError, TypeError, ValueError, pint.errors.PintError):
        return (
            f"`{ARRIVAL}` needs `units` of a duration and a `time_origin` (ISO 8601 with a UTC offset)",
            {},
        )
    try:
        covered = _seconds(group["time"])
        box = _grid_box(group, field.shape)
    except ValueError as error:
        return str(error), {}
    covered = covered[np.isfinite(covered)]
    if not covered.size:
        return "`time` holds no time", {}
    read = {
        "grid": {"cells": int(field.size), "box": box},
        "span": {"start": iso_utc(_utc(covered.min())), "end": iso_utc(_utc(covered.max()))},
        "frame_coverage": round(_share(box, definition["frame"]), 4),
    }
    start, end = (time.timestamp() for time in window_period(definition))
    if covered.min() > start + TIME_TOLERANCE_SECONDS or covered.max() < end - TIME_TOLERANCE_SECONDS:
        return (
            f"`time` covers {_utc_text(covered.min())} to {_utc_text(covered.max())}, not the window's "
            f"period ({_utc_text(start)} to {_utc_text(end)})",
            read,
        )
    if not _inside(definition["fire_frame"], box):
        return "the grid does not hold the frame of the fire at the opening (`fire_frame`)", read
    return None, read


def _utc(stamp: float) -> datetime:
    return datetime.fromtimestamp(float(stamp), timezone.utc)


def _check_arrival(model: h5py.File, definition: dict) -> dict:
    entry = family(definition, ARRIVAL)
    problem, read = _arrival_problem(model.get(entry["model_group"]), definition)
    notes = []
    if problem is None and read["frame_coverage"] < 1:
        notes.append(
            f"The grid holds {read['frame_coverage']:.0%} of the window's frame; beyond it the model "
            "says nothing. The file is accepted because the grid holds the fire at the opening, but a "
            "larger domain is recommended for the next window: if the observed fire leaves the grid "
            "during the window, the evaluation on arrival time is discarded."
        )
    return {
        "family": ARRIVAL,
        "label": FAMILY_LABELS[ARRIVAL],
        "status": UNAVAILABLE if problem else ELIGIBLE,
        "reason": f"`{entry['model_group']}`: {problem}." if problem else None,
        "notes": notes,
        "parts": [],
        **read,
    }


def check_model_for_window(definition: dict, model_file) -> dict:
    """
    Which families of a window a model output can enter, from the definition alone: no observation
    is read, and nothing is scored (schema ``fb-window-check-v1``).

    ``accepted`` is False, with the ``reason``, for a file that is not a FireBench standard file or
    is a template. Otherwise each family of the definition has a ``status``: ``eligible``,
    ``partial`` (some variables of the stations only), or ``unavailable`` with the ``reason``.

    - ``fire_arrival_time``: the group holds the field with its units and time origin, its grid
      positions, and ``time``; the times cover the period; the grid holds ``fire_frame``. The share
      of ``frame`` the grid holds is ``frame_coverage``.
    - ``weather_stations``: per variable (``parts``), every station asked gives a finite value, in
      units that convert to the parameter set's, at every time of ``window_times``.

    Raises
    ------
    CaseDefinitionError
        If the definition has a problem (``check_window``).
    """
    parameters = _checked(definition)
    report = {
        "schema": CHECK_SCHEMA,
        "window": {
            "name": definition["name"],
            "definition_sha256": definition_sha256(definition),
            "period": dict(definition["period"]),
        },
        "firebench": {"version": fb_version, "commit": _firebench_commit()},
        "accepted": False,
        "reason": None,
        "families": [],
    }
    try:
        model = h5py.File(model_file, "r")
    except OSError:
        return {**report, "reason": NOT_HDF5}
    with model:
        try:
            fs.validate_h5_std(model)
        except ValueError as error:
            return {**report, "reason": f"The file is not a FireBench standard file: {error}"}
        if TEMPLATE_ATTRIBUTE in model.attrs:
            return {**report, "reason": EMPTY_TEMPLATE}
        checks = {ARRIVAL: lambda: _check_arrival(model, definition)}
        checks[STATIONS] = lambda: _check_stations(model, definition, parameters)
        families = [checks[entry["family"]]() for entry in definition["families"]]
    return {**report, "accepted": True, "families": families}
