"""
Parameters of the benchmark cases defined outside FireBench, read from the file FireBench ships.

Every number a generic case scores with is in ``resources/benchmarks/fire_case.toml``. A case
definition names the set and its version; the file is read from the installed package and from
nowhere else, so the FireBench version or commit of a result identifies its parameters.
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

PARAMETER_FILE = "resources/benchmarks/fire_case.toml"
METRIC_SETS = ("standard", "wind_direction")


class FireCaseParameterError(ValueError):
    """The parameter file is not what the generic cases expect."""


@dataclass(frozen=True)
class WeatherVariable:
    """A station variable a generic case scores."""

    variable: str
    label: str
    group_label: str
    unit: str
    norm_m: float | int
    metrics: str


@dataclass(frozen=True)
class FireCaseParameters:  # pylint: disable=too-many-instance-attributes
    """The parameter set of the generic cases and the SHA-256 of the file it comes from."""

    set: str
    version: str
    group_weights: MappingProxyType
    building_damage_kpi_weight: float | int
    cbi_high_classes: tuple[int, ...]
    cbi_other_classes: tuple[int, ...]
    cbi_kpi_weight: float | int
    projections: tuple[str, ...]
    area_relative_error_at_score_50: float
    min_perimeters: int
    perimeter_weights: MappingProxyType
    forecast_cycle_hours: tuple[int, ...]
    forecast_hours: int
    forecast_min_perimeters: int
    tso_weight: float | int
    all_weight: float | int
    variables: tuple[WeatherVariable, ...]
    sha256: str

    def reference(self) -> dict:
        """How a definition names this parameter set."""
        return {"set": self.set, "version": self.version}


PERIMETER_WEIGHT_KEYS = (
    "mean_jaccard_weight",
    "min_jaccard_weight",
    "max_jaccard_weight",
    "mean_dice_weight",
    "min_dice_weight",
    "max_dice_weight",
    "final_area_bias_weight",
    "area_rmse_weight",
)
FAMILIES = ("building_damage", "burn_severity_cbi", "fire_perimeters", "weather_stations")


def _keys(table, label: str, expected: set) -> dict:
    if not isinstance(table, dict):
        raise FireCaseParameterError(f"{PARAMETER_FILE}: {label} must be a table")
    missing = sorted(expected - set(table))
    unknown = sorted(set(table) - expected)
    if missing or unknown:
        parts = [f"missing {', '.join(missing)}"] if missing else []
        parts += [f"unknown {', '.join(unknown)}"] if unknown else []
        raise FireCaseParameterError(f"{PARAMETER_FILE}: keys of {label}: {'; '.join(parts)}")
    return table


def _number(table: dict, key: str, label: str, minimum: float = 0, maximum: float | None = None):
    value = table[key]
    valid = isinstance(value, Real) and not isinstance(value, bool) and value >= minimum
    if valid and maximum is not None:
        valid = value <= maximum
    if not valid:
        raise FireCaseParameterError(
            f"{PARAMETER_FILE}: {label}.{key} must be a number at or above {minimum:g}"
        )
    return value


def _whole(table: dict, key: str, label: str, minimum: int = 0) -> int:
    value = table[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise FireCaseParameterError(f"{PARAMETER_FILE}: {label}.{key} must be a whole number")
    return value


def _wholes(table: dict, key: str, label: str) -> tuple[int, ...]:
    value = table[key]
    if not isinstance(value, list) or not value or not all(_is_whole(item) for item in value):
        raise FireCaseParameterError(f"{PARAMETER_FILE}: {label}.{key} must be a list of whole numbers")
    return tuple(value)


def _is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _text(table: dict, key: str, label: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise FireCaseParameterError(f"{PARAMETER_FILE}: {label}.{key} must be a text")
    return value


def _variables(table: dict) -> tuple[WeatherVariable, ...]:
    if not isinstance(table, dict) or not table:
        raise FireCaseParameterError(f"{PARAMETER_FILE}: [weather_stations.variables] must list variables")
    variables = []
    for name, spec in table.items():
        label = f"weather_stations.variables.{name}"
        _keys(spec, f"[{label}]", {"label", "group_label", "unit", "norm_m", "metrics"})
        if spec["metrics"] not in METRIC_SETS:
            raise FireCaseParameterError(f"{PARAMETER_FILE}: {label}.metrics must be one of {METRIC_SETS}")
        norm_m = _number(spec, "norm_m", label)
        if norm_m == 0:
            raise FireCaseParameterError(f"{PARAMETER_FILE}: {label}.norm_m must be above 0")
        variables.append(
            WeatherVariable(
                variable=name,
                label=_text(spec, "label", label),
                group_label=_text(spec, "group_label", label),
                unit=_text(spec, "unit", label),
                norm_m=norm_m,
                metrics=spec["metrics"],
            )
        )
    return tuple(variables)


def parse_parameters(document: dict, sha256: str = "") -> FireCaseParameters:
    """Validate the content of a parameter file. Every key is required; an unknown key is refused."""
    _keys(
        document,
        "the file",
        {
            "set",
            "version",
            "group_weights",
            "building_damage",
            "burn_severity_cbi",
            "fire_perimeters",
            "forecast_windows",
            "weather_stations",
        },
    )
    groups = _keys(document["group_weights"], "[group_weights]", set(FAMILIES))
    damage = _keys(document["building_damage"], "[building_damage]", {"kpi_weight"})
    cbi = _keys(
        document["burn_severity_cbi"],
        "[burn_severity_cbi]",
        {"high_classes", "other_classes", "kpi_weight"},
    )
    perimeters = _keys(
        document["fire_perimeters"],
        "[fire_perimeters]",
        {"projections", "area_relative_error_at_score_50", "min_perimeters", *PERIMETER_WEIGHT_KEYS},
    )
    windows = _keys(
        document["forecast_windows"], "[forecast_windows]", {"cycle_hours", "hours", "min_perimeters"}
    )
    weather = _keys(
        document["weather_stations"], "[weather_stations]", {"tso_weight", "all_weight", "variables"}
    )

    high, other = _wholes(cbi, "high_classes", "burn_severity_cbi"), _wholes(
        cbi, "other_classes", "burn_severity_cbi"
    )
    if set(high) & set(other):
        raise FireCaseParameterError(f"{PARAMETER_FILE}: a CBI class cannot be both high and other")
    projections = perimeters["projections"]
    if (
        not isinstance(projections, list)
        or not projections
        or not all(isinstance(item, str) for item in projections)
    ):
        raise FireCaseParameterError(f"{PARAMETER_FILE}: fire_perimeters.projections must list projections")
    cycle_hours = _wholes(windows, "cycle_hours", "forecast_windows")
    if not all(hour < 24 for hour in cycle_hours):
        raise FireCaseParameterError(f"{PARAMETER_FILE}: forecast_windows.cycle_hours must be UTC hours")

    return FireCaseParameters(
        set=_text(document, "set", "the file"),
        version=_text(document, "version", "the file"),
        group_weights=MappingProxyType({name: _number(groups, name, "group_weights") for name in FAMILIES}),
        building_damage_kpi_weight=_number(damage, "kpi_weight", "building_damage"),
        cbi_high_classes=high,
        cbi_other_classes=other,
        cbi_kpi_weight=_number(cbi, "kpi_weight", "burn_severity_cbi"),
        projections=tuple(projections),
        area_relative_error_at_score_50=_number(
            perimeters, "area_relative_error_at_score_50", "fire_perimeters", minimum=1e-9
        ),
        min_perimeters=_whole(perimeters, "min_perimeters", "fire_perimeters", minimum=1),
        perimeter_weights=MappingProxyType(
            {key: _number(perimeters, key, "fire_perimeters") for key in PERIMETER_WEIGHT_KEYS}
        ),
        forecast_cycle_hours=cycle_hours,
        forecast_hours=_whole(windows, "hours", "forecast_windows", minimum=1),
        forecast_min_perimeters=_whole(windows, "min_perimeters", "forecast_windows", minimum=1),
        tso_weight=_number(weather, "tso_weight", "weather_stations"),
        all_weight=_number(weather, "all_weight", "weather_stations"),
        variables=_variables(weather["variables"]),
        sha256=sha256,
    )


@lru_cache(maxsize=1)
def load_parameters() -> FireCaseParameters:
    """The parameters of the installed FireBench."""
    content = files("firebench").joinpath(PARAMETER_FILE).read_bytes()
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise FireCaseParameterError(f"{PARAMETER_FILE} is not valid TOML: {error}") from error
    return parse_parameters(document, hashlib.sha256(content).hexdigest())


def parameters_for(reference) -> FireCaseParameters:
    """The parameter set a definition names, or an error that says why it is not this FireBench's."""
    parameters = load_parameters()
    if not isinstance(reference, dict) or set(reference) != {"set", "version"}:
        raise FireCaseParameterError("`parameters` must name a `set` and a `version`.")
    if reference["set"] != parameters.set:
        raise FireCaseParameterError(
            f"Unknown parameter set `{reference['set']}`; this FireBench has `{parameters.set}`."
        )
    if reference["version"] != parameters.version:
        raise FireCaseParameterError(
            f"Parameter set `{parameters.set}` version `{reference['version']}` is not this FireBench's "
            f"(`{parameters.version}`)."
        )
    return parameters
