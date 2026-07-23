"""Weather station QC constants and physical sensor bounds.

Defines physical validity bounds for each sensor variable, QC assertion categories,
and tuning parameters for dropout/outage/frozen-value detection.
"""

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
DEFAULT_NAN_THRESH = 30.0
DEFAULT_FROZEN_RUN = 10
DROPOUT_MIN_PTS = 3
GAP_DT_RATIO = 100.0
FUEL_MOISTURE_FROZEN_MIN_RUN = 15
# A NaN/missing-row run only counts as "outage" once its span reaches
# OUTAGE_RUN_FACTOR multiples of the station's median timestep.
# wind_direction/wind_gust additionally only count as outage when
# wind_speed is real and >0 (calm wind makes their NaN expected).
OUTAGE_RUN_FACTOR = 3.0
DEFAULT_MAX_VAR_OUTAGE_MIN = 1440.0  # 24h — worst single variable
DEFAULT_FULL_OUTAGE_MIN = 360.0  # 6h  — every available variable down at once

# QC assertion categories: list of (key, human-readable label) pairs.
# Keys are used internally to tag QC failures; labels are displayed to users.
# "lo:" and "hi:" are prefixed with variable name in output (e.g., "lo:air_temperature").
# "frozen:" is also prefixed with variable name.
ASSERTION_CATS = [
    ("time_neg", "Negative time jumps"),
    ("dup_ts", "Duplicate timestamps"),
    ("dropout", "WD dropout while WS>0 (sustained)"),
    ("gap_dt", "Large gap between obs (outlier)"),
    ("lo:", "Below physical bounds"),
    ("hi:", "Above physical bounds"),
    ("frozen:", "Frozen value runs (excl. calm wind)"),
    ("max_var_outage", "Max variable outage (min) exceeds threshold"),
    ("full_outage", "Full station outage (min) exceeds threshold"),
]


def default_config() -> dict:
    """Return an independent copy of the default GUI configuration."""
    return {
        "nan_pct": DEFAULT_NAN_THRESH,
        "frozen_min_run": DEFAULT_FROZEN_RUN,
        "max_var_outage_min": DEFAULT_MAX_VAR_OUTAGE_MIN,
        "full_outage_min": DEFAULT_FULL_OUTAGE_MIN,
        "dup_max": 5,
        "bounds": dict(PHYS_BOUNDS),
        "hidden_assertions": set(),
        "show_errors": True,
        "show_warns": True,
        "perim_h5_path": None,
        "perim_show_all": False,
        "compare_n_neighbors": 4,
        "compare_include_skip_greenlit": False,
    }
