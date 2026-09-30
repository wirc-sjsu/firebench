"""Neighbour-consistency detection of biased air-temperature sensors."""

from __future__ import annotations

import math

import numpy as np

from .frozen import _nearest_station_cache

NEIGHBOR_VARIABLE = "air_temperature"
ELEVATION_TO_METERS = {"ft": 0.3048, "m": 1.0}
NEIGHBOR_INTEGER_KEYS = ("neighbor_count", "minimum_neighbors", "minimum_paired_hours")
NEIGHBOR_POSITIVE_KEYS = ("radius_km", "maximum_bias")
NEIGHBOR_KEYS = {*NEIGHBOR_INTEGER_KEYS, *NEIGHBOR_POSITIVE_KEYS, "lapse_rate_c_per_km"}


def neighbor_config_from_policy(policy: dict) -> dict:
    """Return neighbour-consistency settings from a normalized QC policy."""
    return dict(policy["neighbor_consistency"])


def _elevation_m(station: dict) -> float:
    """Return the station elevation in metres, or NaN when its unit is unknown."""
    units = station.get("alt_units")
    factor = ELEVATION_TO_METERS.get(str(units).strip().lower()) if units is not None else None
    try:
        elevation = float(station.get("alt"))
    except (TypeError, ValueError):
        return math.nan
    return elevation * factor if factor is not None and math.isfinite(elevation) else math.nan


def _hourly_means(station: dict) -> dict[int, float]:
    """Average finite values into UTC hour bins keyed by hours since the epoch."""
    times = np.asarray(station["times"])
    values = np.asarray(station["variables"][NEIGHBOR_VARIABLE], dtype=float)
    if not np.issubdtype(times.dtype, np.datetime64) or len(times) != len(values):
        return {}
    finite = np.isfinite(values)
    if not finite.any():
        return {}
    hours = times[finite].astype("datetime64[h]").astype(np.int64)
    unique, inverse = np.unique(hours, return_inverse=True)
    means = np.bincount(inverse, weights=values[finite]) / np.bincount(inverse)
    return dict(zip(unique.tolist(), means.tolist()))


def analyze_neighbor_bias(stations: dict[str, dict], config: dict) -> dict[str, dict]:
    """Return stations whose median paired bias against lapse-adjusted neighbours is too large."""
    lapse_per_m = config["lapse_rate_c_per_km"] / 1000.0
    candidates = {}
    for station_id, station in stations.items():
        if NEIGHBOR_VARIABLE not in station["variables"]:
            continue
        elevation = _elevation_m(station)
        hourly = _hourly_means(station) if math.isfinite(elevation) else {}
        if hourly:
            candidates[station_id] = (elevation, hourly)
    nearest = _nearest_station_cache(
        {station_id: stations[station_id] for station_id in candidates}, config["radius_km"]
    )
    findings = {}
    for station_id, (elevation, hourly) in candidates.items():
        neighbors = nearest[station_id][: config["neighbor_count"]]
        if len(neighbors) < config["minimum_neighbors"]:
            continue
        differences = []
        for hour, value in hourly.items():
            reference = [
                candidates[item][1][hour] - lapse_per_m * (elevation - candidates[item][0])
                for item in neighbors
                if hour in candidates[item][1]
            ]
            if len(reference) >= config["minimum_neighbors"]:
                differences.append(value - float(np.median(reference)))
        if len(differences) < config["minimum_paired_hours"]:
            continue
        bias = float(np.median(differences))
        if abs(bias) < config["maximum_bias"]:
            continue
        findings[station_id] = {
            "variable": NEIGHBOR_VARIABLE,
            "bias": bias,
            "spread": float(np.median(np.abs(np.asarray(differences) - bias))),
            "paired_hours": len(differences),
            "elevation_m": elevation,
            "neighbors": neighbors,
        }
    return findings


def validate_neighbor_policy(section: object) -> None:
    """Validate the version-9 neighbour-consistency policy section."""
    if not isinstance(section, dict):
        raise ValueError("neighbor_consistency must be a table")
    if set(section) != NEIGHBOR_KEYS:
        raise ValueError(f"neighbor_consistency must define {', '.join(sorted(NEIGHBOR_KEYS))}")
    for key in NEIGHBOR_INTEGER_KEYS:
        value = section[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"neighbor_consistency.{key} must be a positive integer")
    for key in (*NEIGHBOR_POSITIVE_KEYS, "lapse_rate_c_per_km"):
        value = section[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"neighbor_consistency.{key} must be a finite number")
        if value < 0 or (value == 0 and key in NEIGHBOR_POSITIVE_KEYS):
            qualifier = "non-negative" if key == "lapse_rate_c_per_km" else "greater than zero"
            raise ValueError(f"neighbor_consistency.{key} must be {qualifier}")
    if section["minimum_neighbors"] > section["neighbor_count"]:
        raise ValueError("neighbor_consistency.minimum_neighbors must not exceed neighbor_count")
