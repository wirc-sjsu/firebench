---
layout: default
title: "Rothermel"
parent: "Rate of spread models"
grand_parent: "Fire Models information"
math: mathjax
nav_order: 2
---

# Rothermel_SFIRE
## Description

The Rothermel rate of spread model is a widely used empirical model for predicting the spread rate of surface fires.
Developed by Richard C. Rothermel in 1972 [1], it calculates the forward rate of fire spread based on fuel characteristics, environmental conditions, and topography.
The model integrates parameters like fuel load, moisture, wind speed, and slope to estimate how quickly a fire will move across a landscape [2].
While primarily used for grass, shrub, and forested areas, the Rothermel model is the foundation for many fire behavior prediction systems, such as BEHAVE and FARSITE, providing essential insights for wildfire management and planning.

## Parameters
### Input table

Variable name in model      | Unit  | Standard Variable Name    | type      | Bounds
------------------------    | ----  | ----------------------    | ----      | ------
fgi                         | kg m-2| fuel_load_dry_total       | float64   | $$]0, \infty[$$
fueldens                    | lb ft-3| fuel_density             | float64   | $$]0, \infty[$$
fueldepthm                  | m     | fuel_height               | float64   | $$]0, \infty[$$
fuelmce                     | %     | fuel_moisture_extinction  | float64   | $$]0, \infty[$$
fmc                         | %     | fuel_moisture_content     | float64   | $$[0, 200]$$
ichap                       | -     | fuel_chaparral_flag       | int32     | $$[0, 1]$$
savr                        | ft-1  | fuel_surface_area_volume_ratio| float64| $$]0, \infty[$$
se                          | -     | fuel_mineral_content_effective| float64| $$[0, 1]$$
slope                       | deg   | slope_angle               | float64   | $$]-90, 90[$$
st                          | -     | fuel_mineral_content_total| float64   | $$[0, 1]$$
wind                        | -     | wind_speed                | float64   | $$]-\infty, \infty[$$
windrf                      | -     | fuel_wind_reduction_factor| float64   | $$[0, 1]$$

### Outputs

Variable name in model      | Unit  | Standard Variable Name    | type      | Bounds
------------------------    | ----  | ----------------------    | ----      | ------
ros                         | m s-1 | rate_of_spread            | float64   | $$[0, 6]$$

### Internal parameters

Name in model   | Description               | Unit      | Value
--------------- | ------------------------- | --------- | ---------
cmbcnst         | Combustion enthalpy       | J kg-1    | $$17.433 \cdot 10^6$$

### Internal unit conversion coefficient

From        | To        | Value
----------- | --------- | -----
J kg-1      | BTU lb-1  | $$4.30 \cdot 10^{4}$$
kg m-2      | lb ft-2   | $$0.3048^2 \times 2.205$$
m           | ft        | $$1 / 0.3048$$
m s-1       | ft min-1  | $$196.850$$
ft min-1    | m s-1     | $$0.00508$$

## Usage

### General use
The Rothermel_SFIRE model is a class derived from `firebench.ros_models.RateOfSpreadModel`.
```python
# Import rate of spread package from firebench
import firebench.ros_models as rm
# create the input dictionnary with the inputs listed above
model_inputs = {...}
# compute the rate of spread
ros = rm.Rothermel_SFIRE.compute_ros(model_inputs)
```

### Use with Anderson13 fuel model

The [Anderson13](../21_fuel_models/02_Anderson.md) fuel model provides a set of fuel properties that can be linked to Rothermel_SFIRE's inputs. The following diagram shows the workflow that can be used to connect Anderson fuel model and Rothermel rate of spread model.

Fig. 1 shows an example of usage with Anderson fuel model.
It uses constant environemental inputs for wind, slope and fuel moisture. 
It also uses the wind reduction factor from Anderson fuel model.

<div style="text-align: center;">
    <img src="../../images/fire_models_info/diagram_Rothermel_Anderson.png" alt="Diagram Rothermel Anderson"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Usage of Anderson fuel model for Rothermel_SFIRE rate of spread model. 
    </em>
</p>

### Use with Scott and Burgan fuel model

**TBD**

Fig. 2 shows an example of usage with Scott and Burgan fuel model.
It uses constant environemental inputs for wind, slope and fuel moisture. 
As all the inputs needed for Rothermel_SFIRE are not directly present in SB40, we need to complement the inputs from another source of information or to combine SB40 properties together.
For example, the fuel load input for Rothermel is the sum of the fuel loads for the different fuel sizes in Scott and Burgan.
As Scott and Burgan dataset does not contain the fuel density and wind reduction factors, we can use a correspodance table to get this information from Anderson fuel model instead.
It also uses the wind reduction factor from Anderson fuel model.

<div style="text-align: center;">
    <img src="../../images/fire_models_info/diagram_Rothermel_SB40.png" alt="Diagram Rothermel SB40"/>
</div>
<p style="text-align: center;">
    <strong>
        Fig. 2
    </strong>
    :
    <em>
        Usage of Scott and Burgan fuel model for Rothermel_SFIRE rate of spread model. 
    </em>
</p>

## Compatibility with fire models

## Benchmarks and workflows

## References

[1] Rothermel, R. C. (1972). A mathematical model for predicting fire spread in wildland fuels (Vol. 115). Intermountain Forest & Range Experiment Station, Forest Service, US Department of Agriculture.

[2] [Andrews, P. L. (2018). The Rothermel surface fire spread model and associated developments: A comprehensive explanation. Gen. Tech. Rep. RMRS-GTR-371. Fort
Collins, CO: U.S. Department of Agriculture, Forest Service, Rocky Mountain Research
Station. 121 p.](https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr371.pdf)