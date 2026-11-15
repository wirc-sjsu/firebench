"""
Check and score a bundle of model outputs against an event catalogue (``catalogue_case``).

A bundle is a directory with one sub-directory per event, named exactly by its event ID, each holding
one standard file (``.h5``) and the files it references (see ``catalogue_scoring`` for what the file
gives). The bundle is read by listing the directory; a path is never built from an event ID.

- ``check_catalogue_bundle`` returns a report: the known, unknown, and missing IDs, each event's
  problems and model attributes, the families present, and the coverage of each family.
- ``run_catalogue_benchmark`` scores each event (in a process pool), writes the per-event table (CSV,
  SHA-256 in the card), and returns the collection score card: the median of the events' values and of
  their scores per KPI, the total from FireBench's family weights only when every family reaches the
  coverage threshold, and the statistics per KPI and per stratum (``catalogue_statistics``).

The score of a KPI of the collection is the median of the events' scores, not the score of the median:
a symmetric KPI such as the area bias would otherwise reward scatter around zero. Nothing is averaged
that ``event_catalogue.toml`` does not name.
"""

import csv
import hashlib
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import h5py
import numpy as np
import shapely

from .. import __version__ as fb_version
from .. import metrics as fm
from .. import signing as fsi
from .. import standardize as fs
from .. import tools as ft
from . import c001_caldor as fb001
from . import wx_common as wxc
from .catalogue_case import CatalogueCase, load_catalogue_case
from .catalogue_parameters import load_parameters
from .catalogue_scoring import (
    FAMILY_KPIS,
    FAMILY_NAMES,
    NO_MODEL,
    NO_OBSERVATION,
    NOT_GIVEN,
    kpi_weight,
    null_results,
    observed_frame,
    read_model_attributes,
    read_model_event,
    square_metres_to_acres,
    score_final_perimeter,
    score_structure_loss,
)
from .catalogue_statistics import summarize
from .fire_case_definition import TEMPLATE_REFUSAL

DEFAULT_OUTPUT_PATH_JSON = Path("catalogue_rslt.json")
DEFAULT_SCORE_CARD_REPORT_PATH = Path("catalogue.pdf")
DEFAULT_EVENT_TABLE_PATH = Path("catalogue_events.csv")
TABLE_COLUMNS = ("event_id", "family", "kpi_id", "kpi_name", "value", "score", "null_reason")
H5_SUFFIXES = (".h5", ".hdf5")
KPI_NAMES = {kpi_id: name for kpis in FAMILY_KPIS.values() for kpi_id, name, _ in kpis}
KPI_FAMILY = {kpi_id: family for family, kpis in FAMILY_KPIS.items() for kpi_id, _, _ in kpis}


# ---------------------------
# The directory
# ---------------------------
def _listing(bundle_dir, event_ids) -> dict:
    """
    What the directory holds: ``files`` (event ID: its `.h5` path) of the known events, and the
    ``unknown`` names, the ``duplicate`` events (several `.h5` files), the ``empty`` event directories,
    and the ``stray`` entries (a file beside the event directories). Names starting with a dot are left out.
    """
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.is_dir():
        raise ValueError(f"The bundle {bundle_dir} is not a directory.")
    selected = set(event_ids)
    listing = {"files": {}, "unknown": [], "duplicate": [], "empty": [], "stray": []}
    for entry in sorted(bundle_dir.iterdir(), key=lambda item: item.name):
        if entry.name.startswith("."):
            continue
        if not entry.is_dir():
            listing["stray"].append(entry.name)
        elif entry.name not in selected:
            listing["unknown"].append(entry.name)
        else:
            found = sorted(
                item for item in entry.rglob("*") if item.is_file() and item.suffix.lower() in H5_SUFFIXES
            )
            if not found:
                listing["empty"].append(entry.name)
            elif len(found) > 1:
                listing["duplicate"].append(entry.name)
            else:
                listing["files"][entry.name] = found[0]
    return listing


def _observations(case: CatalogueCase, families) -> tuple[dict, dict]:
    """The observed perimeter (WKB) and the structures' damage labels of each selected event."""
    events = case.catalogue.events.set_index("event_id")
    wkb = {}
    if "final_perimeter" in families:
        wkb = {event: shapely.to_wkb(events.geometry[event]) for event in case.event_ids}
    labels = {}
    if "structure_loss" in families:
        records = case.catalogue.structures
        grouped = {event: list(group["damage"]) for event, group in records.groupby("event_id", sort=False)}
        labels = {event: grouped[event] for event in case.event_ids if event in grouped}
    return wkb, labels


def _tasks(case: CatalogueCase, listing: dict, families) -> list[dict]:
    wkb, labels = _observations(case, families)
    return [
        {
            "event_id": event,
            "file": str(listing["files"][event]) if event in listing["files"] else None,
            "families": list(families),
            "projection": case.projection,
            "observed_wkb": wkb.get(event),
            "observed_labels": labels.get(event),
        }
        for event in case.event_ids
    ]


# ---------------------------
# One event
# ---------------------------
def _evaluate_event(task: dict, score: bool = True) -> dict:
    """
    Read the model file of an event and, with ``score``, score it. Returns
    ``{"event_id", "problem", "sha256", "families": {family: {"expected", "given", "present", "problem"}},
    "rows": [(family, kpi_id, value, score, reason)]}``. Runs in a worker process.
    """
    parameters = load_parameters()
    families = task["families"]
    result = {"event_id": task["event_id"], "problem": None, "sha256": None, "families": {}, "rows": []}
    expected = {
        "final_perimeter": task["observed_wkb"] is not None,
        "structure_loss": bool(task["observed_labels"]),
    }
    model = {}
    if task["file"] is None:
        result["problem"] = NO_MODEL
    else:
        n_structures = len(task["observed_labels"]) if task["observed_labels"] else None
        model = read_model_event(task["file"], families, n_structures)
        result["problem"] = model["problem"]
        if score:
            result["sha256"] = ft.calculate_sha256(task["file"])
    for family in families:
        info = model.get(family, {"present": False, "problem": None})
        reason = result["problem"] or info["problem"] or (None if info["present"] else NOT_GIVEN)
        given = expected[family] and reason is None
        result["families"][family] = {
            "expected": expected[family],
            "given": given,
            "present": bool(info["present"]) and result["problem"] is None,
            "problem": result["problem"] or info["problem"],
        }
        if not score:
            continue
        outcome = null_results(family, NO_OBSERVATION if not expected[family] else reason)
        if given:
            try:
                outcome = _score_family(family, task, info, parameters)
            except (ValueError, shapely.errors.GEOSException) as error:
                outcome = null_results(family, f"scoring failed: {error}")
                result["families"][family].update(given=False, problem=f"scoring failed: {error}")
        result["rows"].extend(
            (family, kpi_id, value, kpi_score, why) for kpi_id, (value, kpi_score, why) in outcome.items()
        )
    return result


def _score_family(family: str, task: dict, info: dict, parameters) -> dict:
    if family == "final_perimeter":
        return score_final_perimeter(
            observed_frame(task["observed_wkb"]), info["frame"], task["projection"], parameters
        )
    return score_structure_loss(task["observed_labels"], info["labels"], parameters)


def _evaluate_all(tasks: list[dict], score: bool, workers: int | None) -> list[dict]:
    workers = os.cpu_count() or 1 if workers is None else workers
    if workers < 1:
        raise ValueError("`workers` must be at least 1.")
    if workers == 1 or len(tasks) < 2:
        results = [_evaluate_event(task, score) for task in tasks]
    else:
        chunk = max(1, len(tasks) // (workers * 8))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_evaluate_event, tasks, [score] * len(tasks), chunksize=chunk))
    return sorted(results, key=lambda item: item["event_id"])


# ---------------------------
# Check
# ---------------------------
def _model_attributes(listing: dict) -> tuple[dict, dict, list[str], list[str]]:
    """The attributes of each event's file, what they hold across the bundle, and the refusals."""
    by_event, templates, unreadable = {}, [], []
    for event, path in listing["files"].items():
        try:
            info = read_model_attributes(path)
        except (OSError, ValueError):
            unreadable.append(event)
            continue
        by_event[event] = info["attributes"]
        if info["template"]:
            templates.append(event)
    values: dict[str, Counter] = {}
    for attributes in by_event.values():
        for name in ("model_name", "model_version"):
            values.setdefault(name, Counter())[attributes.get(name)] += 1
    return by_event, {name: dict(counter) for name, counter in values.items()}, templates, unreadable


def _refusals(listing: dict, templates, values: dict) -> list[str]:
    refusals = []
    if listing["unknown"]:
        refusals.append(f"Directories of unknown events: {', '.join(listing['unknown'][:5])}.")
    if listing["stray"]:
        refusals.append(f"Files beside the event directories: {', '.join(listing['stray'][:5])}.")
    if listing["duplicate"]:
        refusals.append(f"Events with more than one .h5 file: {', '.join(listing['duplicate'][:5])}.")
    if listing["empty"]:
        refusals.append(f"Events with no .h5 file: {', '.join(listing['empty'][:5])}.")
    if templates:
        refusals.append(f"{TEMPLATE_REFUSAL} Events: {', '.join(templates[:5])}.")
    for name, counter in values.items():
        if len(counter) > 1:
            shown = ", ".join(f"{value!r} ({count})" for value, count in sorted(counter.items(), key=str))
            refusals.append(f"The model attribute `{name}` differs between events: {shown}.")
    return refusals


def _coverage(case: CatalogueCase, results: list[dict], families) -> dict:
    coverage = {}
    for family in families:
        expected = [item for item in results if item["families"][family]["expected"]]
        given = sum(1 for item in expected if item["families"][family]["given"])
        share = given / len(expected) if expected else None
        coverage[family] = {
            "n_expected": len(expected),
            "n_given": given,
            "share": share,
            "min_coverage": case.parameters.min_coverage,
            "reaches": share is not None and share >= case.parameters.min_coverage,
        }
    return coverage


def _check(case: CatalogueCase, bundle_dir, families, workers) -> tuple[dict, list[dict]]:
    listing = _listing(bundle_dir, case.event_ids)
    by_event, values, templates, unreadable = _model_attributes(listing)
    results = _evaluate_all(_tasks(case, listing, families), False, workers)
    report = {
        "known": sorted(listing["files"]),
        "unknown": listing["unknown"],
        "duplicate": listing["duplicate"],
        "empty": listing["empty"],
        "stray": listing["stray"],
        "templates": templates,
        "missing": sorted(set(case.event_ids) - set(listing["files"])),
        "model_attributes": {
            "agree": all(len(counter) <= 1 for counter in values.values()),
            "values": {
                name: {str(value): count for value, count in c.items()} for name, c in values.items()
            },
        },
        "events": {
            item["event_id"]: {
                "model_attributes": by_event.get(item["event_id"], {}),
                "families": [name for name, info in item["families"].items() if info["present"]],
                "problems": [
                    f"{name}: {info['problem']}"
                    for name, info in item["families"].items()
                    if info["problem"] and info["expected"]
                ],
            }
            for item in results
            if item["event_id"] in listing["files"]
        },
        "unreadable": unreadable,
        "families": _coverage(case, results, families),
        "refusals": _refusals(listing, templates, values),
    }
    report["families_present"] = {
        family: sum(1 for event in report["events"].values() if family in event["families"])
        for family in families
    }
    return report, results


def check_catalogue_bundle(definition, catalogue_path, bundle_dir, event_ids=None, workers=None) -> dict:
    """
    Check the bundle directory ``bundle_dir`` against the case ``definition`` on ``catalogue_path``.

    Returns a JSON-able report: ``known``, ``unknown``, ``duplicate`` (events with several `.h5`
    files), ``empty``, ``stray`` (files beside the event directories), ``templates`` (unchanged
    templates), and ``missing`` IDs; ``model_attributes`` (whether the files agree and the values);
    ``events`` (per known event: its model attributes, the families it gives, and its problems);
    ``families_present``; ``families`` (the coverage of each family: ``n_expected`` events with an
    observation, ``n_given``, ``share``, and whether it ``reaches`` ``min_coverage``); and ``refusals``,
    the problems that make ``run_catalogue_benchmark`` refuse the bundle. A problem of one event's
    files is not a refusal: its KPIs are null and the coverage drops. Raises ``CaseDefinitionError`` for
    a definition with problems and ``ValueError`` if ``bundle_dir`` is not a directory.
    """
    case = load_catalogue_case(definition, catalogue_path, event_ids)
    return _check(case, bundle_dir, case.families, workers)[0]


# ---------------------------
# The per-event table
# ---------------------------
def _number(value) -> str:
    return "" if value is None else repr(float(value))


def write_event_table(path, results: list[dict]) -> str:
    """Write the per-event table as CSV (sorted by event ID and KPI ID); returns its SHA-256."""
    rows = sorted(
        (
            (item["event_id"], family, kpi_id, value, kpi_score, why)
            for item in results
            for family, kpi_id, value, kpi_score, why in item["rows"]
        ),
        key=lambda row: (row[0], row[2]),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(TABLE_COLUMNS)
        for event, family, kpi_id, value, kpi_score, why in rows:
            writer.writerow(
                [event, family, kpi_id, KPI_NAMES[kpi_id], _number(value), _number(kpi_score), why or ""]
            )
    return ft.calculate_sha256(path)


# ---------------------------
# The collection
# ---------------------------
def _strata_of(case: CatalogueCase) -> dict[str, dict[str, str]]:
    """The class of each selected event in each stratum of the definition: ``{stratum: {event: class}}``."""
    events = case.catalogue.events.set_index("event_id").loc[case.event_ids]
    strata = {}
    for name in case.strata:
        if name == "year":
            strata[name] = {event: row["anchor_time"][:4] for event, row in events.iterrows()}
        else:
            areas = events.geometry.to_crs(case.projection).area
            strata[name] = {
                event: _size_class(square_metres_to_acres(area), case)
                for event, area in zip(events.index, areas.to_numpy())
            }
    return strata


def _size_class(acres: float, case: CatalogueCase) -> str:
    chosen = case.parameters.size_classes[0][0]
    for name, lower in case.parameters.size_classes:
        if acres >= lower:
            chosen = name
    return chosen


def _kpi_block(samples: list[tuple], kpi_id: str, case: CatalogueCase) -> dict:
    statistics = case.parameters.statistics
    values = [value for value, kpi_score in samples if kpi_score is not None]
    scores = [kpi_score for _, kpi_score in samples if kpi_score is not None]
    return {
        "family": KPI_FAMILY[kpi_id],
        "name": KPI_NAMES[kpi_id],
        "n_samples": len(scores),
        "value": summarize(values, statistics),
        "score": summarize(scores, statistics),
    }


def _samples(results: list[dict], events=None) -> dict[str, list[tuple]]:
    """``{kpi_id: [(value, score)]}`` of the events scored, in event order."""
    samples: dict[str, list[tuple]] = {}
    for item in results:
        if events is not None and item["event_id"] not in events:
            continue
        for _, kpi_id, value, kpi_score, _ in item["rows"]:
            samples.setdefault(kpi_id, [])
            if kpi_score is not None:
                samples[kpi_id].append((float(value), float(kpi_score)))
    return samples


def _collection(case: CatalogueCase, families, results: list[dict], table_sha256: str) -> dict:
    kpis_of = [kpi_id for family in families for kpi_id, _, _ in FAMILY_KPIS[family]]
    samples = _samples(results)
    collection = {
        "n_events": len(case.event_ids),
        "families": list(families),
        "event_table_sha256": table_sha256,
        "coverage": _coverage(case, results, families),
        "bootstrap": {
            "resamples": case.parameters.statistics.bootstrap_resamples,
            "seed": case.parameters.statistics.bootstrap_seed,
            "confidence": case.parameters.statistics.confidence,
            "min_samples_interval": case.parameters.statistics.min_samples_interval,
        },
        "kpis": {kpi_id: _kpi_block(samples.get(kpi_id, []), kpi_id, case) for kpi_id in kpis_of},
        "strata": {},
    }
    for name, classes in _strata_of(case).items():
        collection["strata"][name] = {}
        for label in sorted(set(classes.values())):
            members = {event for event, value in classes.items() if value == label}
            part = _samples(results, members)
            collection["strata"][name][label] = {
                "n_events": len(members),
                "kpis": {
                    kpi_id: _kpi_block(part.get(kpi_id, []), kpi_id, case)
                    for kpi_id in kpis_of
                    if part.get(kpi_id)
                },
            }
    return collection


def _omitted(collection: dict) -> dict[str, str]:
    """The KPIs left out of the scheme and why: their family is below coverage, or no event scored."""
    omitted = {}
    for kpi_id, block in collection["kpis"].items():
        coverage = collection["coverage"][block["family"]]
        if not coverage["reaches"]:
            omitted[kpi_id] = _coverage_text(block["family"], coverage)
        elif block["n_samples"] == 0:
            omitted[kpi_id] = "no event scored"
    return omitted


def _coverage_text(family: str, coverage: dict) -> str:
    if coverage["share"] is None:
        return f"{family}: no event has an observation"
    return (
        f"{family}: {coverage['n_given']} of {coverage['n_expected']} events ({coverage['share']:.1%}), "
        f"below the minimum {coverage['min_coverage']:.0%}"
    )


def _scorecard(case: CatalogueCase, families, collection: dict) -> tuple[dict, dict]:
    """The ``benchmarks`` and the ``score_card`` of the collection."""
    parameters = case.parameters
    omitted = _omitted(collection)
    benchmarks, scheme = {}, {}
    for family in families:
        group = FAMILY_NAMES[family]
        scheme[group] = {"weight": parameters.family_weights[family], "benchmarks": {}}
        for kpi_id, _, key in FAMILY_KPIS[family]:
            scheme[group]["benchmarks"][kpi_id] = kpi_weight(parameters, family, key)
            if kpi_id not in omitted:
                block = collection["kpis"][kpi_id]
                benchmarks[kpi_id] = {
                    block["name"]: block["value"]["median"],
                    "Score": block["score"]["median"],
                }
    target = "A" if list(families) == list(case.families) else _composed_name(families)
    card = {"Scheme": scheme}
    for group, content in scheme.items():
        scored = {
            kpi_id: weight for kpi_id, weight in content["benchmarks"].items() if kpi_id in benchmarks
        }
        if sum(scored.values()) > 0:
            card[f"Score {group}"] = sum(benchmarks[k]["Score"] * w for k, w in scored.items()) / sum(
                scored.values()
            )
    below = [family for family in families if not collection["coverage"][family]["reaches"]]
    if below:
        card["no_total_reason"] = "; ".join(_coverage_text(f, collection["coverage"][f]) for f in below)
    else:
        total = wxc.weighted_group_mean(card, scheme)
        if total is None:
            card["no_total_reason"] = "no family has a weight and a score"
        else:
            card["Score Total"] = total
    card["aggregation_scheme_name"] = target
    card["benchmark_target_name"] = target
    card["group_display_names"] = {FAMILY_NAMES[family]: FAMILY_NAMES[family] for family in families}
    return benchmarks, card


def _composed_name(families) -> str:
    return "C-" + hashlib.sha256(",".join(sorted(families)).encode("utf-8")).hexdigest()[:12]


def _bundle_sha256(results: list[dict]) -> str:
    lines = [f"{item['event_id']} {item['sha256']}" for item in results if item["sha256"]]
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def _clean(value):
    """The value for JSON: NaN and infinities are null."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def _header(case: CatalogueCase, catalogue_path: Path, name: str, model: dict, bundle_sha256: str) -> dict:
    with h5py.File(catalogue_path, "r") as h5:
        version = h5.attrs.get("version", "Unofficial")
    version = version.decode() if isinstance(version, bytes) else str(version)
    model_name = name or model.get("model_name") or ""
    header = {
        "created_on": fs.current_datetime_iso8601(include_seconds=True),
        "case_version": version,
        "firebench_version": fb_version,
        "case_name": case.name,
        "benchmark_short_name": case.name,
        # The id of a case defined outside FireBench is given by whoever keeps the case.
        "case_id": None,
        "case_schema": case.definition["schema"],
        "case_definition_sha256": case.sha256,
        "parameters": {**case.parameters.reference(), "sha256": case.parameters.sha256},
        "event_ids_sha256": case.definition["event_ids_sha256"],
        "evaluated_model_name": model_name,
        "model_attributes": model,
        "obs_dataset_hash": ft.calculate_sha256(catalogue_path),
        "bundle_sha256": bundle_sha256,
        "benchmark_script": ft.calculate_sha256(Path(__file__)),
    }
    return header


def run_catalogue_benchmark(  # pylint: disable=too-many-arguments,too-many-locals
    definition,
    catalogue_path,
    bundle_dir,
    *,
    event_ids=None,
    families=None,
    name: str = "",
    output_json=DEFAULT_OUTPUT_PATH_JSON,
    score_card_report=DEFAULT_SCORE_CARD_REPORT_PATH,
    event_table=DEFAULT_EVENT_TABLE_PATH,
    sign: tuple[str, str] | None = None,
    overwrite: bool = False,
    workers: int | None = None,
) -> dict:
    """
    Score the bundle ``bundle_dir`` on the case ``definition`` over the catalogue ``catalogue_path``.

    ``families`` is a non-empty subset of the definition's (all by default); ``event_ids`` the list a
    subset definition was made from; ``workers`` the processes that score the events (the CPU count by
    default, 1 for none). Writes the per-event table (``event_table``), the score card report
    (``score_card_report``), and the result (``output_json``), which is also returned; with ``sign``
    (key, signer) the card is certified as ``run_benchmark`` of ``fb-case-v1`` certifies its own.

    Refuses (``ValueError``, with every problem) an unknown ID, a malformed bundle directory, a
    template, model attributes that differ between events, and families that are not a non-empty subset
    of the definition's. A problem in one event's files is not a refusal: its KPIs are null with the
    reason, and the coverage of its family drops.
    """
    case = load_catalogue_case(definition, catalogue_path, event_ids)
    families = case.families if families is None else list(families)
    if not families or not set(families) <= set(case.families):
        raise ValueError(
            f"`families` must be a non-empty subset of the definition's ({', '.join(case.families)})."
        )
    families = [family for family in case.families if family in families]
    output_json, score_card_report = Path(output_json), Path(score_card_report)
    event_table = Path(event_table)
    listing = _listing(bundle_dir, case.event_ids)
    _, values, templates, _ = _model_attributes(listing)
    refusals = _refusals(listing, templates, values)
    if refusals:
        raise ValueError(" ".join(refusals))
    if not fb001.overwrite_previous_run(overwrite, output_json):
        ft.logger.info("Overwrite not authorized for output file: %s. Benchmark stopped", output_json)
        return {}

    results = _evaluate_all(_tasks(case, listing, families), True, workers)
    table_sha256 = write_event_table(event_table, results)
    collection = _collection(case, families, results, table_sha256)
    benchmarks, score_card = _scorecard(case, families, collection)
    collection["omitted_kpis"] = _omitted(collection)

    agreed = {
        name_: next(iter(counter)) for name_, counter in values.items() if next(iter(counter)) is not None
    }
    output = _header(case, Path(catalogue_path), name, agreed, _bundle_sha256(results))
    output["certificates_input"] = fsi.retrieve_h5_certificates(catalogue_path)
    if fsi.get_observation_certificate_verification(output["certificates_input"]) is None:
        ft.logger.warning(
            "The catalogue %s has no %s certificate; forcing verification level %s.",
            catalogue_path,
            fsi.Certificates.FB_VERIFIED_OBS_DATASET.value,
            fsi.DEFAULT_VL,
        )
    output["verification_lvl"] = fsi.compute_input_verification_lvl(output["certificates_input"])
    output.update(_clean({"benchmarks": benchmarks, "score_card": score_card, "collection": collection}))

    if sign:
        key, signer = sign
        output = fsi.certify_benchmark_run(output, key, signer)
    scores = {
        kpi_id: [
            row[3] for item in results for row in item["rows"] if row[1] == kpi_id and row[3] is not None
        ]
        for kpi_id in output["collection"]["kpis"]
    }
    fm.save_as_table(
        score_card_report, output, bool(sign), "certificate_verif_lvl", catalogue_scores=scores
    )
    if not score_card_report.exists():
        raise FileExistsError(f"Score card report {score_card_report} not found")
    output["score_card_report_hash"] = ft.calculate_sha256(score_card_report)
    if sign:
        output, _ = fsi.add_certificate_to_dict(
            output, "certificate_final", fsi.Certificates.FB_SCORE_CARD.value, key, signer
        )
    fsi.write_case_results(output_json, output)
    return output
