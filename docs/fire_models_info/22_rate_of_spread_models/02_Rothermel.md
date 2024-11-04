---
layout: default
title: "Rothermel"
parent: "Rate of spread models"
grand_parent: "Fire Models information"
nav_order: 2
---
<script src="/assets/js/mathjax.js"></script>

# Rothermel_SFIRE

## Description

## Parameters
### Input table

Variable name in model      | Unit  | Standard Variable Name    | type      | Bounds
------------------------    | ----  | ----------------------    | ----      | ------
fgi                         | kg m-2| fuel_load_dry_total       | float64   | ]0, $\infty$[
fueldens                    | lb ft-3| fuel_density             | float64   | ]0, $\infty$[
fueldepthm                  | m     | fuel_height               | float64   | ]0, $\infty$[
fuelmce                     | %     | fuel_moisture_extinction  | float64   | [0, $\infty$[
fmc                         | %     | fuel_moisture_content     | float64   | [0, 200]
ichap                       | -     | fuel_chaparral_flag       | int32     | [0, 1]
savr                        | ft-1  | fuel_surface_area_volume_ratio| float64| ]0, $\infty$[
se                          | -     | fuel_mineral_content_effective| float64| [0, 1]
slope                       | deg   | slope_angle               | float64   | ]-90, 90[
st                          | -     | fuel_mineral_content_total| float64   | [0, 1]
wind                        | -     | wind_speed                | float64   | ]-$\infty$, $\infty$[
windrf                      | -     | fuel_wind_reduction_factor| float64   | [0, 1]

### Outputs

Variable name in model      | Unit  | Standard Variable Name    | type      | Bounds
------------------------    | ----  | ----------------------    | ----      | ------
ros                         | m s-1 | rate_of_spread            | float64   | [0, 6]

### Internal parameters

Name in model   | Description               | Unit      | Value
--------------- | ------------------------- | --------- | ---------
cmbcnst         | Combustion enthalpy       | J kg-1    | 17.433e06

### Internal unit conversion coefficient

From        | To        | Value
----------- | --------- | -----
J kg-1      | BTU lb-1  | 4.30e-04
kg m-2      | lb ft-2   | 0.3048**2 * 2.205
m           | ft        | 1 / 0.3048
m s-1       | ft min-1  | 196.850
ft min-1    | m s-1     | 0.00508

## Usage

Import data using `FireBench` and output variable.

## Validity domain

## Sensitivity analysis

## Compatibility with fire models

## Benchmarks and workflows

## References

