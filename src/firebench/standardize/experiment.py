"""
Sensors and soundings of a field experiment in the FireBench standard file.

An experiment has *platforms* (a tower, a station, a launch site, a tether line) and *sensors*, the
series of one file at a platform:

- ``fixed``: a time series at one height (a sonic anemometer, a weather station), written under
  ``/time_series/<platform>/<sensor>``;
- ``array``: several heights on one time axis (a thermocouple tower), written under
  ``/spatial_1d/<platform>/<sensor>`` as ``(time, z)``;
- ``moving``: a position per sample (a radiosonde, a tethersonde), written under
  ``/time_series/<platform>/<sensor>`` with its positions as datasets.

The platform's group holds its position, in geographic coordinates or relative to a reference point
of the experiment (one convention per group, as the standard asks). A *sensor sheet* lists the
reference points and the sensors (:func:`read_sensor_sheet`).

A file is read through a :class:`TableRecipe`: how to split it, which column is which variable in
which unit, how its times are built, and its UTC offset. :func:`sniff_table` proposes one from the
file; a file in FireBench's *sensor table* (a ``time`` column in ISO 8601 with its offset, and
columns named ``<variable>[<unit>]``) needs nothing more. :func:`read_sensor_table` applies it and
:func:`write_sensor` writes the sensor's groups. :func:`experiment_geographic` gives the longitude,
latitude, and altitude of a group in either convention, for display.
"""

# pylint: disable=too-many-lines

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import h5py
import hdf5plugin
import numpy as np
import pint
import yaml
from pyproj import Transformer

from ..tools.namespace import StandardVariableNames as svn
from ..tools.units import ureg
from .std_file_info import SPATIAL_1D, TIME_SERIES
from .tools import check_std_version

RECIPE_VERSION = 1
CRS = "EPSG:4326"
SENSOR_KINDS = ("fixed", "array", "moving")
TIME_KINDS = ("iso", "format", "components", "date_decimal_hours", "year_doy_hhmm", "counter")
# The columns each way of building time reads, required then optional.
TIME_ROLES = {
    "iso": (("time",), ()),
    "format": (("time",), ()),
    "components": (("year", "month", "day", "hour"), ("minute", "second")),
    "date_decimal_hours": (("hours",), ()),
    "year_doy_hhmm": (("year", "doy", "hhmm"), ()),
    "counter": (("counter",), ()),
}
# u positive eastward and v northward (the standard), or u positive westward and v southward.
WIND_CONVENTIONS = ("u_east_v_north", "u_west_v_south")
DELIMITERS = ("\t", ",", ";", None)
SAMPLE_ROWS = 10
SNIFF_LINES = 200
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# A column of the sensor table: `<variable>[<unit>]`, or `<variable>@<height>m[<unit>]` in an array.
TABLE_COLUMN = re.compile(r"^(?P<variable>[a-z0-9_]+)(?:@(?P<height>[-+0-9.eE]+)m?)?\[(?P<unit>[^\]]+)\]$")
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP = b"PK\x03\x04"

# The variables a sensor records, with the units FireBench stores them in.
SENSOR_VARIABLES = {
    svn.ABSOLUTE_HUMIDITY.value: ("kg/m**3", "Absolute humidity, mass of water vapour per volume of air"),
    svn.AIR_PRESSURE.value: ("Pa", "Air pressure"),
    svn.AIR_TEMPERATURE.value: ("K", "Air temperature"),
    svn.CO2_MASS_CONCENTRATION.value: ("kg/m**3", "Mass concentration of carbon dioxide in air"),
    svn.DEW_POINT_TEMPERATURE.value: ("K", "Dew point temperature"),
    svn.POTENTIAL_TEMPERATURE.value: ("K", "Potential temperature"),
    svn.RELATIVE_HUMIDITY.value: ("percent", "Relative humidity"),
    svn.SOLAR_RADIATION.value: ("W/m**2", "Solar radiation"),
    svn.SONIC_TEMPERATURE.value: ("K", "Sonic temperature of a sonic anemometer"),
    svn.SPECIFIC_HUMIDITY.value: ("kg/kg", "Specific humidity"),
    svn.TEMPERATURE.value: ("K", "Temperature, e.g. a thermocouple in the fuel"),
    svn.WATER_VAPOR_MIXING_RATIO.value: ("kg/kg", "Water vapour mixing ratio"),
    svn.WIND_DIRECTION.value: ("degree", "Direction the wind blows from, clockwise from true north"),
    svn.WIND_GUST.value: ("m/s", "Wind gust"),
    svn.WIND_SPEED.value: ("m/s", "Wind speed"),
    svn.WIND_SPEED_U.value: ("m/s", "Eastward wind component"),
    svn.WIND_SPEED_V.value: ("m/s", "Northward wind component"),
    svn.WIND_SPEED_W.value: ("m/s", "Upward wind component"),
}
# The position of a moving sensor's sample: geographic, or relative to its platform.
POSITION_VARIABLES = {
    "position_lat": ("degree", "Latitude of the sample"),
    "position_lon": ("degree", "Longitude of the sample"),
    "position_alt": ("m", "Altitude of the sample above mean sea level"),
    "position_x": ("m", "Distance of the sample along +x from its platform"),
    "position_y": ("m", "Distance of the sample along +y from its platform"),
    "position_z": ("m", "Height of the sample above its platform"),
}
# Pint reads `mb` as a millibarn.
UNIT_HINTS = {"mb": "Pint reads `mb` as a millibarn: write `mbar` or `hPa`."}


# --- The sensor sheet ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferencePoint:
    """A surveyed point of the experiment that relative positions start from.

    ``axes_azimuth`` is the azimuth of +y in degrees, clockwise from true north: 0 has x east and y
    north, 90 has y east and x south.
    """

    name: str
    lat: float
    lon: float
    alt: float
    axes_azimuth: float = 0.0

    def __post_init__(self):
        _check_name(self.name, "reference point")
        _check_lat_lon(self.lat, self.lon, f"reference point {self.name}")


@dataclass(frozen=True)
class GeographicPosition:
    """A position in degrees and metres above mean sea level."""

    lat: float
    lon: float
    alt: float


@dataclass(frozen=True)
class RelativePosition:
    """A position in metres from a reference point, along its axes."""

    reference: str
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True)
class SensorRow:  # pylint: disable=too-many-instance-attributes
    """One sensor of the sheet: the series of one file at a platform.

    ``position`` is the platform's. ``height`` is the sensor's above the ground (a fixed sensor);
    ``averaging_period`` is in seconds; ``file`` names the file the sensor's series is read from.
    """

    id: str
    platform: str
    kind: Literal["fixed", "array", "moving"]
    position: GeographicPosition | RelativePosition
    file: str | None = None
    height: float | None = None
    instrument: str = ""
    averaging_period: float | None = None
    wind_convention: str | None = None
    licence: str = ""
    description: str = ""

    def __post_init__(self):
        _check_name(self.id, "sensor")
        _check_name(self.platform, f"platform of sensor {self.id}")
        if self.kind not in SENSOR_KINDS:
            raise ValueError(
                f"Sensor {self.id}: its kind is one of {', '.join(SENSOR_KINDS)}, not `{self.kind}`."
            )
        if self.wind_convention is not None and self.wind_convention not in WIND_CONVENTIONS:
            raise ValueError(
                f"Sensor {self.id}: its wind convention is one of {', '.join(WIND_CONVENTIONS)}, "
                f"not `{self.wind_convention}`."
            )
        if isinstance(self.position, GeographicPosition):
            _check_lat_lon(self.position.lat, self.position.lon, f"sensor {self.id}")


@dataclass(frozen=True)
class SensorSheet:
    """The reference points of an experiment and its sensors."""

    reference_points: tuple[ReferencePoint, ...] = ()
    sensors: tuple[SensorRow, ...] = ()

    def __post_init__(self):
        names = [point.name for point in self.reference_points]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"The sheet names the reference point {repeated[0]} twice.")
        keys = [(row.platform, row.id) for row in self.sensors]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"The sheet lists the sensor {repeated[0][1]} of {repeated[0][0]} twice.")

    def reference(self, name: str) -> ReferencePoint:
        """The reference point named ``name``."""
        for point in self.reference_points:
            if point.name == name:
                return point
        raise ValueError(f"The sheet has no reference point named {name}.")

    def row_for_file(self, filename: str) -> SensorRow:
        """The sensor whose series is read from the file named ``filename``."""
        for row in self.sensors:
            if row.file == filename:
                return row
        raise ValueError(f"No sensor of the sheet names the file {filename}.")


SHEET_COLUMNS = (
    "id",
    "platform",
    "kind",
    "file",
    "lat",
    "lon",
    "alt",
    "reference",
    "x",
    "y",
    "z",
    "axes_azimuth",
    "height",
    "instrument",
    "averaging_period",
    "wind_convention",
    "licence",
    "description",
)


def read_sensor_sheet(path: Path | str) -> SensorSheet:
    """Read a sensor sheet, CSV or YAML.

    A CSV sheet has one row per record, with the columns of ``SHEET_COLUMNS``: a reference point is a
    row of kind ``reference`` (its name in ``id``), a sensor a row of kind ``fixed``, ``array``, or
    ``moving``. A YAML sheet has the lists ``reference_points`` and ``sensors`` with the same keys.
    A position is ``lat``, ``lon``, ``alt``, or ``reference``, ``x``, ``y``, ``z``: never both.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in {".yaml", ".yml"}:
        content = yaml.safe_load(text) or {}
        if not isinstance(content, dict):
            raise ValueError(f"{path.name}: a YAML sheet holds `reference_points` and `sensors`.")
        points = [_reference_point(item) for item in content.get("reference_points") or []]
        sensors = [_sensor_row(item) for item in content.get("sensors") or []]
    else:
        points, sensors = [], []
        for number, item in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            item = {key.strip(): (value or "").strip() for key, value in item.items() if key}
            try:
                if item.get("kind") == "reference":
                    points.append(_reference_point(item | {"name": item.get("id")}))
                elif any(item.values()):
                    sensors.append(_sensor_row(item))
            except ValueError as error:
                raise ValueError(f"{path.name}, line {number}: {error}") from error
    return SensorSheet(reference_points=tuple(points), sensors=tuple(sensors))


def sheet_position(sheet: SensorSheet, row: SensorRow) -> GeographicPosition | RelativePosition:
    """The platform's position the row gives, checked against the other sensors of the platform."""
    for other in sheet.sensors:
        if other.platform != row.platform or other is row:
            continue
        if type(other.position) is not type(row.position):
            raise ValueError(
                f"The sensors of platform {row.platform} mix geographic and relative positions: give one."
            )
        if not _same_position(other.position, row.position):
            raise ValueError(f"The sensors of platform {row.platform} give it different positions.")
    if isinstance(row.position, RelativePosition):
        sheet.reference(row.position.reference)
    return row.position


def _reference_point(item: dict) -> ReferencePoint:
    return ReferencePoint(
        name=str(item.get("name") or ""),
        lat=_required_float(item, "lat", "reference point"),
        lon=_required_float(item, "lon", "reference point"),
        alt=_required_float(item, "alt", "reference point"),
        axes_azimuth=_float(item.get("axes_azimuth")) or 0.0,
    )


def _sensor_row(item: dict) -> SensorRow:
    sensor = str(item.get("id") or "")
    geographic = any(_present(item.get(key)) for key in ("lat", "lon"))
    relative = _present(item.get("reference"))
    if geographic and relative:
        raise ValueError(
            f"Sensor {sensor}: give its platform's latitude and longitude or a reference point, not both."
        )
    what = f"sensor {sensor}"
    if relative:
        position = RelativePosition(
            reference=str(item["reference"]),
            x=_required_float(item, "x", what),
            y=_required_float(item, "y", what),
            z=_float(item.get("z")) or 0.0,
        )
    elif geographic:
        position = GeographicPosition(
            lat=_required_float(item, "lat", what),
            lon=_required_float(item, "lon", what),
            alt=_required_float(item, "alt", what),
        )
    else:
        raise ValueError(
            f"Sensor {sensor}: give its platform's position, geographic or from a reference point."
        )
    return SensorRow(
        id=sensor,
        platform=str(item.get("platform") or ""),
        kind=str(item.get("kind") or ""),
        position=position,
        file=str(item["file"]) if _present(item.get("file")) else None,
        height=_float(item.get("height")),
        instrument=str(item.get("instrument") or ""),
        averaging_period=_float(item.get("averaging_period")),
        wind_convention=str(item["wind_convention"]) if _present(item.get("wind_convention")) else None,
        licence=str(item.get("licence") or ""),
        description=str(item.get("description") or ""),
    )


# --- The recipe ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReaderRecipe:
    """How a file is split into rows and columns.

    ``delimited``: ``delimiter`` is a tab, a comma, or a semicolon, or null for white space.
    ``workbook``: ``sheet`` is the name of a sheet of an ``.xls`` or ``.xlsx`` file (the first one
    when null). ``skip_rows`` lines come before the header, or before the data without one; without a
    header, the columns are named ``column_1``, ``column_2``, …
    """

    kind: Literal["delimited", "workbook"] = "delimited"
    delimiter: str | None = None
    skip_rows: int = 0
    header: bool = True
    sheet: str | None = None


@dataclass(frozen=True)
class ColumnRecipe:
    """A column of the file: a variable and the unit it is written in, or ignored (variable null).

    ``height`` (m) is the height of the column's sensor in an array.
    """

    column: str
    variable: str | None = None
    unit: str | None = None
    height: float | None = None


@dataclass(frozen=True)
class TimeRecipe:
    """How the time of a row is built, in the file's local time unless a value states its offset.

    ``columns`` maps each role of ``kind`` (``TIME_ROLES``) to a column. ``format`` is the
    ``strptime`` format of ``format``; ``date`` (YYYY-MM-DD) the day of ``date_decimal_hours``, whose
    times are rounded to the second;
    ``start`` (ISO 8601) the time at which ``counter`` equals ``counter_origin``, counted in
    ``counter_units``.
    """

    kind: str
    columns: dict[str, str] = field(default_factory=dict)
    format: str | None = None
    date: str | None = None
    start: str | None = None
    counter_origin: float = 0.0
    counter_units: str = "s"


@dataclass(frozen=True)
class TableRecipe:  # pylint: disable=too-many-instance-attributes
    """How to read one file of a sensor.

    ``utc_offset`` is a fixed offset in hours (−6 for CST), never a daylight saving time. Values in
    ``missing_values`` are missing. ``wind_convention`` says how the file signs u and v;
    ``height_reference`` what its heights are measured from.
    """

    reader: ReaderRecipe = field(default_factory=ReaderRecipe)
    columns: tuple[ColumnRecipe, ...] = ()
    time: TimeRecipe | None = None
    utc_offset: float | None = None
    missing_values: tuple[str, ...] = ()
    wind_convention: str = WIND_CONVENTIONS[0]
    height_reference: str | None = None
    version: int = RECIPE_VERSION

    def to_dict(self) -> dict:
        """The recipe's JSON form, which `from_dict` reads back."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "TableRecipe":
        """A recipe from its JSON form, every field checked."""
        if not isinstance(value, dict):
            raise ValueError("A recipe is a JSON object.")
        _known_keys(value, cls, "recipe")
        if value.get("version", RECIPE_VERSION) != RECIPE_VERSION:
            raise ValueError(f"This FireBench reads recipes of version {RECIPE_VERSION}.")
        reader = value.get("reader") or {}
        _known_keys(reader, ReaderRecipe, "reader")
        columns = []
        for item in value.get("columns") or []:
            _known_keys(item, ColumnRecipe, "column")
            columns.append(ColumnRecipe(**item))
        time = value.get("time")
        if time is not None:
            _known_keys(time, TimeRecipe, "time")
            time = TimeRecipe(**time)
        recipe = cls(
            reader=ReaderRecipe(**reader),
            columns=tuple(columns),
            time=time,
            utc_offset=value.get("utc_offset"),
            missing_values=tuple(str(item) for item in value.get("missing_values") or ()),
            wind_convention=value.get("wind_convention") or WIND_CONVENTIONS[0],
            height_reference=value.get("height_reference"),
        )
        check_recipe(recipe)
        return recipe

    @classmethod
    def load(cls, path: Path | str) -> "TableRecipe":
        """A recipe from a JSON or YAML file."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        content = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
        return cls.from_dict(content)


def check_recipe(recipe: TableRecipe) -> None:
    """Refuse a recipe that cannot be applied, whatever the file: a `ValueError` with the reason."""
    reader = recipe.reader
    if reader.kind not in ("delimited", "workbook"):
        raise ValueError(f"The reader is `delimited` or `workbook`, not `{reader.kind}`.")
    if reader.delimiter not in DELIMITERS:
        raise ValueError("The delimiter is a tab, a comma, a semicolon, or white space.")
    if reader.skip_rows < 0:
        raise ValueError("The rows to skip cannot be negative.")
    if recipe.wind_convention not in WIND_CONVENTIONS:
        raise ValueError(f"The wind convention is one of {', '.join(WIND_CONVENTIONS)}.")
    if recipe.utc_offset is not None and not -14 <= recipe.utc_offset <= 14:
        raise ValueError("The UTC offset is in hours, from −14 to +14.")
    seen = {}
    for column in recipe.columns:
        if column.variable is None:
            continue
        units = _variable_units(column.variable)
        if column.unit is None:
            raise ValueError(f"Column {column.column}: give the unit of {column.variable}.")
        _check_unit(column.unit, units, column.column)
        key = (column.variable, column.height)
        if key in seen:
            at = f" at {column.height:g} m" if column.height is not None else ""
            raise ValueError(f"Columns {seen[key]} and {column.column} both give {column.variable}{at}.")
        seen[key] = column.column
    if recipe.time is not None:
        _check_time_recipe(recipe.time)


def table_recipe_schema() -> dict:
    """The JSON schema of a recipe's JSON form (`TableRecipe.to_dict`)."""
    number = {"type": ["number", "null"]}
    text = {"type": ["string", "null"]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "FireBench table recipe",
        "type": "object",
        "additionalProperties": False,
        "required": ["reader", "columns", "time"],
        "properties": {
            "version": {"const": RECIPE_VERSION},
            "reader": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"enum": ["delimited", "workbook"]},
                    "delimiter": {"enum": list(DELIMITERS)},
                    "skip_rows": {"type": "integer", "minimum": 0},
                    "header": {"type": "boolean"},
                    "sheet": text,
                },
            },
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["column"],
                    "properties": {
                        "column": {"type": "string"},
                        "variable": text,
                        "unit": text,
                        "height": number,
                    },
                },
            },
            "time": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": ["kind"],
                "properties": {
                    "kind": {"enum": list(TIME_KINDS)},
                    "columns": {"type": "object", "additionalProperties": {"type": "string"}},
                    "format": text,
                    "date": text,
                    "start": text,
                    "counter_origin": {"type": "number"},
                    "counter_units": {"type": "string"},
                },
            },
            "utc_offset": number,
            "missing_values": {"type": "array", "items": {"type": "string"}},
            "wind_convention": {"enum": list(WIND_CONVENTIONS)},
            "height_reference": text,
        },
    }


def experiment_variables() -> list[dict]:
    """The variables a column can be mapped to, with the units FireBench stores them in."""
    variables = [
        {"name": name, "units": units, "description": text, "position": False}
        for name, (units, text) in SENSOR_VARIABLES.items()
    ]
    variables += [
        {"name": name, "units": units, "description": text, "position": True}
        for name, (units, text) in POSITION_VARIABLES.items()
    ]
    return variables


# --- Reading a file --------------------------------------------------------------------------------


@dataclass(frozen=True)
class TableSniff:  # pylint: disable=too-many-instance-attributes
    """What a file looks like, and a recipe to read it.

    ``rows`` are the first rows as text. ``first_time`` and ``last_time`` are the times the recipe
    gives the first and last rows, in UTC, or ``time_problem`` says why it gives none.
    """

    reader: ReaderRecipe
    columns: list[str]
    rows: list[list[str]]
    n_rows: int
    recipe: TableRecipe
    sheets: list[str] = field(default_factory=list)
    first_time: str | None = None
    last_time: str | None = None
    time_problem: str | None = None


@dataclass(frozen=True)
class SensorColumn:
    """A variable of a sensor, in the units FireBench stores it in."""

    variable: str
    units: str
    height: float | None
    values: np.ndarray


@dataclass(frozen=True)
class SensorTable:
    """A file read through its recipe: times in UTC, values converted, missing values NaN."""

    time: np.ndarray  # datetime64[ms], UTC
    columns: tuple[SensorColumn, ...]
    recipe: TableRecipe
    source_file: str
    source_sha256: str

    def column(self, variable: str) -> SensorColumn | None:
        """The column of ``variable``, or None (the first one in an array)."""
        for column in self.columns:
            if column.variable == variable:
                return column
        return None


@dataclass
class _Grid:
    header: list[str]
    rows: list[list]


def file_kind(path: Path | str) -> Literal["xls", "xlsx", "text"]:
    """Whether a file is an Excel 97 workbook, an Office Open XML workbook, or text."""
    with open(path, "rb") as stream:
        head = stream.read(8)
    if head == OLE2:
        return "xls"
    if head.startswith(ZIP):
        return "xlsx"
    return "text"


def sniff_table(path: Path | str, recipe: TableRecipe | None = None) -> TableSniff:
    """Look at a file and propose a recipe for it, or apply the one given to compute its times.

    The proposal finds the reader (delimiter, title lines, header), maps a column named
    ``<variable>[<unit>]`` to that variable, and takes a ``time`` column in ISO 8601, date-part
    columns (year, month, day, hour, …), or year, day-of-year, and HHMM columns as the time.
    """
    path = Path(path)
    kind = file_kind(path)
    sheets = _workbook_sheets(path, kind) if kind != "text" else []
    if recipe is None:
        reader = _sniff_reader(path, kind, sheets)
        grid = _read_grid(path, reader)
        recipe = _propose(grid, reader)
    else:
        check_recipe(recipe)
        reader = recipe.reader
        grid = _read_grid(path, reader)
    first = last = problem = None
    try:
        times = _times(grid, recipe)
        if times:
            first, last = (_iso_z(times[0]), _iso_z(times[-1]))
    except ValueError as error:
        problem = str(error)
    return TableSniff(
        reader=reader,
        columns=list(grid.header),
        rows=[[_cell_text(value) for value in row] for row in grid.rows[:SAMPLE_ROWS]],
        n_rows=len(grid.rows),
        recipe=recipe,
        sheets=sheets,
        first_time=first,
        last_time=last,
        time_problem=problem,
    )


def read_sensor_table(path: Path | str, recipe: TableRecipe) -> SensorTable:
    """Read a file through its recipe: a `ValueError` with the reason when the recipe does not fit it."""
    path = Path(path)
    check_recipe(recipe)
    grid = _read_grid(path, recipe.reader)
    times = _times(grid, recipe)
    missing = set(recipe.missing_values)
    columns = []
    for column in recipe.columns:
        if column.variable is None:
            continue
        index = _column_index(grid, column.column)
        raw = np.array([_number(row[index] if index < len(row) else None, missing) for row in grid.rows])
        units = _variable_units(column.variable)
        values = _convert(raw, column.unit, units, column.column)
        columns.append(SensorColumn(column.variable, units, column.height, values))
    if not any(column.variable not in POSITION_VARIABLES for column in columns):
        raise ValueError(f"{path.name}: the recipe maps no column to a variable.")
    return SensorTable(
        time=np.array([value.replace(tzinfo=None) for value in times], dtype="datetime64[ms]"),
        columns=tuple(columns),
        recipe=recipe,
        source_file=path.name,
        source_sha256=_sha256(path),
    )


def _workbook_sheets(path: Path, kind: str) -> list[str]:
    if kind == "xls":
        xlrd = _workbook_module("xlrd")
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            return [sheet.name for sheet in book.sheets() if sheet.nrows]
        finally:
            book.release_resources()
    openpyxl = _workbook_module("openpyxl")
    book = openpyxl.load_workbook(str(path), read_only=True)
    try:
        return [sheet.title for sheet in book.worksheets if sheet.max_row and sheet.max_row > 0]
    finally:
        book.close()


def _workbook_module(name: str):
    try:
        return __import__(name)
    except ImportError as error:
        raise ValueError(
            "Reading a workbook needs FireBench's extra `experiment`: pip install 'firebench[experiment]'."
        ) from error


def _sniff_reader(path: Path, kind: str, sheets: list[str]) -> ReaderRecipe:
    if kind != "text":
        if not sheets:
            raise ValueError(f"{path.name}: the workbook has no sheet with data.")
        rows = _workbook_rows(path, kind, sheets[0])
        lines = [[_cell_text(value) for value in row] for row in rows[:SNIFF_LINES]]
        skip, header = _sniff_layout(lines)
        return ReaderRecipe(kind="workbook", sheet=sheets[0], skip_rows=skip, header=header)
    lines = [line for line in _text_lines(path)[:SNIFF_LINES] if line.strip()]
    if not lines:
        raise ValueError(f"{path.name} is empty.")
    best, best_score = None, (0, 0.0)
    for order, delimiter in enumerate(DELIMITERS):
        counts = [len(_split(line, delimiter)) for line in lines]
        modal = max(set(counts), key=counts.count)
        if modal < 2:
            continue
        score = (counts.count(modal), -order)
        if score > best_score:
            best, best_score = delimiter, score
    if best_score[0] == 0:
        raise ValueError(f"{path.name}: no delimiter splits its lines into columns.")
    skip, header = _sniff_layout([_split(line, best) for line in lines])
    return ReaderRecipe(kind="delimited", delimiter=best, skip_rows=skip, header=header)


def _sniff_layout(lines: list[list[str]]) -> tuple[int, bool]:
    """Title lines to skip, and whether a header follows: lines are cut into fields already."""
    counts = [len([value for value in line if value != ""]) for line in lines]
    modal = max(set(counts), key=counts.count)
    skip = 0
    while skip < len(lines) - 1 and counts[skip] != modal:
        skip += 1
    first = lines[skip]
    header = (
        skip + 1 < len(lines)
        and not any(_is_number(value) for value in first if value != "")
        and any(_is_number(value) for value in lines[skip + 1])
    )
    return skip, header


def _read_grid(path: Path, reader: ReaderRecipe) -> _Grid:
    if reader.kind == "workbook":
        kind = file_kind(path)
        if kind == "text":
            raise ValueError(f"{path.name} is not a workbook.")
        sheets = _workbook_sheets(path, kind)
        sheet = reader.sheet or (sheets[0] if sheets else None)
        if sheet not in sheets:
            raise ValueError(f"{path.name} has no sheet named {sheet} with data.")
        rows = _workbook_rows(path, kind, sheet)
    else:
        if file_kind(path) != "text":
            raise ValueError(f"{path.name} is a workbook: read it as one.")
        rows = [_split(line, reader.delimiter) for line in _text_lines(path)]
    rows = rows[reader.skip_rows :]
    if reader.header:
        if not rows:
            raise ValueError(f"{path.name} has no header line after {reader.skip_rows} skipped lines.")
        header = [_cell_text(value) or f"column_{index + 1}" for index, value in enumerate(rows[0])]
        rows = rows[1:]
    else:
        width = max((len(row) for row in rows), default=0)
        header = [f"column_{index + 1}" for index in range(width)]
    rows = [row for row in rows if any(_cell_text(value) for value in row)]
    if not rows:
        raise ValueError(f"{path.name} has no data row.")
    return _Grid(header=header, rows=rows)


def _workbook_rows(path: Path, kind: str, sheet: str) -> list[list]:
    if kind == "xls":
        xlrd = _workbook_module("xlrd")
        book = xlrd.open_workbook(str(path))
        table = book.sheet_by_name(sheet)
        rows = []
        for index in range(table.nrows):
            row = []
            for column, value in enumerate(table.row_values(index)):
                if table.cell_type(index, column) == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                row.append(value)
            rows.append(row)
        return rows
    openpyxl = _workbook_module("openpyxl")
    book = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        return [
            ["" if value is None else value for value in row]
            for row in book[sheet].iter_rows(values_only=True)
        ]
    finally:
        book.close()


def _text_lines(path: Path) -> list[str]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return text.splitlines()


def _split(line: str, delimiter: str | None) -> list[str]:
    if delimiter is None:
        return line.split()
    return [value.strip() for value in next(csv.reader([line], delimiter=delimiter))]


def _propose(grid: _Grid, reader: ReaderRecipe) -> TableRecipe:
    columns = []
    for name in grid.header:
        match = TABLE_COLUMN.match(name.strip())
        known = match and (match["variable"] in SENSOR_VARIABLES or match["variable"] in POSITION_VARIABLES)
        if known:
            height = float(match["height"]) if match["height"] else None
            columns.append(ColumnRecipe(name, match["variable"], match["unit"], height))
        else:
            columns.append(ColumnRecipe(name))
    time = _propose_time(grid)
    roles = set(time.columns.values()) if time else set()
    columns = [column for column in columns if column.column not in roles or column.variable]
    recipe = TableRecipe(reader=reader, columns=tuple(columns), time=time)
    try:
        check_recipe(recipe)
    except ValueError:
        # A column whose unit Pint does not know is left for the builder to map.
        recipe = replace(
            recipe,
            columns=tuple(column if _fits(column) else ColumnRecipe(column.column) for column in columns),
        )
    return recipe


def _fits(column: ColumnRecipe) -> bool:
    try:
        check_recipe(TableRecipe(columns=(column,)))
        return True
    except ValueError:
        return False


def _propose_time(grid: _Grid) -> TimeRecipe | None:
    names = {_bare(name): name for name in grid.header}
    if "time" in names:
        index = _column_index(grid, names["time"])
        value = _cell_text(grid.rows[0][index]) if index < len(grid.rows[0]) else ""
        if _iso(value) is not None:
            return TimeRecipe(kind="iso", columns={"time": names["time"]})
    aliases = {
        "year": ("year", "yr", "yyyy"),
        "month": ("month", "mon", "mm"),
        "day": ("day", "dd"),
        "hour": ("hour", "hr", "hh"),
        "minute": ("minute", "min"),
        "second": ("second", "sec", "ss"),
        "doy": ("doy", "jday", "day_of_year", "julian_day"),
        "hhmm": ("hhmm", "hour", "time"),
    }
    found = {}
    for role, options in aliases.items():
        for option in options:
            if option in names:
                found[role] = names[option]
                break
    if all(role in found for role in ("year", "doy", "hhmm")) and "month" not in found:
        return TimeRecipe(
            kind="year_doy_hhmm", columns={role: found[role] for role in ("year", "doy", "hhmm")}
        )
    if all(role in found for role in ("year", "month", "day", "hour")):
        roles = ("year", "month", "day", "hour", "minute", "second")
        return TimeRecipe(kind="components", columns={role: found[role] for role in roles if role in found})
    return None


def _bare(name: str) -> str:
    """A column name without its unit or spaces, lower-case: `ta(C)` is `ta`."""
    name = re.sub(r"[\(\[].*$", "", name).strip().lower()
    return re.sub(r"[\s-]+", "_", name)


def _times(grid: _Grid, recipe: TableRecipe) -> list[datetime]:
    """The UTC time of every row: a `ValueError` naming the first row that has none or goes back."""
    time = recipe.time
    if time is None:
        raise ValueError("The recipe does not say how to build the time.")
    _check_time_recipe(time)
    indices = {role: _column_index(grid, column) for role, column in time.columns.items()}
    offset = None if recipe.utc_offset is None else timedelta(hours=recipe.utc_offset)
    times = []
    for number, row in enumerate(grid.rows, start=1):
        try:
            local = _row_time(
                time, {role: row[index] if index < len(row) else "" for role, index in indices.items()}
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Data row {number}: no time can be built from it ({error}).") from error
        if local.tzinfo is None:
            if offset is None:
                raise ValueError("The file's times state no UTC offset: give one.")
            local = local.replace(tzinfo=timezone(offset))
        value = local.astimezone(timezone.utc)
        if times and value <= times[-1]:
            what = "repeats the time of" if value == times[-1] else "goes back before"
            raise ValueError(f"Data row {number} {what} the row before ({_iso_z(value)}).")
        times.append(value)
    return times


def _row_time(time: TimeRecipe, cells: dict) -> datetime:  # pylint: disable=too-many-return-statements
    if time.kind == "iso":
        if isinstance(cells["time"], datetime):
            return cells["time"]
        value = _iso(_cell_text(cells["time"]))
        if value is None:
            raise ValueError(f"`{_cell_text(cells['time'])}` is not ISO 8601")
        return value
    if time.kind == "format":
        if isinstance(cells["time"], datetime):
            return cells["time"]
        return datetime.strptime(_cell_text(cells["time"]), time.format)
    if time.kind == "components":
        parts = {role: _cell_float(value) for role, value in cells.items()}
        return datetime(int(parts["year"]), int(parts["month"]), int(parts["day"])) + timedelta(
            hours=parts["hour"], minutes=parts.get("minute", 0.0), seconds=parts.get("second", 0.0)
        )
    if time.kind == "date_decimal_hours":
        # To the second: five decimals of an hour are 0.036 s.
        return datetime.combine(date.fromisoformat(time.date), datetime.min.time()) + timedelta(
            seconds=round(_cell_float(cells["hours"]) * 3600.0)
        )
    if time.kind == "year_doy_hhmm":
        hhmm = int(round(_cell_float(cells["hhmm"])))
        if hhmm % 100 >= 60:
            raise ValueError(f"{hhmm} is not HHMM")
        return datetime(int(_cell_float(cells["year"])), 1, 1) + timedelta(
            days=int(_cell_float(cells["doy"])) - 1, hours=hhmm // 100, minutes=hhmm % 100
        )
    seconds = ureg.Quantity(_cell_float(cells["counter"]) - time.counter_origin, time.counter_units).to("s")
    return datetime.fromisoformat(time.start) + timedelta(seconds=float(seconds.magnitude))


def _check_time_recipe(time: TimeRecipe) -> None:
    if time.kind not in TIME_KINDS:
        raise ValueError(
            f"The time is built one of these ways: {', '.join(TIME_KINDS)}; not `{time.kind}`."
        )
    required, optional = TIME_ROLES[time.kind]
    missing = [role for role in required if not time.columns.get(role)]
    if missing:
        raise ValueError(f"Time from {time.kind} needs the column of: {', '.join(missing)}.")
    unknown = sorted(set(time.columns) - set(required) - set(optional))
    if unknown:
        raise ValueError(f"Time from {time.kind} has no role {', '.join(unknown)}.")
    if time.kind == "format" and not time.format:
        raise ValueError("Give the format of the time column (e.g. %m/%d/%Y %H:%M).")
    if time.kind == "date_decimal_hours":
        try:
            date.fromisoformat(time.date or "")
        except ValueError as error:
            raise ValueError("Give the date the decimal hours count from, YYYY-MM-DD.") from error
    if time.kind == "counter":
        if not time.start or _iso(time.start) is None:
            raise ValueError("Give the time the counter starts from, in ISO 8601.")
        try:
            if ureg.Unit(time.counter_units).dimensionality != ureg.Unit("s").dimensionality:
                raise ValueError(f"The counter counts a duration, not `{time.counter_units}`.")
        except (pint.errors.PintError, AttributeError, TypeError) as error:
            raise ValueError(
                f"Pint does not know the unit `{time.counter_units}` of the counter."
            ) from error


def _column_index(grid: _Grid, column: str) -> int:
    try:
        return grid.header.index(column)
    except ValueError as error:
        raise ValueError(f"The file has no column {column}.") from error


def _variable_units(variable: str) -> str:
    if variable in SENSOR_VARIABLES:
        return SENSOR_VARIABLES[variable][0]
    if variable in POSITION_VARIABLES:
        return POSITION_VARIABLES[variable][0]
    raise ValueError(f"`{variable}` is not a variable FireBench reads from a sensor.")


def _check_unit(unit: str, target: str, column: str) -> None:
    try:
        parsed = ureg.Unit(unit)
    except (pint.errors.PintError, AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"Column {column}: Pint does not know the unit `{unit}`.") from error
    if parsed.dimensionality != ureg.Unit(target).dimensionality:
        hint = UNIT_HINTS.get(unit.strip(), "")
        raise ValueError(
            f"Column {column}: `{unit}` is not a unit of the same kind as {target}. {hint}".strip()
        )


def _convert(values: np.ndarray, unit: str, target: str, column: str) -> np.ndarray:
    _check_unit(unit, target, column)
    return np.asarray(ureg.Quantity(values, unit).to(target).magnitude, dtype=np.float64)


def _number(value, missing: set[str]) -> float:
    text = _cell_text(value)
    if text == "" or text in missing:
        return np.nan
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(text)
    except ValueError:
        return np.nan


def _cell_float(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return float(_cell_text(value))


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().strip('"')


def _is_number(value) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    try:
        float(str(value))
        return True
    except ValueError:
        return False


def _iso(value: str) -> datetime | None:
    text = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- Writing a sensor ------------------------------------------------------------------------------


def write_sensor(  # pylint: disable=too-many-arguments
    h5file: h5py.File,
    row: SensorRow,
    table: SensorTable,
    sheet: SensorSheet,
    *,
    terms: dict | None = None,
    compression_lvl: int = 6,
    overwrite: bool = False,
) -> list[h5py.Group]:
    """Write a sensor's data group under its platform's location group, and return the data groups.

    The location group holds the platform's position, in its convention, and is shared by the
    platform's sensors: a position that differs from the one already written is refused. ``terms``
    (licence attributes) are written on each data group, after the row's ``licence``. An array
    whose variables do not share their heights gets a data group per set of heights,
    ``<sensor>_<first variable>``.
    """
    check_std_version(h5file)
    position = sheet_position(sheet, row)
    variables = [column for column in table.columns if column.variable not in POSITION_VARIABLES]
    positions = {
        column.variable: column for column in table.columns if column.variable in POSITION_VARIABLES
    }
    _check_kind(row, variables, positions)
    root = SPATIAL_1D if row.kind == "array" else TIME_SERIES
    location = _location_group(h5file, root, row.platform, position, sheet)
    convention = row.wind_convention or table.recipe.wind_convention
    variables = [_standard_winds(column, convention) for column in variables]
    sets = _height_sets(variables) if row.kind == "array" else [variables]
    groups = []
    for index, members in enumerate(sets):
        name = row.id if len(sets) == 1 else f"{row.id}_{members[0].variable}"
        if name in location:
            if not overwrite:
                raise ValueError(f"The file already holds the sensor {name} of {row.platform}.")
            del location[name]
        group = location.create_group(name)
        _write_time(group, table.time, compression_lvl)
        if row.kind == "array":
            _write_array(group, members, compression_lvl, table.recipe.height_reference)
        else:
            for column in members:
                dataset = _dataset(group, column.variable, column.values, compression_lvl, column.units)
                if row.kind == "fixed":
                    dataset.attrs["sensor_height"] = float(row.height)
                    dataset.attrs["sensor_height_units"] = "m"
                    dataset.attrs["sensor_height_source"] = "sensor sheet"
        if row.kind == "moving" and index == 0:
            _write_track(group, positions, position, sheet, row, compression_lvl)
        _sensor_attrs(group, row, table, convention, variables)
        for key, value in (terms or {}).items():
            group.attrs[key] = value
        groups.append(group)
    return groups


def _check_kind(row: SensorRow, variables: list[SensorColumn], positions: dict) -> None:
    if row.kind != "moving" and positions:
        raise ValueError(f"Sensor {row.id}: only a moving sensor has a position per sample.")
    if row.kind == "array":
        if any(column.height is None for column in variables):
            raise ValueError(f"Sensor {row.id}: an array gives the height of each of its columns.")
    elif any(column.height is not None for column in variables):
        raise ValueError(
            f"Sensor {row.id}: a height per column is for an array; a {row.kind} sensor has one."
        )
    if row.kind == "fixed" and row.height is None:
        raise ValueError(f"Sensor {row.id}: give the height of the sensor above the ground.")


def _location_group(h5file, root: str, platform: str, position, sheet: SensorSheet) -> h5py.Group:
    attrs = _position_attrs(position, sheet)
    path = f"/{root}/{platform}"
    if path in h5file:
        group = h5file[path]
        written = {key: group.attrs.get(key) for key in attrs}
        if any(not _same_attr(written[key], value) for key, value in attrs.items()):
            raise ValueError(
                f"The file gives platform {platform} another position: one platform, one position."
            )
        return group
    group = h5file.require_group(path)
    for key, value in attrs.items():
        group.attrs[key] = value
    group.attrs["description"] = f"Platform {platform} of a field experiment"
    return group


def _position_attrs(position, sheet: SensorSheet) -> dict:
    if isinstance(position, GeographicPosition):
        return {
            "position_lat": float(position.lat),
            "position_lat_units": "degree",
            "position_lon": float(position.lon),
            "position_lon_units": "degree",
            "position_alt": float(position.alt),
            "position_alt_units": "m",
            "crs": CRS,
        }
    point = sheet.reference(position.reference)
    return _origin_attrs(point) | {
        "position_x": float(position.x),
        "position_x_units": "m",
        "position_y": float(position.y),
        "position_y_units": "m",
        "position_z": float(position.z),
        "position_z_units": "m",
    }


def _origin_attrs(point: ReferencePoint) -> dict:
    return {
        "position_origin_name": point.name,
        "position_origin_lat": float(point.lat),
        "position_origin_lat_units": "degree",
        "position_origin_lon": float(point.lon),
        "position_origin_lon_units": "degree",
        "position_origin_alt": float(point.alt),
        "position_origin_alt_units": "m",
        "position_axes_azimuth": float(point.axes_azimuth),
        "position_axes_azimuth_units": "degree",
        "crs": CRS,
    }


def _standard_winds(column: SensorColumn, convention: str) -> SensorColumn:
    """u eastward and v northward: a file that signs them the other way is turned."""
    flipped = convention == "u_west_v_south" and column.variable in (
        svn.WIND_SPEED_U.value,
        svn.WIND_SPEED_V.value,
    )
    return replace(column, values=-column.values) if flipped else column


def _height_sets(columns: list[SensorColumn]) -> list[list[SensorColumn]]:
    heights = {}
    for column in columns:
        heights.setdefault(column.variable, []).append(column.height)
    sets: dict[tuple, list[str]] = {}
    for variable, values in heights.items():
        sets.setdefault(tuple(sorted(values)), []).append(variable)
    return [[column for column in columns if column.variable in variables] for variables in sets.values()]


def _write_time(group: h5py.Group, time: np.ndarray, compression_lvl: int) -> None:
    origin = time[0].astype("datetime64[ms]").item().replace(tzinfo=timezone.utc)
    seconds = (time - time[0]).astype("timedelta64[ms]").astype(np.float64) / 1000.0
    dataset = _dataset(group, "time", seconds, compression_lvl, "s")
    dataset.attrs["time_origin"] = origin.isoformat()
    dataset.attrs["time_units"] = "s"


def _write_array(group: h5py.Group, columns: list[SensorColumn], compression_lvl: int, reference) -> None:
    heights = sorted({column.height for column in columns})
    z = _dataset(group, "position_z", np.array(heights, dtype=np.float64), compression_lvl, "m")
    z.attrs["description"] = f"Height of each sensor of the array above {reference or 'the ground'}"
    for variable in dict.fromkeys(column.variable for column in columns):
        members = sorted(
            (column for column in columns if column.variable == variable), key=lambda item: item.height
        )
        values = np.stack([column.values for column in members], axis=1)
        _dataset(group, variable, values, compression_lvl, members[0].units)


def _write_track(  # pylint: disable=too-many-arguments
    group: h5py.Group, positions: dict, position, sheet: SensorSheet, row: SensorRow, compression_lvl: int
) -> None:
    """A moving sensor's position per sample: geographic, or relative to the platform's origin."""
    geographic = {"position_lat", "position_lon"} & set(positions)
    relative = {"position_x", "position_y"} & set(positions)
    if geographic and relative:
        raise ValueError(f"Sensor {row.id}: its samples mix geographic and relative positions: give one.")
    if geographic:
        if geographic != {"position_lat", "position_lon"}:
            raise ValueError(f"Sensor {row.id}: give both the latitude and the longitude of its samples.")
        if "position_z" in positions and "position_alt" in positions:
            raise ValueError(f"Sensor {row.id}: give the altitude or the height of its samples, not both.")
        alt = positions.get("position_alt")
        alt = (
            alt.values
            if alt is not None
            else _platform_alt(position, sheet) + _values(positions, "position_z", group)
        )
        _dataset(group, "position_lat", positions["position_lat"].values, compression_lvl, "degree")
        _dataset(group, "position_lon", positions["position_lon"].values, compression_lvl, "degree")
        _dataset(group, "position_alt", alt, compression_lvl, "m")
        group.attrs["crs"] = CRS
        return
    if isinstance(position, GeographicPosition):
        origin = ReferencePoint(f"{row.platform}", position.lat, position.lon, position.alt)
        offset = (0.0, 0.0, 0.0)
    else:
        origin = sheet.reference(position.reference)
        offset = (position.x, position.y, position.z)
    for axis, base in zip(("x", "y", "z"), offset):
        values = _values(positions, f"position_{axis}", group) + base
        _dataset(group, f"position_{axis}", values, compression_lvl, "m")
    for key, value in _origin_attrs(origin).items():
        group.attrs[key] = value


def _platform_alt(position, sheet: SensorSheet) -> float:
    if isinstance(position, GeographicPosition):
        return float(position.alt)
    return float(experiment_position(position, sheet)[2])


def _values(positions: dict, name: str, group: h5py.Group) -> np.ndarray:
    column = positions.get(name)
    if column is not None:
        return column.values
    return np.zeros(group["time"].shape[0])


def _sensor_attrs(
    group: h5py.Group, row: SensorRow, table: SensorTable, convention: str, variables
) -> None:
    group.attrs["sensor_kind"] = row.kind
    group.attrs["platform"] = row.platform
    group.attrs["sensor_id"] = row.id
    if row.instrument:
        group.attrs["instrument"] = row.instrument
    if row.description:
        group.attrs["description"] = row.description
    if row.averaging_period is not None:
        group.attrs["averaging_period"] = float(row.averaging_period)
        group.attrs["averaging_period_units"] = "s"
    if len(table.time) > 1:
        steps = np.diff(table.time).astype("timedelta64[ms]").astype(np.float64) / 1000.0
        group.attrs["sampling_interval"] = float(np.median(steps))
        group.attrs["sampling_interval_units"] = "s"
    if any(column.variable in (svn.WIND_SPEED_U.value, svn.WIND_SPEED_V.value) for column in variables):
        group.attrs["wind_convention"] = WIND_CONVENTIONS[0]
        group.attrs["wind_convention_source"] = convention
    if row.kind == "moving":
        group.attrs["launch_time"] = _iso_z(
            table.time[0].astype("datetime64[ms]").item().replace(tzinfo=timezone.utc)
        )
    group.attrs["source_file"] = table.source_file
    group.attrs["source_sha256"] = table.source_sha256
    if row.licence:
        group.attrs["license"] = row.licence


def _dataset(group: h5py.Group, name: str, values, compression_lvl: int, units: str) -> h5py.Dataset:
    dataset = group.create_dataset(
        name, data=np.asarray(values, dtype=np.float64), **hdf5plugin.Zstd(clevel=compression_lvl)
    )
    dataset.attrs["units"] = units
    return dataset


# --- Positions for display -------------------------------------------------------------------------


def experiment_position(position: GeographicPosition | RelativePosition, sheet: SensorSheet) -> tuple:
    """Longitude, latitude, and altitude of a platform's position."""
    if isinstance(position, GeographicPosition):
        return (position.lon, position.lat, position.alt)
    point = sheet.reference(position.reference)
    lon, lat, alt = _from_local(
        point, np.array([position.x]), np.array([position.y]), np.array([position.z])
    )
    return (float(lon[0]), float(lat[0]), float(alt[0]))


def experiment_geographic(group: h5py.Group) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Longitude, latitude, and altitude of a group's positions, from either convention.

    A sensor's samples when it has a position per sample, else the position of the group or of its
    platform (one value). A relative position goes through a local tangent plane at its origin, its
    axes turned by ``position_axes_azimuth``.
    """
    node = group
    while node is not None and node.name != "/":
        found = _geographic_of(node)
        if found is not None:
            return found
        node = node.parent
    raise ValueError(f"{group.name} has no position.")


def _geographic_of(group: h5py.Group):
    if "position_lat" in group and "position_lon" in group:
        lat = np.asarray(group["position_lat"][()], dtype=np.float64)
        lon = np.asarray(group["position_lon"][()], dtype=np.float64)
        alt = (
            np.asarray(group["position_alt"][()], dtype=np.float64)
            if "position_alt" in group
            else lat * np.nan
        )
        return lon, lat, alt
    if any(f"position_{axis}" in group for axis in "xy") and "position_origin_lat" in group.attrs:
        size = next(group[f"position_{axis}"].shape[0] for axis in "xyz" if f"position_{axis}" in group)
        axes = [
            (
                np.asarray(group[f"position_{axis}"][()], dtype=np.float64)
                if f"position_{axis}" in group
                else np.zeros(size)
            )
            for axis in "xyz"
        ]
        return _from_local(_origin_of(group), *axes)
    if "position_lat" in group.attrs:
        alt = float(group.attrs.get("position_alt", np.nan))
        return (
            np.array([float(group.attrs["position_lon"])]),
            np.array([float(group.attrs["position_lat"])]),
            np.array([alt]),
        )
    if "position_origin_lat" in group.attrs and "position_x" in group.attrs:
        axes = [np.array([float(group.attrs.get(f"position_{axis}", 0.0))]) for axis in "xyz"]
        return _from_local(_origin_of(group), *axes)
    return None


def _origin_of(group: h5py.Group) -> ReferencePoint:
    attrs = group.attrs
    name = attrs.get("position_origin_name", "origin")
    return ReferencePoint(
        name=name.decode() if isinstance(name, bytes) else str(name),
        lat=float(attrs["position_origin_lat"]),
        lon=float(attrs["position_origin_lon"]),
        alt=float(attrs.get("position_origin_alt", 0.0)),
        axes_azimuth=float(attrs.get("position_axes_azimuth", 0.0)),
    )


def _from_local(point: ReferencePoint, x, y, z) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Geographic coordinates of points in metres along a reference point's axes."""
    azimuth = math.radians(point.axes_azimuth)
    x, y, z = (np.atleast_1d(np.asarray(value, dtype=np.float64)) for value in (x, y, z))
    east = x * math.cos(azimuth) + y * math.sin(azimuth)
    north = -x * math.sin(azimuth) + y * math.cos(azimuth)
    pipeline = (
        "+proj=pipeline "
        f"+step +inv +proj=topocentric +ellps=WGS84 +lat_0={point.lat} +lon_0={point.lon} +h_0={point.alt} "
        "+step +inv +proj=cart +ellps=WGS84 "
        "+step +proj=unitconvert +xy_in=rad +xy_out=deg"
    )
    transformer = Transformer.from_pipeline(pipeline)
    if east.size == 1:
        # pyproj takes a one-element array for a scalar, which NumPy deprecates.
        return tuple(np.array([value]) for value in transformer.transform(east[0], north[0], z[0]))
    lon, lat, alt = transformer.transform(east, north, z)
    return np.asarray(lon), np.asarray(lat), np.asarray(alt)


def list_experiment_sensors(h5file: h5py.File) -> list[str]:
    """The data groups of the file's experiment sensors, sorted."""
    found = []
    for root in (TIME_SERIES, SPATIAL_1D):
        if root not in h5file:
            continue
        for platform in h5file[root].values():
            if not isinstance(platform, h5py.Group):
                continue
            for group in platform.values():
                if isinstance(group, h5py.Group) and "sensor_kind" in group.attrs:
                    found.append(group.name)
    return sorted(found)


# --- Templates -------------------------------------------------------------------------------------


TEMPLATE_TABLES = {
    "fixed": (
        ["time", "wind_speed_u[m/s]", "wind_speed_v[m/s]", "wind_speed_w[m/s]", "air_temperature[degC]"],
        [
            ["2026-02-23T12:00:00-06:00", "5.51", "0.56", "0.71", "14.28"],
            ["2026-02-23T12:00:01-06:00", "6.18", "-0.54", "-0.54", "14.18"],
        ],
    ),
    "array": (
        ["time", "air_temperature@1m[degC]", "air_temperature@2m[degC]", "air_temperature@10m[degC]"],
        [
            ["2026-02-23T12:30:00-06:00", "18.54", "17.99", "15.84"],
            ["2026-02-23T12:30:01-06:00", "17.91", "17.86", "16.21"],
        ],
    ),
    "moving": (
        ["time", "position_z[m]", "air_pressure[hPa]", "air_temperature[K]", "relative_humidity[%]"],
        [
            ["2026-02-23T06:55:00-06:00", "10", "1017.1", "288.2", "85"],
            ["2026-02-23T06:55:02-06:00", "16", "1016.4", "287.8", "86"],
        ],
    ),
}


def write_templates(kind: str, directory: Path | str) -> tuple[Path, Path]:
    """Write a sensor table of ``kind`` and a sensor sheet to fill, and return their paths."""
    if kind not in SENSOR_KINDS:
        raise ValueError(f"The kind is one of {', '.join(SENSOR_KINDS)}.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    header, rows = TEMPLATE_TABLES[kind]
    table = directory / f"sensor_{kind}.csv"
    with open(table, "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
    sheet = directory / "sensor_sheet.csv"
    reference = {"id": "plot_corner", "kind": "reference", "lat": "29.4", "lon": "-95.0", "alt": "10"}
    sensor = {
        "id": f"sensor_{kind}",
        "platform": "main_tower",
        "kind": kind,
        "file": table.name,
        "reference": "plot_corner",
        "x": "100",
        "y": "50",
        "z": "0",
        "height": "2" if kind == "fixed" else "",
        "instrument": "",
        "averaging_period": "1",
        "wind_convention": "u_east_v_north" if kind == "fixed" else "",
        "licence": "",
        "description": "",
    }
    with open(sheet, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerow(reference)
        writer.writerow(sensor)
    return table, sheet


# --- Helpers ---------------------------------------------------------------------------------------


def _check_name(value: str, what: str) -> None:
    if not NAME.match(value or ""):
        raise ValueError(f"The name of the {what} is letters, digits, `_`, `.`, and `-`; not `{value}`.")


def _check_lat_lon(lat: float, lon: float, what: str) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"The latitude and longitude of {what} are out of range.")


def _present(value) -> bool:
    return value is not None and str(value).strip() != ""


def _float(value) -> float | None:
    if not _present(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"`{value}` is not a number.") from error


def _required_float(item: dict, key: str, what: str) -> float:
    value = _float(item.get(key))
    if value is None:
        raise ValueError(f"The {what} has no `{key}`.")
    return value


def _known_keys(value: dict, kind, what: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"The {what} of a recipe is a JSON object.")
    unknown = sorted(set(value) - {item.name for item in fields(kind)})
    if unknown:
        raise ValueError(f"The {what} of a recipe has no field {', '.join(unknown)}.")


def _same_position(first, second) -> bool:
    return all(
        _same_attr(getattr(first, item.name), getattr(second, item.name)) for item in fields(type(first))
    )


def _same_attr(written, value) -> bool:
    if isinstance(value, float):
        try:
            return written is not None and abs(float(written) - value) <= 1e-9 * max(1.0, abs(value))
        except (TypeError, ValueError):
            return False
    if isinstance(written, bytes):
        written = written.decode()
    return written == value
