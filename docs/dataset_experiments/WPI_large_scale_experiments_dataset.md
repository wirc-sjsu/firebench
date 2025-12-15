# WPI large scale experiments validation dataset

## Description

The dataset presents wind aided fire spread experiments over Pinus Plaustris needles bed. The experiments were conducted in a large scale wind tunnel having an operating range of 0 - 5 m/s. These burns were performed over a fuel bed of width 1.2 m and length 3 m. Three wind velocities, 0.5 m/s, 1.4 m/s, and 2.2 m/s, were used in these tests. Fuel loading, moisture content, and composition of live and dead needles were varied during the burns. The experiments were simulated using Fire Dynamics Simulator (FDS) and the rate of spread is compared for several cases.

## Firebench dataset content

### Table W1 dataset

Variable name in dataset    | Unit  | Standard Variable Name    | type      | Source
------------------------    | ----  | ----------------------    | ----      | ------
fltyp                       |       |                           | object    | 
fueldepthm                  | m     | fuel_height               | float64   |  
fldf                        | kg m-2| fuel_load_dead            | float64   |
fllf                        | kg m-2| fuel_load_live            | float64   | 
wspd                        | m s-1 | wind_speed                | float64   | 
fmde                        | %     | fuel_moisture_content_dead| float64   | 
fml                         | %     | fuel_moisture_content_live| float64   | 
ros                         | m min-1| rate_of_spread           | float64   | 

The fill value, also called `no_data_value`, for this dataset is -9999.

> **note on wind reduction factor**: The wind reduction factor given in Table 8 is used to get the 2 m wind speed from the 10 m wind speed.

## Usage

Import the WPI dataset using `FireBench` with:
```python
import firebench.tools as ft
wpi_dataset = ft.read_data_file("Table_W1", "ros_model_validation/WPI")
```
The data is stored in the dictionnary `wpi_dataset_W1` for the data of Table W1 
The keys are the standard variable names and the values are numpy array associated with pint unit.

![blockdiagram](../_static/diagram_blocks/dataset/anderson2015_A1.svg)
![blockdiagram](../_static/diagram_blocks/dataset/anderson2015_8.svg)

## Reference
