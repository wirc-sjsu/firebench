"""Auditable Synoptic JSON to FireBench weather-HDF5 QC pipeline."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytz
from pytz.exceptions import AmbiguousTimeError, NonExistentTimeError

from ...standardize.files import new_std_file
from ...standardize.synoptic import standardize_synoptic_raws_from_json
from ...standardize.synoptic_data import VARIABLE_CONVERSION
from ...standardize.tools import validate_h5_std
from ...tools import calculate_sha256
from .constants import default_config
from .data import compute_outage_stats, compute_stats, load_h5, run_assertions, run_outage_assertions
from .file_io import atomic_write_text, temporary_sibling

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


MANIFEST_VERSION = 1
POLICY_VERSION = 1
SUPPORTED_VARIABLES = {value["std_name"] for value in VARIABLE_CONVERSION.values()}
RAW_TO_STANDARD = {key: value["std_name"] for key, value in VARIABLE_CONVERSION.items()}

DEFAULT_POLICY = {
    "version": POLICY_VERSION,
    "output": {
        "authors": "FireBench weather QC pipeline",
        "description": "Weather observations standardized and quality controlled by FireBench.",
        "compression_level": 3,
    },
    "thresholds": {
        "zero_wind_fraction": 0.5,
        "zero_wind_run_minutes": 1440.0,
        "temporal_break_factor": 3.0,
    },
    "gui": {
        "frozen_min_run": 10,
        "max_var_outage_min": 1440.0,
        "full_outage_min": 360.0,
        "duplicate_timestamp_limit": 2,
    },
    "bounds": {
        variable: [lower, upper, unit]
        for variable, (lower, upper, unit) in default_config()["bounds"].items()
    },
    "required_windows": [],
}


class QCError(ValueError):
    """Raised when a QC input, policy, manifest, or decision is invalid."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _operation_id(source_sha256: str, code: str, target: dict, selector: dict, effect: dict) -> str:
    identity = {
        "source_sha256": source_sha256,
        "code": code,
        "target": target,
        "selector": selector,
        "effect": effect,
    }
    return f"WXQC-{code}-{_digest(identity)[:12].upper()}"


def _finding_id(source_sha256: str, code: str, target: dict, message: str) -> str:
    return f"WXQF-{code}-{_digest([source_sha256, target, message])[:12].upper()}"


def _action(
    source_sha256: str,
    code: str,
    severity: str,
    station: str | None,
    variable: str | None,
    selector: dict,
    effect: dict,
    message: str,
    *,
    automatic: bool,
    linked_findings: list[str] | None = None,
) -> dict:
    target = {"station": station, "variable": variable}
    status = "auto_accepted" if automatic else "pending"
    operation_id = _operation_id(source_sha256, code, target, selector, effect)
    return {
        "id": operation_id,
        "code": code,
        "severity": severity,
        "target": target,
        "selector": selector,
        "effect": effect,
        "message": message,
        "automatic": automatic,
        "decision": {"status": status, "reviewer": None, "decided_at": None, "comment": None},
        "application": {"candidate": "not_applicable", "final": "not_built"},
        "linked_findings": linked_findings or [],
        "history": [],
        "supersedes": None,
    }


def _finding(source_sha256: str, code: str, severity: str, station: str, message: str) -> dict:
    target = {"station": station}
    return {
        "id": _finding_id(source_sha256, code, target, message),
        "code": code,
        "severity": severity,
        "target": target,
        "message": message,
    }


def load_policy(path: str | Path | dict | None) -> dict:
    """Load and validate a versioned TOML QC policy."""
    policy = copy.deepcopy(DEFAULT_POLICY)
    if isinstance(path, dict):
        supplied = copy.deepcopy(path)
    elif path is not None:
        with Path(path).open("rb") as stream:
            supplied = tomllib.load(stream)
    else:
        supplied = {}
    if supplied:
        for section, value in supplied.items():
            if isinstance(value, dict) and isinstance(policy.get(section), dict):
                policy[section].update(value)
            else:
                policy[section] = value
    if policy.get("version") != POLICY_VERSION:
        raise QCError(f"unsupported QC policy version {policy.get('version')!r}; expected {POLICY_VERSION}")
    output = policy["output"]
    level = output.get("compression_level")
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 22:
        raise QCError("output.compression_level must be an integer from 1 through 22")
    for key in ("zero_wind_fraction", "zero_wind_run_minutes", "temporal_break_factor"):
        value = policy["thresholds"].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise QCError(f"thresholds.{key} must be a finite number")
    if not 0 <= policy["thresholds"]["zero_wind_fraction"] <= 1:
        raise QCError("thresholds.zero_wind_fraction must be between zero and one")
    normalized_bounds = {}
    for variable, bounds in policy.get("bounds", {}).items():
        if not isinstance(bounds, list) or len(bounds) != 3:
            raise QCError(f"bounds.{variable} must be [minimum, maximum, unit]")
        lower, upper, unit = bounds
        if (
            isinstance(lower, bool)
            or not isinstance(lower, (int, float))
            or isinstance(upper, bool)
            or not isinstance(upper, (int, float))
            or not math.isfinite(lower)
            or not math.isfinite(upper)
            or lower >= upper
            or not isinstance(unit, str)
        ):
            raise QCError(f"bounds.{variable} requires ordered finite numbers and a unit string")
        normalized_bounds[variable] = [float(lower), float(upper), unit]
    policy["bounds"] = normalized_bounds
    windows = policy.get("required_windows", [])
    if not isinstance(windows, list):
        raise QCError("required_windows must be an array of tables")
    normalized_windows = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict) or not {"name", "start", "end"} <= set(window):
            raise QCError(f"required_windows[{index}] requires name, start, and end")
        start = _parse_aware_iso(window["start"], f"required_windows[{index}].start")
        end = _parse_aware_iso(window["end"], f"required_windows[{index}].end")
        if start >= end:
            raise QCError(f"required_windows[{index}] start must precede end")
        normalized_windows.append(
            {"name": str(window["name"]), "start": start.isoformat(), "end": end.isoformat()}
        )
    policy["required_windows"] = normalized_windows
    return policy


def _parse_aware_iso(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise QCError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise QCError(f"{label} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _parse_source_time(value: Any, timezone_name: str) -> datetime:
    if not isinstance(value, str):
        raise QCError(f"timestamp must be a string, got {type(value).__name__}")
    tz = pytz.timezone(timezone_name)
    if value.endswith("Z"):
        fmt = "%Y%m%d%H%M%SZ" if value[:-1].isdigit() else "%Y-%m-%dT%H:%M:%SZ"
        return pytz.utc.localize(datetime.strptime(value, fmt))
    if "T" in value and ("+" in value[10:] or "-" in value[10:]):
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    fmt = "%Y%m%d%H%M%S" if value.isdigit() else "%Y-%m-%dT%H:%M:%S"
    return tz.localize(datetime.strptime(value, fmt), is_dst=None).astimezone(pytz.utc)


def _row_signature(observations: dict, index: int) -> str:
    row = {}
    for variable, values in sorted(observations.items()):
        if not isinstance(values, list) or index >= len(values):
            row[variable] = "<missing>"
            continue
        value = values[index]
        if isinstance(value, float) and math.isnan(value):
            value = "<nan>"
        row[variable] = value
    return _canonical(row)


def _normalize_source(source_path: Path, source_sha256: str) -> tuple[dict, list[dict], list[dict]]:
    with source_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or not isinstance(data.get("STATION"), list):
        raise QCError("Synoptic input must contain a STATION array")
    actions: list[dict] = []
    findings: list[dict] = []
    normalized = copy.deepcopy(data)
    for station in normalized["STATION"]:
        station_id = str(station.get("STID", ""))
        observations = station.get("OBSERVATIONS", {})
        raw_times = observations.get("date_time", [])
        malformed_lengths = sorted(
            variable
            for variable, values in observations.items()
            if variable != "date_time" and isinstance(values, list) and len(values) != len(raw_times)
        )
        if not raw_times or malformed_lengths:
            message = (
                "Station has no timestamps"
                if not raw_times
                else f"Observation arrays do not align with timestamps: {', '.join(malformed_lengths)}"
            )
            finding = _finding(source_sha256, "STRUCT", "ERROR", station_id, message)
            findings.append(finding)
            actions.append(
                _action(
                    source_sha256,
                    "EXCL",
                    "ERROR",
                    station_id,
                    None,
                    {"variables": malformed_lengths},
                    {"kind": "exclude_station"},
                    message,
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
            station["_WXQC_QUARANTINED"] = True
            continue
        try:
            parsed_times = [_parse_source_time(value, station["TIMEZONE"]) for value in raw_times]
        except (KeyError, ValueError, AmbiguousTimeError, NonExistentTimeError, QCError) as exc:
            finding = _finding(source_sha256, "TIME", "ERROR", station_id, f"Invalid timestamp: {exc}")
            findings.append(finding)
            actions.append(
                _action(
                    source_sha256,
                    "EXCL",
                    "ERROR",
                    station_id,
                    None,
                    {"reason": "invalid_timestamp"},
                    {"kind": "exclude_station"},
                    "Exclude station because its timestamp axis cannot be standardized",
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
            station["_WXQC_QUARANTINED"] = True
            continue
        observations["date_time"] = [value.isoformat().replace("+00:00", "Z") for value in parsed_times]
        if raw_times:
            actions.append(
                _action(
                    source_sha256,
                    "TIME",
                    "INFO",
                    station_id,
                    "time",
                    {"records": len(raw_times)},
                    {"kind": "normalize_timestamps", "timezone": "UTC"},
                    f"Normalized {len(raw_times)} timestamps to unambiguous UTC instants",
                    automatic=True,
                )
            )

        backwards = [
            index for index in range(1, len(parsed_times)) if parsed_times[index] < parsed_times[index - 1]
        ]
        if backwards:
            message = f"Timestamp axis has {len(backwards)} backwards jump(s)"
            finding = _finding(source_sha256, "TIMEORDER", "ERROR", station_id, message)
            findings.append(finding)
            actions.append(
                _action(
                    source_sha256,
                    "EXCL",
                    "ERROR",
                    station_id,
                    None,
                    {"backwards_indices": backwards},
                    {"kind": "exclude_station"},
                    message,
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
            station["_WXQC_QUARANTINED"] = True

        duplicate_indices = []
        conflicting_times = []
        first_by_time: dict[str, tuple[int, str]] = {}
        for index, timestamp in enumerate(observations["date_time"]):
            signature = _row_signature(observations, index)
            if timestamp not in first_by_time:
                first_by_time[timestamp] = (index, signature)
            elif first_by_time[timestamp][1] == signature:
                duplicate_indices.append(index)
            else:
                conflicting_times.append(timestamp)
        if duplicate_indices:
            actions.append(
                _action(
                    source_sha256,
                    "DUP",
                    "WARN",
                    station_id,
                    None,
                    {"raw_indices": duplicate_indices},
                    {"kind": "remove_identical_duplicates", "count": len(duplicate_indices)},
                    f"Removed {len(duplicate_indices)} identical duplicate records",
                    automatic=True,
                )
            )
        if conflicting_times:
            message = f"Conflicting records at {len(set(conflicting_times))} duplicate timestamp(s)"
            finding = _finding(source_sha256, "DUPC", "ERROR", station_id, message)
            findings.append(finding)
            actions.append(
                _action(
                    source_sha256,
                    "EXCL",
                    "ERROR",
                    station_id,
                    None,
                    {"timestamps": sorted(set(conflicting_times))},
                    {"kind": "exclude_station"},
                    message,
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
            station["_WXQC_QUARANTINED"] = True

        height_count = 0
        for sensor in station.get("SENSOR_VARIABLES", {}).values():
            if not isinstance(sensor, dict):
                continue
            for metadata in sensor.values():
                if not isinstance(metadata, dict):
                    continue
                position = metadata.get("position")
                if isinstance(position, str):
                    try:
                        parsed = float(position)
                    except ValueError:
                        continue
                    if math.isfinite(parsed):
                        metadata["position"] = parsed
                        height_count += 1
        if height_count:
            actions.append(
                _action(
                    source_sha256,
                    "META",
                    "INFO",
                    station_id,
                    None,
                    {"fields": height_count},
                    {"kind": "normalize_sensor_height", "type": "number"},
                    f"Converted {height_count} numeric sensor-height strings to numbers",
                    automatic=True,
                )
            )
    return normalized, actions, findings


def _decision_applies(action: dict) -> bool:
    return action["decision"]["status"] in ("auto_accepted", "accepted")


def _prepare_json(data: dict, actions: list[dict]) -> dict:
    prepared = copy.deepcopy(data)
    by_station: dict[str, list[dict]] = {}
    for action in actions:
        by_station.setdefault(action["target"].get("station"), []).append(action)
    retained = []
    for station in prepared["STATION"]:
        station_id = str(station.get("STID", ""))
        station_actions = by_station.get(station_id, [])
        excluded = any(
            item["effect"]["kind"] == "exclude_station" and _decision_applies(item)
            for item in station_actions
        )
        if station.pop("_WXQC_QUARANTINED", False):
            # Invalid structural data cannot safely enter an HDF5 candidate.
            excluded = True
        if excluded:
            continue
        duplicate_indices = set()
        for item in station_actions:
            if item["effect"]["kind"] == "remove_identical_duplicates" and _decision_applies(item):
                duplicate_indices.update(item["selector"]["raw_indices"])
        if duplicate_indices:
            observations = station["OBSERVATIONS"]
            for variable, values in observations.items():
                if isinstance(values, list):
                    observations[variable] = [
                        value for index, value in enumerate(values) if index not in duplicate_indices
                    ]
        retained.append(station)
    prepared["STATION"] = retained
    return prepared


def _write_base_h5(
    data: dict,
    source_path: Path,
    source_sha256: str,
    policy: dict,
    actions: list[dict],
    destination: Path,
    run_id: str,
    stage: str,
) -> None:
    prepared = _prepare_json(data, actions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="firebench-wx-qc-") as directory:
        prepared_path = Path(directory) / source_path.name
        prepared_path.write_text(json.dumps(prepared, allow_nan=True), encoding="utf-8")
        output = new_std_file(str(destination), policy["output"]["authors"], overwrite=True)
        try:
            output.attrs["description"] = policy["output"]["description"]
            standardize_synoptic_raws_from_json(
                prepared_path,
                output,
                overwrite=True,
                compression_lvl=policy["output"]["compression_level"],
                source_sha256=source_sha256,
                source_name=source_path.name,
                time_origin_utc=True,
            )
            output.attrs["wx_qc_run_id"] = run_id
            output.attrs["wx_qc_source_sha256"] = source_sha256
            output.attrs["wx_qc_policy_sha256"] = _digest(policy)
            output.attrs["wx_qc_stage"] = stage
        finally:
            output.close()


def _h5_times(group: h5py.Group) -> np.ndarray:
    origin = datetime.fromisoformat(str(group["time"].attrs["time_origin"]).replace("Z", "+00:00"))
    return np.asarray(
        [
            np.datetime64((origin + timedelta(minutes=float(value))).replace(tzinfo=None))
            for value in group["time"][:]
        ],
        dtype="datetime64[us]",
    )


def _iso_at(times: np.ndarray, index: int) -> str:
    return np.datetime_as_string(times[index], unit="s") + "Z"


def _apply_h5_actions(path: Path, actions: list[dict], stage: str) -> None:
    with h5py.File(path, "r+") as output:
        time_series = output.get("time_series")
        if time_series is None:
            return
        effect_order = {"exclude_station": 0, "exclude_variable": 1}
        ordered_actions = sorted(actions, key=lambda item: effect_order.get(item["effect"]["kind"], 2))
        for action in ordered_actions:
            if not _decision_applies(action):
                continue
            station_id = action["target"].get("station")
            group_name = f"station_{station_id}"
            kind = action["effect"]["kind"]
            if kind == "exclude_station":
                if group_name in time_series:
                    del time_series[group_name]
                    action["application"][stage] = "applied"
                else:
                    action["application"][stage] = "shadowed"
                continue
            if kind == "exclude_variable":
                if group_name not in time_series:
                    action["application"][stage] = "shadowed"
                    continue
                group = time_series[group_name]
                variable_names = action["effect"].get("variables") or [action["target"].get("variable")]
                removed = 0
                for variable in variable_names:
                    if variable in group and variable != "time":
                        del group[variable]
                        removed += 1
                action["application"][stage] = "applied" if removed else "no_match"
                continue
            if kind not in ("set_nan", "set_nan_ranges"):
                continue
            if group_name not in time_series:
                action["application"][stage] = "shadowed"
                continue
            group = time_series[group_name]
            times = _h5_times(group)
            variable_names = action["effect"].get("variables") or [action["target"].get("variable")]
            if "*" in variable_names:
                variable_names = [name for name in group if name != "time"]
            mask = np.zeros(len(times), dtype=bool)
            predicate = action["selector"].get("predicate")
            if predicate:
                predicate_variable = predicate.get("variable")
                if predicate_variable in group and "equals" in predicate:
                    mask |= group[predicate_variable][:] == predicate["equals"]
            timestamps = action["selector"].get("timestamps", [])
            if timestamps:
                selected = np.asarray([np.datetime64(item.removesuffix("Z")) for item in timestamps])
                mask |= np.isin(times, selected)
            for time_range in action["selector"].get("ranges", []):
                start = np.datetime64(time_range["start"].removesuffix("Z"))
                end = np.datetime64(time_range["end"].removesuffix("Z"))
                mask |= (times >= start) & (times <= end)
            changed = 0
            for variable in variable_names:
                if variable not in group or not np.issubdtype(group[variable].dtype, np.floating):
                    continue
                values = group[variable][:]
                changed += int((mask & np.isfinite(values)).sum())
                values[mask] = np.nan
                group[variable][...] = values
            action["application"][stage] = "applied" if changed else "no_match"


def _physical_actions(path: Path, source_sha256: str, bounds: dict) -> list[dict]:
    actions = []
    with h5py.File(path, "r") as source:
        for group_name, group in source.get("time_series", {}).items():
            station_id = group_name.removeprefix("station_")
            times = _h5_times(group)
            for variable, (lower, upper, unit) in bounds.items():
                if variable not in group:
                    continue
                values = group[variable][:]
                mask = np.isfinite(values) & ((values < lower) | (values > upper))
                if not mask.any():
                    continue
                timestamps = [_iso_at(times, index) for index in np.flatnonzero(mask)]
                actions.append(
                    _action(
                        source_sha256,
                        "BOUND",
                        "ERROR",
                        station_id,
                        variable,
                        {"timestamps": timestamps, "bounds": [lower, upper, unit]},
                        {"kind": "set_nan", "variables": [variable], "count": len(timestamps)},
                        f"Replaced {len(timestamps)} values outside [{lower}, {upper}] {unit} with NaN",
                        automatic=True,
                    )
                )
    return actions


def _window_and_empty_actions(
    path: Path, source_sha256: str, policy: dict
) -> tuple[list[dict], list[dict]]:
    actions = []
    findings = []
    with h5py.File(path, "r") as source:
        for group_name, group in source.get("time_series", {}).items():
            station_id = group_name.removeprefix("station_")
            variable_names = [name for name in group if name in SUPPORTED_VARIABLES]
            times = _h5_times(group)
            if not variable_names or not any(np.isfinite(group[name][:]).any() for name in variable_names):
                actions.append(
                    _action(
                        source_sha256,
                        "EMPTY",
                        "ERROR",
                        station_id,
                        None,
                        {"scope": "all_supported_variables"},
                        {"kind": "exclude_station"},
                        "Excluded station with no finite supported observations",
                        automatic=True,
                    )
                )
                continue
            for window in policy["required_windows"]:
                start = np.datetime64(window["start"].replace("+00:00", "").replace("Z", ""))
                end = np.datetime64(window["end"].replace("+00:00", "").replace("Z", ""))
                in_window = (times >= start) & (times <= end)
                finite = any(np.isfinite(group[name][:][in_window]).any() for name in variable_names)
                if not finite:
                    actions.append(
                        _action(
                            source_sha256,
                            "WINDOW",
                            "ERROR",
                            station_id,
                            None,
                            {"window": window},
                            {"kind": "exclude_station"},
                            f"Excluded station with no finite supported observations in {window['name']}",
                            automatic=True,
                        )
                    )
                elif times[0] > start or times[-1] < end:
                    message = f"Station does not fully cover required window {window['name']}"
                    finding = _finding(source_sha256, "COVER", "WARN", station_id, message)
                    findings.append(finding)
                    actions.append(
                        _action(
                            source_sha256,
                            "ACK",
                            "WARN",
                            station_id,
                            None,
                            {"finding": finding["id"], "window": window},
                            {"kind": "no_change"},
                            f"Acknowledge incomplete coverage without changing data: {window['name']}",
                            automatic=False,
                            linked_findings=[finding["id"]],
                        )
                    )
    return actions, findings


def _add_automatic_findings(actions: list[dict], findings: list[dict], source_sha256: str) -> None:
    """Record warning/error observations for automatic actions and link both records."""
    for action in actions:
        if not action["automatic"] or action["severity"] not in ("WARN", "ERROR"):
            continue
        if action["linked_findings"]:
            continue
        station_id = action["target"].get("station")
        if station_id is None:
            continue
        message = f"Condition handled automatically: {action['message']}"
        finding = _finding(source_sha256, f"AUTO_{action['code']}", action["severity"], station_id, message)
        findings.append(finding)
        action["linked_findings"].append(finding["id"])


def _qualifying_runs(
    mask: np.ndarray, times: np.ndarray, min_minutes: float, break_factor: float
) -> list[dict]:
    if not mask.any() or len(mask) < 2:
        return []
    deltas = np.diff(times).astype("timedelta64[s]").astype(float) / 60.0
    positive = deltas[deltas > 0]
    median = float(np.median(positive)) if len(positive) else 0.0
    ranges = []
    start = None
    for index, selected in enumerate(mask):
        temporal_break = index > 0 and median and deltas[index - 1] >= break_factor * median
        if selected and (start is None or temporal_break):
            if start is not None:
                duration = (times[index - 1] - times[start]).astype("timedelta64[s]").astype(float) / 60.0
                if duration >= min_minutes:
                    ranges.append({"start": _iso_at(times, start), "end": _iso_at(times, index - 1)})
            start = index
        elif not selected and start is not None:
            duration = (times[index - 1] - times[start]).astype("timedelta64[s]").astype(float) / 60.0
            if duration >= min_minutes:
                ranges.append({"start": _iso_at(times, start), "end": _iso_at(times, index - 1)})
            start = None
    if start is not None:
        duration = (times[-1] - times[start]).astype("timedelta64[s]").astype(float) / 60.0
        if duration >= min_minutes:
            ranges.append({"start": _iso_at(times, start), "end": _iso_at(times, len(times) - 1)})
    return ranges


def _source_flag_actions(data: dict, source_sha256: str) -> tuple[list[dict], list[dict]]:
    actions, findings = [], []
    for station in data["STATION"]:
        value = station.get("QC_FLAGGED")
        if value not in (True, 1, "true", "True", "TRUE"):
            continue
        station_id = str(station["STID"])
        message = "Synoptic source metadata marks this station QC_FLAGGED"
        finding = _finding(source_sha256, "SRCFLAG", "WARN", station_id, message)
        findings.append(finding)
        actions.append(
            _action(
                source_sha256,
                "SRCFLAG",
                "WARN",
                station_id,
                None,
                {"source_field": "QC_FLAGGED"},
                {"kind": "exclude_station"},
                message,
                automatic=False,
                linked_findings=[finding["id"]],
            )
        )
    return actions, findings


def _zero_wind_actions(path: Path, source_sha256: str, policy: dict) -> tuple[list[dict], list[dict]]:
    actions, findings = [], []
    thresholds = policy["thresholds"]
    with h5py.File(path, "r") as source:
        for group_name, group in source.get("time_series", {}).items():
            if "wind_speed" not in group:
                continue
            station_id = group_name.removeprefix("station_")
            values = group["wind_speed"][:]
            known = np.isfinite(values)
            zero = known & (values == 0)
            fraction = float(zero.sum() / known.sum()) if known.any() else 0.0
            times = _h5_times(group)
            ranges = _qualifying_runs(
                zero,
                times,
                thresholds["zero_wind_run_minutes"],
                thresholds["temporal_break_factor"],
            )
            if fraction < thresholds["zero_wind_fraction"] and not ranges:
                continue
            selector = {"ranges": ranges, "zero_fraction": fraction}
            if fraction >= thresholds["zero_wind_fraction"]:
                selector = {
                    "predicate": {"variable": "wind_speed", "equals": 0.0},
                    "zero_fraction": fraction,
                }
            message = f"Suspicious zero wind: {fraction:.1%} of known speed samples are zero"
            finding = _finding(source_sha256, "ZEROWIND", "WARN", station_id, message)
            findings.append(finding)
            actions.append(
                _action(
                    source_sha256,
                    "ZEROWIND",
                    "WARN",
                    station_id,
                    "wind",
                    selector,
                    {
                        "kind": "set_nan_ranges",
                        "variables": ["wind_speed", "wind_gust", "wind_direction"],
                    },
                    message,
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
    return actions, findings


def _frozen_ranges(values: np.ndarray, times: np.ndarray, minimum_run: int) -> list[dict]:
    """Return contiguous equal-value runs, split across large temporal gaps."""
    if len(values) < minimum_run:
        return []
    deltas = np.diff(times).astype("timedelta64[s]").astype(float) / 60.0
    positive = deltas[deltas > 0]
    break_limit = 3.0 * float(np.median(positive)) if len(positive) else math.inf
    ranges = []
    start = 0
    for index in range(1, len(values) + 1):
        end_run = index == len(values)
        if not end_run:
            end_run = (
                not np.isfinite(values[index])
                or not np.isfinite(values[index - 1])
                or values[index] != values[index - 1]
                or deltas[index - 1] >= break_limit
            )
        if end_run:
            if index - start >= minimum_run and np.isfinite(values[start]):
                ranges.append(
                    {
                        "start": _iso_at(times, start),
                        "end": _iso_at(times, index - 1),
                        "value": float(values[start]),
                        "records": index - start,
                    }
                )
            start = index
    return ranges


def _h5_qc_findings(path: Path, source_sha256: str, policy: dict) -> tuple[list[dict], list[dict]]:
    stations = load_h5(path)
    findings, actions = [], []
    cfg = default_config()
    gui_policy = policy.get("gui", {})
    cfg["frozen_min_run"] = int(gui_policy.get("frozen_min_run", cfg["frozen_min_run"]))
    cfg["max_var_outage_min"] = float(gui_policy.get("max_var_outage_min", cfg["max_var_outage_min"]))
    cfg["full_outage_min"] = float(gui_policy.get("full_outage_min", cfg["full_outage_min"]))
    cfg["dup_max"] = int(gui_policy.get("duplicate_timestamp_limit", cfg["dup_max"]))
    valid_times = [st["times"] for st in stations.values() if len(st["times"])]
    global_start = min(values[0] for values in valid_times) if valid_times else None
    global_end = max(values[-1] for values in valid_times) if valid_times else None
    for station_id, station in stations.items():
        stats = compute_stats(station)
        if global_start is not None and len(station["times"]):
            leading = float((station["times"][0] - global_start) / np.timedelta64(1, "m"))
            trailing = float((global_end - station["times"][-1]) / np.timedelta64(1, "m"))
            duration = float((global_end - global_start) / np.timedelta64(1, "m"))
            compute_outage_stats(station, stats, leading, trailing, duration)
        issues = run_assertions(station, stats, cfg) + run_outage_assertions(stats, cfg)
        for severity, code, message in issues:
            finding = _finding(source_sha256, code.replace(":", "_"), severity, station_id, message)
            findings.append(finding)
            if code.startswith("frozen:"):
                variable = code.split(":", 1)[1]
                minimum_run = 15 if variable == "fuel_moisture_content_10h" else cfg["frozen_min_run"]
                ranges = _frozen_ranges(station["variables"][variable], station["times"], minimum_run)
                if variable == "solar_radiation":
                    ranges = [item for item in ranges if item["value"] != 0.0]
                actions.append(
                    _action(
                        source_sha256,
                        "FROZEN",
                        severity,
                        station_id,
                        variable,
                        {"ranges": ranges},
                        {"kind": "set_nan_ranges", "variables": [variable]},
                        f"Replace frozen {variable} ranges with NaN: {message}",
                        automatic=False,
                        linked_findings=[finding["id"]],
                    )
                )
                continue
            actions.append(
                _action(
                    source_sha256,
                    "ACK",
                    severity,
                    station_id,
                    code.split(":", 1)[1] if ":" in code else None,
                    {"finding": finding["id"]},
                    {"kind": "no_change"},
                    f"Acknowledge without changing data: {message}",
                    automatic=False,
                    linked_findings=[finding["id"]],
                )
            )
    return actions, findings


def _decision_digest(actions: list[dict]) -> str:
    return _digest(
        [
            {
                "id": item["id"],
                "status": item["decision"]["status"],
                "reviewer": item["decision"]["reviewer"],
            }
            for item in actions
        ]
    )


def _validate_destinations(paths: list[Path], overwrite: bool) -> None:
    repeated = len({path.resolve() for path in paths}) != len(paths)
    if repeated:
        raise QCError("candidate, manifest, and log paths must be different")
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"output already exists: {existing[0]} (use --overwrite to replace it)")


def process_synoptic_json(
    source: str | Path,
    policy_path: str | Path | None,
    candidate: str | Path,
    manifest_path: str | Path,
    log_path: str | Path,
    *,
    overwrite: bool = False,
) -> dict:
    """Create a candidate HDF5, decision manifest, and human-readable audit log."""
    source = Path(source).resolve()
    candidate, manifest_path, log_path = Path(candidate), Path(manifest_path), Path(log_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    _validate_destinations([candidate, manifest_path, log_path], overwrite)
    policy = load_policy(policy_path)
    source_sha256 = calculate_sha256(source)
    run_id = f"WXQC-RUN-{_digest([source_sha256, policy])[:12].upper()}"
    data, actions, findings = _normalize_source(source, source_sha256)
    flag_actions, flag_findings = _source_flag_actions(data, source_sha256)
    actions.extend(flag_actions)
    findings.extend(flag_findings)

    temporary_candidate = temporary_sibling(candidate)
    try:
        _write_base_h5(
            data, source, source_sha256, policy, actions, temporary_candidate, run_id, "candidate"
        )
        physical = _physical_actions(temporary_candidate, source_sha256, policy["bounds"])
        actions.extend(physical)
        _apply_h5_actions(temporary_candidate, physical, "candidate")
        zero_actions, zero_findings = _zero_wind_actions(temporary_candidate, source_sha256, policy)
        actions.extend(zero_actions)
        findings.extend(zero_findings)
        empty_actions, window_findings = _window_and_empty_actions(
            temporary_candidate, source_sha256, policy
        )
        actions.extend(empty_actions)
        findings.extend(window_findings)
        _apply_h5_actions(temporary_candidate, empty_actions, "candidate")
        qc_actions, qc_findings = _h5_qc_findings(temporary_candidate, source_sha256, policy)
        actions.extend(qc_actions)
        findings.extend(qc_findings)
        _add_automatic_findings(actions, findings, source_sha256)
        with h5py.File(temporary_candidate, "r+") as output:
            validate_h5_std(output)
            output.attrs["wx_qc_decision_sha256"] = _decision_digest(actions)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        temporary_candidate.replace(candidate)
    finally:
        temporary_candidate.unlink(missing_ok=True)

    with h5py.File(candidate, "r") as candidate_file:
        time_series = candidate_file.get("time_series")
        retained_stations = (
            {name.removeprefix("station_") for name in time_series} if time_series is not None else set()
        )
    for action in actions:
        if (
            not action["automatic"]
            and action["effect"]["kind"] == "exclude_station"
            and action["target"].get("station") not in retained_stations
        ):
            action["application"]["candidate"] = "quarantined"
        if action["automatic"] and action["application"]["candidate"] == "not_applicable":
            action["application"]["candidate"] = "applied"
        elif not action["automatic"] and action["application"]["candidate"] == "not_applicable":
            action["application"]["candidate"] = "not_applied_pending"
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "run_id": run_id,
        "created_at": _now(),
        "updated_at": _now(),
        "source": {"path": str(source), "sha256": source_sha256},
        "policy": {
            "path": (
                str(Path(policy_path).resolve())
                if policy_path is not None and not isinstance(policy_path, dict)
                else None
            ),
            "sha256": _digest(policy),
            "normalized": policy,
        },
        "artifacts": {
            "candidate_h5": str(candidate.resolve()),
            "final_h5": None,
            "log": str(log_path.resolve()),
        },
        "findings": findings,
        "actions": actions,
        "summary": {},
        "history": [{"at": _now(), "event": "candidate_created"}],
    }
    _refresh_summary(manifest)
    write_manifest(manifest_path, manifest)
    write_log(manifest, log_path)
    return manifest


def _refresh_summary(manifest: dict) -> None:
    statuses: dict[str, int] = {}
    for action in manifest["actions"]:
        status = action["decision"]["status"]
        statuses[status] = statuses.get(status, 0) + 1
    severities: dict[str, int] = {}
    for finding in manifest["findings"]:
        severity = finding["severity"]
        severities[severity] = severities.get(severity, 0) + 1
    manifest["summary"] = {
        "findings": len(manifest["findings"]),
        "actions": len(manifest["actions"]),
        "action_statuses": statuses,
        "finding_severities": severities,
        "pending": statuses.get("pending", 0),
    }


def validate_manifest(manifest: dict) -> dict:
    """Validate the top-level manifest schema and operation ID uniqueness."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_VERSION:
        raise QCError(f"unsupported QC manifest; expected schema version {MANIFEST_VERSION}")
    required = {"run_id", "source", "policy", "artifacts", "findings", "actions", "history"}
    missing = sorted(required - set(manifest))
    if missing:
        raise QCError(f"QC manifest missing fields: {', '.join(missing)}")
    source = manifest["source"]
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("sha256"), str)
        or len(source["sha256"]) != 64
    ):
        raise QCError("QC manifest source requires a path and SHA-256")
    if not isinstance(manifest["actions"], list) or not isinstance(manifest["findings"], list):
        raise QCError("QC manifest findings and actions must be arrays")
    ids = [action.get("id") for action in manifest["actions"]]
    if len(ids) != len(set(ids)):
        raise QCError("QC manifest contains duplicate action IDs")
    statuses = {"auto_accepted", "pending", "accepted", "rejected", "acknowledged", "superseded"}
    for index, action in enumerate(manifest["actions"]):
        try:
            expected_id = _operation_id(
                source["sha256"],
                action["code"],
                action["target"],
                action["selector"],
                action["effect"],
            )
            status = action["decision"]["status"]
            effect_kind = action["effect"]["kind"]
        except (KeyError, TypeError) as exc:
            raise QCError(f"QC manifest action {index} is malformed") from exc
        if action["id"] != expected_id:
            raise QCError(f"QC manifest action ID does not match its content: {action['id']}")
        if status not in statuses:
            raise QCError(f"QC manifest action {action['id']} has invalid status {status!r}")
        if effect_kind not in {
            "exclude_station",
            "exclude_variable",
            "normalize_timestamps",
            "remove_identical_duplicates",
            "normalize_sensor_height",
            "set_nan",
            "set_nan_ranges",
            "no_change",
        }:
            raise QCError(f"QC manifest action {action['id']} has invalid effect {effect_kind!r}")
        if effect_kind == "exclude_variable":
            variables = action["effect"].get("variables") or [action["target"].get("variable")]
            if (
                not variables
                or not all(isinstance(variable, str) and variable for variable in variables)
                or "time" in variables
                or "*" in variables
            ):
                raise QCError(
                    f"QC manifest action {action['id']} must name one or more observation variables"
                )
    for index, finding in enumerate(manifest["findings"]):
        try:
            expected_id = _finding_id(
                source["sha256"],
                finding["code"],
                finding["target"],
                finding["message"],
            )
        except (KeyError, TypeError) as exc:
            raise QCError(f"QC manifest finding {index} is malformed") from exc
        if finding.get("id") != expected_id:
            raise QCError(f"QC manifest finding ID does not match its content: {finding.get('id')}")
    return manifest


def read_manifest(path: str | Path) -> dict:
    """Read and validate a weather-QC JSON manifest."""
    with Path(path).open("r", encoding="utf-8") as stream:
        return validate_manifest(json.load(stream))


def write_manifest(path: str | Path, manifest: dict) -> None:
    """Atomically write a validated weather-QC JSON manifest."""
    validate_manifest(manifest)
    manifest["updated_at"] = _now()
    _refresh_summary(manifest)
    atomic_write_text(path, json.dumps(_json_safe(manifest), indent=2, sort_keys=True) + "\n")


def write_log(manifest: dict, path: str | Path | None = None) -> None:
    """Regenerate the human-readable audit log from a manifest."""
    path = Path(path or manifest["artifacts"]["log"])
    lines = [
        f"FireBench weather QC run {manifest['run_id']}",
        f"source: {manifest['source']['path']}",
        f"source sha256: {manifest['source']['sha256']}",
        f"policy sha256: {manifest['policy']['sha256']}",
        f"updated: {manifest.get('updated_at', '--')}",
        "",
        "FINDINGS",
    ]
    for finding in manifest["findings"]:
        lines.append(
            " | ".join(
                [
                    finding["severity"],
                    finding["id"],
                    f"station={finding['target'].get('station') or '--'}",
                    finding["message"],
                ]
            )
        )
    lines.extend(["", "ACTIONS"])
    for action in manifest["actions"]:
        decision = action["decision"]
        effect = action["effect"]["kind"]
        lines.append(
            " | ".join(
                [
                    action["severity"],
                    action["id"],
                    f"station={action['target'].get('station') or '--'}",
                    f"variable={action['target'].get('variable') or '--'}",
                    f"effect={effect}",
                    f"decision={decision['status']}",
                    f"reviewer={decision.get('reviewer') or '--'}",
                    f"candidate={action['application'].get('candidate', '--')}",
                    f"final={action['application'].get('final', '--')}",
                    action["message"],
                ]
            )
        )
    if manifest.get("final_findings") is not None:
        lines.extend(["", "POST-FINALIZATION FINDINGS"])
        for finding in manifest["final_findings"]:
            lines.append(
                " | ".join(
                    [
                        finding["severity"],
                        finding["id"],
                        f"station={finding['target'].get('station') or '--'}",
                        finding["message"],
                    ]
                )
            )
    summary = manifest["summary"]
    lines.extend(
        [
            "",
            "SUMMARY",
            f"findings={summary['findings']} actions={summary['actions']} pending={summary['pending']}",
        ]
    )
    atomic_write_text(path, "\n".join(lines) + "\n")


def decide_action(
    manifest_path: str | Path,
    action_id: str,
    decision: str,
    reviewer: str,
    comment: str | None = None,
) -> dict:
    """Record a reviewed action decision and regenerate the human log."""
    if decision not in ("accepted", "rejected", "acknowledged", "pending", "reset"):
        raise QCError("decision must be accepted, rejected, acknowledged, pending, or reset")
    if decision != "pending" and not reviewer.strip():
        raise QCError("reviewer identity is required")
    manifest = read_manifest(manifest_path)
    action = next((item for item in manifest["actions"] if item["id"] == action_id), None)
    if action is None:
        raise QCError(f"unknown action ID: {action_id}")
    if decision == "acknowledged" and action["effect"]["kind"] != "no_change":
        raise QCError("only no-change actions can be acknowledged")
    if decision == "reset":
        decision = "auto_accepted" if action["automatic"] else "pending"
    previous = copy.deepcopy(action["decision"])
    action["history"].append({"at": _now(), "reviewer": reviewer, "previous": previous})
    action["decision"] = {
        "status": decision,
        "reviewer": reviewer.strip() or None,
        "decided_at": _now() if decision != "pending" else None,
        "comment": comment,
    }
    manifest["history"].append(
        {"at": _now(), "event": "decision_changed", "action_id": action_id, "reviewer": reviewer}
    )
    write_manifest(manifest_path, manifest)
    write_log(manifest)
    return manifest


def add_manual_action(
    manifest_path: str | Path,
    *,
    station: str,
    variable: str | None,
    selector: dict,
    effect: dict,
    message: str,
    reviewer: str,
) -> dict:
    """Add an accepted GUI-authored operation to an existing manifest."""
    if not reviewer.strip():
        raise QCError("reviewer identity is required")
    manifest = read_manifest(manifest_path)
    action = _action(
        manifest["source"]["sha256"],
        "MANUAL",
        "WARN",
        station,
        variable,
        selector,
        effect,
        message,
        automatic=False,
    )
    if any(item["id"] == action["id"] for item in manifest["actions"]):
        return manifest
    decided_at = _now()
    action["decision"] = {
        "status": "accepted",
        "reviewer": reviewer.strip(),
        "decided_at": decided_at,
        "comment": "Created in wx-qc GUI",
    }
    action["application"]["candidate"] = "not_applied_after_candidate"
    action["history"].append(
        {"at": decided_at, "reviewer": reviewer.strip(), "event": "manual_action_created"}
    )
    manifest["actions"].append(action)
    manifest["history"].append(
        {
            "at": decided_at,
            "event": "manual_action_created",
            "action_id": action["id"],
            "reviewer": reviewer.strip(),
        }
    )
    write_manifest(manifest_path, manifest)
    write_log(manifest)
    return manifest


def edit_action(
    manifest_path: str | Path,
    action_id: str,
    selector: dict,
    effect: dict,
    reviewer: str,
    comment: str | None = None,
) -> dict:
    """Supersede an action with a new content-addressed, pending operation."""
    if not reviewer.strip():
        raise QCError("reviewer identity is required")
    if not isinstance(selector, dict) or not isinstance(effect, dict) or "kind" not in effect:
        raise QCError("edited selector and effect must be JSON objects and effect requires kind")
    manifest = read_manifest(manifest_path)
    original = next((item for item in manifest["actions"] if item["id"] == action_id), None)
    if original is None:
        raise QCError(f"unknown action ID: {action_id}")
    replacement = copy.deepcopy(original)
    replacement["selector"] = selector
    replacement["effect"] = effect
    replacement["id"] = _operation_id(
        manifest["source"]["sha256"],
        replacement["code"],
        replacement["target"],
        selector,
        effect,
    )
    if replacement["id"] == original["id"]:
        raise QCError("edit did not change the operation")
    if any(item["id"] == replacement["id"] for item in manifest["actions"]):
        raise QCError(f"edited operation already exists: {replacement['id']}")
    changed_at = _now()
    original["history"].append(
        {"at": changed_at, "reviewer": reviewer.strip(), "event": "superseded", "comment": comment}
    )
    original["decision"] = {
        "status": "superseded",
        "reviewer": reviewer.strip(),
        "decided_at": changed_at,
        "comment": comment,
    }
    original["superseded_by"] = replacement["id"]
    replacement["automatic"] = False
    replacement["decision"] = {
        "status": "pending",
        "reviewer": None,
        "decided_at": None,
        "comment": None,
    }
    replacement["application"] = {"candidate": "not_applied_pending", "final": "not_built"}
    replacement["history"] = [
        {"at": changed_at, "reviewer": reviewer.strip(), "event": "created_by_edit", "comment": comment}
    ]
    replacement["supersedes"] = original["id"]
    replacement.pop("superseded_by", None)
    manifest["actions"].append(replacement)
    manifest["history"].append(
        {
            "at": changed_at,
            "event": "action_edited",
            "action_id": original["id"],
            "replacement_id": replacement["id"],
            "reviewer": reviewer.strip(),
        }
    )
    write_manifest(manifest_path, manifest)
    write_log(manifest)
    return manifest


def finalize_manifest(
    manifest_path: str | Path,
    output_path: str | Path,
    reviewer: str,
    *,
    overwrite: bool = False,
) -> dict:
    """Rebuild a final HDF5 from immutable source after all actions are decided."""
    if not reviewer.strip():
        raise QCError("reviewer identity is required")
    manifest = read_manifest(manifest_path)
    pending = [item["id"] for item in manifest["actions"] if item["decision"]["status"] == "pending"]
    if pending:
        raise QCError(f"cannot finalize with {len(pending)} pending action(s)")
    rejected_structural = [
        item["id"]
        for item in manifest["actions"]
        if item["code"] in ("TIME", "META") and item["decision"]["status"] == "rejected"
    ]
    if rejected_structural:
        raise QCError(
            "cannot finalize with rejected structural normalization; edit it to a replacement "
            "operation or accept it"
        )
    source = Path(manifest["source"]["path"])
    if calculate_sha256(source) != manifest["source"]["sha256"]:
        raise QCError("source JSON SHA-256 no longer matches the manifest")
    output_path = Path(output_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output_path} (use --overwrite to replace it)")
    data, _source_actions, _findings = _normalize_source(source, manifest["source"]["sha256"])
    temporary_output = temporary_sibling(output_path)
    try:
        _write_base_h5(
            data,
            source,
            manifest["source"]["sha256"],
            manifest["policy"]["normalized"],
            manifest["actions"],
            temporary_output,
            manifest["run_id"],
            "final",
        )
        _apply_h5_actions(temporary_output, manifest["actions"], "final")
        with h5py.File(temporary_output, "r+") as output:
            validate_h5_std(output)
            output.attrs["wx_qc_decision_sha256"] = _decision_digest(manifest["actions"])
            output.attrs["wx_qc_finalized_by"] = reviewer.strip()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output.replace(output_path)
    finally:
        temporary_output.unlink(missing_ok=True)
    manifest["artifacts"]["final_h5"] = str(output_path.resolve())
    for action in manifest["actions"]:
        if action["application"]["final"] != "not_built":
            continue
        status = action["decision"]["status"]
        if status in ("rejected", "superseded"):
            action["application"]["final"] = "not_applied"
        elif action["effect"]["kind"] == "no_change":
            action["application"]["final"] = "acknowledged"
        elif _decision_applies(action):
            action["application"]["final"] = "applied"
    _post_actions, final_findings = _h5_qc_findings(
        output_path, manifest["source"]["sha256"], manifest["policy"]["normalized"]
    )
    manifest["final_findings"] = final_findings
    manifest["history"].append({"at": _now(), "event": "finalized", "reviewer": reviewer.strip()})
    write_manifest(manifest_path, manifest)
    write_log(manifest)
    return manifest
