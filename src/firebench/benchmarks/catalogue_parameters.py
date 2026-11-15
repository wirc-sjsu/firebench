"""
Parameters of the event-catalogue benchmark, read from the file FireBench ships.

Every number a collection of events is scored with is in ``resources/benchmarks/event_catalogue.toml``.
A catalogue case definition names the set and its version; the file is read from the installed package
and from nowhere else, so the FireBench version or commit of a result identifies its parameters.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from numbers import Real
from types import MappingProxyType

from ..standardize.event_catalogue import DAMAGE_CLASSES

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

PARAMETER_FILE = "resources/benchmarks/event_catalogue.toml"
FAMILIES = ("final_perimeter", "structure_loss")
FINAL_PERIMETER_WEIGHT_KEYS = ("jaccard_weight", "dice_weight", "area_bias_weight", "area_ratio_weight")


class CatalogueParameterError(ValueError):
    """The parameter file is not what the catalogue benchmark expects."""


@dataclass(frozen=True)
class FinalPerimeterParameters:
    """The values of ``[final_perimeter]``."""

    jaccard_weight: float | int
    dice_weight: float | int
    area_bias_weight: float | int
    area_ratio_weight: float | int
    area_relative_error_at_score_50: float
    area_log_ratio_at_score_50: float


@dataclass(frozen=True)
class StructureLossParameters:
    """The values of ``[structure_loss]``."""

    lost_classes: tuple[str, ...]
    count_floor: int
    count_relative_error_at_score_50: float
    count_error_weight: float | int


@dataclass(frozen=True)
class StatisticsParameters:
    """The values of ``[statistics]``."""

    bootstrap_resamples: int
    bootstrap_seed: int
    confidence: float
    min_samples_interval: int


@dataclass(frozen=True)
class TemplateParameters:
    """The values of ``[template]``."""

    default_window_days: float | int
    box_half_width_km: float | int


@dataclass(frozen=True)
class CatalogueParameters:  # pylint: disable=too-many-instance-attributes
    """The parameter set of the event-catalogue benchmark and the SHA-256 of the file it comes from."""

    set: str
    version: str
    projections: tuple[str, ...]
    family_weights: MappingProxyType
    final_perimeter: FinalPerimeterParameters
    structure_loss: StructureLossParameters
    min_coverage: float
    statistics: StatisticsParameters
    size_classes: tuple[tuple[str, float | int], ...]  # (name, lower bound in acres), ascending
    template: TemplateParameters
    sha256: str

    def reference(self) -> dict:
        """How a definition names this parameter set."""
        return {"set": self.set, "version": self.version}


def _keys(table, label: str, expected: set) -> dict:
    if not isinstance(table, dict):
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {label} must be a table")
    missing = sorted(expected - set(table))
    unknown = sorted(set(table) - expected)
    if missing or unknown:
        parts = [f"missing {', '.join(missing)}"] if missing else []
        parts += [f"unknown {', '.join(unknown)}"] if unknown else []
        raise CatalogueParameterError(f"{PARAMETER_FILE}: keys of {label}: {'; '.join(parts)}")
    return table


def _number(table: dict, key: str, label: str, minimum: float = 0, maximum: float | None = None):
    value = table[key]
    valid = isinstance(value, Real) and not isinstance(value, bool) and value >= minimum
    if valid and maximum is not None:
        valid = value <= maximum
    if not valid:
        raise CatalogueParameterError(
            f"{PARAMETER_FILE}: {label}.{key} must be a number at or above {minimum:g}"
            + (f" and at most {maximum:g}" if maximum is not None else "")
        )
    return value


def _whole(table: dict, key: str, label: str, minimum: int = 0) -> int:
    value = table[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise CatalogueParameterError(
            f"{PARAMETER_FILE}: {label}.{key} must be a whole number at or above {minimum}"
        )
    return value


def _texts(value, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {label} must be a list of texts")
    if len(set(value)) != len(value):
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {label} lists a name twice")
    return tuple(value)


def _final_perimeter(table: dict) -> FinalPerimeterParameters:
    label = "final_perimeter"
    weights = {key: _number(table, key, label) for key in FINAL_PERIMETER_WEIGHT_KEYS}
    if not any(weights.values()):
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {label} needs a KPI with a weight above 0")
    return FinalPerimeterParameters(
        **weights,
        area_relative_error_at_score_50=_number(
            table, "area_relative_error_at_score_50", label, minimum=1e-9
        ),
        area_log_ratio_at_score_50=_number(table, "area_log_ratio_at_score_50", label, minimum=1e-9),
    )


def _structure_loss(table: dict) -> StructureLossParameters:
    label = "structure_loss"
    classes = _texts(table["lost_classes"], f"{label}.lost_classes")
    unknown = sorted(set(classes) - set(DAMAGE_CLASSES))
    if unknown:
        raise CatalogueParameterError(
            f"{PARAMETER_FILE}: {label}.lost_classes names no damage class: {', '.join(unknown)}"
        )
    weight = _number(table, "count_error_weight", label)
    if weight == 0:
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {label}.count_error_weight must be above 0")
    return StructureLossParameters(
        lost_classes=classes,
        count_floor=_whole(table, "count_floor", label, minimum=1),
        count_relative_error_at_score_50=_number(table, "count_relative_error_at_score_50", label, 1e-9),
        count_error_weight=weight,
    )


def _size_classes(table) -> tuple[tuple[str, float | int], ...]:
    if not isinstance(table, dict) or not table:
        raise CatalogueParameterError(f"{PARAMETER_FILE}: [strata.size_classes] must list classes")
    classes = tuple((name, _number(table, name, "strata.size_classes")) for name in table)
    bounds = [bound for _, bound in classes]
    if bounds[0] != 0 or bounds != sorted(set(bounds)):
        raise CatalogueParameterError(
            f"{PARAMETER_FILE}: strata.size_classes must start at 0 and rise from class to class"
        )
    return classes


def parse_parameters(document: dict, sha256: str = "") -> CatalogueParameters:
    """Validate the content of a parameter file. Every key is required; an unknown key is refused."""
    _keys(
        document,
        "the file",
        {
            "set",
            "version",
            "projections",
            "family_weights",
            "final_perimeter",
            "structure_loss",
            "coverage",
            "statistics",
            "strata",
            "template",
        },
    )
    weights = _keys(document["family_weights"], "[family_weights]", set(FAMILIES))
    coverage = _keys(document["coverage"], "[coverage]", {"min_coverage"})
    statistics = _keys(
        document["statistics"],
        "[statistics]",
        {"bootstrap_resamples", "bootstrap_seed", "confidence", "min_samples_interval"},
    )
    strata = _keys(document["strata"], "[strata]", {"size_classes"})
    template = _keys(document["template"], "[template]", {"default_window_days", "box_half_width_km"})
    final = _keys(
        document["final_perimeter"],
        "[final_perimeter]",
        {*FINAL_PERIMETER_WEIGHT_KEYS, "area_relative_error_at_score_50", "area_log_ratio_at_score_50"},
    )
    loss = _keys(
        document["structure_loss"],
        "[structure_loss]",
        {"lost_classes", "count_floor", "count_relative_error_at_score_50", "count_error_weight"},
    )
    confidence = _number(statistics, "confidence", "statistics", minimum=1e-9, maximum=1 - 1e-9)
    return CatalogueParameters(
        set=_text(document, "set"),
        version=_text(document, "version"),
        projections=_texts(document["projections"], "projections"),
        family_weights=MappingProxyType(
            {name: _number(weights, name, "family_weights") for name in FAMILIES}
        ),
        final_perimeter=_final_perimeter(final),
        structure_loss=_structure_loss(loss),
        min_coverage=float(_number(coverage, "min_coverage", "coverage", minimum=1e-9, maximum=1)),
        statistics=StatisticsParameters(
            bootstrap_resamples=_whole(statistics, "bootstrap_resamples", "statistics", minimum=1),
            bootstrap_seed=_whole(statistics, "bootstrap_seed", "statistics"),
            confidence=float(confidence),
            min_samples_interval=_whole(statistics, "min_samples_interval", "statistics", minimum=2),
        ),
        size_classes=_size_classes(strata["size_classes"]),
        template=TemplateParameters(
            default_window_days=_number(template, "default_window_days", "template", minimum=1e-9),
            box_half_width_km=_number(template, "box_half_width_km", "template", minimum=1e-9),
        ),
        sha256=sha256,
    )


def _text(table: dict, key: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value:
        raise CatalogueParameterError(f"{PARAMETER_FILE}: {key} must be a text")
    return value


@lru_cache(maxsize=1)
def load_parameters() -> CatalogueParameters:
    """The parameters of the installed FireBench."""
    content = files("firebench").joinpath(PARAMETER_FILE).read_bytes()
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise CatalogueParameterError(f"{PARAMETER_FILE} is not valid TOML: {error}") from error
    return parse_parameters(document, hashlib.sha256(content).hexdigest())


def parameters_for(reference) -> CatalogueParameters:
    """The parameter set a definition names, or an error that says why it is not this FireBench's."""
    parameters = load_parameters()
    if not isinstance(reference, dict) or set(reference) != {"set", "version"}:
        raise CatalogueParameterError("`parameters` must name a `set` and a `version`.")
    if reference["set"] != parameters.set:
        raise CatalogueParameterError(
            f"Unknown parameter set `{reference['set']}`; this FireBench has `{parameters.set}`."
        )
    if reference["version"] != parameters.version:
        raise CatalogueParameterError(
            f"Parameter set `{parameters.set}` version `{reference['version']}` is not this FireBench's "
            f"(`{parameters.version}`)."
        )
    return parameters
