---
layout: default
title: "Anderson 2015"
parent: "Datasets and fire experiment information"
nav_order: 1
---

# Anderson 2015 validation dataset

## Description

The dataset presented in [1] compiles shrubland fire behavior data from experimental studies conducted across Australia, New Zealand, Europe, and South Africa. It encompasses a wide range of heathland and shrubland vegetation types and structures.  The dataset contains independent data from prescribed fires and wildfires. Additionally, the dataset supports the evaluation of a model for dead fuel moisture prediction and introduces a correction for ignition line length. While the models offer robust predictions across diverse shrubland conditions, further research is needed to address the impacts of slope steepness, fuel variation, and thresholds for continuous fire spread.

## Firebench dataset content

### Table A1 dataset

Variable name in dataset    | Unit  | Standard Variable Name    | type      | Source
------------------------    | ----  | ----------------------    | ----      | ------
code                        |       |                           | object    | [1]
country                     |       |                           | object    | [1]
fityp                       |       |                           | object    | [1]
fueldepthm                  | m     | fuel_height               | float64   | [1]
fcover                      | %     | fuel_cover                | float64   | [1]
fldf                        | kg m-2| fuel_load_fine_dead       | float64   | [1]
fllf                        | kg m-2| fuel_load_fine_live       | float64   | [1]
fldry                       | kg m-2| fuel_load_dry_total       | float64   | [1]
temperature                 | degC  | temperature               | float64   | [1]
rh                          | %     | relative_humidity         | float64   | [1]
whgt                        | m     | fuel_wind_height          | float64   | [1]
wspd                        | km h-1| wind_speed                | float64   | [1]
slope                       | %     | slope_angle               | float64   | [1]
fmde                        | %     | fuel_moisture_content_elevated_dead | float64   | [1]
fml                         | %     | fuel_moisture_content_live| float64   | [1]
ignln                       | m     | ignition_length           | float64   | [1]
ros                         | m min-1| rate_of_spread           | float64   | [1]

The fill value, also called `no_data_value`, for this dataset is -9999.

### Table 8 dataset

Variable name in dataset    | Unit  | Standard Variable Name    | type      | Source
------------------------    | ----  | ----------------------    | ----      | ------
firename                    |       |                           | object    | [1]
country                     |       |                           | object    | [1]
location                    |       |                           | object    | [1]
date                        |       |                           | object    | [1]
starttime                   | hhmm  |                           | int32     | [1]
endtime                     | hhmm  |                           | int32     | [1]
fuelname                    |       |                           | object    | [1]
ros                         | m min-1| rate_of_spread           | float64   | [1]
whgt                        | m     | fuel_wind_height          | float64   | [1]
wspd                        | km h-1| wind_speed                | float64   | [1]
windrf                      | -     | fuel_wind_reduction_factor| float64   | [1]
temperature                 | degC  | temperature               | float64   | [1]
rh                          | %     | relative_humidity         | float64   | [1]
fmoistdf                    | %     | fuel_moisture_content_fine_dead         | float64   | [1]
fheight                     | m     | fuel_height               | float64   | [1]
flf                         | m     | fuel_load_fine            | float64   | [1]
fbd                         | kg m-3| fuel_density_bulk         | float64   | [1]
relwthr                     |       |                           | object    | [1]
relfuel                     |       |                           | object    | [1]
relros                      |       |                           | object    | [1]

The fill value, also called `no_data_value`, for this dataset is -9999.

> **note on wind reduction factor**: The wind reduction factor given in Table 8 is used to get the 2 m wind speed from the 10 m wind speed.

## Usage

Import the Anderson 2015 dataset using `FireBench` with:
```python
import firebench.tools as ft
anderson_dataset_A1 = ft.read_data_file("Table_A1", "ros_model_validation/Anderson_2015")
anderson_dataset_8 = ft.read_data_file("Table_8", "ros_model_validation/Anderson_2015")
```
The data is stored in the dictionnary `anderson_dataset_A1` for the data of Table A1 and `anderson_dataset_8` for the data of Table 8.
The keys are the standard variable names and the values are numpy array associated with pint unit.

<div style="text-align: center;">
    <img src="../../assets/diagram_blocks/dataset/anderson2015_A1.svg" alt="Block A1" style="margin-right: 10px;"/>
    <img src="../../assets/diagram_blocks/dataset/anderson2015_8.svg" alt="Block A1" style="margin-left: 10px;"/>
</div>

## Reference

[1] [Anderson, W. R., Cruz, M. G., Fernandes, P. M., McCaw, L., Vega, J. A., Bradstock, R. A., ... & van Wilgen, B. W. (2015). A generic, empirical-based model for predicting rate of fire spread in shrublands. International Journal of Wildland Fire, 24(4), 443-460.](https://doi.org/10.1071/WF14130)