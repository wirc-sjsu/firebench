---
layout: default
title: "Anderson 13"
parent: "Fuel models"
grand_parent: "Fire Models information"
nav_order: 2
---

# Anderson 13 fuel model

## Description

## Firebench dataset content

Variable name in dataset    | Unit  | Standard Variable Name    | type      | Source
------------------------    | ----  | ----------------------    | ----      | ------
fcwh                        | m     | fuel_wind_height          | float64   | TBD
fcz0                        | m     | fuel_roughness_height     | float64   | TBD
ffw                         | -     | fuel_fraction_consumed_flame_zone | float64 | TBD
fgi                         | kg m-2| fuel_load_dry_total       | float64   | TBD
fuel_name                   |       |                           | object    | TBD
fueldens                    | lb ft-3| fuel_density             | float64   | TBD
fueldepthm                  | m     | fuel_height               | float64   | TBD
fuelmce                     | %     | fuel_moisture_extinction  | float64   | TBD
ichap                       | -     | fuel_chaparral_flag       | int32     | TBD
k_tc                        | W m-1 K-1| fuel_thermal_conductivity| float64 | TBD
savr                        | ft-1  | fuel_surface_area_volume_ratio| float64 | TBD
se                          | -  | fuel_mineral_content_effective| float64  | TBD
st                          | -  | fuel_mineral_content_total   | float64   | TBD
weight                      | -  | fuel_sfireburnup_consumption_cst| float64| TBD
windrf                      | -  | fuel_wind_reduction_factor   | float64   | TBD

## Usage

Import data using `FireBench` and output variable.

## Compatibility with fire models

Compatibility levels:
- Full: The data contained in the fuel model covers **all** the fuel input needed by the fire model
- Partial: The data contained in the fuel model covers **some** of the fuel input needed by the fire model
- None: The data contained in the fuel model covers **none** of the fuel input needed by the fire model


Fire model              | Category          | Compatibility level
----------              | --------          | -----------------
Rothermel_SFIRE         | ROS vegetation    | Full
Balbi_2022_fixed_SFIRE  | ROS vegetation    | Full
Hamada_1                | ROS urban         | None
Hamada_2                | ROS urban         | None


## References

