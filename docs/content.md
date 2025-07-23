# 8. Content of the package

This page lists fire sub-models included in the package, the datasets and the tools.

## Fire submodels
### Fuel models

- `Anderson13`: Anderson 13 categories ([info](./fire_models_info/21_fuel_models/02_Anderson.md))
- `ScottandBurgan40`: Scott and Burgan 40 categories ([info](./fire_models_info/21_fuel_models/03_SB40.md))
- `WUDAPT10`: WUDAPT urban 10 categories ([info](./fire_models_info/21_fuel_models/50_WUDAPT.md))

### Vegetation rate of spread models

- `Rothermel_SFIRE`: Rothermel model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE) ([info](./fire_models_info/22_rate_of_spread_models/02_Rothermel.md))
- `Balbi_2022_fixed_SFIRE`: Balbi 2022 model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE) ([info](./fire_models_info/22_rate_of_spread_models/03_Balbi2022.md))
- `Santoni2011`: Santoni 2011 model ([info](./fire_models_info/22_rate_of_spread_models/04_Santoni2011.md))

### Urban rate of spread models
- `Hamada_1`: Hamada model derived from Scawthorn, C. (2009). Enhancements in HAZUS-MH. Fire Following Earthquake Task, 3 ([info](./fire_models_info/22_rate_of_spread_models/50_Hamada1.md)).
- `Hamada_2`: Hamada model derived from the equations in [Himoto, K., & Tanaka, T. (2008)](https://doi.org/10.1016/j.firesaf.2007.12.008) ([info](./fire_models_info/22_rate_of_spread_models/51_Hamada2.md)).

### Wind interpolation 

#### Vertical interpolation to midflame height / average wind over flame height

- `Baughman_20ft_wind_reduction_factor_unsheltered`: Calculate the wind reduction factor for a wind 20ft above vegetation level ([info](./fire_models_info/23_wind_red_factor/index.md))
- `Baughman_generalized_wind_reduction_factor_unsheltered`: Generalized version of wind reduction factor from Baughman and Albini (1980) ([info](./fire_models_info/23_wind_red_factor/index.md))
- `Masson_canyon`: Urban canyon wind speed Masson (2000)

## Datasets

- Anderson 2015 rate of spread validation ([info](./dataset_experiments/Anderson_2015_dataset.md))

## Tools

Non-exhaustive list of high-level tools available. For more information about tools, please refer to the [API Reference](./api/index.rst).

### 0d metrics
- `bias`: Compute the bias between two arrays, ignoring NaNs.
- `nmse_power`: Compute the Normalized Mean Square Error (NMSE) between two arrays, using the product of their mean values as normalization.
- `nmse_range`: Compute the Normalized Mean Square Error (NMSE) between two arrays, using the range of the reference signal as normalization.
- `rmse`: Compute the Root Mean Square Error (RMSE) between two arrays, ignoring NaNs.

### Perimeters metrics

- `jaccard_binary`: Jaccard index (Intersection over Union) for binary matrix.
- `jaccard_polygon`: Jaccard index (Intersection over Union) for polygons (geopandas).
- `sorensen_dice_binary`: Sorensen-Dice index for binary matrix.
- `sorensen_dice_polygon`: Sorensen-Dice index for polygons (geopandas).

### Raster/polygons utils

- `array_to_geopolygons`: Convert an array field into geospatial polygons at a given iso-value, preserving holes.

### Sub-models utils

- `anderson_2015_stats`: Plot statistics from the Anderson 2015 dataset.
- `apply_wind_reduction_factor`: Calculate the wind speed at a different height by applying a wind reduction factor.
- `check_data_quality_ros_model`: Check and process the input data quality for a Rate of Spread (ROS) model.
- `check_input_completeness`: Check the completeness of the input data against the metadata dictionary.
- `check_validity_range`: Check if the input data values fall within the specified validity range in the metadata dictionary.
- `convert_input_data_units`: Convert the units of input data based on the metadata dictionary.
- `create_file_handler`: Create a file handler for logging.
- `extract_magnitudes`: Extract magnitudes from a dictionary of quantities.
- `find_closest_fuel_class_by_properties`: Find the fuel class index that has the closest properties to the given set of properties.
- `get_value_by_category`: Retrieve a value from `x` based on the specified category index.
- `import_anderson_13_fuel_model`: Import and return the Anderson 13 fuel model data.
- `import_scott_burgan_40_fuel_model`: Import and return the Scott and Burgan 40 fuel model data, with optional complementary computations.
- `import_wudapt_fuel_model`: Import and return the WUDAPT urban fuel model data.
- `merge_dictionaries`: Merge two dictionaries, resolving key conflicts by favoring one dictionary.
- `set_logging_level`: Set the logging level for both the logger and all its handlers.
- `sobol_seq`: Generate a Sobol sequence for the given variables with specified units and ranges.
