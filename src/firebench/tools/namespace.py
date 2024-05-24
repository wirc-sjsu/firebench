from enum import Enum


class StandardVariableNames(Enum):  # pragma: no cover
    """
    Enum class for standard variable names used in the firebench project.

    This enumeration defines standard names for various physical and model variables
    related to fire modeling. These names are used to ensure consistency and
    clarity across the codebase and related data files.
    """

    CANOPY_DENSITY_BULK = "canopy_density_bulk"
    CANOPY_HEIGHT_BOTTOM = "canopy_height_bottom"
    CANOPY_HEIGHT_TOP = "canopy_height_top"
    FUEL_CLASS = "fuel_class"
    FUEL_CHAPARRAL_FLAG = "fuel_chaparral_flag"
    FUEL_DENSITY = "fuel_density"
    FUEL_FRACTION_CONSUMED_FLAME_ZONE = "fuel_fraction_consumed_flame_zone"
    FUEL_HEIGHT = "fuel_height"
    FUEL_LOAD_DRY_1H = "fuel_load_dry_1h"
    FUEL_LOAD_DRY_10H = "fuel_load_dry_10h"
    FUEL_LOAD_DRY_100H = "fuel_load_dry_100h"
    FUEL_LOAD_DRY_1000H = "fuel_load_dry_1000h"
    FUEL_LOAD_DRY_LIVE = "fuel_load_dry_live"
    FUEL_LOAD_DRY_TOTAL = "fuel_load_dry_total"
    FUEL_MINERAL_CONTENT_EFFECTIVE = "fuel_mineral_content_effective"
    FUEL_MINERAL_CONTENT_TOTAL = "fuel_mineral_content_total"
    FUEL_MOISTURE_CONTENT = "fuel_moisture_content"
    FUEL_MOISTURE_CONTENT_1H = "fuel_moisture_content_1h"
    FUEL_MOISTURE_CONTENT_10H = "fuel_moisture_content_10h"
    FUEL_MOISTURE_CONTENT_100H = "fuel_moisture_content_100h"
    FUEL_MOISTURE_CONTENT_1000H = "fuel_moisture_content_1000h"
    FUEL_MOISTURE_CONTENT_LIVE = "fuel_moisture_content_live"
    FUEL_MOISTURE_EXTINCTION = "fuel_moisture_extinction"
    FUEL_ROUGHNESS_HEIGHT = "fuel_roughness_height"
    FUEL_SFIREBURNUP_CONSUMPTION_CST = "fuel_sfireburnup_consumption_cst"
    FUEL_SURFACE_AREA_VOLUME_RATIO = "fuel_surface_area_volume_ratio"
    FUEL_THERMAL_CONDUCTIVITY = "fuel_thermal_conductivity"
    FUEL_TREE_CLASS = "fuel_tree_class"
    FUEL_WIND_HEIGHT = "fuel_wind_height"
    FUEL_WIND_REDUCTION_FACTOR = "fuel_wind_reduction_factor"
    RATE_OF_SPREAD = "rate_of_spread"
    SLOPE_ANGLE = "slope_angle"
    WIND = "wind"
