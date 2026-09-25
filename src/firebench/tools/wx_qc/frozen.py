"""Resolution-aware, spatially corroborated frozen-sensor detection."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

DEFAULT_FROZEN_DURATION_HOURS = {
    "air_temperature": 6.0,
    "relative_humidity": 6.0,
    "wind_speed": 3.0,
    "wind_gust": 3.0,
    "wind_direction": 3.0,
    "solar_radiation": 2.0,
    "fuel_moisture_content_10h": 24.0,
}


def frozen_config_from_policy(policy: dict) -> dict:
    """Translate a normalized version-2/3 policy into shared detector settings."""
    frozen = policy["frozen"]
    config = {
        "frozen_min_duration_hours": dict(frozen["minimum_duration_hours"]),
        "frozen_adaptive_percentile": float(frozen["adaptive_percentile"]),
        "frozen_neighbor_count": int(frozen["neighbor_count"]),
        "frozen_neighbor_radius_km": float(frozen["neighbor_radius_km"]),
        "frozen_required_neighbors": int(frozen["required_neighbors"]),
        "frozen_min_neighbor_coverage": float(frozen["minimum_neighbor_coverage"]),
        "frozen_neighbor_change_steps": float(frozen["neighbor_change_steps"]),
        "frozen_calm_wind_threshold": float(frozen["calm_wind_threshold"]),
        "frozen_triage": policy["version"] >= 3,
    }
    if policy["version"] >= 3:
        config.update(
            {
                "frozen_review_duration_multiplier": float(frozen["review_duration_multiplier"]),
                "frozen_review_adaptive_percentile": float(frozen["review_adaptive_percentile"]),
                "frozen_automatic_duration_multiplier": float(frozen["automatic_duration_multiplier"]),
                "frozen_automatic_adaptive_percentile": float(frozen["automatic_adaptive_percentile"]),
                "frozen_automatic_required_neighbors": int(frozen["automatic_required_neighbors"]),
                "frozen_automatic_min_neighbor_coverage": float(
                    frozen["automatic_minimum_neighbor_coverage"]
                ),
                "frozen_minimum_reference_runs": int(frozen["minimum_reference_runs"]),
            }
        )
    return config


def _time_minutes(times):
    values = np.asarray(times)
    if len(values) == 0:
        return np.asarray([], dtype=float)
    if np.issubdtype(values.dtype, np.datetime64):
        return (values - values[0]).astype("timedelta64[us]").astype(float) / 60_000_000.0
    return np.asarray(values, dtype=float)


def _iso_time(value):
    if isinstance(value, np.datetime64):
        return np.datetime_as_string(value, unit="s") + "Z"
    return str(value)


def infer_reporting_resolution(values) -> float | None:
    """Infer the coarsest value grid explaining at least 95% of observations.

    Candidate grids come from the lower tail of adjacent unique-value spacings,
    which avoids mistaking a large meteorological change for sensor resolution.
    """
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) < 20:
        return None
    unique = np.unique(np.round(finite, decimals=12))
    if len(unique) < 5:
        return None
    gaps = np.diff(unique)
    gaps = gaps[gaps > 0]
    if len(gaps) < 4:
        return None
    upper = float(np.quantile(gaps, 0.25))
    candidates = np.unique(np.round(gaps[gaps <= upper * (1.0 + 1e-9)], decimals=12))[::-1]
    origin = float(unique[0])
    for step in candidates:
        if not math.isfinite(float(step)) or step <= 0:
            continue
        residual = np.abs((finite - origin) / step - np.rint((finite - origin) / step))
        if float(np.mean(residual <= 1e-6)) >= 0.95:
            return float(step)
    return float(np.min(gaps))


def infer_dataset_resolutions(stations: dict) -> dict:
    """Return station and pooled reporting-resolution estimates."""
    pooled = defaultdict(list)
    station = {}
    for station_id, item in stations.items():
        station[station_id] = {}
        for variable, values in item["variables"].items():
            pooled[variable].extend(np.asarray(values, dtype=float).tolist())
            station[station_id][variable] = infer_reporting_resolution(values)
    pooled_resolution = {
        variable: infer_reporting_resolution(values) for variable, values in pooled.items()
    }
    for station_id, variables in station.items():
        for variable, resolution in variables.items():
            if resolution is None:
                variables[variable] = pooled_resolution.get(variable)
    return {"station": station, "pooled": pooled_resolution}


def _solar_elevation_degrees(times, latitude, longitude):
    """Approximate solar elevation using UTC day/hour and station coordinates."""
    values = np.asarray(times).astype("datetime64[s]")
    days = values.astype("datetime64[D]")
    years = values.astype("datetime64[Y]")
    day_of_year = (days - years).astype(int) + 1
    seconds = (values - days).astype("timedelta64[s]").astype(float)
    utc_hour = seconds / 3600.0
    gamma = 2.0 * np.pi / 365.0 * (day_of_year - 1 + (utc_hour - 12.0) / 24.0)
    declination = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )
    equation = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )
    solar_minutes = utc_hour * 60.0 + equation + 4.0 * longitude
    hour_angle = np.radians(solar_minutes / 4.0 - 180.0)
    latitude_rad = math.radians(latitude)
    cosine_zenith = np.sin(latitude_rad) * np.sin(declination) + np.cos(latitude_rad) * np.cos(
        declination
    ) * np.cos(hour_angle)
    return 90.0 - np.degrees(np.arccos(np.clip(cosine_zenith, -1.0, 1.0)))


def _eligible_mask(station, variable, values, calm_threshold):
    eligible = np.isfinite(values)
    wind_speed = station["variables"].get("wind_speed")
    if variable == "wind_speed":
        eligible &= values != 0.0
    elif variable in ("wind_gust", "wind_direction") and wind_speed is not None:
        eligible &= np.isfinite(wind_speed) & (wind_speed > calm_threshold)
    elif variable == "solar_radiation" and np.issubdtype(np.asarray(station["times"]).dtype, np.datetime64):
        zero = values == 0.0
        if zero.any():
            daylight = (
                _solar_elevation_degrees(
                    station["times"], float(station.get("lat", 0.0)), float(station.get("lon", 0.0))
                )
                > 0.0
            )
            eligible &= ~zero | daylight
    return eligible


def _raw_plateaus(station, variable, resolution, calm_threshold):
    values = np.asarray(station["variables"][variable], dtype=float)
    minutes = _time_minutes(station["times"])
    finite_values = values[np.isfinite(values)]
    if len(values) < 3 or len(minutes) != len(values) or len(finite_values) == 0:
        return []
    deltas = np.diff(minutes)
    positive = deltas[np.isfinite(deltas) & (deltas > 0)]
    break_limit = 3.0 * float(np.median(positive)) if len(positive) else math.inf
    eligible = _eligible_mask(station, variable, values, calm_threshold)
    tolerance = max(
        np.finfo(float).eps * max(1.0, float(np.max(np.abs(finite_values)))),
        (resolution or 0) * 1e-6,
    )
    result = []
    start = 0
    for index in range(1, len(values) + 1):
        ended = index == len(values)
        if not ended:
            ended = (
                not eligible[index]
                or not eligible[index - 1]
                or abs(values[index] - values[index - 1]) > tolerance
                or not math.isfinite(float(deltas[index - 1]))
                or deltas[index - 1] >= break_limit
            )
        if ended:
            if index - start >= 3 and eligible[start]:
                duration = float(minutes[index - 1] - minutes[start]) / 60.0
                if duration > 0:
                    result.append(
                        {
                            "start_index": start,
                            "end_index": index - 1,
                            "start": _iso_time(station["times"][start]),
                            "end": _iso_time(station["times"][index - 1]),
                            "value": float(values[start]),
                            "records": index - start,
                            "duration_hours": duration,
                            "complete": start > 0 and index < len(values),
                        }
                    )
            start = index
    return result


def _circular_span(values):
    angles = np.sort(np.mod(values, 360.0))
    if len(angles) < 2:
        return 0.0
    gaps = np.diff(np.concatenate([angles, [angles[0] + 360.0]]))
    return float(360.0 - np.max(gaps))


def _neighbor_evidence(variable, plateau, stations, resolutions, neighbor_ids, cfg):
    try:
        start = np.datetime64(plateau["start"].removesuffix("Z"))
        end = np.datetime64(plateau["end"].removesuffix("Z"))
    except ValueError:
        return []
    usable = []
    for neighbor_id in neighbor_ids:
        neighbor = stations[neighbor_id]
        if variable not in neighbor["variables"]:
            continue
        times = np.asarray(neighbor["times"])
        if not np.issubdtype(times.dtype, np.datetime64):
            continue
        mask = (times >= start) & (times <= end) & np.isfinite(neighbor["variables"][variable])
        indexes = np.flatnonzero(mask)
        if len(indexes) < 3:
            continue
        coverage = _finite_temporal_coverage(
            times,
            np.asarray(neighbor["variables"][variable], dtype=float),
            start,
            end,
        )
        if coverage < cfg["frozen_min_neighbor_coverage"]:
            continue
        values = np.asarray(neighbor["variables"][variable], dtype=float)[indexes]
        if variable == "wind_direction":
            span = _circular_span(values)
        else:
            span = float(np.quantile(values, 0.95) - np.quantile(values, 0.05))
        resolution = resolutions["station"].get(neighbor_id, {}).get(variable)
        reference = resolution or resolutions["pooled"].get(variable)
        changed = reference is not None and span >= cfg["frozen_neighbor_change_steps"] * reference
        usable.append(
            {
                "station": neighbor_id,
                "coverage": round(coverage, 3),
                "span": round(span, 6),
                "resolution": resolution,
                "changed": bool(changed),
            }
        )
    return usable


def _same_station_activity(station, target_variable, plateau, resolutions, station_id, cfg):
    """Return activity evidence from non-target variables over a plateau."""
    start = plateau["start_index"]
    end = plateau["end_index"] + 1
    evidence = []
    for variable, raw_values in station["variables"].items():
        if variable == target_variable:
            continue
        values = np.asarray(raw_values, dtype=float)
        selected = values[start:end]
        selected = selected[np.isfinite(selected)]
        if len(selected) < 3:
            continue
        span = (
            _circular_span(selected)
            if variable == "wind_direction"
            else float(np.quantile(selected, 0.95) - np.quantile(selected, 0.05))
        )
        resolution = resolutions["station"].get(station_id, {}).get(variable)
        reference = resolution or resolutions["pooled"].get(variable)
        changed = reference is not None and span >= cfg["frozen_neighbor_change_steps"] * reference
        evidence.append(
            {
                "variable": variable,
                "span": round(span, 6),
                "resolution": resolution,
                "changed": bool(changed),
            }
        )
    return evidence


def _finite_temporal_coverage(times, values, start, end, break_factor=3.0):
    """Return the fraction of an interval covered by contiguous finite samples."""
    times = np.asarray(times)
    values = np.asarray(values, dtype=float)
    duration = float((end - start) / np.timedelta64(1, "s"))
    if duration <= 0 or len(times) != len(values) or len(times) < 2:
        return 0.0
    deltas = np.diff(times) / np.timedelta64(1, "s")
    positive = deltas[np.isfinite(deltas) & (deltas > 0)]
    if positive.size == 0:
        return 0.0
    break_limit = break_factor * float(np.median(positive))
    inside = (times >= start) & (times <= end) & np.isfinite(values)
    covered = inside[:-1] & inside[1:] & np.isfinite(deltas) & (deltas > 0) & (deltas < break_limit)
    return min(float(deltas[covered].sum()) / duration, 1.0)


def _nearest_station_cache(stations, radius_km):
    """Return every geographically valid neighbor within the radius, nearest first."""
    station_ids = list(stations)
    coordinates = []
    for item in station_ids:
        try:
            latitude = float(stations[item].get("lat"))
            longitude = float(stations[item].get("lon"))
        except (TypeError, ValueError):
            latitude = longitude = math.nan
        valid = (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        )
        coordinates.append((latitude, longitude) if valid else (math.nan, math.nan))
    latitudes = np.radians([item[0] for item in coordinates])
    longitudes = np.radians([item[1] for item in coordinates])
    cache = {}
    for index, station_id in enumerate(station_ids):
        if not np.isfinite(latitudes[index]) or not np.isfinite(longitudes[index]):
            cache[station_id] = []
            continue
        delta_latitude = latitudes - latitudes[index]
        delta_longitude = longitudes - longitudes[index]
        value = (
            np.sin(delta_latitude / 2) ** 2
            + np.cos(latitudes[index]) * np.cos(latitudes) * np.sin(delta_longitude / 2) ** 2
        )
        distances = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))
        distances[index] = np.inf
        candidates = np.flatnonzero(distances <= radius_km)
        ranked = candidates[np.argsort(distances[candidates])]
        cache[station_id] = [station_ids[item] for item in ranked]
    return cache


def analyze_zero_wind_stations(stations: dict, cfg: dict) -> dict:
    """Classify sustained zero wind as audit, review, or automatic evidence."""
    neighbor_cache = _nearest_station_cache(stations, float(cfg["zero_wind_neighbor_radius_km"]))
    results = {}
    for station_id, station in stations.items():
        if "wind_speed" not in station["variables"]:
            continue
        values = np.asarray(station["variables"]["wind_speed"], dtype=float)
        times = np.asarray(station["times"])
        known = np.isfinite(values)
        zero = known & (values == 0.0)
        if not known.any() or len(times) != len(values):
            continue
        fraction = float(zero.sum() / known.sum())
        minutes = _time_minutes(times)
        deltas = np.diff(minutes)
        positive = deltas[np.isfinite(deltas) & (deltas > 0)]
        break_limit = (
            float(cfg["zero_wind_temporal_break_factor"]) * float(np.median(positive))
            if len(positive)
            else math.inf
        )
        runs = []
        start = None
        for index in range(len(values) + 1):
            selected = index < len(values) and zero[index]
            temporal_break = (
                0 < index < len(values)
                and math.isfinite(float(deltas[index - 1]))
                and deltas[index - 1] >= break_limit
            )
            if selected and start is None:
                start = index
            if start is None or (selected and not temporal_break):
                continue
            end = index - 1
            duration = float(minutes[end] - minutes[start]) / 60.0
            if duration >= cfg["zero_wind_diagnostic_duration_hours"]:
                runs.append(
                    {
                        "start": _iso_time(times[start]),
                        "end": _iso_time(times[end]),
                        "duration_hours": duration,
                        "records": end - start + 1,
                    }
                )
            start = index if selected else None

        if fraction < cfg["zero_wind_fraction"] and not runs:
            continue
        all_zero = bool(zero.sum() == known.sum())
        for run in runs:
            start_time = np.datetime64(run["start"].removesuffix("Z"))
            end_time = np.datetime64(run["end"].removesuffix("Z"))
            neighbors = []
            usable_neighbor_ids = [
                item for item in neighbor_cache[station_id] if "wind_speed" in stations[item]["variables"]
            ][: int(cfg["zero_wind_neighbor_count"])]
            for neighbor_id in usable_neighbor_ids:
                neighbor = stations[neighbor_id]
                if "wind_speed" not in neighbor["variables"]:
                    continue
                neighbor_times = np.asarray(neighbor["times"])
                neighbor_values = np.asarray(neighbor["variables"]["wind_speed"], dtype=float)
                mask = (
                    (neighbor_times >= start_time)
                    & (neighbor_times <= end_time)
                    & np.isfinite(neighbor_values)
                )
                indexes = np.flatnonzero(mask)
                if len(indexes) < 3:
                    continue
                coverage = _finite_temporal_coverage(
                    neighbor_times,
                    neighbor_values,
                    start_time,
                    end_time,
                    float(cfg["zero_wind_temporal_break_factor"]),
                )
                noncalm_fraction = float(
                    np.mean(neighbor_values[indexes] > cfg["zero_wind_calm_threshold"])
                )
                corroborates = (
                    coverage >= cfg["zero_wind_min_neighbor_coverage"]
                    and noncalm_fraction >= cfg["zero_wind_neighbor_noncalm_fraction"]
                )
                neighbors.append(
                    {
                        "station": neighbor_id,
                        "coverage": round(coverage, 3),
                        "noncalm_fraction": round(noncalm_fraction, 3),
                        "corroborates": bool(corroborates),
                    }
                )
            actionable = run["duration_hours"] >= cfg["zero_wind_review_duration_hours"]
            automatic = actionable and (
                all_zero
                or sum(item["corroborates"] for item in neighbors) >= cfg["zero_wind_required_neighbors"]
            )
            run["neighbors"] = neighbors
            run["disposition"] = "automatic" if automatic else "review" if actionable else "audit"
        results[station_id] = {
            "station": station_id,
            "zero_fraction": fraction,
            "all_observations_zero": all_zero,
            "ranges": runs,
        }
    return results


# The branches mirror independent scientific eligibility rules and keep their
# evidence construction in one auditable pass.
# pylint: disable=too-many-branches
def analyze_frozen_stations(stations: dict, cfg: dict) -> tuple[dict, dict]:
    """Return per-station findings and reporting-resolution estimates."""
    resolutions = infer_dataset_resolutions(stations)
    raw = defaultdict(dict)
    reference_durations = defaultdict(list)
    local_durations = defaultdict(list)
    calm = float(cfg["frozen_calm_wind_threshold"])
    for station_id, station in stations.items():
        for variable in station["variables"]:
            resolution = resolutions["station"].get(station_id, {}).get(variable)
            plateaus = _raw_plateaus(station, variable, resolution, calm)
            raw[station_id][variable] = plateaus
            reference_durations[variable].extend(
                item["duration_hours"] for item in plateaus if item["complete"]
            )
            local_durations[(station_id, variable)].extend(
                item["duration_hours"] for item in plateaus if item["complete"]
            )

    thresholds = {}
    for station_id, variables in raw.items():
        for variable in variables:
            floor = float(cfg["frozen_min_duration_hours"].get(variable, math.inf))
            local = local_durations.get((station_id, variable), [])
            pooled = reference_durations.get(variable, [])
            minimum_runs = int(cfg.get("frozen_minimum_reference_runs", 100))
            durations = local if len(local) >= minimum_runs else pooled
            if cfg.get("frozen_triage"):
                diagnostic_adaptive = (
                    float(np.percentile(durations, cfg["frozen_adaptive_percentile"]))
                    if len(durations) >= minimum_runs
                    else 0.0
                )
                review_adaptive = (
                    float(np.percentile(durations, cfg["frozen_review_adaptive_percentile"]))
                    if len(durations) >= minimum_runs
                    else 0.0
                )
                automatic_adaptive = (
                    float(np.percentile(durations, cfg["frozen_automatic_adaptive_percentile"]))
                    if len(durations) >= minimum_runs
                    else 0.0
                )
                thresholds[(station_id, variable)] = {
                    "diagnostic": max(floor, diagnostic_adaptive),
                    "review": max(floor * cfg["frozen_review_duration_multiplier"], review_adaptive),
                    "automatic": max(
                        floor * cfg["frozen_automatic_duration_multiplier"],
                        automatic_adaptive,
                    ),
                }
            else:
                adaptive = (
                    float(np.percentile(durations, cfg["frozen_adaptive_percentile"]))
                    if len(durations) >= minimum_runs
                    else 0.0
                )
                thresholds[(station_id, variable)] = {"diagnostic": max(floor, adaptive)}

    neighbor_cache = _nearest_station_cache(stations, cfg["frozen_neighbor_radius_km"])

    findings = defaultdict(list)
    required = int(cfg["frozen_required_neighbors"])
    for station_id, variables in raw.items():
        for variable, plateaus in variables.items():
            variable_thresholds = thresholds.get((station_id, variable))
            if variable_thresholds is None:
                continue
            resolution = resolutions["station"].get(station_id, {}).get(variable)
            for plateau in plateaus:
                if plateau["duration_hours"] < variable_thresholds["diagnostic"]:
                    continue
                neighbor_ids = [
                    item for item in neighbor_cache[station_id] if variable in stations[item]["variables"]
                ][: cfg["frozen_neighbor_count"]]
                evidence = _neighbor_evidence(
                    variable,
                    plateau,
                    stations,
                    resolutions,
                    neighbor_ids,
                    cfg,
                )
                changing = [item for item in evidence if item["changed"]]
                if not cfg.get("frozen_triage"):
                    if len(changing) < required <= len(evidence):
                        continue
                    confidence = "high" if len(changing) >= required else "low"
                    disposition = "review" if confidence == "high" else "audit"
                    same_station = []
                else:
                    same_station = _same_station_activity(
                        stations[station_id], variable, plateau, resolutions, station_id, cfg
                    )
                    active_neighbors = [
                        item
                        for item in changing
                        if item["coverage"] >= cfg["frozen_automatic_min_neighbor_coverage"]
                    ]
                    review_ready = (
                        plateau["complete"]
                        and plateau["duration_hours"] >= variable_thresholds["review"]
                        and len(changing) >= required
                    )
                    automatic_ready = (
                        review_ready
                        and plateau["duration_hours"] >= variable_thresholds["automatic"]
                        and resolution is not None
                        and len(active_neighbors) >= cfg["frozen_automatic_required_neighbors"]
                        and any(item["changed"] for item in same_station)
                    )
                    disposition = "automatic" if automatic_ready else "review" if review_ready else "audit"
                    confidence = (
                        "near-certain" if automatic_ready else "ambiguous" if review_ready else "low"
                    )
                finding = dict(plateau)
                finding.update(
                    {
                        "station": station_id,
                        "variable": variable,
                        "confidence": confidence,
                        "resolution": resolution,
                        "quantization_uncertainty": resolution / 2.0 if resolution else None,
                        "threshold_hours": variable_thresholds["diagnostic"],
                        "review_threshold_hours": variable_thresholds.get("review"),
                        "automatic_threshold_hours": variable_thresholds.get("automatic"),
                        "neighbors": evidence,
                        "same_station_activity": same_station,
                        "disposition": disposition,
                    }
                )
                findings[station_id].append(finding)
    return dict(findings), resolutions


def frozen_finding_message(finding: dict) -> str:
    """Format full diagnostic evidence for GUI and manifest review."""
    resolution = finding["resolution"]
    resolution_text = (
        f"resolution={resolution:g}, quantization=±{finding['quantization_uncertainty']:g}"
        if resolution is not None
        else "resolution=unknown"
    )
    neighbors = (
        ", ".join(
            f"{item['station']} coverage={item['coverage']:.0%} span={item['span']:g}"
            for item in finding["neighbors"]
        )
        or "none"
    )
    return (
        f"{finding['variable']} suspected frozen from {finding['start']} to {finding['end']} "
        f"at {finding['value']:g} for "
        f"{finding['duration_hours']:.1f} h (threshold={finding['threshold_hours']:.1f} h, "
        f"{resolution_text}, confidence={finding['confidence']}, "
        f"disposition={finding.get('disposition', 'review')}; neighbors: {neighbors})"
    )
