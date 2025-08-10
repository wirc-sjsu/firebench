# 8. Standard Namespace

This page lists the standard variable names used in the FireBench project. These names ensure consistency and clarity across the codebase and related data files.
The standard names are structured from left to right from the broader category to the highest details. For example, the dry fuel load variables all start with `FUEL_LOAD_DRY` even if you would say `dry fuel load`.
This rule ensures to group the variables with common meaning.
The standard unit is given between brackets `[]`.
If units are not applicable, the varibale type is given between parenthesis `()`.

The Standard Variable Namespace `svn` is accessed in workflows using `from firebench import svn`.

## Standard Variable Names

- `AIR_DENSITY`: Air density [kg m-3]
- `AIR_TEMPERATURE`: Air temperature [K]
- `ALPHA`: Alpha
- `BETA`: Beta
- `CANOPY_DENSITY_BULK`: Canopy bulk density [kg m-3]
- `CANOPY_HEIGHT_BOTTOM`: Canopy height bottom [m]
- `CANOPY_HEIGHT_TOP`: Canopy height top [m]
- `FUEL_CLASS`: Fuel class (int)
- `FUEL_CHAPARRAL_FLAG`: Fuel chaparral flag (int)
- `FUEL_COVER`: Fuel cover [%]
- `FUEL_DENSITY`: Fuel density [kg m-3]
- `FUEL_DENSITY_BULK`: Fuel bulk density [kg m-3]
- `FUEL_DENSITY_DEAD`: Dead fuel density [kg m-3]
- `FUEL_DENSITY_LIVE`: Live fuel density [kg m-3]
- `FUEL_FRACTION_CONSUMED_FLAME_ZONE`: Fuel fraction consumed flame zone [-]
- `FUEL_HEAT_CONTENT`: Fuel heat content [J kg-1]
- `FUEL_HEIGHT`: Fuel height [m]
- `FUEL_LOAD_DEAD_RATIO`: Dead fuel load ratio [-]
- `FUEL_LOAD_FINE`: Fine fuels load [kg m-2]
- `FUEL_LOAD_FINE_DEAD`: Dead fine fuels load [kg m-2]
- `FUEL_LOAD_FINE_LIVE`: Live fine fuels load [kg m-2]
- `FUEL_LOAD_DRY_1H`: Fuel load dry 1 hour [kg m-2]
- `FUEL_LOAD_DRY_10H`: Fuel load dry 10 hours [kg m-2]
- `FUEL_LOAD_DRY_100H`: Fuel load dry 100 hours [kg m-2]
- `FUEL_LOAD_DRY_1000H`: Fuel load dry 1000 hours [kg m-2]
- `FUEL_LOAD_DRY_LIVE`: Fuel load dry live [kg m-2]
- `FUEL_LOAD_DRY_LIVE_HERB`: Fuel load dry live herb [kg m-2]
- `FUEL_LOAD_DRY_LIVE_WOODY`: Fuel load dry live woody [kg m-2]
- `FUEL_LOAD_DRY_TOTAL`: Fuel load dry total [kg m-2]
- `FUEL_MINERAL_CONTENT_EFFECTIVE`: Fuel mineral content effective [-]
- `FUEL_MINERAL_CONTENT_TOTAL`: Fuel mineral content total [-]
- `FUEL_MOISTURE_CONTENT`: Fuel moisture content [%]
- `FUEL_MOISTURE_CONTENT_1H`: Fuel moisture content 1 hour [%]
- `FUEL_MOISTURE_CONTENT_10H`: Fuel moisture content 10 hours [%]
- `FUEL_MOISTURE_CONTENT_100H`: Fuel moisture content 100 hours [%]
- `FUEL_MOISTURE_CONTENT_1000H`: Fuel moisture content 1000 hours [%]
- `FUEL_MOISTURE_CONTENT_DEAD`: Dead fuel moisture content [%]
- `FUEL_MOISTURE_CONTENT_ELEVATED_DEAD`: Dead fuel moisture content elevated [%]
- `FUEL_MOISTURE_CONTENT_FINE_DEAD`: Dead fine fuel moisture content elevated [%]
- `FUEL_MOISTURE_CONTENT_LIVE`: Live fuel moisture content [%]
- `FUEL_MOISTURE_EXTINCTION`: Fuel moisture extinction [%]
- `FUEL_ROUGHNESS_HEIGHT`: Fuel roughness height [m]
- `FUEL_SFIREBURNUP_CONSUMPTION_CST`: Fuel SFIRE BURNUP consumption constant [-]
- `FUEL_SURFACE_AREA_VOLUME_RATIO`: Fuel surface area volume ratio [m-1]
- `FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD`: Dead fuel surface area volume ratio [m-1]
- `FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H`: Fuel surface area volume ratio for dead 1h fuel [m-1]
- `FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE`: Live fuel surface area volume ratio [m-1]
- `FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB`: Fuel surface area volume ratio for live herb fuel [m-1]
- `FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY`: Fuel surface area volume ratio for live woody fuel [m-1]
- `FUEL_TEMPERATURE_IGNITION`: Fuel igntiion temperature [K]
- `FUEL_THERMAL_CONDUCTIVITY`: Fuel thermal conductivity [W kg-1 K-1]
- `FUEL_TREE_CLASS`: Fuel tree class (int)
- `FUEL_WIND_HEIGHT`: Fuel wind height [m]
- `FUEL_WIND_REDUCTION_FACTOR`: Fuel wind reduction factor [-]
- `IGNITION_LENGTH`: Ignition length [m]
- `LENGTH`: Length [m]
- `RATE_OF_SPREAD`: Rate of spread [m s-1]
- `RELATIVE_HUMIDITY`: Relative Humidity [m s-1]
- `SLOPE_ANGLE`: Slope angle [deg]
- `TEMPERATURE`: Temperature [K]
- `TIME`: Time [s]
- `WIND_SPEED`: Wind [m s-1]
