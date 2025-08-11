# Cheney
## Description

The Cheney rate of spread model is a widely used empirical model for predicting the spread rate of grassland and eucalyptus fuels.
Developed by Cheney in 1998 [1] for grassland fuels and leter for eucalyptus fuels in 2012 [2], it calculates the forward rate of fire spread based on fuel characteristics, environmental conditions, and topography.

## Parameters
### Input table

Variable name in model      | Unit   | Standard Variable Name                | type      | Bounds
------------------------    | ----   | ----------------------------------    | ----      | ------
fhs_s                       | -      | fuel_hazard_score_surface_fuel        | int32     | $$]0, 1[$$
fhs_ns                      | -      | fuel_hazard_score_near_surface_fuel   | int32     | $$]0, 1[$$
hf_ns                       | -      | height_near_surface_fuel              | int32     | $$]0, 1[$$
igrass                      | -      | fuel_grassland_flag                   | int32     | $$[0, 1]$$
igrass_state                | -      | fuel_grassland_state_flag             | int32     | $$[0, 1]$$
ieuca                       | -      | fuel_eucalyptus_flag                  | int32     | $$[0, 1]$$
ieuca_ros                   | -      | fuel_eucalyptus_ros_flag              | int32     | $$[0, 1]$$
fmoist_period               | -      | fuel_grassland_flag                   | int32     | $$[0, 1]$$
wind                        | km h-1 | wind_speed                            | float64   | $$]0, \infty[$$
slope                       | deg    | slope_angle                           | float64   | $$]0, \infty[$$
temp_air                    | C      | air_temperature                       | float64   | $$]0, \infty[$$
rel_humid                   | %      | relative_humidity                     | float64   | $$]0, 100[$$
deg_curing                  | %      | degree_of_curing                      | float64   | $$[0, 100]$$

### Outputs

Variable name in model      | Unit    | Standard Variable Name               | type      | Bounds
------------------------    | ----    | ---------------------------------    | ----      | ------
ros                         | m min-1 | rate_of_spread                       | float64   | $$[0, \infty]$$

### Internal parameters

## Usage

### General use
The Cheney model is a class derived from `firebench.ros_models.RateOfSpreadModel`.
```python
# Import rate of spread package from firebench
import firebench.ros_models as rm
# create the input dictionnary with the inputs listed above
model_inputs = {...}
# compute the rate of spread
ros = rm.Cheney.compute_ros(model_inputs)
```

![blockdiagram](../../_static/diagram_blocks/ros_model/Cheney.svg)

### Use with grassland fuels 

**Fig. 2** shows an example of usage with grassland fuels.
It uses constant environmental inputs for wind, slope, air temperature, relative humidity, and degree of curing. 

![blockdiagram](../../_static/images/fire_models_info/diagram_Cheney_grassland.png)
<p style="text-align: center;">
    <strong>
        Fig. 2
    </strong>
    :
    <em>
        Usage of grassland fuel for Cheney rate of spread model. 
    </em>
</p>

An example of use of grassland fuel with Cheney, corresponding the **Fig. 2** diagram:
```python
import firebench as fb

# Define constant values as fb.Quantity (not pint.Quantity that does not share the same unit registry)

fhs_s = fb.Quantity(1, "dimensionless"), 
fhs_ns = fb.Quantity(1, "dimensionless"), 
hf_ns = fb.Quantity(1, "dimensionless"), 
igrass = fb.Quantity(1, "dimensionless"),
igrass_state = fb.Quantity(1, "dimensionless"),
ieuca = fb.Quantity(0, "dimensionless"),
ieuca_ros = fb.Quantity(0, "dimensionless"),
fmoist_period = fb.Quantity(0, "dimensionless"),
wind = fb.Quantity(10.0, "km h-1") # wind is given 10 m above ground level
slope = fb.Quantity(10.0, "degree") 
temp_air = fb.Quantity(35.0, "celsius"),
rel_humid = fb.Quantity(40.0, "percentage"),
deg_curing = fb.Quantity(60.0, "percentage"),

# Select the rate of spread model class
ros_model = fb.ros_models.Cheney

# Merge the fuel dict and the constant inputs
input_dict = fb.tools.merge_dictionaries(
    {
        fb.svn.FUEL_HAZARD_SCORE_SURFACE_FUEL: hazard score of surface fuel, fb.Quantity(2.0, "dimensionless"),
        fb.svn.FUEL_HAZARD_SCORE_NEAR_SURFACE_FUEL: hazard score of near surface fuel, fb.Quantity(2.0, "dimensionless"),
        fb.svn.FUEL_HEIGHT_NEAR_SURFACE_FUEL: height of near surface fuel, fb.Quantity(1.0, "cm"),
        fb.svn.FUEL_GRASSLAND_FLAG: fuel grassland flag, fb.Quantity(1, "dimensionless"),
        fb.svn.FUEL_GRASSLAND_STATE_FLAG: fuel grassland state flag,fb.Quantity(1, "dimensionless"),
        fb.svn.FUEL_EUCALYPTUS_FLAG: fuel eucalyptus flag, fb.Quantity(1, "dimensionless"),
        fb.svn.FUEL_EUCALYPTUS_ROS_FLAG: fuel eucalyptus ros flag, fb.Quantity(1, "dimensionless"),
        fb.svn.FUEL_MOISTURE_CONTENT_PERIOD_FLAG: fuel moisture content period, fb.Quantity(1, "int"),
        fb.svn.WIND_SPEED: wind, fb.Quantity(10.0, "km h-1"),
        fb.svn.SLOPE_ANGLE: slope, fb.Quantity(10.0, "degree"),
        fb.svn.AIR_TEMPERATURE: air temperature, fb.Quantity(35.0, "celsius"),
        fb.svn.RELATIVE_HUMIDITY: relative humidity, fb.Quantity(40.0, "percentage"),
        fb.svn.DEGREE_OF_CURING: degree of curing, fb.Quantity(60.0, "percentage"),
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

[1] [Cheney, N. P., Gould, J. S., Catchpole W. R. (1998). Prediction of Fire Spread in Grasslands. International Journal of Wildland Fire 8(l), 1-13.] (https://doi.org/10.1071/WF9980001)

[2] [Cheney, N. P., Gould, J. S., McCawb, W. L., Anderson W. R. (2012). Predicting fire behaviour in dry eucalypt forest in southern Australia. Forest Ecology and Management, 280, 120–131.] (https://doi.org/10.1016/j.foreco.2012.06.012)