"""
The engine that runs a benchmark case from its definition (schema ``fb-case-v1``).

``load_case`` returns a ``FireCase``, which offers what a case module such as ``c001_caldor`` offers
to a program that runs it: the registries (``REQUIREMENTS``, ``BENCHMARK_FUNCTIONS``, ``GROUPS``,
``AGGREGATION``), target discovery and resolution, score cards composed of chosen KPI groups, and
``run_benchmark``, with the arguments of ``run_caldor_benchmark``.

The KPI functions are FB001's, with the paths, projection, and parameters of the definition and of
``fire_case.toml``. The one family FB001 does not have, burn severity from RAVG's composite burn
index, is defined here, and so is canopy cover loss, scored as RAVG's classes on the cells both sides
burnt; the radar plume family is in ``fire_case_radar`` and the fire radiative power family in
``fire_case_frp``. KPI ids are ``G-`` and a family code (BD, SV, CC, FP, WX, RP, FR) with a number that
follows the order of families and periods in the definition, so they are stable for a definition.
"""

import hashlib
import re
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from h5py import File
from scipy.spatial import cKDTree

from .. import __version__ as fb_version
from .. import metrics as fm
from .. import signing as fsi
from .. import standardize as fs
from .. import tools as ft
from . import c001_caldor as fb001
from . import wx_common as wxc
from . import fire_case_frp as frp
from . import fire_case_radar as radar
from .fire_case_radar import RADAR_KPIS, RADAR_TOP_KPIS, bench_radar_plume, bench_radar_top
from .fire_case_radar_model import model_requirements, top_requirements
from .fire_case_definition import (
    TEMPLATE_REFUSAL,
    CaseDefinitionError,
    _check_document,
    check_case,
    definition_sha256,
    family,
    is_template,
    period_bounds,
    read_case_definition,
)

KPI_PREFIX = "G-"
COMPOSED_TARGET_PREFIX = "C-"
DEFAULT_OUTPUT_PATH_JSON = Path("case_rslt.json")
DEFAULT_SCORE_CARD_REPORT_PATH = Path("case.pdf")
PERIOD_TARGET_PATTERN = re.compile(r"^(P\d{2}|H\d{3})_([BSCPTWRF]+)$")
FLAG_ORDER = "BSCPTWRF"

BINARY_METRICS = (
    ("Accuracy", fm.confusion_matrix.binary_accuracy),
    ("Precision", fm.confusion_matrix.binary_precision),
    ("Recall", fm.confusion_matrix.binary_recall_rate),
    ("Specificity", fm.confusion_matrix.binary_specificity),
    ("Negative Predictive Value", fm.confusion_matrix.binary_negative_predicted_value),
    ("F1 Score", fm.confusion_matrix.binary_f_score),
)
PERIMETER_INDICES = (
    ("Average Jaccard", fb001.jaccard_from_list, np.mean, "mean_jaccard_weight"),
    ("Minimum Jaccard", fb001.jaccard_from_list, np.min, "min_jaccard_weight"),
    ("Maximum Jaccard", fb001.jaccard_from_list, np.max, "max_jaccard_weight"),
    ("Average Dice-Sorensen", fb001.sorensen_dice_from_list, np.mean, "mean_dice_weight"),
    ("Minimum Dice-Sorensen", fb001.sorensen_dice_from_list, np.min, "min_dice_weight"),
    ("Maximum Dice-Sorensen", fb001.sorensen_dice_from_list, np.max, "max_dice_weight"),
)
WX_METRICS = {
    "standard": (("MAE", fm.stats.mae), ("RMSE", fm.stats.rmse), ("Bias", fm.stats.bias)),
    "wind_direction": (("circular bias", fm.stats.circular_bias_deg),),
}
WX_STATS = (("min", np.nanmin), ("mean", np.nanmean), ("max", np.nanmax))
STATION_SETS = {
    "TSO": ("TSO", fs.WeatherStationSet.TSO, "tso_weight"),
    "ALL": ("All sources", fs.WeatherStationSet.ALL_SOURCES, "all_weight"),
}
CATEGORIES = {
    "B": "Building Damage",
    "S": "Burn Severity",
    "C": "Canopy Cover Loss",
    "P": "Fire Perimeters",
    "W": "Weather Stations",
    "R": "Radar Plume",
    "F": "Fire Radiative Power",
}
CTX_SPEC = {
    **fb001.CTX_SPEC,
    (
        "agg_bin",
        "ravg_cbi",
        "pair",
    ): "High burn severity of observations and model, on the cells both classify",
    (
        "classes",
        "ravg_cc",
        "pair",
    ): "Canopy cover loss classes of observations and model, on the cells with canopy both classify",
}


# ---------------------------
# Burn severity from RAVG's composite burn index
# ---------------------------
def cbi_high_binary(
    obs_dataset: File,
    model_dataset: File,
    dataset_path: str,
    high_classes: tuple[int, ...],
    other_classes: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """
    High burn severity (1) or not (0) of the cells the observations and the model both classify.

    The grids are RAVG's four CBI classes. A class in neither ``high_classes`` nor ``other_classes``
    (no data) leaves its cell out, in either file.
    """
    obs = np.asarray(obs_dataset[dataset_path][()])
    model = np.asarray(model_dataset[dataset_path][()])
    if obs.shape != model.shape:
        raise ValueError(
            f"The model's `{dataset_path}` has the shape {model.shape}; the observations have {obs.shape}. "
            "The model must give the severity on the observation grid."
        )
    known = np.array(sorted({*high_classes, *other_classes}))
    valid = np.isin(obs, known) & np.isin(model, known)
    high = np.array(sorted(high_classes))
    binary_obs = np.isin(obs[valid], high).astype(np.int8)
    binary_model = np.isin(model[valid], high).astype(np.int8)
    ft.logger.info(
        "high burn severity on %d cells: %d observed, %d modelled",
        binary_obs.size,
        int(binary_obs.sum()),
        int(binary_model.sum()),
    )
    return binary_obs, binary_model


def bench_cbi_index(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    func_cm_index,
    dataset_path: str,
    high_classes: tuple[int, ...],
    other_classes: tuple[int, ...],
):
    """A binary index of high burn severity, scored from 0 to 100 as FB001's severity KPIs are."""
    binary_obs, binary_model = fm.ctx_get_or_compute(
        CTX_SPEC,
        ctx,
        ("agg_bin", "ravg_cbi", "pair"),
        cbi_high_binary,
        obs_dataset,
        model_dataset,
        dataset_path,
        high_classes,
        other_classes,
    )
    rslt = func_cm_index(fm.confusion_matrix.binary_cm(binary_obs, binary_model))
    ft.logger.info("%s: %f", kpi_name_custom, rslt)
    return {kpi_name_custom: rslt, "Score": fm.kpi_norm_bounded_linear(rslt, 0, 1)}


# ---------------------------
# Canopy cover loss from RAVG, where LANDFIRE had canopy
# ---------------------------
def canopy_mask(obs_dataset: File, dataset_path: str, canopy_paths: list[str]) -> np.ndarray:
    """
    The cells of the RAVG grid ``dataset_path`` that are scored: LANDFIRE had canopy there before the
    fire, and the observations classify the cell.

    A LANDFIRE cell has canopy when every layer of ``canopy_paths`` is above 0 and is not its
    ``_FillValue``; FB001's mask counts the fill value as canopy. The canopy is carried to the RAVG grid
    by the nearest LANDFIRE cell, in latitude and longitude, as FB001 does.
    """
    group = canopy_paths[0].rsplit("/", 1)[0]
    has_canopy = np.ones(obs_dataset[canopy_paths[0]].shape, dtype=bool)
    for path in canopy_paths:
        values = np.asarray(obs_dataset[path][()])
        has_canopy &= (values > 0) & (values != obs_dataset[path].attrs["_FillValue"])
    tree = cKDTree(
        np.column_stack(
            (
                np.asarray(obs_dataset[f"{group}/position_lat"][()]).ravel(),
                np.asarray(obs_dataset[f"{group}/position_lon"][()]).ravel(),
            )
        )
    )
    target = dataset_path.rsplit("/", 1)[0]
    lat = np.asarray(obs_dataset[f"{target}/position_lat"][()])
    _, nearest = tree.query(
        np.column_stack((lat.ravel(), np.asarray(obs_dataset[f"{target}/position_lon"][()]).ravel()))
    )
    on_grid = has_canopy.ravel()[nearest].reshape(lat.shape)
    observed = np.asarray(obs_dataset[dataset_path][()])
    return on_grid & (observed != obs_dataset[dataset_path].attrs["_FillValue"])


@dataclass
class CanopyCells:
    """
    The canopy cover loss classes of both files on the RAVG grid, and which cells are scored.

    ``canopy``: LANDFIRE had canopy there and the observations do not mark the cell as fill
    (``canopy_mask``). ``observed``: ``canopy``, and the observations give one of the classes.
    ``scored``: ``observed``, and the model gives one of the classes too.
    """

    observations: np.ndarray
    model: np.ndarray
    canopy: np.ndarray
    observed: np.ndarray
    scored: np.ndarray


def cc_cells(
    obs_dataset: File,
    model_dataset: File,
    dataset_path: str,
    canopy_paths: list[str],
    classes: tuple[int, ...],
) -> CanopyCells:
    """The cells of the canopy cover loss grid and which are scored (see ``cc_pairs``)."""
    obs = np.asarray(obs_dataset[dataset_path][()])
    model = np.asarray(model_dataset[dataset_path][()])
    if obs.shape != model.shape:
        raise ValueError(
            f"The model's `{dataset_path}` has the shape {model.shape}; the observations have {obs.shape}. "
            "The model must give the canopy cover loss on the observation grid."
        )
    known = np.array(sorted(classes))
    canopy = canopy_mask(obs_dataset, dataset_path, canopy_paths)
    observed = canopy & np.isin(obs, known)
    return CanopyCells(obs, model, canopy, observed, observed & np.isin(model, known))


def cc_pairs(
    obs_dataset: File,
    model_dataset: File,
    dataset_path: str,
    canopy_paths: list[str],
    classes: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    The canopy cover loss classes of the observations and of the model on the cells that are scored,
    and the number of cells the observations classify where LANDFIRE had canopy.

    A cell is scored where LANDFIRE had canopy (``canopy_mask``) and both files give it one of
    ``classes``: a cell the model leaves unburnt (9) or without a value (0) is left out, so a model is
    not scored here on where it burns, only on how much canopy it consumes where it does.
    """
    cells = cc_cells(obs_dataset, model_dataset, dataset_path, canopy_paths, classes)
    obs_classes, model_classes = cells.observations[cells.scored], cells.model[cells.scored]
    ft.logger.info(
        "canopy cover loss on %d of the %d cells with canopy the observations classify; "
        "confusion matrix (rows observed, columns model, classes %s):\n%s",
        int(cells.scored.sum()),
        int(cells.observed.sum()),
        list(classes),
        fm.confusion_matrix.multiclass_cm(obs_classes, model_classes, classes),
    )
    return obs_classes, model_classes, int(cells.observed.sum())


CANOPY_KPIS = (
    ("Class Accuracy", "class_accuracy_weight"),
    ("Within-One-Class Accuracy", "within_one_class_accuracy_weight"),
    ("Quadratic Weighted Kappa", "quadratic_weighted_kappa_weight"),
    ("Macro F1 Score", "macro_f1_weight"),
    ("Mean Absolute Class Error", "mean_absolute_class_error_weight"),
    ("Mean Class Bias", "mean_class_bias_weight"),
    ("High Loss Precision", "high_precision_weight"),
    ("High Loss Recall", "high_recall_weight"),
    ("High Loss F1 Score", "high_f1_weight"),
    ("Evaluated Share", "evaluated_share_weight"),
)


def _cc_value(kpi: str, obs_classes, model_classes, n_observed: int, parameters) -> tuple[float, float]:
    """The value of a canopy cover loss KPI and its score; NaN when it cannot be computed."""
    cmx = fm.confusion_matrix
    cm = cmx.multiclass_cm(obs_classes, model_classes, parameters.classes)
    high = np.array(sorted(parameters.high_classes))
    high_cm = cmx.binary_cm(np.isin(obs_classes, high), np.isin(model_classes, high))
    with np.errstate(divide="ignore", invalid="ignore"):
        value = float(
            {
                "Class Accuracy": lambda: cmx.multiclass_accuracy(cm),
                "Within-One-Class Accuracy": lambda: cmx.within_k_accuracy(cm, 1),
                "Quadratic Weighted Kappa": lambda: cmx.quadratic_weighted_kappa(cm),
                "Macro F1 Score": lambda: cmx.macro_f1(cm),
                "Mean Absolute Class Error": lambda: cmx.mean_absolute_class_error(cm),
                "Mean Class Bias": lambda: cmx.mean_class_bias(cm),
                "High Loss Precision": lambda: cmx.binary_precision(high_cm),
                "High Loss Recall": lambda: cmx.binary_recall_rate(high_cm),
                "High Loss F1 Score": lambda: cmx.binary_f_score(high_cm),
                "Evaluated Share": lambda: len(obs_classes) / n_observed if n_observed else np.nan,
            }[kpi]()
        )
    if np.isnan(value):
        return value, value
    if kpi == "Mean Absolute Class Error":
        return value, fm.kpi_norm_half_open_exponential(value, 0, parameters.mae_at_score_50)
    if kpi == "Mean Class Bias":
        return value, fm.kpi_norm_symmetric_open_exponential(value, parameters.bias_at_score_50)
    # A kappa below 0, worse than chance, scores 0 as chance does.
    return value, fm.kpi_norm_bounded_linear(max(value, 0.0), 0, 1)


def bench_cc_kpi(
    model_dataset: File,
    obs_dataset: File,
    ctx: dict,
    kpi_name_custom: str,
    dataset_path: str,
    canopy_paths: list[str],
    parameters,
):
    """
    A KPI of the canopy cover loss classes on the cells both files classify, scored from 0 to 100.

    A KPI that cannot be computed returns None and is left out of its group: every KPI when no cell is
    scored, a kappa when both sides give one class only.
    """
    obs_classes, model_classes, n_observed = fm.ctx_get_or_compute(
        CTX_SPEC,
        ctx,
        ("classes", "ravg_cc", "pair"),
        cc_pairs,
        obs_dataset,
        model_dataset,
        dataset_path,
        canopy_paths,
        parameters.classes,
    )
    if obs_classes.size == 0:
        ft.logger.warning(
            "%s not computed: the model burns no cell the observations classify.", kpi_name_custom
        )
        return None
    value, score = _cc_value(kpi_name_custom, obs_classes, model_classes, n_observed, parameters)
    if np.isnan(value):
        ft.logger.warning("%s not computed: no cell gives it a value.", kpi_name_custom)
        return None
    ft.logger.info("%s: %f", kpi_name_custom, value)
    return {kpi_name_custom: value, "Score": score}


def _epsg(projection: str) -> int:
    return int(projection.split(":", 1)[1])


class FireCase:  # pylint: disable=too-many-instance-attributes
    """A benchmark case run from its definition. See the module documentation."""

    COMPOSED_TARGET_PREFIX = COMPOSED_TARGET_PREFIX

    def __init__(self, definition: dict):
        problems, parameters = _check_document(definition)
        if problems:
            raise CaseDefinitionError(" ".join(problems))
        self.definition = definition
        self.parameters = parameters
        self.sha256 = definition_sha256(definition)
        self.CASE_NAME = definition["name"]  # pylint: disable=invalid-name
        self.periods = period_bounds(definition)
        self.WX_VARIABLE_SPECS = tuple(  # pylint: disable=invalid-name
            {
                "requirement": f"R_WX_{spec.variable}",
                "label": spec.label,
                "group_label": spec.group_label,
                "variable": spec.variable,
                "common_unit": spec.unit,
                "norm_m": spec.norm_m,
                "metric_set": spec.metrics,
            }
            for spec in parameters.variables
        )
        # Where a program written for FB001 looks for the weather variables.
        self.cfg = SimpleNamespace(WX_VARIABLE_SPECS=self.WX_VARIABLE_SPECS)
        self.REQUIREMENTS: dict = {}  # pylint: disable=invalid-name
        self.BENCHMARK_FUNCTIONS: dict = {}  # pylint: disable=invalid-name
        self.GROUPS: dict = {}  # pylint: disable=invalid-name
        self.AGGREGATION: dict = {}  # pylint: disable=invalid-name
        self._groups: dict[str, dict] = {}
        self._perimeters: dict[str, list[str]] = {}
        self.build_registries()

    # ---------------------------
    # Registries
    # ---------------------------
    def _requirement(self, name: str, required: dict, weather: bool = False) -> None:
        def main(model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx):
            if weather:
                return wxc.run_weather_requirement(
                    model_dataset,
                    obs_dataset,
                    list_benchmarks,
                    required_datasets,
                    ctx,
                    name,
                    self.BENCHMARK_FUNCTIONS,
                )
            return self._run_requirement(
                model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, name
            )

        self.REQUIREMENTS[name] = {"main": main, "benchmarks": [], "required_datasets": required}

    def _run_requirement(self, model_dataset, obs_dataset, list_benchmarks, required_datasets, ctx, name):
        output = {}
        if not list_benchmarks:
            return output
        met, missing = fs.validate_h5_requirement(model_dataset, required_datasets)
        if not met:
            ft.logger.warning(
                "Requirement %s not satisfied. All related benchmarks ignored. Missing item(s): %s",
                name,
                missing,
            )
            return output
        for bench_id in list_benchmarks:
            ft.logger.info("Run Benchmark %s", bench_id)
            result = self.BENCHMARK_FUNCTIONS[bench_id](model_dataset, obs_dataset, ctx)
            if result is None:
                # A KPI with nothing to score (a radar plume no volume shows) is left out of its group.
                ctx.setdefault("ignored_benchmarks", set()).add(bench_id)
                continue
            output[bench_id] = result
        return output

    def _add(self, requirement: str, group: str, bench_id: str, function, weight) -> None:
        self.BENCHMARK_FUNCTIONS[bench_id] = function
        self.REQUIREMENTS[requirement]["benchmarks"].append(bench_id)
        self.GROUPS[group]["benchmarks"][bench_id] = weight

    def _group(
        self, name: str, family_name: str, kind: str, label: str, period=None, variable=None
    ) -> None:
        self.GROUPS[name] = {"weight": self.parameters.group_weights[family_name], "benchmarks": {}}
        self._groups[name] = {"kind": kind, "label": label, "period": period, "variable": variable}

    def _add_building_damage(self, entry: dict) -> None:
        path = entry["dataset"]
        self._requirement("R_BD", {path: ["units"]})
        self._group("Building Damage", "building_damage", "B", "Building Damage")
        for index, (suffix, func) in enumerate(BINARY_METRICS, start=1):
            function = partial(
                fb001.bench_bd_generic,
                kpi_name_custom=f"Binary Structure Loss {suffix}",
                func_cm_index=func,
                dataset_path=path,
            )
            weight = self.parameters.building_damage_kpi_weight
            self._add("R_BD", "Building Damage", f"{KPI_PREFIX}BD{index:02d}", function, weight)

    def _add_burn_severity(self, entry: dict) -> None:
        path = entry["dataset"]
        group_path = path.rsplit("/", 1)[0]
        required = {
            group_path: ["crs"],
            path: ["units", "_FillValue"],
            f"{group_path}/position_lat": ["units"],
            f"{group_path}/position_lon": ["units"],
        }
        self._requirement("R_SV", required)
        self._group("Burn Severity", "burn_severity_cbi", "S", "Burn Severity")
        for index, (suffix, func) in enumerate(BINARY_METRICS, start=1):
            function = partial(
                bench_cbi_index,
                kpi_name_custom=f"Binary High Severity {suffix}",
                func_cm_index=func,
                dataset_path=path,
                high_classes=self.parameters.cbi_high_classes,
                other_classes=self.parameters.cbi_other_classes,
            )
            self._add(
                "R_SV",
                "Burn Severity",
                f"{KPI_PREFIX}SV{index:02d}",
                function,
                self.parameters.cbi_kpi_weight,
            )

    def _add_canopy_cover(self, entry: dict) -> None:
        path = entry["dataset"]
        group_path = path.rsplit("/", 1)[0]
        required = {
            group_path: ["crs"],
            path: ["units", "_FillValue"],
            f"{group_path}/position_lat": ["units"],
            f"{group_path}/position_lon": ["units"],
        }
        self._requirement("R_CC", required)
        self._group("Canopy Cover Loss", "canopy_cover_loss", "C", "Canopy Cover Loss")
        parameters = self.parameters.canopy_cover
        for index, (kpi_name, weight_key) in enumerate(CANOPY_KPIS, start=1):
            function = partial(
                bench_cc_kpi,
                kpi_name_custom=kpi_name,
                dataset_path=path,
                canopy_paths=list(entry["canopy"]),
                parameters=parameters,
            )
            self._add(
                "R_CC",
                "Canopy Cover Loss",
                f"{KPI_PREFIX}CC{index:02d}",
                function,
                parameters.kpi_weights[weight_key],
            )

    def _add_perimeters(self, entry: dict) -> None:
        projection = self.definition["projection"]
        weights = self.parameters.perimeter_weights
        relative_error = self.parameters.area_relative_error_at_score_50
        number = 1
        for item in entry["periods"]:
            period, perimeters = item["period"], list(item["perimeters"])
            requirement, group = f"R_FP_{period}", f"Fire Perimeters {period}"
            self._requirement(requirement, {path: ["rel_path", "time"] for path in perimeters})
            self._group(group, "fire_perimeters", "P", "Fire Perimeters", period=period)
            self._perimeters[group] = perimeters
            functions = [
                (
                    partial(
                        fb001.bench_fp_generic_index,
                        kpi_name_custom=name,
                        period_name=period,
                        list_perims=perimeters,
                        func_index=func,
                        func_index_rslt_agg=aggregate,
                        projection=projection,
                    ),
                    weights[weight],
                )
                for name, func, aggregate, weight in PERIMETER_INDICES
            ]
            functions.append(
                (
                    partial(
                        fb001.bench_fp_generic_area_final_bias,
                        period_name=period,
                        list_perims=perimeters,
                        projection_epsg=_epsg(projection),
                        relative_error=relative_error,
                    ),
                    weights["final_area_bias_weight"],
                )
            )
            functions.append(
                (
                    partial(
                        fb001.bench_fp_generic_area,
                        kpi_name_custom="Burn Area RMSE",
                        period_name=period,
                        list_perims=perimeters,
                        func=fm.stats.rmse,
                        projection_epsg=_epsg(projection),
                        relative_error=relative_error,
                    ),
                    weights["area_rmse_weight"],
                )
            )
            for function, weight in functions:
                self._add(requirement, group, f"{KPI_PREFIX}FP{number:02d}", function, weight)
                number += 1

    def _add_weather(self, entry: dict) -> None:
        for spec in self.WX_VARIABLE_SPECS:
            self._requirement(
                spec["requirement"],
                {"station_pattern": "station_", "variable": spec["variable"]},
                weather=True,
            )
        number = 1
        for period in entry["periods"]:
            for spec in self.WX_VARIABLE_SPECS:
                group = f"{spec['group_label']} {period}"
                self._group(
                    group, "weather_stations", "W", spec["label"], period=period, variable=spec["variable"]
                )
                for metric_name, metric_func in WX_METRICS[spec["metric_set"]]:
                    for set_name in entry["station_sets"]:
                        set_text, station_set, weight_key = STATION_SETS[set_name]
                        for stat_name, stat_func in WX_STATS:
                            function = partial(
                                fb001.bench_wx_generic_index,
                                kpi_name_custom=f"{spec['label']} {metric_name} {stat_name} {period} {set_text}",
                                period=self.periods[period],
                                wx_variable_name=spec["variable"],
                                common_unit=spec["common_unit"],
                                metric_func=metric_func,
                                stat_func=stat_func,
                                value_norm_param_m=spec["norm_m"],
                                station_set=station_set,
                            )
                            weight = getattr(self.parameters, weight_key)
                            self._add(
                                spec["requirement"], group, f"{KPI_PREFIX}WX{number:03d}", function, weight
                            )
                            number += 1

    def _add_radar_plume(self, entry: dict) -> None:
        parameters = self.parameters.radar_plume
        group_path = entry["model_group"]
        self._requirement("R_RP", model_requirements(group_path, entry))
        number = 1
        for section in entry["sections"]:
            for period in entry["periods"]:
                group = f"Radar Plume {section} {period}"
                self._group(group, "radar_plume", "R", "Radar Plume", period=period)
                for kpi_name, kpi, weight_key in RADAR_KPIS:
                    function = partial(
                        bench_radar_plume,
                        kpi_name_custom=kpi_name,
                        kpi=kpi,
                        section=section,
                        period_name=period,
                        period=self.periods[period],
                        model_group=group_path,
                        parameters=parameters,
                    )
                    self._add(
                        "R_RP",
                        group,
                        f"{KPI_PREFIX}RP{number:02d}",
                        function,
                        parameters.kpi_weights[weight_key],
                    )
                    number += 1
        # The plume over a radar's frame (its top, footprint, and top map), after the sections, so
        # their KPI ids stay those of a definition without `echo_top`.
        if entry.get("echo_top"):
            self._requirement("R_RT", top_requirements(group_path, entry))
        for site in entry.get("echo_top", []):
            for period in entry["periods"]:
                group = f"Radar Plume Frame {site} {period}"
                self._group(group, "radar_plume", "R", "Radar Plume Frame", period=period)
                for kpi_name, kpi, weight_key in RADAR_TOP_KPIS:
                    function = partial(
                        bench_radar_top,
                        kpi_name_custom=kpi_name,
                        kpi=kpi,
                        site=site,
                        period_name=period,
                        period=self.periods[period],
                        model_group=group_path,
                        parameters=parameters,
                    )
                    self._add(
                        "R_RT",
                        group,
                        f"{KPI_PREFIX}RP{number:02d}",
                        function,
                        parameters.kpi_weights[weight_key],
                    )
                    number += 1

    def _add_frp(self, entry: dict) -> None:
        parameters = self.parameters.fire_radiative_power
        group_path = entry["model_group"]
        systems = {system.name: system for system in parameters.systems}
        every_stream = [stream for streams in entry["systems"].values() for stream in streams]
        weights = parameters.kpi_weights
        kpis = [
            (f"In-Band Fraction {systems[name].label}", "in_band", streams, systems[name].weight)
            for name, streams in entry["systems"].items()
        ]
        kpis += [
            ("In-Band Fraction All", "in_band", every_stream, weights["all_weight"]),
            ("Above-Band Fraction", "above", every_stream, weights["above_weight"]),
            ("Below-Band Fraction", "below", every_stream, weights["below_weight"]),
        ]
        # The log error came after the KPIs above: its ids follow theirs, so theirs did not change.
        log_errors = [
            (f"Band Log Error {systems[name].label}", "log_error", streams, weights["log_error_weight"])
            for name, streams in entry["systems"].items()
        ]
        self._requirement("R_FR", frp.model_requirements(group_path))
        for period in entry["periods"]:
            group = f"Fire Radiative Power {period}"
            self._group(group, "fire_radiative_power", "F", "Fire Radiative Power", period=period)
        order = [
            (period, item) for items in (kpis, log_errors) for period in entry["periods"] for item in items
        ]
        for number, (period, (kpi_name, kpi, streams, weight)) in enumerate(order, start=1):
            function = partial(
                frp.bench_frp,
                kpi_name_custom=kpi_name,
                kpi=kpi,
                streams=list(streams),
                period_name=period,
                period=self.periods[period],
                frame=list(entry["frame"]),
                model_group=group_path,
                parameters=parameters,
            )
            self._add(
                "R_FR", f"Fire Radiative Power {period}", f"{KPI_PREFIX}FR{number:02d}", function, weight
            )

    def build_registries(self):
        """Build the registries again from the definition. Composed targets are forgotten."""
        self.REQUIREMENTS, self.BENCHMARK_FUNCTIONS, self.GROUPS, self.AGGREGATION = {}, {}, {}, {}
        self._groups, self._perimeters = {}, {}
        builders = {
            "building_damage": self._add_building_damage,
            "burn_severity_cbi": self._add_burn_severity,
            "canopy_cover_loss": self._add_canopy_cover,
            "fire_perimeters": self._add_perimeters,
            "weather_stations": self._add_weather,
            "radar_plume": self._add_radar_plume,
            "fire_radiative_power": self._add_frp,
        }
        for entry in self.definition["families"]:
            builders[entry["family"]](entry)
        self._create_aggregation_schemes()
        return self.BENCHMARK_FUNCTIONS, self.GROUPS, self.AGGREGATION

    def _copy_groups(self, names) -> dict:
        return {
            name: {
                "weight": self.GROUPS[name]["weight"],
                "benchmarks": dict(self.GROUPS[name]["benchmarks"]),
            }
            for name in names
        }

    def perimeter_values(
        self, model_dataset: File, obs_dataset: File, list_perims: list[str] | None = None
    ) -> list[dict]:
        """The case's per-perimeter values, in the projection of its definition.

        See `c001_caldor.perimeter_values_generic`.
        """
        projection = self.definition["projection"]
        return fb001.perimeter_values_generic(
            model_dataset, obs_dataset, list_perims, projection, _epsg(projection)
        )

    def frp_values(self, model_dataset: File, obs_dataset: File) -> dict | None:
        """
        What the fire radiative power KPIs compare, for a figure; None when the case has no such family.

        See `fire_case_frp.frp_values`.
        """
        entry = family(self.definition, "fire_radiative_power")
        if entry is None:
            return None
        periods = {name: self.periods[name] for name in entry["periods"]}
        return frp.frp_values(
            model_dataset, obs_dataset, entry, periods, self.parameters.fire_radiative_power
        )

    def radar_plume_values(self, model_dataset: File, obs_dataset: File) -> dict | None:
        """
        What the radar plume KPIs compare, for a figure; None when the case has no such family.

        See `fire_case_radar.radar_plume_values`.
        """
        entry = family(self.definition, "radar_plume")
        if entry is None:
            return None
        periods = {name: self.periods[name] for name in entry["periods"]}
        return radar.radar_plume_values(
            model_dataset, obs_dataset, entry, periods, self.parameters.radar_plume
        )

    def radar_plume_threshold_sweep(
        self, model_dataset: File, obs_dataset: File, thresholds, min_dbz: float | None = None
    ) -> dict | None:
        """
        The section KPIs of the radar plume at each tracer threshold, to calibrate
        ``tracer_threshold``; None when the case has no such family.

        See `fire_case_radar.radar_plume_threshold_sweep`.
        """
        entry = family(self.definition, "radar_plume")
        if entry is None:
            return None
        periods = {name: self.periods[name] for name in entry["periods"]}
        return radar.radar_plume_threshold_sweep(
            model_dataset,
            obs_dataset,
            entry,
            periods,
            self.parameters.radar_plume,
            thresholds,
            min_dbz=min_dbz,
        )

    def canopy_cover_values(self, model_dataset: File, obs_dataset: File) -> dict | None:
        """
        What the canopy cover loss KPIs compare, for a figure; None when the case has no such family.

        ``observations`` and ``model`` are the class grids of both files at ``dataset_path``, with the
        observations' ``position_lat`` and ``position_lon`` and its group's ``crs``; ``canopy``,
        ``observed``, and ``scored`` are the masks of ``cc_cells``. ``confusion_matrix`` is the matrix
        of the KPIs on the scored cells, rows observed and columns model, in the order of ``classes``.
        """
        entry = family(self.definition, "canopy_cover_loss")
        if entry is None:
            return None
        path = entry["dataset"]
        classes = tuple(self.parameters.canopy_cover.classes)
        cells = cc_cells(obs_dataset, model_dataset, path, list(entry["canopy"]), classes)
        group = obs_dataset[path.rsplit("/", 1)[0]]
        crs = group.attrs.get("crs")
        return {
            "dataset_path": path,
            "classes": list(classes),
            "high_classes": list(self.parameters.canopy_cover.high_classes),
            "crs": crs.decode() if isinstance(crs, bytes) else (None if crs is None else str(crs)),
            "position_lat": np.asarray(group["position_lat"][()]),
            "position_lon": np.asarray(group["position_lon"][()]),
            "observations": cells.observations,
            "model": cells.model,
            "canopy": cells.canopy,
            "observed": cells.observed,
            "scored": cells.scored,
            "confusion_matrix": fm.confusion_matrix.multiclass_cm(
                cells.observations[cells.scored], cells.model[cells.scored], classes
            ),
            "n_observed": int(cells.observed.sum()),
            "n_scored": int(cells.scored.sum()),
        }

    def _of_kind(self, kind: str) -> list[str]:
        return [name for name, info in self._groups.items() if info["kind"] == kind]

    def _create_aggregation_schemes(self) -> None:
        self.AGGREGATION["A"] = self._copy_groups(self.GROUPS)
        for target, kind in (
            ("B", "B"),
            ("S", "S"),
            ("CC", "C"),
            ("FP", "P"),
            ("WX", "W"),
            ("RP", "R"),
            ("FR", "F"),
        ):
            if self._of_kind(kind):
                self.AGGREGATION[target] = self._copy_groups(self._of_kind(kind))

    # ---------------------------
    # Targets
    # ---------------------------
    def _used_periods(self) -> list[str]:
        used = {info["period"] for info in self._groups.values() if info["period"]}
        return [name for name in self.periods if name in used]

    def _period_ref(self, period: str) -> dict:
        start, end = self.periods[period]
        return {"target": period, "start": start, "end": end}

    def describe_available_targets(self, benchmark_target: str | None = None, obs_data=None) -> dict:
        """The target syntax and periods of the case, or the details of one target."""
        del obs_data  # the definition holds everything a target needs
        if benchmark_target is None:
            standalone = {"A": "Every KPI group of the case"}
            for target, kind, label in (
                ("B", "B", "Building Damage"),
                ("S", "S", "Burn Severity"),
                ("CC", "C", "Canopy Cover Loss"),
                ("FP", "P", "Fire Perimeters (all periods)"),
                ("WX", "W", "Weather Stations (all periods)"),
                ("RP", "R", "Radar Plume (all periods)"),
                ("FR", "F", "Fire Radiative Power (all periods)"),
            ):
                if self._of_kind(kind):
                    standalone[target] = label
            flags = {}
            for flag, kind, label in (
                ("B", "B", "Building Damage"),
                ("S", "S", "Burn Severity"),
                ("C", "C", "Canopy Cover Loss"),
                ("P", "P", "Fire Perimeters"),
                ("T", "W", "Weather Stations (TSO only)"),
                ("W", "W", "Weather Stations (TSO and all sources)"),
                ("R", "R", "Radar Plume"),
                ("F", "F", "Fire Radiative Power"),
            ):
                if self._of_kind(kind):
                    flags[flag] = label
            return {
                "standalone_targets": standalone,
                "period_target_syntax": "PERIOD_FLAGS",
                "periods": [self._period_ref(period) for period in self._used_periods()],
                "kpi_groups": flags,
            }

        target = self.resolve_benchmark_target(benchmark_target)
        selected = self.GROUPS if target == "0" else self.AGGREGATION[target]
        match = PERIOD_TARGET_PATTERN.fullmatch(target)
        perimeters, kpis = [], []
        for group_name, group in selected.items():
            for path in self._perimeters.get(group_name, []):
                if path not in [item["path"] for item in perimeters]:
                    perimeters.append({"time": path.rsplit("_", 1)[-1], "path": path})
            for bench_id, weight in group["benchmarks"].items():
                keywords = getattr(self.BENCHMARK_FUNCTIONS[bench_id], "keywords", {})
                kpis.append(
                    {
                        "id": bench_id,
                        "name": self._kpi_name(bench_id),
                        "group": CATEGORIES[self._groups[group_name]["kind"]],
                        "weight": None if target == "0" else weight,
                        "value_norm_param_m": keywords.get("value_norm_param_m"),
                    }
                )
        return {
            "target": target,
            "period": self._period_ref(match.group(1)) if match else None,
            "aggregated": target != "0",
            "kpi_groups": {
                kind: label
                for kind, label in CATEGORIES.items()
                if any(self._groups[name]["kind"] == kind for name in selected)
            },
            "perimeters": perimeters,
            "weather_stations": [],
            "kpis": kpis,
        }

    def _kpi_name(self, bench_id: str) -> str:
        function = self.BENCHMARK_FUNCTIONS[bench_id]
        keywords = getattr(function, "keywords", {})
        if function.func is fb001.bench_fp_generic_index:
            return f"{keywords['kpi_name_custom']} Index"
        if function.func is fb001.bench_fp_generic_area_final_bias:
            return "Final Burn Area Bias"
        return keywords["kpi_name_custom"]

    def resolve_benchmark_target(self, benchmark_target: str) -> str:
        """The canonical name of a target, registered in ``AGGREGATION``.

        A target is a scheme (``A``, ``B``, ``S``, ``CC``, ``FP``, ``WX``, ``RP``, ``FR``, a composed one),
        ``0`` for every KPI unaggregated, or a period and flags such as ``P02_PW`` or ``H003_T``.
        """
        raw = str(benchmark_target).strip()
        if raw == "0" or raw in self.AGGREGATION:
            return raw
        target = raw.upper()
        if target in self.AGGREGATION:
            return target
        match = PERIOD_TARGET_PATTERN.fullmatch(target)
        if match is None:
            raise ValueError(
                f"Invalid benchmark target '{benchmark_target}'. Expected a scheme "
                f"({', '.join(self.AGGREGATION)}) or a period and flags, such as P01_PW."
            )
        period, flags = match.groups()
        if period not in self.periods:
            raise ValueError(f"Unknown period selector '{period}'.")
        if "T" in flags and "W" in flags:
            raise ValueError(
                f"Invalid benchmark target '{benchmark_target}'. Weather flags T and W cannot be combined: "
                "T selects TSO only, while W already includes TSO and all sources."
            )
        flags = "".join(flag for flag in FLAG_ORDER if flag in flags)
        # A group of the whole event (building damage, burn severity) belongs to every period.
        names = [
            name
            for name, info in self._groups.items()
            if (info["kind"] in flags or (info["kind"] == "W" and "T" in flags))
            and info["period"] in (None, period)
        ]
        aggregation = self._copy_groups(names)
        if "T" in flags:
            for name, group in aggregation.items():
                if self._groups[name]["kind"] == "W":
                    group["benchmarks"] = {
                        bench_id: weight
                        for bench_id, weight in group["benchmarks"].items()
                        if self.BENCHMARK_FUNCTIONS[bench_id].keywords["station_set"]
                        is fs.WeatherStationSet.TSO
                    }
        canonical = f"{period}_{flags}"
        self.AGGREGATION[canonical] = aggregation
        return canonical

    def normalize_benchmark_target(self, benchmark_target: str) -> str:
        """The canonical name of a target."""
        return self.resolve_benchmark_target(benchmark_target)

    def get_list_benchmark_with_agg(self, agg_dict: dict, agg_scheme: str) -> list[str]:
        """The KPIs of a scheme, each once, in order."""
        if agg_scheme == "0":
            return list(self.BENCHMARK_FUNCTIONS)
        listed = []
        for group in agg_dict.get(agg_scheme, {}).values():
            for bench_id in group["benchmarks"]:
                if bench_id not in listed:
                    listed.append(bench_id)
        return listed

    def get_benchmark_requirements(self) -> dict[str, list[str]]:
        """The requirements each KPI depends on."""
        return wxc.benchmark_requirements(self.REQUIREMENTS)

    def describe_composable_groups(self) -> list[dict]:
        """Every KPI group a score card can be composed of, in registry order (see FB001's)."""
        return [
            {
                "name": name,
                "label": info["label"],
                "kind": info["kind"],
                "period": self._period_ref(info["period"]) if info["period"] else None,
                "variable": info["variable"],
                "weight": self.GROUPS[name]["weight"],
                "kpis": dict(self.GROUPS[name]["benchmarks"]),
            }
            for name, info in self._groups.items()
        ]

    def compose_target(self, group_names: list[str]) -> str:
        """Register the scheme made of ``group_names``, with their own weights, and return its name."""
        selected = set(group_names)
        if not selected:
            raise ValueError("A composed target needs at least one KPI group.")
        unknown = sorted(selected - self.GROUPS.keys())
        if unknown:
            raise ValueError(f"Unknown KPI group(s): {', '.join(unknown)}.")
        digest = hashlib.sha256("\n".join(sorted(selected)).encode("utf-8")).hexdigest()
        target = f"{COMPOSED_TARGET_PREFIX}{digest[:12]}"
        self.AGGREGATION[target] = self._copy_groups([name for name in self.GROUPS if name in selected])
        return target

    def _display_names(self, scheme: str) -> dict[str, str]:
        selected = self.GROUPS if scheme == "0" else self.AGGREGATION.get(scheme, {})
        return {name: CATEGORIES[self._groups[name]["kind"]] for name in selected}

    # ---------------------------
    # Run
    # ---------------------------
    def run_all_benchmarks(
        self, model_output: Path, scheme: str, list_bench: list[str], obs_data: Path
    ) -> dict:
        """Score every KPI of ``list_bench`` and aggregate them with ``scheme``."""
        ctx = {"ignored_benchmarks": set()}
        with File(obs_data, "r") as obs_dataset, File(model_output, "r") as model_dataset:
            wxc.validate_benchmark_inputs(obs_dataset, model_dataset)
            wxc.validate_selected_weather_confidence(obs_dataset, self.BENCHMARK_FUNCTIONS, list_bench, ctx)
            results = {
                "benchmarks": wxc.run_requirements(
                    model_dataset, obs_dataset, self.REQUIREMENTS, list_bench, ctx
                )
            }
        ignored = ctx["ignored_benchmarks"]
        wxc.raise_if_selected_benchmarks_missing(
            results["benchmarks"], list_bench, ignored, self.REQUIREMENTS
        )
        if scheme == "0":
            return results
        return wxc.aggregate_scheme_scores(
            results, scheme, self.AGGREGATION[scheme], ignored, self._display_names(scheme)
        )

    def _header(self, model_output: Path, obs_data: Path, name: str) -> dict:
        with File(obs_data, "r") as obs:
            version = obs.attrs.get("version", "Unofficial")
        version = version.decode() if isinstance(version, bytes) else str(version)
        header = {
            "created_on": fs.current_datetime_iso8601(include_seconds=True),
            "case_version": version,
            "firebench_version": fb_version,
            "case_name": self.CASE_NAME,
            "benchmark_short_name": self.CASE_NAME,
            # The id of a case defined outside FireBench is given by whoever keeps the case.
            "case_id": None,
            "case_schema": self.definition["schema"],
            "case_definition_sha256": self.sha256,
            "parameters": {**self.parameters.reference(), "sha256": self.parameters.sha256},
            "evaluated_model_name": str(name) if name else model_output.stem,
        }
        files = fb001.get_files_hash(model_output, obs_data)
        files["benchmark_script"] = ft.calculate_sha256(Path(__file__))
        return ft.merge_dictionaries(header, files)

    def run_benchmark(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        model_output,
        benchmark_target: str = "A",
        name: str = "",
        overwrite: bool = False,
        sign: tuple[str, str] | None = None,
        obs_data=None,
        output_json=DEFAULT_OUTPUT_PATH_JSON,
        score_card_report=DEFAULT_SCORE_CARD_REPORT_PATH,
        score_card_full_name: bool = False,
        groups: list[str] | None = None,
    ) -> dict:
        """
        Score ``model_output`` against ``obs_data`` on ``benchmark_target``, or on ``groups`` when given.

        The arguments and the result file are those of ``run_caldor_benchmark``; the result names the
        definition by its hash instead of a case id.
        """
        if obs_data is None:
            raise ValueError("A generic case needs the observation file (`obs_data`).")
        model_output, obs_data = Path(model_output), Path(obs_data)
        if is_template(obs_data):
            raise CaseDefinitionError(TEMPLATE_REFUSAL)
        output_json, score_card_report = Path(output_json), Path(score_card_report)
        if not fb001.overwrite_previous_run(overwrite, output_json):
            ft.logger.info("Overwrite not authorized for output file: %s. Benchmark stopped", output_json)
            return {}

        output = self._header(model_output, obs_data, name)
        output["certificates_input"] = fsi.retrieve_h5_certificates(
            obs_data, model_output if sign else None
        )
        if fsi.get_observation_certificate_verification(output["certificates_input"]) is None:
            ft.logger.warning(
                "Observational dataset %s has no %s certificate; forcing verification level %s.",
                obs_data,
                fsi.Certificates.FB_VERIFIED_OBS_DATASET.value,
                fsi.DEFAULT_VL,
            )
        output["verification_lvl"] = fsi.compute_input_verification_lvl(output["certificates_input"])

        self.build_registries()
        scheme = (
            self.compose_target(groups)
            if groups is not None
            else self.resolve_benchmark_target(benchmark_target)
        )
        list_bench = self.get_list_benchmark_with_agg(self.AGGREGATION, scheme)
        if not list_bench:
            raise ValueError(f"The target `{scheme}` holds no KPI of this case.")
        output = ft.merge_dictionaries(
            output, self.run_all_benchmarks(model_output, scheme, list_bench, obs_data)
        )

        if sign:
            key, signer = sign
            output = fsi.certify_benchmark_run(output, key, signer)
        fm.save_as_table(
            score_card_report, output, bool(sign), "certificate_verif_lvl", full_name=score_card_full_name
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


def load_case(definition: dict | None, std_file=None) -> FireCase:
    """
    The case of ``definition``, checked against the standard file ``std_file`` when given.

    Without a definition, the one kept in ``std_file`` is read. A definition with problems is refused
    with all of them in the message.
    """
    if definition is None:
        if std_file is None:
            raise CaseDefinitionError("Give a definition, or a standard file that holds one.")
        definition = read_case_definition(std_file)
        if definition is None:
            raise CaseDefinitionError(f"{std_file} holds no case definition.")
    if std_file is not None:
        problems = check_case(definition, std_file)
        if problems:
            raise CaseDefinitionError(" ".join(problems))
    return FireCase(definition)
