"""
The KPIs of one event of a catalogue, by family (``catalogue_case``).

Each function scores one event and returns ``{kpi_id: (value, score, reason)}``; a family that cannot be
scored for an event gives ``null_results`` (a null value and score with the reason). The KPI ids and
names are fixed here: ``G-FP01`` to ``G-FP04`` for ``final_perimeter`` and ``G-SL01`` for
``structure_loss``. Every number that changes a score is read from ``event_catalogue.toml``.

A model that burnt nothing (an empty perimeter) is scored, not null: Jaccard and Dice 0, area bias -1,
area ratio 0. A value FireBench did not compute is null with its reason, never zero.

The model file of an event is a standard file holding ``/polygons/final_perimeter`` (a KML file at
``rel_path``, beside the file, with its ``sha256``) and, for ``structure_loss``, the group written by
``catalogue_template`` at ``BUILDING_DAMAGE_PATH``: one DINS damage label per structure, in the order of
the catalogue's records.
"""

import math
from pathlib import Path

import geopandas as gpd
import h5py
import numpy as np
import shapely

from .. import metrics as fm
from .. import standardize as fs
from ..standardize.event_catalogue import damage_class
from ..standardize.tools import validate_h5_std
from ..tools import calculate_sha256
from ..tools.units import ureg
from .catalogue_parameters import CatalogueParameters
from .fire_case_definition import BUILDING_DAMAGE_PATH, TEMPLATE_ATTRIBUTE

FINAL_PERIMETER_PATH = f"/{fs.GEOPOLYGONS}/final_perimeter"
MODEL_ATTRIBUTES = ("model_name", "model_version")
# KPI id, name, and the key of its weight in the parameter file, by family.
FAMILY_KPIS = {
    "final_perimeter": (
        ("G-FP01", "Final Perimeter Jaccard", "jaccard_weight"),
        ("G-FP02", "Final Perimeter Dice-Sorensen", "dice_weight"),
        ("G-FP03", "Final Perimeter Area Bias", "area_bias_weight"),
        ("G-FP04", "Final Perimeter Area Ratio", "area_ratio_weight"),
    ),
    "structure_loss": (("G-SL01", "Structure Loss Count Relative Error", "count_error_weight"),),
}
FAMILY_NAMES = {"final_perimeter": "Final Perimeter", "structure_loss": "Structure Loss"}
NOT_GIVEN = "not given"
NO_OBSERVATION = "no observation"
NO_MODEL = "no model output"


def kpi_weight(parameters: CatalogueParameters, family: str, key: str):
    """The weight of a KPI of ``family`` in its group, from the parameter file."""
    return getattr(getattr(parameters, family), key)


def null_results(family: str, reason: str) -> dict:
    """The KPIs of ``family`` of an event that cannot be scored: ``{kpi_id: (None, None, reason)}``."""
    return {kpi_id: (None, None, reason) for kpi_id, _, _ in FAMILY_KPIS[family]}


def square_metres_to_acres(value: float) -> float:
    """An area in square metres, in acres."""
    return float(ureg.Quantity(value, "m^2").to("acre").magnitude)


def area_acres(geometries: gpd.GeoDataFrame, projection: str) -> float:
    """The area of the polygons of a perimeter, in acres, in an equal-area projection."""
    if geometries.empty:
        return 0.0
    return square_metres_to_acres(float(geometries.to_crs(projection).area.sum()))


def observed_frame(wkb: bytes) -> gpd.GeoDataFrame:
    """The catalogue's perimeter of an event (WKB, EPSG:4326) as a one-row frame."""
    return gpd.GeoDataFrame(geometry=[shapely.from_wkb(wkb)], crs="EPSG:4326")


# ---------------------------
# Scoring
# ---------------------------
def score_final_perimeter(
    observed: gpd.GeoDataFrame, model: gpd.GeoDataFrame, projection: str, parameters: CatalogueParameters
) -> dict:
    """
    Jaccard index, Dice-Sorensen index, relative area bias, and area ratio of the model's perimeter
    against the observed one, in ``projection``. ``{kpi_id: (value, score, reason)}``.
    """
    spec = parameters.final_perimeter
    observed_area = area_acres(observed, projection)
    if observed_area <= 0:
        return null_results("final_perimeter", "the observed area is zero")
    model_area = area_acres(model, projection)
    if model.empty:
        jaccard = dice = 0.0
    else:
        jaccard = float(fm.perimeter.jaccard_polygon(observed, model, projection=projection))
        dice = float(fm.perimeter.sorensen_dice_polygon(observed, model, projection=projection))
    bias = (model_area - observed_area) / observed_area
    ratio = model_area / observed_area
    ratio_score = 0.0
    if ratio > 0:
        ratio_score = fm.kpi_norm_symmetric_open_exponential(
            math.log(ratio), spec.area_log_ratio_at_score_50
        )
    return {
        "G-FP01": (jaccard, fm.kpi_norm_bounded_linear(jaccard, 0, 1), None),
        "G-FP02": (dice, fm.kpi_norm_bounded_linear(dice, 0, 1), None),
        "G-FP03": (
            bias,
            fm.kpi_norm_symmetric_open_exponential(bias, spec.area_relative_error_at_score_50),
            None,
        ),
        "G-FP04": (ratio, ratio_score, None),
    }


def lost_count(labels, parameters: CatalogueParameters) -> int:
    """The structures of DINS damage ``labels`` that count as lost (``lost_classes``)."""
    lost = parameters.structure_loss.lost_classes
    return sum(1 for label in labels if damage_class(label) in lost)


def score_structure_loss(observed_labels, model_labels, parameters: CatalogueParameters) -> dict:
    """
    The count error of the structures lost: modelled minus observed over the larger of the observed
    count and ``count_floor``. The labels are in the same order, one per structure.
    """
    spec = parameters.structure_loss
    if len(observed_labels) != len(model_labels):
        return null_results(
            "structure_loss",
            f"the model gives {len(model_labels)} structures, the catalogue has {len(observed_labels)}",
        )
    observed_lost = lost_count(observed_labels, parameters)
    error = (lost_count(model_labels, parameters) - observed_lost) / max(observed_lost, spec.count_floor)
    score = fm.kpi_norm_symmetric_open_exponential(error, spec.count_relative_error_at_score_50)
    return {"G-SL01": (error, score, None)}


# ---------------------------
# The model's file
# ---------------------------
def _text(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else ""
    return value.decode("utf-8") if isinstance(value, (bytes, np.bytes_)) else str(value)


def read_model_attributes(path) -> dict:
    """
    The model attributes of the root of a model file and whether it is an unchanged template.
    ``{"attributes": {name: text}, "template": bool}``; raises ``OSError`` or ``ValueError`` when the
    file is not a standard file.
    """
    with h5py.File(path, "r") as h5:
        validate_h5_std(h5)
        return {
            "attributes": {name: _text(h5.attrs[name]) for name in MODEL_ATTRIBUTES if name in h5.attrs},
            "template": TEMPLATE_ATTRIBUTE in h5.attrs,
        }


def read_model_kml(path: Path) -> gpd.GeoDataFrame:
    """
    The polygons of a model's KML perimeter, in EPSG:4326. A file with no polygon (the model burnt
    nothing) gives an empty frame. Raises ``ValueError`` when the file cannot be read.
    """
    try:
        frame = gpd.read_file(path, driver="KML")
    except Exception as error:  # pylint: disable=broad-exception-caught
        # An empty KML file has no layer, which the reader cannot open.
        try:
            empty = not any(layer["n_polygons"] for layer in fs.list_kml_layers(path))
        except Exception:  # pylint: disable=broad-exception-caught
            empty = False
        if not empty:
            raise ValueError(str(error)) from error
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return frame[frame.geometry.geom_type.isin(("Polygon", "MultiPolygon"))].reset_index(drop=True)


def _final_perimeter(h5: h5py.File):  # pylint: disable=too-many-return-statements
    """``(frame, problem)``: the model's perimeter, or why it cannot be read."""
    group = h5[FINAL_PERIMETER_PATH]
    if "rel_path" not in group.attrs:
        return None, "`/polygons/final_perimeter` has no `rel_path`: it names no KML file"
    rel_path = Path(_text(group.attrs["rel_path"]))
    directory = Path(h5.filename).resolve().parent
    kml_path = (directory / rel_path).resolve()
    if rel_path.is_absolute() or not kml_path.is_relative_to(directory):
        return None, f"`rel_path` `{rel_path}` is not inside the event's directory"
    if not kml_path.is_file():
        return None, f"the perimeter file `{rel_path}` is not in the bundle"
    expected = group.attrs.get("sha256")
    if expected is not None and _text(expected) != calculate_sha256(kml_path):
        return None, f"the perimeter file `{rel_path}` does not match its `sha256`"
    try:
        frame = read_model_kml(kml_path)
    except ValueError as error:
        return None, f"the perimeter file `{rel_path}` cannot be read: {error}"
    invalid = [shapely.is_valid_reason(item) for item in frame.geometry if not item.is_valid]
    if invalid:
        return None, f"the model's perimeter has an invalid geometry ({invalid[0]})"
    return frame, None


def read_model_event(path, families, n_structures: int | None = None) -> dict:
    """
    What the model file of an event gives for ``families``:
    ``{"problem": str | None, "final_perimeter": {...}, "structure_loss": {...}}``.

    ``problem`` is set when the file is not a standard file at all. Each family has ``present``
    (the model gives it), ``problem`` (why what it gives cannot be used), and its data:
    ``frame`` (the perimeter's polygons, empty when the model burnt nothing) or ``labels``
    (``n_structures`` is the catalogue's count, checked against the labels).
    """
    result = {"problem": None}
    try:
        with h5py.File(path, "r") as h5:
            validate_h5_std(h5)
            if "final_perimeter" in families:
                present = FINAL_PERIMETER_PATH in h5
                frame, problem = _final_perimeter(h5) if present else (None, None)
                result["final_perimeter"] = {"present": present, "problem": problem, "frame": frame}
            if "structure_loss" in families:
                result["structure_loss"] = _structure_labels(h5, n_structures)
    except (OSError, ValueError, KeyError) as error:
        result["problem"] = f"not a standard file ({error})"
    return result


def _structure_labels(h5: h5py.File, n_structures: int | None) -> dict:
    present = BUILDING_DAMAGE_PATH in h5
    if not present:
        return {"present": False, "problem": None, "labels": None}
    labels = [_text(value).strip() for value in np.asarray(h5[BUILDING_DAMAGE_PATH][()]).reshape(-1)]
    problem = None
    if n_structures is not None and len(labels) != n_structures:
        problem = f"the model gives {len(labels)} structures, the catalogue has {n_structures}"
    return {"present": True, "problem": problem, "labels": labels}
