"""Lightweight discovery metadata for the Caldor benchmark."""

from . import c001_caldor_config as cfg

KPI_GROUP_CATEGORIES = (
    ("B", "Building Damage"),
    ("S", "Burn Severity"),
    ("CC", "Canopy Cover Loss"),
    ("P", "Fire Perimeters"),
    ("W", "Weather Stations"),
)
STANDALONE_TARGETS = (
    ("B", "Building Damage"),
    ("S", "Burn Severity"),
    ("CC", "Canopy Cover Loss"),
    ("FP", "Fire Perimeters (all curated periods)"),
)
PERIOD_TARGET_FLAGS = (
    ("B", "Building Damage"),
    ("P", "Fire Perimeters"),
    ("T", "Weather Stations (TSO only)"),
    ("W", "Weather Stations (TSO and all sources)"),
)


def describe_available_targets_summary() -> dict:
    """Describe static target syntax and periods without loading benchmark runtime dependencies."""
    periods = []
    for period_name, (start, end) in cfg.HRRR_PERIODS.items():
        period_number = int(period_name.removeprefix("WH"))
        periods.append(
            {
                "target": f"H{period_number:03d}",
                "start": start,
                "end": end,
            }
        )
    for period_name, (start, end) in cfg.CURATED_PERIODS.items():
        period_number = int(period_name.removeprefix("W"))
        periods.append(
            {
                "target": f"P{period_number:02d}",
                "start": start,
                "end": end,
            }
        )

    return {
        "standalone_targets": dict(STANDALONE_TARGETS),
        "period_target_syntax": "PERIOD_FLAGS",
        "periods": periods,
        "kpi_groups": dict(PERIOD_TARGET_FLAGS),
    }
