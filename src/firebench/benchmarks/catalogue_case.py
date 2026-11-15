"""
Benchmark cases over an event catalogue: the definition document (schema ``fb-catalogue-case-v1``).

A definition says which events a collection scores (by the hash of their IDs), which families of KPIs
and strata it reports, and in which projection it measures areas. It names its parameters by reference
to ``event_catalogue.toml`` and carries no number that changes a score. Its canonical JSON is hashed
with SHA-256, and that hash names it, as for ``fb-case-v1``. It holds no case or set ID: whoever keeps
the cases gives those, and FireBench takes event IDs as opaque strings.

- ``propose_catalogue_case`` proposes a definition from a catalogue file;
- ``check_catalogue_case`` lists the problems of a definition against a catalogue file;
- ``load_catalogue_case`` returns the checked case, with the events it scores.
"""

from dataclasses import dataclass

from ..standardize.event_catalogue import (
    DEFAULT_AREA_CRS,
    EventCatalogue,
    event_ids_sha256,
    read_event_catalogue,
)
from .catalogue_parameters import (
    FAMILIES,
    CatalogueParameterError,
    CatalogueParameters,
    load_parameters,
    parameters_for,
)
from .fire_case_definition import CaseDefinitionError, definition_sha256

SCHEMA = "fb-catalogue-case-v1"
STRATA = ("size_class", "year")
DEFAULT_STRATA = ("size_class", "year")
KEYS = {"schema", "name", "parameters", "projection", "event_ids_sha256", "families", "strata"}
LATER_FAMILIES = ("progression", "area_growth")


@dataclass
class CatalogueCase:  # pylint: disable=too-many-instance-attributes
    """A checked catalogue case: its definition, parameters, and the events it scores."""

    definition: dict
    parameters: CatalogueParameters
    catalogue: EventCatalogue
    event_ids: list[str]  # sorted

    @property
    def sha256(self) -> str:
        """The SHA-256 that names the definition."""
        return definition_sha256(self.definition)

    @property
    def projection(self) -> str:
        """The equal-area projection areas are measured in."""
        return self.definition["projection"]

    @property
    def families(self) -> list[str]:
        """The families of KPIs the definition scores."""
        return list(self.definition["families"])

    @property
    def strata(self) -> list[str]:
        """The strata the definition reports."""
        return list(self.definition["strata"])

    @property
    def name(self) -> str:
        """The name of the case."""
        return self.definition["name"]


def _selection_problems(catalogue: EventCatalogue, event_ids) -> tuple[list[str], list[str]]:
    """The events a case scores (sorted), and the problems of a list of IDs that selects them."""
    known = set(catalogue.events["event_id"])
    if event_ids is None:
        return sorted(known), []
    ids = [str(item) for item in event_ids]
    problems = []
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        problems.append(f"Duplicate event IDs: {', '.join(duplicates[:5])}.")
    unknown = sorted(set(ids) - known)
    if unknown:
        problems.append(f"Event IDs the catalogue does not hold: {', '.join(unknown[:5])}.")
    if not ids:
        problems.append("The list of event IDs is empty.")
    return sorted(set(ids) & known), problems


def _definition_problems(definition, catalogue: EventCatalogue, event_ids) -> tuple[list[str], list[str]]:
    """The problems of a definition, and the events it selects."""
    if not isinstance(definition, dict):
        return ["The definition must be a JSON object."], []
    problems = []
    unknown = sorted(set(definition) - KEYS)
    missing = sorted(KEYS - set(definition))
    if unknown:
        problems.append(f"Unknown keys in the definition: {', '.join(unknown)}.")
    if missing:
        problems.append(f"Missing keys in the definition: {', '.join(missing)}.")
    if definition.get("schema") != SCHEMA:
        problems.append(f"`schema` must be `{SCHEMA}`.")
    if not isinstance(definition.get("name"), str) or not definition.get("name"):
        problems.append("`name` must be a text.")
    parameters = None
    try:
        parameters = parameters_for(definition.get("parameters"))
    except CatalogueParameterError as error:
        problems.append(str(error))
    projection = definition.get("projection")
    if parameters is not None and projection not in parameters.projections:
        problems.append(f"`projection` must be one of {', '.join(parameters.projections)}.")

    selected, selection_problems = _selection_problems(catalogue, event_ids)
    problems.extend(selection_problems)
    if not selection_problems and definition.get("event_ids_sha256") != event_ids_sha256(selected):
        problems.append(
            "`event_ids_sha256` is not the hash of "
            + ("the IDs given." if event_ids is not None else "the catalogue's IDs.")
        )
    problems.extend(_family_problems(definition.get("families"), catalogue))
    problems.extend(_strata_problems(definition.get("strata")))
    return problems, selected


def _family_problems(families, catalogue: EventCatalogue) -> list[str]:
    if (
        not isinstance(families, list)
        or not families
        or not all(isinstance(item, str) for item in families)
    ):
        return ["`families` must be a non-empty list of family names."]
    problems = []
    if len(set(families)) != len(families):
        problems.append("`families` lists a family twice.")
    for name in dict.fromkeys(families):
        if name in LATER_FAMILIES:
            problems.append(f"The family `{name}` comes in a later version of FireBench.")
        elif name not in FAMILIES:
            problems.append(f"Unknown family `{name}`; the families are {', '.join(FAMILIES)}.")
    if "structure_loss" in families and catalogue.structures is None:
        problems.append(
            "The family `structure_loss` needs the catalogue's structures (`/events/structures`)."
        )
    return problems


def _strata_problems(strata) -> list[str]:
    if not isinstance(strata, list) or not all(isinstance(item, str) for item in strata):
        return ["`strata` must be a list of stratum names."]
    problems = [
        f"Unknown stratum `{name}`; the strata are {', '.join(STRATA)}."
        for name in strata
        if name not in STRATA
    ]
    if len(set(strata)) != len(strata):
        problems.append("`strata` lists a stratum twice.")
    return problems


def propose_catalogue_case(
    catalogue_path, name: str, event_ids=None, families=None, projection: str | None = None
) -> dict:
    """
    Propose a definition for the catalogue file ``catalogue_path``.

    ``event_ids`` selects a subset of the catalogue's events (the definition carries their hash; the
    list is passed again to ``check_catalogue_case`` and ``load_catalogue_case``). ``families`` defaults
    to ``final_perimeter``, and ``structure_loss`` when the catalogue holds structures. ``projection``
    defaults to the catalogue's ``area_crs`` when the parameters allow it. The strata are
    ``DEFAULT_STRATA``. Raises ``CaseDefinitionError`` with every problem of the proposal.
    """
    parameters = load_parameters()
    catalogue = read_event_catalogue(catalogue_path)
    selected, problems = _selection_problems(catalogue, event_ids)
    if families is None:
        families = ["final_perimeter"] + (["structure_loss"] if catalogue.structures is not None else [])
    if projection is None:
        projection = catalogue.attrs.get("area_crs") or DEFAULT_AREA_CRS
    definition = {
        "schema": SCHEMA,
        "name": name,
        "parameters": parameters.reference(),
        "projection": projection,
        "event_ids_sha256": event_ids_sha256(selected),
        "families": list(families),
        "strata": list(DEFAULT_STRATA),
    }
    problems = [*problems, *_definition_problems(definition, catalogue, event_ids)[0]]
    if problems:
        raise CaseDefinitionError(" ".join(dict.fromkeys(problems)))
    return definition


def check_catalogue_case(definition, catalogue_path, event_ids=None) -> list[str]:
    """
    The problems of ``definition`` against the catalogue file ``catalogue_path``, as a list of texts
    (empty when it can be run). ``event_ids`` is the list a subset definition was made from.
    """
    return _definition_problems(definition, read_event_catalogue(catalogue_path), event_ids)[0]


def load_catalogue_case(definition, catalogue_path, event_ids=None) -> CatalogueCase:
    """The case of ``definition`` on the catalogue file, or ``CaseDefinitionError`` with every problem."""
    catalogue = read_event_catalogue(catalogue_path)
    problems, selected = _definition_problems(definition, catalogue, event_ids)
    if problems:
        raise CaseDefinitionError(" ".join(problems))
    return CatalogueCase(
        definition=definition,
        parameters=parameters_for(definition["parameters"]),
        catalogue=catalogue,
        event_ids=selected,
    )
