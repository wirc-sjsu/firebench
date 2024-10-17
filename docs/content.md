---
layout: default
title: "Content"
nav_order: 4
---

# Content of the package

This page lists the fuels models, the rate of spread models and the workflows that are contained within the package.

## Fuel models

- `Anderson13`: Anderson 13 categories ([reference](https://www.fs.usda.gov/rm/pubs_int/int_gtr122.pdf))

## Rate of spread models

### Vegetation
- `Rothermel_SFIRE`: Rothermel model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE), from 
- `Balbi_2022_fixed_SFIRE`: Balbi 2022 model as implemented in [WRF-SFIRE](https://github.com/openwfm/WRF-SFIRE)

### Urban
- `Hamada_1`: Hamada model derived from Scawthorn, C. (2009). Enhancements in HAZUS-MH. Fire Following Earthquake Task, 3.
- `Hamada_2`: Hamada model derived from the equations in [Himoto, K., & Tanaka, T. (2008)](https://doi.org/10.1016/j.firesaf.2007.12.008)

## Workflows

### 3. Sensitivity

1. [Sensitivity to environemental variables](./workflows/sensitivity/ros_sensitivity.md) (`03_01_calc_sensitity_env_var`, `03_01_post_sensitity_env_var`)