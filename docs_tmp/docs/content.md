---
layout: default
title: "Content"
nav_order: 7
---

# Content of the package

This page lists the fuels models, the rate of spread models and the workflows that are contained within the package.

## Fuel models

- `Anderson13`: Anderson 13 categories [info](./fire_models_info/21_fuel_models/02_Anderson.md)
- `ScottandBurgan40`: Scott and Burgan 40 categories [info](./fire_models_info/21_fuel_models/03_SB40.md)

## Rate of spread models

Rate fo spread models are contained in `firebench.ros_models`.

### Vegetation
- `Rothermel_SFIRE`: Rothermel model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE) [info](./fire_models_info/22_rate_of_spread_models/02_Rothermel.md)
- `Balbi_2022_fixed_SFIRE`: Balbi 2022 model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE) [info](./fire_models_info/22_rate_of_spread_models/03_Balbi2022.md)

### Urban
- `Hamada_1`: Hamada model derived from Scawthorn, C. (2009). Enhancements in HAZUS-MH. Fire Following Earthquake Task, 3.
- `Hamada_2`: Hamada model derived from the equations in [Himoto, K., & Tanaka, T. (2008)](https://doi.org/10.1016/j.firesaf.2007.12.008)

## Wind interpolation 

### Vertical interpolation to midflame height / average wind over flame height

- `Baughman_20ft_wind_reduction_factor_unsheltered`: Calculate the wind reduction factor for a wind 20ft above vegetation level [info](./fire_models_info/23_wind_red_factor/index.md)
- `Baughman_generalized_wind_reduction_factor_unsheltered`: Generalized version of wind reduction factor from Baughman and Albini (1980) [info](./fire_models_info/23_wind_red_factor/index.md)
- `Masson_canyon`: Urban canyon wind speed Masson (2000)

## W0D models workflows and benchmarks

### Accuracy

### Efficiency

### Sensitivity

1. [Sensitivity to environemental variables](./workflows/sensitivity/ros_sensitivity.md) (`03_01_calc_sensitity_env_var`, `03_01_post_sensitity_env_var`)