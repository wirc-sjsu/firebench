# McArthur
## Description

The McArthur rate of spread model is a widely used empirical model for predicting the spread rate of surface fires mainly in grassland fuels.
Developed by A.G.McArthur in 1960 and converted to equations by Nobel in 1980 [1], it calculates the forward rate of fire spread based on fuel characteristics, environmental conditions, and topography.

## Parameters
### Input table

Variable name in model      | Unit   | Standard Variable Name    | type      | Bounds
------------------------    | ----   | ----------------------    | ----      | ------
fgi                         | t ha-1 | fuel_load_dry_total       | float64   | $$]0, \infty[$$
igrass                      | -      | fuel_grassland_flag       | int32     | $$[0, 1]$$
wind                        | km h-1 | wind_speed                | float64   | $$]-\infty, \infty[$$
slope                       | deg    | slope_angle               | float64   | $$]0, 30[$$
temp_air                    | C      | air_temperature           | float64   | $$]0, \infty[$$
rel_humid                   | %      | relative_humidity         | float64   | $$]0, 100[$$
precip                      | mm     | precipitation             | float64   | $$]0, \infty[$$
deg_curing                  | %      | degree_of_curing          | float64   | $$[0, 100]$$
drought_index               | mm     | drought_index             | float64   | $$]0, \infty[$$
time_since_rain             | days   | time_since_rain           | float64   | $$]0, \infty[$$

### Outputs

Variable name in model      | Unit   | Standard Variable Name    | type      | Bounds
------------------------    | ----   | ----------------------    | ----      | ------
ros                         | km h-1 | rate_of_spread            | float64   | $$[0, 6]$$

### Internal parameters

## Usage

### General use
The McArthur model is a class derived from `firebench.ros_models.RateOfSpreadModel`.
```python
# Import rate of spread package from firebench
import firebench.ros_models as rm
# create the input dictionnary with the inputs listed above
model_inputs = {...}
# compute the rate of spread
ros = rm.McArthur.compute_ros(model_inputs)
```

![blockdiagram](../../_static/diagram_blocks/ros_model/McArthur.svg)

### Use with grassland fuels 

**Fig. 2** shows an example of usage with grassland fuels.
It uses constant environmental inputs for wind, slope, air temperature, precipitaion, relative humidity, degree of curing, and drought index. 

![blockdiagram](../../_static/images/fire_models_info/diagram_McArthur_grassland.png)
<p style="text-align: center;">
    <strong>
        Fig. 2
    </strong>
    :
    <em>
        Usage of grassland fuel for McArthur rate of spread model. 
    </em>
</p>

An example of use of grassland fuel with McArthur, corresponding the **Fig. 2** diagram:
```python
import firebench as fb

# Define constant values as fb.Quantity (not pint.Quantity that does not share the same unit registry)

fgi = fb.Quantity(3.0, "t ha-1"), # Maximum fuel load is 5 t ha-1
igrass = fb.Quantity(1, "int"),
wind = fb.Quantity(10.0, "km h-1") # wind is given 10 m above ground level
slope = fb.Quantity(10.0, "degree") # Maximum slope value is 30 degrees
temp_air = fb.Quantity(35.0, "celsius"),
rel_humid = fb.Quantity(40.0, "percentage"),
precip = fb.Quantity(3.0, "mm"),
deg_curing = fb.Quantity(60.0, "percentage"),
drought_index = fb.Quantity(1.0, "mm"), # Drough index is taken from Keetch-Byram [2]
time_since_rain = fb.Quantity(10, "days"),

# Select the rate of spread model class
ros_model = fb.ros_models.McArthur

# Merge the fuel dict and the constant inputs
input_dict = fb.tools.merge_dictionaries(
    {
        fb.svn.FUEL_LOAD_DRY_TOTAL: dry fuel load, fb.Quantity(3.0, "t ha-1"),
        fb.svn.FUEL_GRASSLAND_FLAG: fuel grassland flag, fb.Quantity(1, "int"),
        fb.svn.WIND_SPEED: wind, fb.Quantity(10.0, "km h-1"),
        fb.svn.SLOPE_ANGLE: slope, fb.Quantity(10.0, "degree"),
        fb.svn.AIR_TEMPERATURE: air temperature, fb.Quantity(35.0, "celsius"),
        fb.svn.RELATIVE_HUMIDITY: relative humidity, fb.Quantity(40.0, "percentage"),
        fb.svn.PRECIPITATION: precipitation, fb.Quantity(3.0, "mm"),
        fb.svn.DEGREE_OF_CURING: degree of curing, fb.Quantity(60.0, "percentage"),
        fb.svn.DROUGHT_INDEX: drought index, fb.Quantity(1.0, "mm"),
        fb.svn.TIME_SINCE_RAIN: time since rain, fb.Quantity(10, "days"),
    },
    fuel_data,
)

# perform checks, conversion and magnitude extraction
final_input = fb.tools.check_data_quality_ros_model(input_dict, ros_model)

# compute the rate of spread
ros = ros_model.compute_ros_with_units(final_input)
```

## Benchmarks and workflows

## References

[1] [NOBLE, I. R., BARY, A. V., GILL A. M. (1980). McArthur's fire-danger meters expressed as equations. Australian Journal of Ecology, 5, 201-203.] (https://doi.org/10.1111/j.1442-9993.1980.tb01243.x)

[2] [Keetch, J. J., BYRAM, G. M. (1968). A Drought Index for Forest Fire Control, U.S.D.A. Forest Service Research Paper SE-38.] 