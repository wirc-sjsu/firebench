# VanWagner
## Description

The VanWagner rate of spread model is a widely used empirical model for predicting the spread rate in a variety of forest fuels.
Developed by VanWagner in 1998 [1], it calculates the forward rate of fire spread based on fuel characteristics, environmental conditions, and topography.
It is the foundation model of the Canadian Forest Fire Behavior Prediction System (CFFBPR)

## Parameters
### Input table

Variable name in model      | Unit     | Standard Variable Name                | type      | Bounds
------------------------    | ----     | ----------------------------------    | ----      | ------
fclass                      | -        | fuel_class                            | int32     | $$]0, 1[$$
fcon                        | %        | fuel_conifer_content                  | int32     | $$]0, 1[$$
fhard                       | %        | fuel_hardwood_content                 | int32     | $$]0, 1[$$
fdir                        | %        | fuel_deadfir_content                  | int32     | $$[0, 1]$$
sh                          | m        | fuel_deadfir_content                  | float64   | $$[0, 1]$$
sd                          | stems/ha | fuel_deadfir_content                  | float64   | $$[0, 1]$$
Dj                          | -        | julian_date                           | int32     | $$[0, 366]$$
month                       | -        | month                                 | int32     | $$[0, 12]$$
lat                         | deg      | latitude                              | float34   | $$[-90, 90]$$
lon                         | deg      | longitude                             | float64   | $$[-180, 180]$$
wind                        | km h-1   | wind_speed                            | float64   | $$]0, \infty[$$
wind_dir                    | deg      | wind_direction                        | float64   | $$]-\infty, \infty[$$               
slope                       | deg      | slope_angle                           | float64   | $$]-90, 90[$$
elev                        | m        | elevation                             | float64   | $$]0, \infty[$$
ffmci                       | -        | fine_fuel_moisture_code_initial       | float64   | $$]0, 200[$$
dmci                        | -        | duff_moisture_code_initial            | float64   | $$]0, 200[$$
dci                         | -        | drought_code_initial                  | float64   | $$]0, 200[$$
air_temp                    | C        | air_temperature                       | float64   | $$]0, \infty[$$
rel_humid                   | %        | relative_humidity                     | float64   | $$]0, 100[$$
precip                      | mm       | precipitation                         | float64   | $$]0, \infty[$$
deg_curing                  | %        | degree_of_curing                      | float64   | $$[0, 100]$$

### Outputs

Variable name in model      | Unit    | Standard Variable Name               | type      | Bounds
------------------------    | ----    | ---------------------------------    | ----      | ------
ros                         | m min-1 | rate_of_spread                       | float64   | $$[0, \infty]$$

### Internal parameters

## Usage

### General use
The VanWagner model is a class derived from `firebench.ros_models.RateOfSpreadModel`.
```python
# Import rate of spread package from firebench
import firebench.ros_models as rm
# create the input dictionnary with the inputs listed above
model_inputs = {...}
# compute the rate of spread
ros = rm.VanWagner.compute_ros(model_inputs)
```

![blockdiagram](../../_static/diagram_blocks/ros_model/VanWagner.svg)

### Use with grassland fuels 

**Fig. 2** shows an example of usage with conifer fuels.
It uses constant environmental inputs for wind, wind direction, slope, elevation, air temperature, precipitation, relative humidity, and degree of curing. 

![blockdiagram](../../_static/images/fire_models_info/diagram_VanWagner_grassland.png)
<p style="text-align: center;">
    <strong>
        Fig. 2
    </strong>
    :
    <em>
        Usage of conifer fuel for VanWagner rate of spread model. 
    </em>
</p>

An example of use of conifer fuel with VanWagner, corresponding the **Fig. 2** diagram:
```python
import firebench as fb

# Define constant values as fb.Quantity (not pint.Quantity that does not share the same unit registry)

fclass = fb.Quantity(6, "dimensionless"), 
fcon = fb.Quantity(25.0, "dimensionless"), 
fhard = fb.Quantity(10.0, "dimensionless"), 
fdfir = fb.Quantity(50.0, "dimensionless"),
sh = fb.Quantity(15.0, "m"),
sd = fb.Quantity(1000.0, "stems/ha"),
Dj = fb.Quantity(30, "dimensionless"),
month = fb.Quantity(1, "dimensionless"),
lat = fb.Quantity(45.0, "degree"),
lon = fb.Quantity(45.0, "degree"),
wind = fb.Quantity(10.0, "km h-1") # wind is given 10 m above ground level
wind_dir = fb.Quantity(10.0, "degree") 
slope = fb.Quantity(10.0, "degree") 
elev = fb.Quantity(0.0, "m")
ffmci = fb.Quantity(85.0, "percentage") 
dmci = fb.Quantity(25.0, "percentage") 
dci = fb.Quantity(10.0, "percentage")  
temp_air = fb.Quantity(35.0, "celsius"),
precip = fb.Quantity(1.0, "mm") 
rel_humid = fb.Quantity(40.0, "percentage"),
deg_curing = fb.Quantity(60.0, "percentage"),

# Select the rate of spread model class
ros_model = fb.ros_models.VanWagner

# Merge the fuel dict and the constant inputs
input_dict = fb.tools.merge_dictionaries(
    {
        fb.svn.FUEL_CLASS: fuel_class, fb.Quantity(6, "dimensionless"),
        fb.svn.FUEL_CONIFER_CONTENT: fuel conifer content, fb.Quantity(25.0, "percentage"),
        fb.svn.FUEL_HARDWOOD_CONTENT: fuel hardwood content, fb.Quantity(10.0, "percentage"),
        fb.svn.FUEL_DEAD_FIR_CONTENT: fuel dead fir content, fb.Quantity(50.0, "percentage"),
        fb.svn.STAND_HEIGHT: stand height, fb.Quantity(15.0, "m"),
        fb.svn.STAND_DENSITY: stand density, fb.Quantity(1000.0, "stems/ha"),
        fb.svn.JULIAN_DATE: julian date,fb.Quantity(30, "dimensionless"),
        fb.svn.MONTH: month, fb.Quantity(1, "dimensionless"),
        fb.svn.LATITUDE: latitude, fb.Quantity(45.0, "degree"),
        fb.svn.LONGITUDE: longitude, fb.Quantity(45.0, "degree"),
        fb.svn.WIND_SPEED: wind, fb.Quantity(10.0, "km h-1"),
        fb.svn.WIND_DIRECTION: wind direction, fb.Quantity(10.0, "degree"),
        fb.svn.SLOPE_ANGLE: slope, fb.Quantity(10.0, "degree"),
        fb.svn.ELEVATION: elevation, fb.Quantity(0.0, "m"),
        fb.svn.FINE_FUEL_MOISTURE_CODE_INITIAL: fine fuel moisture code initial value, fb.Quantity(85.0, "percentage"),
        fb.svn.DUFF_MOISTURE_CODE_INITIAL: duff moisture code initial value, fb.Quantity(25.0, "percentage"),
        fb.svn.DROUGHT_CODE_INITIAL: drought code initial value, fb.Quantity(10.0, "percentage"),
        fb.svn.AIR_TEMPERATURE: air temperature, fb.Quantity(35.0, "celsius"),
        fb.svn.PRECIPITATION: precipitation, fb.Quantity(1.0, "mm"),
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

[1] [Forestry Canada. 1992. Development and structure of the Canadian Forest Fire Behavior Prediction System. Forestry Canada, Headquarters, Fire Danger Group and Science and Sustainable Development Directorate, Ottawa. Information Report ST-X-3. 64 p.] (https://ostrnrcan-dostrncan.canada.ca/handle/1845/235421)

[2] [Wotton, B . M., Alexander, M. E., Taylor. S. W. 2009. Updates and revisions to the 1992 Canadian Forest Fire Behavior Prediction System. Information Report GLC-X-10, Sault Ste. Marie, ON, Canada: Great Lakes Forestry Centre.] 