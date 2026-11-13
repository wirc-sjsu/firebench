"""
Forecast windows: bring a model output to the observations that arrived, and score it.

``fire_window`` says what a model gives before anything is observed. Here the observations exist, and
two steps follow (the schemas are ``fb-window-prepared-v1`` and the score card of a case):

- ``prepare_window_model`` writes, from the model output and the observation file, the file the KPIs
  of a case read: the model's station series interpolated to the observed times of the window so
  far, and the burnt area of its arrival-time field cut at the time of each observed perimeter;
- ``score_window`` runs the KPIs of a generic case (``fire_case``) on that file, on what it holds.

Nothing here is a KPI: the burnt area (``burnt_area_polygons``) and the interpolation only put the
model on the observations' times and places, and the scores are those of ``fire_case``. The fire
perimeters are scored on the observed perimeters after the reception of the forecast (``after``); the
last one at or before it is the starting state, named in the report and the result and used by no KPI.
What cannot be made is left out with its reason, never filled.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import contourpy
import geopandas as gpd
import h5py
import numpy as np
import pint
from shapely.geometry import Polygon

from .. import __version__ as fb_version
from .. import standardize as fs
from .. import tools as ft
from ..tools.units import ureg
from . import wx_common as wxc
from .c001_caldor import resolve_h5_relative_path
from .fire_case import FireCase
from .fire_case_definition import (
    SCHEMA as CASE_SCHEMA,
    STATION_PREFIX,
    STATION_SETS,
    TEMPLATE_ATTRIBUTE,
    TEMPLATE_REFUSAL,
    CaseDefinitionError,
    data_span,
    definition_sha256,
    iso_utc,
    parse_time,
    perimeter_times,
)
from .fire_window import (
    ARRIVAL,
    FAMILY_LABELS,
    STATIONS,
    TIME_TOLERANCE_SECONDS,
    _checked,
    _convertible,
    _inside,
    _seconds,
    _text,
    _utc_text,
    check_model_for_window,
    family,
    report_header,
    window_period,
)

PREPARED_SCHEMA = "fb-window-prepared-v1"
PERIMETER_LAYER = "fire_perimeter"
MADE, PARTIAL, NOT_MADE = "made", "partial", "not_made"
SCORED, NULL = "scored", "null"
# The kind of the case's groups (``FireCase.CATEGORIES``) that each family of a window is scored with.
FAMILY_KINDS = {ARRIVAL: "P", STATIONS: "W"}
NOT_OBSERVED = "The observation file is not a readable HDF5 file."


# ---------------------------
# The burnt area of an arrival-time field
# ---------------------------
def burnt_area_polygons(field_seconds, lon, lat, time_s: float) -> gpd.GeoDataFrame:
    """
    The area a fire has burnt at ``time_s``, as polygons in EPSG:4326, from its arrival-time field.

    ``field_seconds`` (n_y, n_x) is the time the fire arrives in each cell, in seconds, NaN where it
    did not arrive; ``lon`` and ``lat`` are the cell centres, each of that shape or the two axes
    (``lon`` of length n_x, ``lat`` of length n_y). A cell is burnt when its arrival time is finite
    and at most ``time_s``. The perimeter is the contour at 0.5 of that mask, with no smoothing, so
    every map is cut the same way; rings inside others are their holes. A fire that burns no cell
    gives no polygon. The method is that of the WRF-SFIRE adapter's perimeters.
    """
    field = np.asarray(field_seconds, dtype=np.float64)
    lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
    if lon.ndim == 1 and lat.ndim == 1:
        lon, lat = np.meshgrid(lon, lat)
    if not lon.shape == lat.shape == field.shape:
        raise ValueError(
            "`lon`, `lat`, and the field must have the same shape, or `lon` and `lat` be axes."
        )
    burnt = (np.isfinite(field) & (field <= time_s)).astype(np.float64)
    generator = contourpy.contour_generator(
        x=lon, y=lat, z=burnt, line_type=contourpy.LineType.Separate, corner_mask=True
    )
    rings = [ring for ring in generator.lines(0.5) if len(ring) >= 4]
    polygons = [Polygon(ring) for ring in rings]
    valid = [index for index, polygon in enumerate(polygons) if polygon.is_valid and polygon.area > 0]
    # The largest rings first; a ring inside another that is not already a hole is a hole of it.
    valid.sort(key=lambda index: polygons[index].area, reverse=True)
    holes_of, used = {}, set()
    for index in valid:
        if index in used:
            continue
        holes_of[index] = []
        for other in valid:
            if other == index or other in used or not polygons[other].within(polygons[index]):
                continue
            if any(polygons[other].within(Polygon(hole)) for hole in holes_of[index]):
                continue
            holes_of[index].append(rings[other])
            used.add(other)
    final = [Polygon(rings[index], holes=holes) for index, holes in holes_of.items()]
    final = [polygon for polygon in final if polygon.is_valid and polygon.area > 0]
    return gpd.GeoDataFrame(geometry=final, crs="EPSG:4326")


# ---------------------------
# What the observations hold
# ---------------------------
def _window_state(definition: dict, obs: h5py.File, after: datetime | None) -> dict:
    """
    The window so far: its period, the last observation in it (``until``), ``after``, and the observed
    perimeters: the ``target`` (later than ``after``, or than the start when it is None, up to
    ``until``) and the ``starting_state`` (the last one at or before that time).
    """
    parameters = _checked(definition)
    start, end = window_period(definition)
    if after is not None:
        if after.tzinfo is None or after.utcoffset() is None:
            raise ValueError("`after` must be a time with a UTC offset.")
        after = after.astimezone(timezone.utc).replace(microsecond=0)
        if not start <= after <= end:
            raise ValueError("`after` is outside the window's period.")
    span = data_span(obs, parameters)
    until = min(span[1], end).replace(microsecond=0) if span else None
    if until is None or until <= start:
        raise ValueError("The observation file holds no observation after the window opens.")
    boundary = start if after is None else after
    times = perimeter_times(obs)
    before = [path for path, time in times.items() if time <= boundary]
    return {
        "parameters": parameters,
        "start": start,
        "end": end,
        "after": after,
        "until": until,
        "boundary": boundary,
        "target": {path: time for path, time in times.items() if boundary < time <= until},
        "starting_state": {"path": before[-1], "time": iso_utc(times[before[-1]])} if before else None,
    }


def _perimeter_refs(perimeters: dict[str, datetime]) -> list[dict]:
    return [{"path": path, "time": iso_utc(time)} for path, time in perimeters.items()]


def _open_observations(obs_file) -> h5py.File:
    try:
        obs = h5py.File(obs_file, "r")
    except OSError as error:
        raise ValueError(NOT_OBSERVED) from error
    if TEMPLATE_ATTRIBUTE in obs.attrs:
        obs.close()
        raise CaseDefinitionError(TEMPLATE_REFUSAL)
    return obs


# ---------------------------
# Prepare: the perimeters
# ---------------------------
def _perimeter_family(
    out: h5py.File, out_path: Path, model: h5py.File, obs: h5py.File, definition: dict, state: dict, arrival
) -> dict:
    """Write the burnt area of the model at each target perimeter; the entry of the report."""
    target = state["target"]
    entry = {
        "family": ARRIVAL,
        "label": FAMILY_LABELS[ARRIVAL],
        "status": NOT_MADE,
        "reason": None,
        "target_after": iso_utc(state["boundary"]),
        "target": _perimeter_refs(target),
        "starting_state": state["starting_state"],
        "made": 0,
    }
    minimum = state["parameters"].window_preparation.min_perimeters
    if family(definition, ARRIVAL) is None:
        return {**entry, "reason": f"The window does not ask `{ARRIVAL}`."}
    if arrival["status"] != "eligible":
        return {**entry, "reason": arrival["reason"]}
    if len(target) < minimum:
        return {
            **entry,
            "reason": f"The observations hold {len(target)} perimeter(s) after "
            f"{iso_utc(state['boundary'])}; a window needs at least {minimum}.",
        }
    box = arrival["grid"]["box"]
    for path, time in target.items():
        read = gpd.read_file(resolve_h5_relative_path(obs, obs[path].attrs["rel_path"]), driver="KML")
        if not _inside(read.total_bounds.tolist(), box):
            return {
                **entry,
                "reason": f"The observed perimeter of {iso_utc(time)} is outside the model's grid: the "
                f"evaluation on arrival time is discarded.",
            }
    group = model[family(definition, ARRIVAL)["model_group"]]
    field = group[ARRIVAL]
    seconds = ureg.Quantity(np.asarray(field[()], dtype=np.float64), _text(field.attrs["units"])).to("s")
    origin = parse_time(_text(field.attrs["time_origin"])).timestamp()
    lat, lon = group["position_lat"][()], group["position_lon"][()]
    kml_dir = out_path.with_name(f"{out_path.stem}_perimeters")
    kml_dir.mkdir(parents=True, exist_ok=True)
    for path, time in target.items():
        polygons = burnt_area_polygons(seconds.magnitude, lon, lat, time.timestamp() - origin)
        name = path.rsplit("/", 1)[-1]
        kml = kml_dir / (re.sub(r"[^A-Za-z0-9_]", "_", name) + ".kml")
        # GDAL updates an existing KML file with another driver than the one that writes a new file.
        kml.unlink(missing_ok=True)
        polygons.to_file(kml, driver="KML", layer=PERIMETER_LAYER)
        made = out.require_group(path)
        made.attrs["rel_path"] = f"{kml_dir.name}/{kml.name}"
        made.attrs["sha256"] = ft.calculate_sha256(kml)
        made.attrs["file_size_bytes"] = kml.stat().st_size
        made.attrs["time"] = obs[path].attrs["time"]
    return {**entry, "status": MADE, "made": len(target)}


# ---------------------------
# Prepare: the station series
# ---------------------------
# pylint: disable-next=too-many-return-statements
def _interpolated(group, variable: str, spec, targets: np.ndarray, max_step: float):
    """
    The model's series of ``variable`` at ``targets`` (seconds since the epoch), in the unit of ``spec``.

    Returns ``(values, None)``, or ``(None, reason)`` when the finite samples of the model do not
    bracket every target, or a target lies in a step over ``max_step`` seconds. Linear, and for a
    circular variable along the shortest arc between two samples. Nothing is extrapolated.
    """
    if not isinstance(group, h5py.Group) or variable not in group or "time" not in group:
        return None, "is not in the model output"
    dataset = group[variable]
    if not _convertible(dataset, spec.unit):
        return None, f"has no `units` that convert to `{spec.unit}`"
    try:
        times = _seconds(group["time"])
        raw = np.asarray(dataset[()], dtype=np.float64).reshape(-1)
        values = ureg.Quantity(raw, _text(dataset.attrs["units"])).to(spec.unit).magnitude
    except (ValueError, TypeError, pint.errors.PintError):
        return None, "has times or values that cannot be read"
    if times.shape != values.shape:
        return None, "has a `time` of another length than its values"
    keep = np.isfinite(times) & np.isfinite(values)
    order = np.argsort(times[keep])
    times, values = times[keep][order], values[keep][order]
    if times.size == 0:
        return None, "holds no value"
    first, last = targets.min(), targets.max()
    if times[0] > first + TIME_TOLERANCE_SECONDS or times[-1] < last - TIME_TOLERANCE_SECONDS:
        return None, (
            f"holds values from {_utc_text(times[0])} to {_utc_text(times[-1])}, not the observed times "
            f"({_utc_text(first)} to {_utc_text(last)})"
        )
    if times.size > 1:
        above = np.clip(np.searchsorted(times, targets), 1, times.size - 1)
        step = times[above] - times[above - 1]
        nearest = np.minimum(np.abs(times[above] - targets), np.abs(times[above - 1] - targets))
        over = (step > max_step) & (nearest > TIME_TOLERANCE_SECONDS)
        if over.any():
            return None, (
                f"has a step of {step[over].max() / 60:g} min where the observations need it, over the "
                f"{max_step / 60:g} min allowed"
            )
    if spec.metrics == "wind_direction":
        values = np.unwrap(values, period=360.0)
    result = np.interp(targets, times, values)
    return (result % 360.0 if spec.metrics == "wind_direction" else result), None


def _station_values(model: h5py.File, obs: h5py.File, station: dict, state: dict):
    """
    The model's series of a station asked, at the times the station was observed in the window so far.

    Returns the mask of those times in the observed ``time``, the values by variable, and, by variable,
    why it could not be made.
    """
    parameters = state["parameters"]
    max_step = parameters.window_preparation.max_step_minutes * 60
    path = f"/{fs.TIME_SERIES}/{station['station']}"
    obs_group, mask, targets = obs.get(path), None, None
    if isinstance(obs_group, h5py.Group) and "time" in obs_group:
        try:
            mask = wxc.get_mask_from_period(obs, path, (state["start"], state["until"]))
            targets = _seconds(obs_group["time"])[mask]
        except (ValueError, TypeError):
            mask = None
    values, left_out = {}, {}
    for spec in parameters.variables:
        if spec.variable not in station["variables"]:
            continue
        if mask is None:
            left_out[spec.variable] = "has no observed times that can be read"
        elif not mask.any():
            left_out[spec.variable] = "has no observation in the window so far"
        elif spec.variable not in obs_group:
            left_out[spec.variable] = "is not in the observations"
        else:
            result, why = _interpolated(model.get(path), spec.variable, spec, targets, max_step)
            if why:
                left_out[spec.variable] = why
            else:
                values[spec.variable] = result
    return mask, values, left_out


def _write_station(out, model, obs, station: dict, mask, values: dict, units: dict[str, str]):
    path = f"/{fs.TIME_SERIES}/{station['station']}"
    group = out.create_group(path)
    group.attrs["position_lat"] = float(station["lat"])
    group.attrs["position_lon"] = float(station["lon"])
    group.attrs["position_lat_units"] = "degree"
    group.attrs["position_lon_units"] = "degree"
    # The observed times as the observation file encodes them, so that both count the same samples.
    observed = obs[f"{path}/time"]
    time = group.create_dataset("time", data=np.asarray(observed[()])[mask], dtype=observed.dtype)
    for key, value in observed.attrs.items():
        time.attrs[key] = value
    for variable, series in values.items():
        dataset = group.create_dataset(variable, data=series)
        source = model[f"{path}/{variable}"]
        dataset.attrs["units"] = units[variable]
        for key in (fs.SENSOR_HEIGHT_ATTRIBUTE, fs.SENSOR_HEIGHT_UNITS_ATTRIBUTE):
            if key in source.attrs:
                dataset.attrs[key] = source.attrs[key]


def _station_family(
    out: h5py.File, model: h5py.File, obs: h5py.File, definition: dict, state: dict
) -> dict:
    """Write the model's station series at the observed times of the window so far; the report entry."""
    asked = family(definition, STATIONS)["stations"]
    units = {spec.variable: spec.unit for spec in state["parameters"].variables}
    made = {spec.variable: 0 for spec in state["parameters"].variables}
    left_out = {spec.variable: [] for spec in state["parameters"].variables}
    for station in asked:
        mask, values, why = _station_values(model, obs, station, state)
        for variable, reason in why.items():
            left_out[variable].append({"station": station["station"], "reason": reason})
        for variable in values:
            made[variable] += 1
        if values:
            _write_station(out, model, obs, station, mask, values, units)
    parts = [
        {
            "name": spec.variable,
            "label": spec.label,
            "stations": sum(spec.variable in station["variables"] for station in asked),
            "made": made[spec.variable],
            "left_out": left_out[spec.variable],
        }
        for spec in state["parameters"].variables
        if any(spec.variable in station["variables"] for station in asked)
    ]
    total, done = sum(part["stations"] for part in parts), sum(part["made"] for part in parts)
    return {
        "family": STATIONS,
        "label": FAMILY_LABELS[STATIONS],
        "status": MADE if done == total else PARTIAL if done else NOT_MADE,
        "reason": None if done else "No station series could be made.",
        "parts": parts,
    }


def prepare_window_model(  # pylint: disable=too-many-locals
    definition: dict,
    model_file,
    obs_file,
    out_path,
    *,
    after: datetime | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Write the file the KPIs of a window read, from a model output and the observation file
    (report schema ``fb-window-prepared-v1``).

    The window so far runs from its start to the last observation in it (``observed_until``). The
    prepared file holds, per station asked and variable, the model's series interpolated to the times
    that station was observed in the window so far (``time`` as the observation file encodes it), and,
    per observed perimeter later than ``after`` (later than the start when None), a KML file beside
    ``out_path`` (``<stem>_perimeters/``) with the burnt area of the model's arrival-time field at that
    time, under the perimeter's own path. The last perimeter at or before that time is the starting
    state: named in the report, used by no KPI.

    What cannot be made is left out and the report says why: a variable of a station when the model's
    finite samples do not bracket every observed time or a step between them is over
    ``max_step_minutes`` (``fire_case.toml``); the perimeters when the family is not asked, the model's
    arrival-time group cannot enter the window (``check_model_for_window``), too few perimeters
    (``min_perimeters``) follow ``after``, or an observed perimeter is outside the model's grid. No
    NaN is written for a value that could not be interpolated. The model output is opened read-only.
    The prepared file can be made again (``overwrite``); it records the window and ``after`` it was
    made for, which ``score_window`` checks.

    Raises
    ------
    CaseDefinitionError
        If the definition has a problem, the model output is not accepted by
        ``check_model_for_window``, or the observation file is a template.
    ValueError
        If ``after`` is outside the period, or the observation file holds nothing after the opening.
    """
    _checked(definition)
    check = check_model_for_window(definition, model_file)
    if not check["accepted"]:
        raise CaseDefinitionError(check["reason"])
    out_path = Path(out_path)
    with _open_observations(obs_file) as obs:
        state = _window_state(definition, obs, after)
        families = {item["family"]: item for item in check["families"]}
        entries = []
        with h5py.File(model_file, "r") as model:
            out = fs.new_std_file(out_path, authors=f"FireBench {fb_version}", overwrite=overwrite)
            try:
                out.attrs["window_definition_sha256"] = definition_sha256(definition)
                out.attrs["window_after"] = iso_utc(state["boundary"])
                if family(definition, ARRIVAL) is not None:
                    entries.append(
                        _perimeter_family(out, out_path, model, obs, definition, state, families[ARRIVAL])
                    )
                if family(definition, STATIONS) is not None:
                    entries.append(_station_family(out, model, obs, definition, state))
            finally:
                out.close()
    return {
        "schema": PREPARED_SCHEMA,
        **report_header(definition),
        "after": None if state["after"] is None else iso_utc(state["after"]),
        "observed_until": iso_utc(state["until"]),
        "families": entries,
    }


# ---------------------------
# Score
# ---------------------------
def _stations_given(prepared: h5py.File, parameters) -> dict[str, set[str]]:
    """The stations that hold each variable in the prepared file: what the model gives."""
    given = {spec.variable: set() for spec in parameters.variables}
    series = prepared.get(fs.TIME_SERIES)
    for name, group in (series.items() if isinstance(series, h5py.Group) else []):
        if name.startswith(STATION_PREFIX) and "time" in group:
            for variable, names in given.items():
                if variable in group:
                    names.add(name)
    return given


def _observations_used(obs: h5py.File, given: dict[str, set[str]], periods: dict) -> dict:
    """Per variable and period, the stations given that were observed in it and their samples."""
    used = {}
    for variable, names in given.items():
        used[variable] = {}
        for period, bounds in periods.items():
            counts = [
                int(wxc.get_mask_from_period(obs, f"/{fs.TIME_SERIES}/{name}", bounds).sum())
                for name in sorted(names)
                if variable in obs.get(f"/{fs.TIME_SERIES}/{name}", {})
            ]
            used[variable][period] = {
                "stations": sum(count > 0 for count in counts),
                "samples": sum(counts),
            }
    return used


def _with_scores(case: FireCase, output: dict, entry: dict) -> dict:
    """
    ``entry`` of the ``window`` block with the card's groups of its family and their scores, by period.

    The groups of a family are those of its kind in the case's tables, in the order of the scheme; the
    score of a period is the mean of their scores weighted as the total is (``weighted_group_mean``).
    A family with no group in the card (null) has none.
    """
    kind = FAMILY_KINDS[entry["family"]]
    card = output["score_card"]
    groups: dict[str, list[str]] = {}
    for name in card["Scheme"]:
        info = case._groups[name]  # pylint: disable=protected-access
        if info["kind"] == kind and f"Score {name}" in card:
            groups.setdefault(info["period"], []).append(name)
    scores = {
        period: score
        for period, names in groups.items()
        if (score := wxc.weighted_group_mean(card, card["Scheme"], names)) is not None
    }
    return {**entry, "groups": groups, "scores": scores}


def score_window(  # pylint: disable=too-many-arguments,too-many-locals
    definition: dict,
    prepared_file,
    obs_file,
    *,
    after: datetime | None = None,
    output_json,
    score_card_report,
    name: str = "",
    overwrite: bool = False,
    sign: tuple[str, str] | None = None,
) -> dict:
    """
    Score a prepared window (``prepare_window_model``) against the observation file with the KPIs of
    a generic case, and write an ordinary score card (JSON and PDF, signable) with a ``window`` block.

    The case is built in memory from the window: ``P01`` from the opening to the last observation, and
    ``P02`` from ``after`` to the last observation when ``after`` is inside it. The fire perimeters
    are scored on ``P01`` with the target perimeters, the weather stations on both periods, with the
    stations the prepared file holds for each variable. A family with nothing to score is null with
    its reason in the ``window`` block, which also names the target and the starting state, the share
    of the period observed, the stations given of those asked, and the observations used. Each family
    of the block also has ``groups`` (period name -> the card's groups of that family in that period, in
    the order of the scheme) and ``scores`` (period name -> FireBench's mean of those groups' scores,
    weighted as the total is, not rounded); both are empty for a null family, and a period without a
    scored group of the family is absent.
    ``check_case`` is not called: its refusals (a period inside the data, two perimeters) are the ones
    a window replaces.

    Raises
    ------
    CaseDefinitionError
        If the definition has a problem, the prepared file was not made for this window and this
        ``after``, or the observation file is a template.
    ValueError
        If nothing can be scored (the message gives each family's reason), or ``after`` is outside the
        period.
    """
    with _open_observations(obs_file) as obs, h5py.File(prepared_file, "r") as prepared:
        if prepared.attrs.get("window_definition_sha256") != definition_sha256(definition):
            raise CaseDefinitionError("The prepared file was not made for this window.")
        state = _window_state(definition, obs, after)
        if prepared.attrs.get("window_after") != iso_utc(state["boundary"]):
            raise CaseDefinitionError("The prepared file was not made for this reception time (`after`).")
        state_parameters = state["parameters"]
        given = _stations_given(prepared, state_parameters)
        made = [path for path in state["target"] if path in prepared.get(fs.GEOPOLYGONS, {})]
        periods = {"P01": (state["start"], state["until"])}
        if state["after"] is not None and state["start"] < state["after"] < state["until"]:
            periods["P02"] = (state["after"], state["until"])
        used = _observations_used(obs, given, periods)

    minimum = state_parameters.window_preparation.min_perimeters
    reasons, families = {}, []
    if len(made) >= minimum:
        families.append({"family": "fire_perimeters", "periods": [{"period": "P01", "perimeters": made}]})
    else:
        reasons[ARRIVAL] = (
            f"{len(state['target'])} observed perimeter(s) after {iso_utc(state['boundary'])}; a window "
            f"needs at least {minimum}."
            if len(state["target"]) < minimum
            else "The prepared file holds no burnt area of the model at the observed perimeters."
        )
    if any(given.values()):
        families.append(
            {"family": "weather_stations", "periods": list(periods), "station_sets": list(STATION_SETS)}
        )
    else:
        reasons[STATIONS] = "The prepared file holds no station series."
    if not families:
        raise ValueError(
            "Nothing can be scored: "
            + " ".join(f"{FAMILY_LABELS[key]}: {reason}" for key, reason in reasons.items())
        )

    case = FireCase(
        {
            "schema": CASE_SCHEMA,
            "name": definition["name"],
            "parameters": definition["parameters"],
            "projection": state_parameters.projections[0],
            "periods": [
                {
                    "name": period,
                    "start": iso_utc(bounds[0]),
                    "end": iso_utc(bounds[1]),
                    "origin": "window" if period == "P01" else "custom",
                }
                for period, bounds in periods.items()
            ],
            "families": families,
        }
    )
    asked = family(definition, STATIONS)["stations"] if family(definition, STATIONS) else []
    block = {
        "name": definition["name"],
        "definition_sha256": definition_sha256(definition),
        "after": None if state["after"] is None else iso_utc(state["after"]),
        "observed_until": iso_utc(state["until"]),
        "observed_share": round(
            (state["until"] - state["start"]).total_seconds()
            / (state["end"] - state["start"]).total_seconds(),
            4,
        ),
        "target": _perimeter_refs(state["target"]),
        "starting_state": state["starting_state"],
        "families": [
            {
                "family": ARRIVAL,
                "label": FAMILY_LABELS[ARRIVAL],
                "status": NULL if ARRIVAL in reasons else SCORED,
                "reason": reasons.get(ARRIVAL),
                "perimeters": len(made) if ARRIVAL not in reasons else 0,
            },
            {
                "family": STATIONS,
                "label": FAMILY_LABELS[STATIONS],
                "status": NULL if STATIONS in reasons else SCORED,
                "reason": reasons.get(STATIONS),
                "stations": {
                    spec.variable: {
                        "asked": sum(spec.variable in station["variables"] for station in asked),
                        "given": len(given[spec.variable]),
                    }
                    for spec in state_parameters.variables
                    if any(spec.variable in station["variables"] for station in asked)
                },
                "observations": used,
            },
        ],
    }

    def with_family_scores(output: dict) -> dict:
        return {
            "window": {
                **block,
                "families": [_with_scores(case, output, item) for item in block["families"]],
            }
        }

    return case.run_benchmark(
        prepared_file,
        "A",
        name=name,
        overwrite=overwrite,
        sign=sign,
        obs_data=obs_file,
        output_json=output_json,
        score_card_report=score_card_report,
        stations_given=given,
        extra=with_family_scores,
    )
