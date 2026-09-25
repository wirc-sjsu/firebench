"""Local-context detection of implausible weather-variable excursions."""

from __future__ import annotations

import math

import numpy as np


def jump_config_from_policy(policy: dict) -> dict:
    """Return jump-analysis settings from a normalized QC policy."""
    return {
        **policy["jumps"],
        "temporal_break_factor": policy["thresholds"]["temporal_break_factor"],
    }


def _iso_at(times: np.ndarray, index: int) -> str:
    return np.datetime_as_string(times[index], unit="s") + "Z"


def _local_medians(
    values: np.ndarray,
    relative_minutes: np.ndarray,
    context_hours: float,
    minimum_context_points: int,
) -> np.ndarray:
    """Calculate a centered time-window median for every sample."""
    medians = np.full(len(values), np.nan, dtype=float)
    half_window_minutes = 30.0 * context_hours
    left = 0
    right = 0
    for index, minute in enumerate(relative_minutes):
        while left < len(values) and relative_minutes[left] < minute - half_window_minutes:
            left += 1
        while right < len(values) and relative_minutes[right] <= minute + half_window_minutes:
            right += 1
        finite = values[left:right][np.isfinite(values[left:right])]
        if len(finite) >= minimum_context_points:
            medians[index] = float(np.median(finite))
    return medians


def _boundary_evidence(
    values: np.ndarray,
    times: np.ndarray,
    relative_minutes: np.ndarray,
    left: int,
    right: int,
    threshold: dict,
    break_minutes: float,
) -> dict | None:
    """Describe a qualifying change between two adjacent samples."""
    duration_minutes = float(relative_minutes[right] - relative_minutes[left])
    if (
        not math.isfinite(duration_minutes)
        or not math.isfinite(float(values[left]))
        or not math.isfinite(float(values[right]))
        or not 0 < duration_minutes < break_minutes
    ):
        return None
    change = float(abs(values[right] - values[left]))
    rate_per_hour = change / (duration_minutes / 60.0)
    if (
        not math.isfinite(change)
        or not math.isfinite(rate_per_hour)
        or change < threshold["minimum_change"]
        or rate_per_hour < threshold["minimum_rate_per_hour"]
    ):
        return None
    return {
        "start": _iso_at(times, left),
        "end": _iso_at(times, right),
        "change": change,
        "rate_per_hour": rate_per_hour,
        "duration_minutes": duration_minutes,
    }


def _excursion_ranges(
    values: np.ndarray,
    times: np.ndarray,
    threshold: dict,
    config: dict,
) -> list[dict]:
    if len(values) < config["minimum_context_points"] or len(times) != len(values):
        return []
    if not np.issubdtype(times.dtype, np.datetime64):
        return []
    relative_minutes = np.asarray((times - times[0]) / np.timedelta64(1, "m"), dtype=float)
    deltas = np.diff(relative_minutes)
    positive_deltas = deltas[np.isfinite(deltas) & (deltas > 0)]
    if positive_deltas.size == 0:
        return []
    break_minutes = config["temporal_break_factor"] * float(np.median(positive_deltas))
    medians = _local_medians(
        values,
        relative_minutes,
        config["context_hours"],
        config["minimum_context_points"],
    )
    deviations = np.abs(values - medians)
    suspect = np.isfinite(values) & np.isfinite(medians) & (deviations >= threshold["minimum_deviation"])
    ranges = []
    start = None
    for index in range(len(values) + 1):
        temporal_break = 0 < index < len(values) and deltas[index - 1] >= break_minutes
        selected = index < len(values) and bool(suspect[index])
        if selected and (start is None or temporal_break):
            if start is not None:
                ranges.extend(
                    _confirmed_range(
                        values,
                        times,
                        relative_minutes,
                        deviations,
                        start,
                        index - 1,
                        threshold,
                        break_minutes,
                    )
                )
            start = index
        elif not selected and start is not None:
            ranges.extend(
                _confirmed_range(
                    values,
                    times,
                    relative_minutes,
                    deviations,
                    start,
                    index - 1,
                    threshold,
                    break_minutes,
                )
            )
            start = None
    return ranges


def _confirmed_range(
    values: np.ndarray,
    times: np.ndarray,
    relative_minutes: np.ndarray,
    deviations: np.ndarray,
    start: int,
    end: int,
    threshold: dict,
    break_minutes: float,
) -> list[dict]:
    """Return one range when either edge confirms an anomalous excursion."""
    entry = (
        _boundary_evidence(
            values,
            times,
            relative_minutes,
            start - 1,
            start,
            threshold,
            break_minutes,
        )
        if start > 0
        else None
    )
    exit_boundary = (
        _boundary_evidence(
            values,
            times,
            relative_minutes,
            end,
            end + 1,
            threshold,
            break_minutes,
        )
        if end + 1 < len(values)
        else None
    )
    if entry is None and exit_boundary is None:
        return []
    return [
        {
            "start": _iso_at(times, start),
            "end": _iso_at(times, end),
            "records": end - start + 1,
            "maximum_deviation": float(np.nanmax(deviations[start : end + 1])),
            "entry": entry,
            "exit": exit_boundary,
        }
    ]


def analyze_jump_excursions(stations: dict[str, dict], config: dict) -> dict[str, list[dict]]:
    """Return configured variable excursions grouped by station."""
    findings: dict[str, list[dict]] = {}
    thresholds = config["thresholds"]
    for station_id, station in stations.items():
        station_findings = []
        times = np.asarray(station["times"])
        for variable, threshold in thresholds.items():
            if variable not in station["variables"]:
                continue
            values = np.asarray(station["variables"][variable], dtype=float)
            ranges = _excursion_ranges(values, times, threshold, config)
            if not ranges:
                continue
            station_findings.append(
                {
                    "variable": variable,
                    "ranges": ranges,
                    "records": sum(item["records"] for item in ranges),
                    "maximum_deviation": max(item["maximum_deviation"] for item in ranges),
                }
            )
        if station_findings:
            findings[station_id] = station_findings
    return findings


def validate_jump_policy(jumps: object, supported_variables: set[str]) -> None:
    """Validate the version-7 jump policy section."""
    if not isinstance(jumps, dict):
        raise ValueError("jumps must be a table")
    context_hours = jumps.get("context_hours")
    if (
        isinstance(context_hours, bool)
        or not isinstance(context_hours, (int, float))
        or not math.isfinite(context_hours)
        or context_hours <= 0
    ):
        raise ValueError("jumps.context_hours must be a positive finite number")
    minimum_points = jumps.get("minimum_context_points")
    if isinstance(minimum_points, bool) or not isinstance(minimum_points, int) or minimum_points < 3:
        raise ValueError("jumps.minimum_context_points must be an integer of at least three")
    thresholds = jumps.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError("jumps.thresholds must name at least one supported variable")
    required = {"minimum_change", "minimum_rate_per_hour", "minimum_deviation"}
    for variable, threshold in thresholds.items():
        if variable not in supported_variables or not isinstance(threshold, dict):
            raise ValueError("jumps.thresholds must contain supported variable tables")
        if set(threshold) != required:
            raise ValueError(f"jumps.thresholds.{variable} must define {', '.join(sorted(required))}")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in threshold.values()
        ):
            raise ValueError(f"jumps.thresholds.{variable} values must be positive finite numbers")
