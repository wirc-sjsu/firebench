"""
What a model output must hold to enter a benchmark case defined by a document (``fire_case``).

- ``write_model_output_template`` writes the observation file's layout for one case: the groups the
  case scores, at their paths, with the grids, positions, station times, and attributes a model
  output is written on, and no observed value.
- ``case_requirements`` lists what ``FireCase`` will check (schema ``fb-requirements-v1``), with the
  stations it selects in each period and station set.

Both read the observation file, because the station selection needs the observed values. The
template is marked by the root attribute ``firebench_template``; a case refuses one as its
observation file.
"""

import json
from importlib import metadata
from pathlib import Path

import h5py
import numpy as np

from .. import __version__ as fb_version
from .. import standardize as fs
from ..standardize.tools import REFERENCED_FILE_ATTRIBUTES
from . import wx_common as wxc
from .fire_case import STATION_SETS, load_case
from .fire_case_radar import model_requirements
from .fire_case_definition import (
    TEMPLATE_ATTRIBUTE,
    definition_sha256,
    family,
    write_case_definition,
)

TEMPLATE_KIND = "model-output"
REQUIREMENTS_SCHEMA = "fb-requirements-v1"
FAMILY_OF_KIND = {
    "B": "building_damage",
    "S": "burn_severity_cbi",
    "C": "canopy_cover_loss",
    "P": "fire_perimeters",
    "W": "weather_stations",
    "R": "radar_plume",
}
# Observed values a perimeter group carries beside its file reference.
PERIMETER_VALUES = ("burnt_area", "burnt_area_units")
INACCESSIBLE = "Inaccessible"
FILES_TEXT = "Each perimeter group references a KML file at `rel_path`, beside the output."
SENSOR_HEIGHT_TEXT = (
    "TSO stations: the model's `sensor_height` within "
    f"{fs.SENSOR_HEIGHT_MATCH_TOLERANCE_METERS:g} m of the observation's."
)
SENSOR_HEIGHT_EXEMPT_TEXT = "Not checked: this variable does not depend on the sensor height."


def _firebench_commit() -> str | None:
    """The commit FireBench was installed from, when pip recorded one."""
    try:
        text = metadata.distribution("firebench").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    return json.loads(text).get("vcs_info", {}).get("commit_id") if text else None


def _text(value) -> str:
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else str(value)


# ---------------------------
# Station selection
# ---------------------------
def _selections(case, obs: h5py.File) -> list[dict]:
    """``select_weather_stations`` for each variable, period, and station set of the definition."""
    entry = family(case.definition, "weather_stations")
    if entry is None:
        return []
    ctx: dict = {}
    selections = []
    for spec in case.WX_VARIABLE_SPECS:
        for period in entry["periods"]:
            for set_name in entry["station_sets"]:
                selection = wxc.select_weather_stations(
                    obs, spec["variable"], case.periods[period], STATION_SETS[set_name][1], ctx
                )
                selections.append(
                    {
                        "variable": spec["variable"],
                        "period": period,
                        "station_set": set_name,
                        "included": [item["station"] for item in selection["included"]],
                        "excluded": [
                            {"station": item["station"], "reason": item["reason"]}
                            for item in selection["excluded"]
                        ],
                    }
                )
    return selections


def _selected_variables(selections: list[dict]) -> dict[str, list[str]]:
    """The variables each station is selected for, in the order of the parameter set."""
    stations: dict[str, list[str]] = {}
    for selection in selections:
        for station in selection["included"]:
            variables = stations.setdefault(station, [])
            if selection["variable"] not in variables:
                variables.append(selection["variable"])
    return dict(sorted(stations.items()))


# ---------------------------
# Template
# ---------------------------
def _copy_attrs(source, target, leave_out=()) -> None:
    for key in source.attrs:
        if key not in leave_out:
            target.attrs.create(key, source.attrs[key], dtype=source.attrs.get_id(key).dtype)


def _group(out: h5py.File, obs: h5py.File, path: str) -> h5py.Group:
    """The group at ``path`` in the template, made with its parents and their attributes."""
    group = out["/"]
    for name in path.strip("/").split("/"):
        if name not in group:
            created = group.create_group(name)
            _copy_attrs(obs[created.name], created)
        group = group[name]
    return group


def _dataset(out: h5py.File, obs: h5py.File, path: str, data=None) -> None:
    """The dataset at ``path`` with its attributes, holding ``data``, or the observation's own values.

    Only positions, grids, and times are copied; anything observed is given as ``data``. A dataset is
    always written whole, never overwritten, so no observed byte is left in the file.
    """
    source = obs[path]
    parent, name = path.rsplit("/", 1)
    values = source[()] if data is None else data
    options = {"compression": "gzip", "shuffle": True} if np.ndim(values) and np.size(values) else {}
    dataset = _group(out, obs, parent).create_dataset(name, data=values, dtype=source.dtype, **options)
    _copy_attrs(source, dataset)


def _write_perimeters(out: h5py.File, obs: h5py.File, entry: dict) -> None:
    paths = []
    for item in entry["periods"]:
        paths += [path for path in item["perimeters"] if path not in paths]
    for path in paths:
        source = obs[path]
        parent, name = path.rsplit("/", 1)
        if isinstance(source, h5py.Group):
            target = _group(out, obs, parent).create_group(name)
        else:
            target = _group(out, obs, parent).create_dataset(
                name, data=np.zeros(source.shape, source.dtype)
            )
        _copy_attrs(source, target, leave_out=(*REFERENCED_FILE_ATTRIBUTES, *PERIMETER_VALUES))


def _write_grid(out: h5py.File, obs: h5py.File, entry: dict) -> None:
    """The grid of a family that names one (CBI, canopy cover loss), every value its `_FillValue`."""
    path = entry["dataset"]
    group = path.rsplit("/", 1)[0]
    source = obs[path]
    if "_FillValue" not in source.attrs:
        raise ValueError(f"`{path}` has no `_FillValue` to write the template's grid with.")
    _dataset(out, obs, f"{group}/position_lat")
    _dataset(out, obs, f"{group}/position_lon")
    _dataset(out, obs, path, np.full(source.shape, source.attrs["_FillValue"], dtype=source.dtype))


def _write_building_damage(out: h5py.File, obs: h5py.File, entry: dict) -> None:
    path = entry["dataset"]
    group = path.rsplit("/", 1)[0]
    values = np.asarray(obs[path][()])
    # Whether a building was surveyed is not what happened to it: "Inaccessible" stays.
    keep = np.array([_text(value).strip() == INACCESSIBLE for value in values.reshape(-1)], dtype=bool)
    blank = np.zeros_like(values)
    blank.reshape(-1)[keep] = values.reshape(-1)[keep]
    for name in ("position_lat", "position_lon"):
        if f"{group}/{name}" in obs:
            _dataset(out, obs, f"{group}/{name}")
    _dataset(out, obs, path, blank)


def _write_stations(out: h5py.File, obs: h5py.File, stations: dict[str, list[str]]) -> None:
    for station, variables in stations.items():
        path = f"/{fs.TIME_SERIES}/{station}"
        _group(out, obs, path)
        _dataset(out, obs, f"{path}/time")
        for variable in variables:
            source = obs[f"{path}/{variable}"]
            dtype = source.dtype if np.issubdtype(source.dtype, np.floating) else np.float64
            _dataset(out, obs, f"{path}/{variable}", np.full(source.shape, np.nan, dtype=dtype))


def _write_plume(out: h5py.File, entry: dict) -> None:
    """The group of the model's plume, empty: the model writes it on its own grid."""
    group = out.require_group(entry["model_group"])
    group.attrs["description"] = (
        "The model's plume on its own grid: time; position_lat and position_lon of the columns; "
        "position_z (m above mean sea level), passive_tracer (any scale), and wind_u, wind_v, wind_w "
        "(earth-relative, m/s), each (time, z, y, x). FireBench samples them on the radar cross sections "
        f"{', '.join(entry['sections'])}: the nearest column, then linear in height."
    )
    group.attrs["required_datasets"] = json.dumps(
        sorted(path.rsplit("/", 1)[-1] for path in model_requirements(entry["model_group"]))
    )


def write_model_output_template(std_file, definition: dict, out_path, *, overwrite: bool = False) -> Path:
    """
    Write the model-output template of ``definition`` on the observation file ``std_file``.

    The template keeps the groups the case scores, at the observation file's paths: each perimeter
    group with its attributes but no file reference and no burnt area; the CBI and canopy cover loss
    grids with their positions, every value its ``_FillValue``; the buildings' positions, each damage blank but
    ``"Inaccessible"``; and each station the case selects for some variable, period, and station set,
    with its ``time`` and, for each variable it is selected for, NaN values. Licence attributes go
    with each group. The definition is written in too, so an adapter can read the case from it.
    """
    case = load_case(definition, std_file)
    out_path = Path(out_path)
    with h5py.File(std_file, "r") as obs:
        stations = _selected_variables(_selections(case, obs))
        out = fs.new_std_file(out_path, authors=f"FireBench {fb_version}", overwrite=overwrite)
        try:
            out.attrs[TEMPLATE_ATTRIBUTE] = TEMPLATE_KIND
            out.attrs["case_definition_sha256"] = definition_sha256(definition)
            writers = {
                "fire_perimeters": _write_perimeters,
                "burn_severity_cbi": _write_grid,
                # The LANDFIRE layers stay out: the canopy mask is read from the observations.
                "canopy_cover_loss": _write_grid,
                "building_damage": _write_building_damage,
            }
            for entry in definition["families"]:
                if entry["family"] in writers:
                    writers[entry["family"]](out, obs, entry)
            plume = family(definition, "radar_plume")
            if plume is not None:
                _write_plume(out, plume)
            _write_stations(out, obs, stations)
        finally:
            out.close()
    write_case_definition(out_path, definition)
    return out_path


# ---------------------------
# Requirement list
# ---------------------------
def _sensor_heights(obs: h5py.File, stations: set[str], variable: str) -> list[float]:
    heights = set()
    for station in stations:
        path = f"/{fs.TIME_SERIES}/{station}/{variable}"
        try:
            height = fs.read_sensor_height(obs[path], dataset_path=path, allow_legacy_text=True)
        except (KeyError, ValueError):
            continue
        heights.add(round(float(height.magnitude), 2))
    return sorted(heights)


def case_requirements(definition: dict, std_file) -> dict:
    """
    What ``FireCase`` checks in a model output for ``definition``, on the observation file ``std_file``.

    One entry per requirement of the case, with its KPIs and KPI groups: the datasets and attributes
    it needs, and, for a weather variable, the stations FireBench selects in each period and station
    set. A ``summary`` gives the counts a page shows. Times are UTC with ``Z``.
    """
    case = load_case(definition, std_file)
    groups = case.describe_composable_groups()
    with h5py.File(std_file, "r") as obs:
        selections = _selections(case, obs)
        heights = {
            spec["variable"]: _sensor_heights(
                obs,
                {
                    station
                    for item in selections
                    if item["variable"] == spec["variable"]
                    for station in item["included"]
                },
                spec["variable"],
            )
            for spec in case.WX_VARIABLE_SPECS
        }

    requirements = []
    for name, requirement in case.REQUIREMENTS.items():
        kpis = list(requirement["benchmarks"])
        held = [group for group in groups if set(group["kpis"]) & set(kpis)]
        kind = held[0]["kind"] if held else None
        item = {
            "name": name,
            "family": FAMILY_OF_KIND.get(kind),
            "kpi_groups": [group["name"] for group in held],
            "kpis": kpis,
        }
        if kind == "W":
            variable = requirement["required_datasets"]["variable"]
            item["variable"] = variable
            item["stations"] = [
                {key: value for key, value in selection.items() if key != "variable"}
                for selection in selections
                if selection["variable"] == variable
            ]
            item["at_observation_times"] = True
            item["sensor_height"] = (
                SENSOR_HEIGHT_TEXT if fs.tso_requires_sensor_height(variable) else SENSOR_HEIGHT_EXEMPT_TEXT
            )
        else:
            item["datasets"] = {
                path: list(attrs) for path, attrs in requirement["required_datasets"].items()
            }
        if kind == "P":
            item["period"] = held[0]["period"]["target"]
            item["files"] = FILES_TEXT
        requirements.append(item)

    perimeters = set()
    for entry in (family(definition, "fire_perimeters") or {}).get("periods", []):
        perimeters.update(entry["perimeters"])
    weather = []
    for spec in case.WX_VARIABLE_SPECS:
        mine = [item for item in selections if item["variable"] == spec["variable"]]
        stations = {station for item in mine for station in item["included"]}
        if not mine:
            continue
        weather.append(
            {
                "variable": spec["variable"],
                "label": spec["label"],
                "stations": len(stations),
                "tso_stations": len(
                    {
                        station
                        for item in mine
                        if item["station_set"] == "TSO"
                        for station in item["included"]
                    }
                ),
                "sensor_heights_m": heights[spec["variable"]],
            }
        )
    return {
        "schema": REQUIREMENTS_SCHEMA,
        "case": {
            "name": definition["name"],
            "definition_sha256": definition_sha256(definition),
            "parameters": dict(definition["parameters"]),
        },
        "firebench": {"version": fb_version, "commit": _firebench_commit()},
        "periods": [dict(period) for period in definition["periods"]],
        "requirements": requirements,
        "summary": {
            "families": [entry["family"] for entry in definition["families"]],
            "periods": len({group["period"]["target"] for group in groups if group["period"]}),
            "perimeters": len(perimeters),
            "weather": weather,
        },
    }
