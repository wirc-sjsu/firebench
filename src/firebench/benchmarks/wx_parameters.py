"""
Parameters of the weather-forecast benchmark, read from the file FireBench ships.

Every number ``wx_forecast`` scores with is in ``resources/benchmarks/wx_forecast.toml``. The file is
read from the installed package and from nowhere else: no option, setup key, or environment variable
replaces it, so the FireBench version or commit of a result identifies its parameters.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from numbers import Real
from types import MappingProxyType

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

PARAMETER_FILE = "resources/benchmarks/wx_forecast.toml"


class WxParameterError(ValueError):
    """The parameter file is not what the benchmark expects."""


@dataclass(frozen=True)
class SetupDefaults:
    """Values of the setup options a setup file leaves out."""

    horizon_hours: int
    cadences: tuple[int, ...]
    lead_bins: tuple[tuple[int, int], ...]
    informational_lead_bins: tuple[tuple[int, int], ...]
    obs_tolerance_min: float
    model_tolerance_s: float
    min_coverage: float

    @property
    def obs_tolerance_s(self) -> float:
        """Observation matching tolerance in seconds."""
        return self.obs_tolerance_min * 60.0


@dataclass(frozen=True)
class Normalization:
    """Unit a quantity is compared in and error, in that unit, at which its score is 50."""

    unit: str
    norm_m: float | int


@dataclass(frozen=True)
class WxParameters:  # pylint: disable=too-many-instance-attributes
    """Parameters of the weather-forecast benchmark and the SHA-256 of the file they come from."""

    setup_defaults: SetupDefaults
    penalty_value: float
    circular_penalty_offset_deg: float
    station_set_weights: MappingProxyType
    group_weights: MappingProxyType
    variables: MappingProxyType
    indices: MappingProxyType
    low_relative_humidity_max_percent: float
    strong_wind_speed_min_ms: float
    sha256: str


def parse_parameters(document: dict, sha256: str = "") -> WxParameters:
    """Validate the content of a parameter file. Every key is required; an unknown key is refused."""
    _keys(
        document,
        "the file",
        {
            "setup_defaults",
            "missing_model_data",
            "station_set_weights",
            "group_weights",
            "variables",
            "indices",
            "events",
        },
    )
    missing = _table(document, "missing_model_data", {"penalty_value", "circular_penalty_offset_deg"})
    events = _table(document, "events", {"low_relative_humidity_max_percent", "strong_wind_speed_min_ms"})
    return WxParameters(
        setup_defaults=_setup_defaults(document),
        penalty_value=_number(missing, "missing_model_data.penalty_value"),
        circular_penalty_offset_deg=_number(
            missing, "missing_model_data.circular_penalty_offset_deg", minimum=0, maximum=360
        ),
        station_set_weights=_weights(document, "station_set_weights"),
        group_weights=_weights(document, "group_weights"),
        variables=_normalizations(document, "variables"),
        indices=_normalizations(document, "indices"),
        low_relative_humidity_max_percent=_number(
            events, "events.low_relative_humidity_max_percent", minimum=0, maximum=100
        ),
        strong_wind_speed_min_ms=_number(events, "events.strong_wind_speed_min_ms", minimum=0),
        sha256=sha256,
    )


@lru_cache(maxsize=1)
def load_parameters() -> WxParameters:
    """The parameters of the installed FireBench."""
    content = files("firebench").joinpath(PARAMETER_FILE).read_bytes()
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise WxParameterError(f"{PARAMETER_FILE} is not valid TOML: {error}") from error
    return parse_parameters(document, hashlib.sha256(content).hexdigest())


def check_names(table: str, found, expected) -> None:
    """A table of the file must name exactly what the benchmark defines."""
    if set(found) != set(expected):
        raise WxParameterError(
            f"{PARAMETER_FILE}: [{table}] must have exactly the entries {', '.join(expected)}; "
            f"found {', '.join(found) or 'none'}"
        )


def _setup_defaults(document: dict) -> SetupDefaults:
    name = "setup_defaults"
    table = _table(
        document,
        name,
        {
            "horizon_hours",
            "cadences",
            "lead_bins",
            "informational_lead_bins",
            "obs_tolerance_min",
            "model_tolerance_s",
            "min_coverage",
        },
    )
    cadences = table["cadences"]
    if not isinstance(cadences, list) or not cadences or not all(_is_int(item, 1) for item in cadences):
        raise WxParameterError(f"{PARAMETER_FILE}: {name}.cadences must be a list of whole hours")
    horizon = table["horizon_hours"]
    if not _is_int(horizon, 1):
        raise WxParameterError(f"{PARAMETER_FILE}: {name}.horizon_hours must be a whole number of hours")
    return SetupDefaults(
        horizon_hours=horizon,
        cadences=tuple(cadences),
        lead_bins=_bins(table, f"{name}.lead_bins"),
        informational_lead_bins=_bins(table, f"{name}.informational_lead_bins"),
        obs_tolerance_min=_number(table, f"{name}.obs_tolerance_min", minimum=0),
        model_tolerance_s=_number(table, f"{name}.model_tolerance_s", minimum=0),
        min_coverage=_number(table, f"{name}.min_coverage", minimum=0, maximum=1),
    )


def _keys(table, label: str, expected: set) -> None:
    if not isinstance(table, dict):
        raise WxParameterError(f"{PARAMETER_FILE}: {label} must be a table")
    missing = sorted(expected - set(table))
    unknown = sorted(set(table) - expected)
    if missing or unknown:
        parts = [f"missing {', '.join(missing)}"] if missing else []
        parts += [f"unknown {', '.join(unknown)}"] if unknown else []
        raise WxParameterError(f"{PARAMETER_FILE}: keys of {label}: {'; '.join(parts)}")


def _table(document: dict, name: str, expected: set) -> dict:
    _keys(document[name], f"[{name}]", expected)
    return document[name]


def _is_int(value, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _number(table: dict, path: str, minimum=None, maximum=None) -> float | int:
    """The number at ``path``, with the type the file gives it: a result prints a weight as written."""
    value = table[path.rsplit(".", 1)[-1]]
    valid = isinstance(value, Real) and not isinstance(value, bool)
    if valid and minimum is not None:
        valid = value >= minimum
    if valid and maximum is not None:
        valid = value <= maximum
    if not valid:
        bounds = "" if minimum is None else f" at or above {minimum:g}"
        bounds += "" if maximum is None else f" and at or below {maximum:g}"
        raise WxParameterError(f"{PARAMETER_FILE}: {path} must be a number{bounds}")
    return value


def _bins(table: dict, path: str) -> tuple[tuple[int, int], ...]:
    value = table[path.rsplit(".", 1)[-1]]
    valid = isinstance(value, list) and all(
        isinstance(item, list)
        and len(item) == 2
        and all(_is_int(bound, 0) for bound in item)
        and item[0] <= item[1]
        for item in value
    )
    if not valid:
        raise WxParameterError(f"{PARAMETER_FILE}: {path} must be a list of [start, end] lead hours")
    return tuple((start, end) for start, end in value)


def _weights(document: dict, name: str) -> MappingProxyType:
    table = document[name]
    if not isinstance(table, dict) or not table:
        raise WxParameterError(f"{PARAMETER_FILE}: [{name}] must be a table of weights")
    return MappingProxyType({key: _number(table, f"{name}.{key}", minimum=0) for key in table})


def _normalizations(document: dict, name: str) -> MappingProxyType:
    tables = document[name]
    if not isinstance(tables, dict) or not tables:
        raise WxParameterError(f"{PARAMETER_FILE}: [{name}] must have one table per quantity")
    normalizations = {}
    for key, table in tables.items():
        _keys(table, f"[{name}.{key}]", {"unit", "norm_m"})
        if not isinstance(table["unit"], str) or not table["unit"]:
            raise WxParameterError(f"{PARAMETER_FILE}: {name}.{key}.unit must be a unit name")
        norm_m = _number(table, f"{name}.{key}.norm_m", minimum=0)
        if norm_m == 0:
            raise WxParameterError(f"{PARAMETER_FILE}: {name}.{key}.norm_m must be above 0")
        normalizations[key] = Normalization(unit=table["unit"], norm_m=norm_m)
    return MappingProxyType(normalizations)
