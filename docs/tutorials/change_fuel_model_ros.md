# How to Use Fuel Models

This guide will walk you through the steps to use fuel models in the FireBench library.
You can use a default fuel model or create and use a custom one.
Specify the name of the model in `fuel_model_name`.
If a path to a directory containing a custom fuel model JSON file is specified in `local_path_json_fuel_db`, then `FireBench` will search for the file in the given path before searching within the package database.

## Overview

Using a fuel model involves:
1. Understanding the default fuel model structure.
2. Using a default fuel model.
3. Creating a custom fuel model.
4. Using a custom fuel model.

## Step 1: Understanding the Default Fuel Model Structure

FireBench includes several default fuel models.
Fuel models are inputs to other components in `FireBench`.
The fuel models distributed within the package are listed [here](../content.md).

The fuel models are stored as a JSON metadata file and a CSV data file. The CSV data file contains a header with variable names; each row represents a fuel class. The metadata file contains information about fuel model variables. For example, the `Anderson13` fuel model is composed of the `Anderson13.json` metadata file:

```json
{
  "data_path": "data_Anderson13.csv",
  "metadata": {
    "fcwh": {
      "variable_name": "fuel_wind_height",
      "unit": "m",
      "type": "float64"
    },
    "fcz0": {
      "variable_name": "fuel_roughness_height",
      "unit": "m",
      "type": "float64"
    },
    "ffw": {
      "variable_name": "fuel_fraction_consumed_flame_zone",
      "unit": "dimensionless",
      "type": "float64"
    },
    "fgi": {
      "variable_name": "fuel_load_dry_total",
      "unit": "kg/m^2",
      "type": "float64"
    },
    "fuel_name": {
      "variable_name": "fuel_description",
      "unit": "None",
      "type": "object"
    },
    "fueldens": {
      "variable_name": "fuel_density",
      "unit": "lb/ft^3",
      "type": "float64"
    },
    "fueldepthm": {
      "variable_name": "fuel_height",
      "unit": "m",
      "type": "float64"
    },
    "fuelmce": {
      "variable_name": "fuel_moisture_extinction",
      "unit": "dimensionless",
      "type": "float64"
    },
    "ichap": {
      "variable_name": "fuel_chaparral_flag",
      "unit": "dimensionless",
      "type": "int32"
    },
    "k_tc": {
      "variable_name": "fuel_thermal_conductivity",
      "unit": "W/m/K",
      "type": "float64"
    },
    "savr": {
      "variable_name": "fuel_surface_area_volume_ratio",
      "unit": "1/ft",
      "type": "float64"
    },
    "se": {
      "variable_name": "fuel_mineral_content_effective",
      "unit": "dimensionless",
      "type": "float64"
    },
    "st": {
      "variable_name": "fuel_mineral_content_total",
      "unit": "dimensionless",
      "type": "float64"
    },
    "weight": {
      "variable_name": "fuel_sfireburnup_consumption_cst",
      "unit": "dimensionless",
      "type": "float64"
    },
    "windrf": {
      "variable_name": "fuel_wind_reduction_factor",
      "unit": "dimensionless",
      "type": "float64"
    },
    "fuel_load_1h": {
      "variable_name": "fuel_load_dry_1h",
      "unit": "short_ton/acre",
      "type": "float64"
    },
    "fuel_load_10h": {
      "variable_name": "fuel_load_dry_10h",
      "unit": "short_ton/acre",
      "type": "float64"
    },
    "fuel_load_100h": {
      "variable_name": "fuel_load_dry_100h",
      "unit": "short_ton/acre",
      "type": "float64"
    },
    "fuel_load_live": {
      "variable_name": "fuel_load_dry_live",
      "unit": "short_ton/acre",
      "type": "float64"
    }
  }
}
```
The metadata file stores the path of the data file in `data_path`. The metadata dictionary contains the following information for each variable in the data file:
- `variable_name` as given within the [standard namespace](../namespace.md) in lowercase
- `unit` using [Pint library](https://pint.readthedocs.io/en/stable/) standard. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).
- `type` as `numpy` dtype for memory allocation.

The first three lines of the CSV data file `data_Anderson13.csv` looks like this:
```
fcwh,fcz0,ffw,fgi,fuel_name,fueldens,fueldepthm,fuelmce,ichap,k_tc,savr,se,st,weight,windrf,fuel_load_1h,fuel_load_10h,fuel_load_100h,fuel_load_live
6.096,0.0396,0.9,0.166,1: Short grass (1 ft),32.0,0.305,0.12,0,0.04025,3500.0,0.01,0.0555,7.0,0.36,0.74,0.00,0.00,0.00
6.096,0.0396,0.9,0.897,2: Timber (grass and understory),32.0,0.305,0.15,0,0.01621,2784.0,0.01,0.0555,7.0,0.36,2.00,1.00,0.50,0.50
```

The CSV file stores the data itself. The headers can be chosen arbitrarily as the connection with the standard namespace is done in the JSON file.

## Step 2: Using a default fuel model

Default fuel models are imported using a wrapped function. The default fuel models distributed within the package are listed [here](../content.md). For example, importing `Anderson13` Fuel Model is done using `firebench.tools.fuel_models_utils.import_anderson_13_fuel_model`. Such wrapper function has extra features integrated to add fields to the fuel dictionary or do specific processing. 
For example, the following script imports `Anderson 13` Fuel Model, computes the dead fuel ratio and adds it to the fuel dictionary. It also imports `Scott and Burgan 40` Fuel Model, computes the total fuel load, the total surface area to volume ratio, and the dead fuel ratio, and adds these fields to the fuel dictionary.

```python
import firebench.tools as ft

fuel_dict   = ft.import_anderson_13_fuel_model(add_complementary_fields=True)
fuel_dict_2 = ft.import_scott_burgan_40_fuel_model(add_complementary_fields=True)
```

It is also possible to import Fuel Model using low level file reading function. The extra fields must be added manually.

```python
import firebench.tools as ft

fuel_dict = ft.read_fuel_data_file("ScottandBurgan40")
```

## Step 3: Create a custom fuel model

You can create your custom fuel model and use it locally.
First, you have to create the CSV data file `my_custom_fuel_model.csv` that contains the data with one header line specifying the names of the variables. The order is not important. Each line of the CSV file corresponds to a fuel class. Here is an example of the CSV file:
```
x_1,t_1
1.0,2.0
4.5,1.0
```

Then, you have to create the metadata file `my_custom_fuel_model.json` that will contain the relative path to the datafile and information about the variables:
```json
{
    "data_path": "my_custom_fuel_model.csv",
    "metadata": {
      "x_1": {
        "variable_name": "length",
        "unit": "m"
      },
      "t_1": {
        "variable_name": "time",
        "unit": "s"
      },
}
```

## Step 4: Using a custom fuel model

To use the custom data, specify the path of the directory that contains the JSON file and the name of the fuel model:
```python
fuel_model_name = "my_custom_fuel_model" # name of the fuel model -> looking for my_custom_fuel_model.json
local_path_json_fuel_db = "/path/to/the/custom/fuel/models/database" # path to the json file
# import custom fuel model
fuel_dict = ft.read_fuel_data_file(
  fuel_model_name=fuel_model_name,
  local_path_json_fuel_db=local_path_json_fuel_db,
)
```
