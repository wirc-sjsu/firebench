"""Weather station QC constants and physical sensor bounds.

Defines physical validity bounds for each sensor variable, QC assertion categories,
and tuning parameters for dropout/outage/frozen-value detection.
"""

import math

# Sensor variable name -> (min, max, unit) bounds.
# Maps each weather sensor variable to its valid physical range and unit string.
# Temperature in Celsius, wind speeds in m/s, direction in degrees (0-360),
# humidity and fuel moisture in percent, solar radiation in W/m2.
PHYS_BOUNDS = {
    "air_temperature": (-50.0, 60.0, "C"),
    "relative_humidity": (0.0, 100.0, "%"),
    "wind_speed": (0.0, 60.0, "m/s"),
    "wind_gust": (0.0, 80.0, "m/s"),
    "wind_direction": (0.0, 360.0, "deg"),
    "solar_radiation": (0.0, 1500.0, "W/m2"),
    "fuel_moisture_content_10h": (0.0, 60.0, "%"),
}
DEFAULT_FROZEN_RUN = 10
DEFAULT_CALM_WIND_THRESHOLD = 1.5
DROPOUT_MIN_PTS = 3
GAP_DT_RATIO = 100.0
FUEL_MOISTURE_FROZEN_MIN_RUN = 15
# A NaN/missing-row run only counts as "outage" once its span reaches
# OUTAGE_RUN_FACTOR multiples of the station's median timestep.
# wind_direction/wind_gust additionally only count as outage when
# wind_speed is real and >0 (calm wind makes their NaN expected).
OUTAGE_RUN_FACTOR = 3.0
DEFAULT_MAX_VAR_OUTAGE_MIN = 1440.0  # 24h, worst single variable
DEFAULT_FULL_OUTAGE_MIN = 360.0  # 6h, every available variable down at once

# QC assertion categories: list of (key, human-readable label) pairs.
# Keys are used internally to tag QC failures; labels are displayed to users.
# "lo:" and "hi:" are prefixed with variable name in output (e.g., "lo:air_temperature").
# "frozen:" is also prefixed with variable name.
ASSERTION_CATS = [
    ("time_axis", "Invalid time axes"),
    ("time_neg", "Negative time jumps"),
    ("dup_ts", "Duplicate timestamps"),
    ("dropout", "WD dropout while WS>0 (sustained)"),
    ("gap_dt", "Large gap between obs (outlier)"),
    ("no_data", "No sensor variables recorded"),
    ("lo:", "Below physical bounds"),
    ("hi:", "Above physical bounds"),
    ("frozen:", "Frozen value runs (excl. calm wind)"),
    ("max_var_outage", "Longest variable outage exceeds threshold"),
    ("full_outage", "Longest full-station outage exceeds threshold"),
]

# Severity each assertion category is emitted with when no per-category
# override is configured. "time_neg" and "dup_ts" are conditionally WARN or
# ERROR depending on count; WARN is shown here as their typical case.
ASSERTION_DEFAULT_SEVERITY = {
    "time_axis": "ERROR",
    "time_neg": "WARN",
    "dup_ts": "WARN",
    "dropout": "WARN",
    "gap_dt": "WARN",
    "no_data": "ERROR",
    "lo:": "ERROR",
    "hi:": "ERROR",
    "frozen:": "WARN",
    "max_var_outage": "WARN",
    "full_outage": "WARN",
}

MAP_COLOR_MODES = (
    "issues",
    "wd_nan_pct",
    "n_variables",
    "n_pts",
    "qc_status",
    "variable_value",
    "wind_combo",
)


def default_config() -> dict:
    """Return an independent copy of the default GUI configuration."""
    return {
        "frozen_min_run": DEFAULT_FROZEN_RUN,
        "frozen_exempt_calm_wind": False,
        "frozen_exempt_rh": False,
        "max_var_outage_min": DEFAULT_MAX_VAR_OUTAGE_MIN,
        "full_outage_min": DEFAULT_FULL_OUTAGE_MIN,
        "dup_max": 2,
        "bounds": dict(PHYS_BOUNDS),
        "hidden_assertions": set(),
        "assertion_severity_override": {},
        "perim_h5_path": None,
        "perim_show_all": True,
        "compare_n_neighbors": 4,
        "compare_include_skip_greenlit": False,
        "map_nav_fire_area_deriv": False,
        "ts_nav_fire_area": False,
        "map_marker_size": 1.0,
        "cbar_overrides": {},
    }


def parse_nonnegative_finite(value, label: str) -> float:
    """Return ``value`` as a finite non-negative float or raise ``ValueError``."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return parsed


def validate_gui_config(config: dict) -> None:
    """Validate user-editable QC settings before they replace App state."""
    for key, label in (
        ("frozen_min_run", "Frozen run length"),
        ("compare_n_neighbors", "Neighbor count"),
        ("dup_max", "Duplicate-timestamp threshold"),
    ):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")

    for key, label in (
        ("max_var_outage_min", "Maximum variable outage threshold"),
        ("full_outage_min", "Full-station outage threshold"),
    ):
        parse_nonnegative_finite(config.get(key), label)

    marker_size = config.get("map_marker_size", 1.0)
    if isinstance(marker_size, bool) or not isinstance(marker_size, (int, float)):
        raise ValueError("Marker size must be a number")
    if not math.isfinite(marker_size) or marker_size <= 0:
        raise ValueError("Marker size must be finite and greater than zero")

    for key, severity in config.get("assertion_severity_override", {}).items():
        if not isinstance(key, str) or severity not in ("WARN", "ERROR"):
            raise ValueError(f"Assertion severity override for {key!r} must be WARN or ERROR")

    for variable, bounds in config.get("bounds", {}).items():
        try:
            lower, upper, _unit = bounds
            lower = float(lower)
            upper = float(upper)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{variable} bounds must be numbers") from exc
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError(f"{variable} bounds must be finite")
        if lower >= upper:
            raise ValueError(f"{variable} lower bound must be less than its upper bound")

    for variable, override in config.get("cbar_overrides", {}).items():
        if not isinstance(override, dict):
            raise ValueError(f"Colorbar override for {variable} must be an object")
        vmin, vmax = override.get("vmin"), override.get("vmax")
        for bound_value, bound_label in ((vmin, "min"), (vmax, "max")):
            if bound_value is not None and (
                isinstance(bound_value, bool)
                or not isinstance(bound_value, (int, float))
                or not math.isfinite(bound_value)
            ):
                raise ValueError(f"Colorbar {bound_label} for {variable} must be a finite number")
        if vmin is not None and vmax is not None and vmin >= vmax:
            raise ValueError(f"Colorbar min for {variable} must be less than its max")
        cmap = override.get("cmap")
        if cmap is not None and not isinstance(cmap, str):
            raise ValueError(f"Colorbar scheme for {variable} must be a string")
        if not isinstance(override.get("reversed", False), bool):
            raise ValueError(f"Colorbar reversed flag for {variable} must be true or false")
