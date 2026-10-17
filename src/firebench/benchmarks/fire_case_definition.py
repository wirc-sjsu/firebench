"""
Benchmark cases defined outside FireBench: the definition document (schema ``fb-case-v1``).

A definition says what a case scores: its periods, and per family of KPIs the data it reads. It
names its parameters by reference to ``fire_case.toml`` and carries no number that changes a score.
Its canonical JSON (sorted keys, no spaces, UTF-8) is hashed with SHA-256, and that hash names it.

- ``propose_case`` proposes a definition from a standard file;
- ``check_case`` lists the problems of a definition against a standard file;
- ``write_case_definition`` and ``read_case_definition`` keep it inside the file.

The case id and its versions belong to whoever keeps the cases (the FireBench Foundation's site):
FireBench never gives or reads one.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np

from .. import standardize as fs
from ..tools.units import ureg
from .fire_case_parameters import (
    FireCaseParameterError,
    FireCaseParameters,
    load_parameters,
    parameters_for,
)

SCHEMA = "fb-case-v1"
DEFINITION_PATH = "/benchmark_case/definition"
PERIOD_ORIGINS = ("window", "perimeters", "forecast_window", "custom")
PERIOD_NAME = re.compile(r"^(P\d{2}|H\d{3})$")
STATION_SETS = ("TSO", "ALL")
STATION_PREFIX = "station_"
BUILDING_DAMAGE_PATH = f"/{fs.POINTS}/building_damaged/building_damage"
CBI_PATH = f"/{fs.SPATIAL_2D}/ravg_cbi/ravg_composite_burn_index_severity"
CANOPY_COVER_LOSS_PATH = f"/{fs.SPATIAL_2D}/ravg_cc/ravg_canopy_cover_loss"
# The LANDFIRE canopy layers that tell where there was canopy before the fire (FB001's mask), as
# ``standardize_landfire_canopy`` writes them.
CANOPY_PATHS = tuple(
    f"/{fs.SPATIAL_2D}/{fs.LANDFIRE_CANOPY_PRODUCTS[product][2]}/{fs.LANDFIRE_CANOPY_PRODUCTS[product][0]}"
    for product in ("ch", "cbh", "cbd")
)
FAMILIES = (
    "fire_perimeters",
    "building_damage",
    "burn_severity_cbi",
    "canopy_cover_loss",
    "weather_stations",
)
FAMILY_KEYS = {
    "fire_perimeters": {"family", "periods"},
    "building_damage": {"family", "dataset"},
    "burn_severity_cbi": {"family", "dataset"},
    "canopy_cover_loss": {"family", "dataset", "canopy"},
    "weather_stations": {"family", "periods", "station_sets"},
}
CANOPY_COVER_REASON = (
    "canopy cover loss needs the LANDFIRE canopy height, base height, and bulk density, "
    "which the dataset does not have"
)
# The root attribute of a model-output template (``fire_case_template``), and why one is refused.
TEMPLATE_ATTRIBUTE = "firebench_template"
TEMPLATE_REFUSAL = "This file is a model-output template, not an observation file."


class CaseDefinitionError(ValueError):
    """A definition that cannot be read, or that does not match the file it is checked against."""


# ---------------------------
# The document
# ---------------------------
def canonical_json(definition: dict) -> bytes:
    """The bytes a definition is hashed and stored as."""
    return json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def definition_sha256(definition: dict) -> str:
    """The SHA-256 that names a definition."""
    return hashlib.sha256(canonical_json(definition)).hexdigest()


def iso_utc(value: datetime) -> str:
    """A time as a definition writes it: UTC, to the second, with `Z`."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value) -> datetime:
    """A time of a definition or of a file, which must carry its offset."""
    text = value.decode() if isinstance(value, bytes) else str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise CaseDefinitionError(f"The time `{text}` has no UTC offset.")
    return parsed.astimezone(timezone.utc)


def period_bounds(definition: dict) -> dict[str, tuple[datetime, datetime]]:
    """The periods of a definition, by name. The definition must have been checked."""
    return {
        period["name"]: (parse_time(period["start"]), parse_time(period["end"]))
        for period in definition["periods"]
    }


def family(definition: dict, name: str) -> dict | None:
    """The entry of a family in a definition, or None."""
    return next((item for item in definition.get("families", []) if item.get("family") == name), None)


# ---------------------------
# What a standard file holds
# ---------------------------
def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else b""
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)


def perimeter_times(h5: h5py.File) -> dict[str, datetime]:
    """Each perimeter of the file that points at a KML file and has a time, by path, in time order."""
    polygons = h5.get(fs.GEOPOLYGONS)
    if not isinstance(polygons, h5py.Group):
        return {}
    times = {}
    for name, item in polygons.items():
        if "rel_path" not in item.attrs or "time" not in item.attrs:
            continue
        try:
            times[f"/{fs.GEOPOLYGONS}/{name}"] = parse_time(_text(item.attrs["time"]))
        except (CaseDefinitionError, ValueError):
            continue
    return dict(sorted(times.items(), key=lambda item: item[1]))


def _station_groups(h5: h5py.File) -> dict[str, h5py.Group]:
    series = h5.get(fs.TIME_SERIES)
    if not isinstance(series, h5py.Group):
        return {}
    return {
        name: group
        for name, group in series.items()
        if name.startswith(STATION_PREFIX) and isinstance(group, h5py.Group)
    }


def _series_span(time_dataset: h5py.Dataset) -> tuple[datetime, datetime] | None:
    if time_dataset.shape[0] == 0:
        return None
    attrs = time_dataset.attrs
    if "time_origin" in attrs and "time_units" in attrs:
        origin = parse_time(_text(attrs["time_origin"]))
        values = np.asarray(time_dataset[:], dtype=np.float64)
        values = values[np.isfinite(values)]
        if values.size == 0:
            return None
        seconds = ureg.Quantity(values, _text(attrs["time_units"])).to("s").magnitude
        return origin + timedelta(seconds=float(seconds.min())), origin + timedelta(
            seconds=float(seconds.max())
        )
    ends = sorted(parse_time(time_dataset[index]) for index in (0, -1))
    return ends[0], ends[1]


def station_span(h5: h5py.File, variables: tuple[str, ...]) -> tuple[datetime, datetime] | None:
    """First and last time of the station series that hold one of ``variables``."""
    spans = []
    for group in _station_groups(h5).values():
        if "time" not in group or not any(variable in group for variable in variables):
            continue
        try:
            span = _series_span(group["time"])
        except (CaseDefinitionError, ValueError, TypeError, KeyError):
            span = None
        if span is not None:
            spans.append(span)
    if not spans:
        return None
    return min(span[0] for span in spans), max(span[1] for span in spans)


def data_span(h5: h5py.File, parameters: FireCaseParameters) -> tuple[datetime, datetime] | None:
    """The time span of the file's perimeters and station series."""
    times = list(perimeter_times(h5).values())
    stations = station_span(h5, tuple(spec.variable for spec in parameters.variables))
    if stations is not None:
        times.extend(stations)
    if not times:
        return None
    return min(times), max(times)


def is_template(std_file) -> bool:
    """Whether a standard file is a model-output template, which is never an observation file."""
    with h5py.File(std_file, "r") as h5:
        return TEMPLATE_ATTRIBUTE in h5.attrs


def _has_dataset(h5: h5py.File, path: str) -> bool:
    return isinstance(h5.get(path), h5py.Dataset)


def _cbi_problem(h5: h5py.File, path: str) -> str | None:
    if not _has_dataset(h5, path):
        return f"`{path}` is not in the file."
    group = path.rsplit("/", 1)[0]
    missing = [name for name in ("position_lat", "position_lon") if not _has_dataset(h5, f"{group}/{name}")]
    if missing:
        return f"The group `{group}` has no {' or '.join(missing)}."
    return None


def _canopy_problem(h5: h5py.File, dataset: str, canopy) -> str | None:
    """Why canopy cover loss cannot be scored from a RAVG grid and LANDFIRE canopy layers, or None."""
    problem = _cbi_problem(h5, dataset)
    if problem:
        return problem
    if (
        not isinstance(canopy, list)
        or not canopy
        or not all(isinstance(path, str) for path in canopy)
        or len(set(canopy)) != len(canopy)
    ):
        return "`canopy` must list the paths of the LANDFIRE canopy layers, once each."
    for path in canopy:
        problem = _cbi_problem(h5, path)
        if problem:
            return problem
        if "_FillValue" not in h5[path].attrs:
            return f"`{path}` has no `_FillValue`."
    groups = [path.rsplit("/", 1)[0] for path in canopy]
    shape = h5[canopy[0]].shape
    for group, path in zip(groups[1:], canopy[1:]):
        same = h5[path].shape == shape and all(
            np.allclose(h5[f"{groups[0]}/{name}"][()], h5[f"{group}/{name}"][()])
            for name in ("position_lat", "position_lon")
        )
        if not same:
            return f"The LANDFIRE layers `{groups[0]}` and `{group}` are not on the same grid."
    return None


# ---------------------------
# Proposal
# ---------------------------
def _perimeters_in(
    times: dict[str, datetime], start: datetime, end: datetime, closed_start: bool
) -> list[str]:
    return [
        path
        for path, time in times.items()
        if (start <= time if closed_start else start < time) and time <= end
    ]


def _forecast_windows(
    times: dict[str, datetime], within: tuple[datetime, datetime], parameters: FireCaseParameters
) -> list[tuple[datetime, datetime]]:
    """FB001's HRRR windows on the file's perimeters, kept inside ``within``."""
    if len(times) < parameters.forecast_min_perimeters:
        return []
    values = list(times.values())
    length = timedelta(hours=parameters.forecast_hours)
    day = values[0].replace(hour=0, minute=0, second=0, microsecond=0) - length
    last_day = values[-1].replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    windows = []
    while day <= last_day:
        for hour in parameters.forecast_cycle_hours:
            start = day + timedelta(hours=hour)
            end = start + length
            inside = within[0] <= start and end <= within[1]
            if (
                inside
                and len(_perimeters_in(times, start, end, True)) >= parameters.forecast_min_perimeters
            ):
                windows.append((start, end))
        day += timedelta(days=1)
    return windows


def propose_case(
    std_file, window: tuple[datetime, datetime] | None = None, name: str | None = None
) -> dict:
    """
    Propose a definition for a standard file, with every family the file allows.

    The periods are ``P01``, the ``window`` given (else the span of the file's data); ``P02``, from
    the first to the last perimeter when there are at least two; and ``H###``, the forecast windows
    of the parameter set that hold enough perimeters and lie inside ``P01``. A perimeter belongs to
    a period when its time is after the start, at the latest at the end; to a forecast window, from
    its start.

    Returns ``{"definition": ..., "left_out": [{"family": ..., "reason": ...}]}``.
    """
    parameters = load_parameters()
    left_out = []
    with h5py.File(std_file, "r") as h5:
        span = data_span(h5, parameters)
        times = perimeter_times(h5)
        has_damage = _has_dataset(h5, BUILDING_DAMAGE_PATH)
        cbi_problem = _cbi_problem(h5, CBI_PATH)
        has_canopy_cover = f"/{fs.SPATIAL_2D}/ravg_cc" in h5
        canopy_problem = _canopy_problem(h5, CANOPY_COVER_LOSS_PATH, list(CANOPY_PATHS))
        canopy_reason = (
            CANOPY_COVER_REASON
            if not all(_has_dataset(h5, path) for path in CANOPY_PATHS)
            else f"the LANDFIRE canopy layers cannot be used: {canopy_problem}"
        )
        has_stations = station_span(h5, tuple(spec.variable for spec in parameters.variables)) is not None
        title = name or _text(h5.attrs.get("description", "")) or Path(std_file).stem

    if window is not None:
        overall = (window[0].astimezone(timezone.utc), window[1].astimezone(timezone.utc))
    elif span is not None:
        overall = span
    else:
        raise CaseDefinitionError(
            "The file holds no perimeter or station time series to define a period with."
        )

    periods = [
        {"name": "P01", "start": iso_utc(overall[0]), "end": iso_utc(overall[1]), "origin": "window"}
    ]
    perimeter_periods = []
    in_window = _perimeters_in(times, overall[0], overall[1], False)
    if len(in_window) >= parameters.min_perimeters:
        perimeter_periods.append({"period": "P01", "perimeters": in_window})
    values = list(times.values())
    if len(values) >= 2:
        first, last = values[0], values[-1]
        periods.append(
            {"name": "P02", "start": iso_utc(first), "end": iso_utc(last), "origin": "perimeters"}
        )
        after_first = _perimeters_in(times, first, last, False)
        if len(after_first) >= parameters.min_perimeters:
            perimeter_periods.append({"period": "P02", "perimeters": after_first})
    for index, (start, end) in enumerate(_forecast_windows(times, overall, parameters), start=1):
        period_name = f"H{index:03d}"
        periods.append(
            {"name": period_name, "start": iso_utc(start), "end": iso_utc(end), "origin": "forecast_window"}
        )
        perimeter_periods.append(
            {"period": period_name, "perimeters": _perimeters_in(times, start, end, True)}
        )

    families = []
    if perimeter_periods:
        families.append({"family": "fire_perimeters", "periods": perimeter_periods})
    else:
        reason = f"fewer than {parameters.min_perimeters} perimeters in any period"
        left_out.append({"family": "fire_perimeters", "reason": reason})
    if has_damage:
        families.append({"family": "building_damage", "dataset": BUILDING_DAMAGE_PATH})
    else:
        left_out.append({"family": "building_damage", "reason": "no building damage group"})
    if cbi_problem is None:
        families.append({"family": "burn_severity_cbi", "dataset": CBI_PATH})
    else:
        left_out.append({"family": "burn_severity_cbi", "reason": "no RAVG CBI grid"})
    if has_stations:
        families.append(
            {
                "family": "weather_stations",
                "periods": [period["name"] for period in periods],
                "station_sets": list(STATION_SETS),
            }
        )
    else:
        left_out.append({"family": "weather_stations", "reason": "no weather station time series"})
    if has_canopy_cover and canopy_problem is None:
        families.append(
            {"family": "canopy_cover_loss", "dataset": CANOPY_COVER_LOSS_PATH, "canopy": list(CANOPY_PATHS)}
        )
    elif has_canopy_cover:
        left_out.append({"family": "canopy_cover_loss", "reason": canopy_reason})

    definition = {
        "schema": SCHEMA,
        "name": title,
        "parameters": parameters.reference(),
        "projection": parameters.projections[0],
        "periods": periods,
        "families": families,
    }
    return {"definition": definition, "left_out": left_out}


def edit_case(
    definition: dict,
    std_file,
    remove_families=(),
    remove_periods=(),
    add_periods=(),
) -> dict:
    """
    A copy of ``definition`` with families and periods removed, and periods added.

    A removed period leaves every family; a family left with no period is removed. An added period,
    ``(start, end)``, is named with the next free ``P##`` and has the origin ``custom``: the weather
    stations are scored on it, and the fire perimeters too when it holds enough of them (the rule of
    ``propose_case``). The result is not checked: pass it to ``check_case``.
    """
    edited = json.loads(json.dumps(definition))
    removed = set(remove_periods)
    edited["families"] = [
        item for item in edited.get("families", []) if item.get("family") not in set(remove_families)
    ]
    edited["periods"] = [
        period for period in edited.get("periods", []) if period.get("name") not in removed
    ]
    for item in edited["families"]:
        if item.get("family") == "fire_perimeters":
            item["periods"] = [entry for entry in item["periods"] if entry.get("period") not in removed]
        elif item.get("family") == "weather_stations":
            item["periods"] = [name for name in item["periods"] if name not in removed]
    if add_periods:
        parameters = load_parameters()
        with h5py.File(std_file, "r") as h5:
            times = perimeter_times(h5)
        taken = {period.get("name") for period in edited["periods"]}
        perimeters = family(edited, "fire_perimeters")
        weather = family(edited, "weather_stations")
        for start, end in add_periods:
            start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
            name = next(f"P{number:02d}" for number in range(1, 100) if f"P{number:02d}" not in taken)
            taken.add(name)
            edited["periods"].append(
                {"name": name, "start": iso_utc(start), "end": iso_utc(end), "origin": "custom"}
            )
            inside = _perimeters_in(times, start, end, False)
            if perimeters is not None and len(inside) >= parameters.min_perimeters:
                perimeters["periods"].append({"period": name, "perimeters": inside})
            if weather is not None:
                weather["periods"].append(name)
    edited["families"] = [item for item in edited["families"] if "periods" not in item or item["periods"]]
    return edited


# ---------------------------
# Check
# ---------------------------
def _check_document(definition) -> tuple[list[str], FireCaseParameters | None]:
    """Problems of the document alone, and its parameters when it names this FireBench's."""
    if not isinstance(definition, dict):
        return ["The definition is not a JSON object."], None
    if definition.get("schema") != SCHEMA:
        return [f"Unknown schema `{definition.get('schema')}`; this FireBench reads `{SCHEMA}`."], None
    expected = {"schema", "name", "parameters", "projection", "periods", "families"}
    problems = []
    if set(definition) != expected:
        missing = sorted(expected - set(definition))
        unknown = sorted(set(definition) - expected)
        problems.append(
            "The definition must have exactly the keys "
            f"{', '.join(sorted(expected))}"
            + (f"; missing {', '.join(missing)}" if missing else "")
            + (f"; unknown {', '.join(unknown)}" if unknown else "")
            + "."
        )
        return problems, None
    if not isinstance(definition["name"], str) or not definition["name"].strip():
        problems.append("The case has no name.")
    try:
        parameters = parameters_for(definition["parameters"])
    except FireCaseParameterError as error:
        problems.append(str(error))
        parameters = None
    if parameters is not None and definition["projection"] not in parameters.projections:
        problems.append(
            f"The projection `{definition['projection']}` is not one of {', '.join(parameters.projections)}."
        )
    return problems, parameters


def _check_periods(definition: dict, span) -> tuple[list[str], dict[str, tuple[datetime, datetime]]]:
    problems, bounds = [], {}
    periods = definition["periods"]
    if not isinstance(periods, list) or not periods:
        return ["The definition has no period."], bounds
    for index, period in enumerate(periods, start=1):
        if not isinstance(period, dict) or set(period) != {"name", "start", "end", "origin"}:
            problems.append(f"Period {index} must have exactly a name, a start, an end, and an origin.")
            continue
        name = period["name"]
        if not isinstance(name, str) or not PERIOD_NAME.fullmatch(name):
            problems.append(f"Period {index}: `{name}` is not a period name (P01, H001, …).")
            continue
        if name in bounds:
            problems.append(f"The period {name} is defined twice.")
            continue
        if period["origin"] not in PERIOD_ORIGINS:
            problems.append(f"Period {name}: the origin must be one of {', '.join(PERIOD_ORIGINS)}.")
        try:
            start, end = parse_time(period["start"]), parse_time(period["end"])
        except (CaseDefinitionError, ValueError, TypeError):
            problems.append(f"Period {name}: the start and the end must be times with a UTC offset.")
            continue
        if start >= end:
            problems.append(f"Period {name} is empty: it ends at or before its start.")
            continue
        if span is None:
            problems.append(f"Period {name}: the file holds no time to place it against.")
        elif start < span[0] or end > span[1]:
            problems.append(
                f"Period {name} ({iso_utc(start)} to {iso_utc(end)}) is not inside the data of the file "
                f"({iso_utc(span[0])} to {iso_utc(span[1])})."
            )
        bounds[name] = (start, end)
    return problems, bounds


def _check_perimeters(entry: dict, bounds: dict, times: dict, parameters: FireCaseParameters) -> list[str]:
    problems = []
    periods = entry["periods"]
    if not isinstance(periods, list) or not periods:
        return ["Fire perimeters: the family scores no period."]
    seen = set()
    for item in periods:
        if not isinstance(item, dict) or set(item) != {"period", "perimeters"}:
            problems.append(
                "Fire perimeters: each period must have exactly a `period` and its `perimeters`."
            )
            continue
        name, paths = item["period"], item["perimeters"]
        if name not in bounds:
            problems.append(f"Fire perimeters: unknown period `{name}`.")
            continue
        if name in seen:
            problems.append(f"Fire perimeters: the period {name} is listed twice.")
            continue
        seen.add(name)
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            problems.append(f"Fire perimeters, {name}: `perimeters` must list paths.")
            continue
        missing = [path for path in paths if path not in times]
        if missing:
            problems.append(f"Fire perimeters, {name}: not a perimeter of the file: {', '.join(missing)}.")
            continue
        start, end = bounds[name]
        outside = [path for path in paths if not start <= times[path] <= end]
        if outside:
            problems.append(f"Fire perimeters, {name}: outside the period: {', '.join(outside)}.")
        if len(set(paths)) < parameters.min_perimeters:
            problems.append(
                f"Fire perimeters, {name}: {len(set(paths))} perimeter(s); a period needs at least "
                f"{parameters.min_perimeters}."
            )
    return problems


def _check_weather(entry: dict, bounds: dict, h5: h5py.File) -> list[str]:
    problems = []
    periods, sets = entry["periods"], entry["station_sets"]
    if not isinstance(periods, list) or not periods:
        problems.append("Weather stations: the family scores no period.")
    else:
        unknown = [name for name in periods if name not in bounds]
        if unknown:
            problems.append(f"Weather stations: unknown period(s) {', '.join(map(str, unknown))}.")
        if len(set(periods)) != len(periods):
            problems.append("Weather stations: a period is listed twice.")
    if (
        not isinstance(sets, list)
        or not sets
        or not set(sets) <= set(STATION_SETS)
        or len(set(sets)) != len(sets)
    ):
        problems.append(
            f"Weather stations: `station_sets` must list some of {', '.join(STATION_SETS)}, once each."
        )
    if not _station_groups(h5):
        problems.append("Weather stations: the file has no station time series.")
    return problems


def check_case(definition, std_file) -> list[str]:
    """
    The problems of ``definition`` against the standard file ``std_file``, in words a person reads.

    An empty list means the definition can be run on the file.
    """
    problems, parameters = _check_document(definition)
    if parameters is None:
        return problems
    with h5py.File(std_file, "r") as h5:
        if TEMPLATE_ATTRIBUTE in h5.attrs:
            return problems + [TEMPLATE_REFUSAL]
        period_problems, bounds = _check_periods(definition, data_span(h5, parameters))
        problems += period_problems
        families = definition["families"]
        if not isinstance(families, list) or not families:
            return problems + ["The definition has no family of KPIs."]
        seen = set()
        times = perimeter_times(h5)
        for entry in families:
            name = entry.get("family") if isinstance(entry, dict) else None
            if name not in FAMILIES:
                problems.append(f"Unknown family `{name}`; FireBench knows {', '.join(FAMILIES)}.")
                continue
            if name in seen:
                problems.append(f"The family {name} is listed twice.")
                continue
            seen.add(name)
            if set(entry) != FAMILY_KEYS[name]:
                problems.append(
                    f"The family {name} must have exactly the keys {', '.join(sorted(FAMILY_KEYS[name]))}."
                )
                continue
            if name == "fire_perimeters":
                problems += _check_perimeters(entry, bounds, times, parameters)
            elif name == "weather_stations":
                problems += _check_weather(entry, bounds, h5)
            elif name == "building_damage" and not _has_dataset(h5, str(entry["dataset"])):
                problems.append(f"Building damage: `{entry['dataset']}` is not in the file.")
            elif name == "burn_severity_cbi":
                problem = _cbi_problem(h5, str(entry["dataset"]))
                if problem:
                    problems.append(f"Burn severity: {problem}")
            elif name == "canopy_cover_loss":
                problem = _canopy_problem(h5, str(entry["dataset"]), entry["canopy"])
                if problem:
                    problems.append(f"Canopy cover loss: {problem}")
    return problems


# ---------------------------
# The definition inside a standard file
# ---------------------------
def write_case_definition(std_file, definition: dict) -> str:
    """
    Write ``definition`` into the standard file at ``/benchmark_case/definition`` and return its hash.

    The canonical JSON is stored as a fixed-length byte string: the signing digest hashes a
    variable-length string as pointers, which can change from one read of the file to the next.
    An existing definition is replaced.
    """
    content = canonical_json(definition)
    digest = hashlib.sha256(content).hexdigest()
    with h5py.File(std_file, "a") as h5:
        if DEFINITION_PATH in h5:
            del h5[DEFINITION_PATH]
        dataset = h5.create_dataset(DEFINITION_PATH, data=np.array(content, dtype=f"S{len(content)}"))
        dataset.attrs["schema"] = np.bytes_(definition.get("schema", ""))
        dataset.attrs["sha256"] = np.bytes_(digest)
    return digest


def read_case_definition(std_file) -> dict | None:
    """The definition kept in a standard file, or None when it holds none. Its hash is checked."""
    with h5py.File(std_file, "r") as h5:
        dataset = h5.get(DEFINITION_PATH)
        if dataset is None:
            return None
        content = bytes(dataset[()])
        stated = _text(dataset.attrs.get("sha256", b""))
    if hashlib.sha256(content).hexdigest() != stated:
        raise CaseDefinitionError("The case definition in the file does not match its recorded SHA-256.")
    return json.loads(content.decode("utf-8"))
