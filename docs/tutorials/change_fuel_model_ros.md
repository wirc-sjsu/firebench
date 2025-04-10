# How to Use Fuel Models

This guide will walk you through the steps to use fuel models in the FireBench library.
You can use a default fuel model or create and use a custom one.
Specify the name of the model in `fuel_model_name`.
If a path to a directory containing a custom fuel model JSON file is specified in `local_path_json_fuel_db`, then `FireBench` will search for the file in the given path before searching within the package database.

## Overview

Using a fuel model involves:
1. Understanding the default fuel model structure.
2. Using a default fuel model in the workflow.
3. Creating a custom fuel model.
4. Using a custom fuel model in the workflow.

## Step 1: Understanding the Default Fuel Model Structure

FireBench includes several default fuel models.
Fuel models are inputs to other components in `FireBench`.
If you want to build a custom fuel model for a specific rate of spread model, for example, you should refer first to the metadata of the rate of spread model that contains its list of required inputs.
The fuel models distributed within the package are listed [here](../content.md).

### Default Fuel Model Management

The fuel models are stored as a JSON metadata file and a CSV data file. The CSV data file contains a header with variable names; each row represents a fuel class. The metadata file contains information about fuel model variables. For example, the `Anderson13` fuel model is composed of the `Anderson13.json` metadata file:

```json
{
    "data_path": "data_Anderson13.csv",
    "metadata": {
      "fgi": {
        "variable_name": "fuel_load_dry_total",
        "unit": "kg/m^2"
      },
      "windrf": {
        "variable_name": "fuel_wind_reduction_factor",
        "unit": "dimensionless"
      },
    }
}
```
The metadata file stores the path of the data file in `data_path`. The metadata dictionary contains the following information for each variable in the data file:
- `variable_name` as given within the [standard namespace](../namespace.md) in lowercase
- `unit` using [Pint library](https://pint.readthedocs.io/en/stable/) standard. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

The CSV data file `data_Anderson13.csv` looks like this:
```
windrf,fgi,fueldepthm,fueldens,savr,fuelmce,st,se,ichap
0.45,0.200,0.350,30.0,3600.0,10.0,0.0655,0.02,1
```

## Step 2: Using a default fuel model in the workflow

In most workflows that use Fuel Models, two variables are dedicated to fuel model configuration. When using a default Fuel Model, `local_path_json_fuel_db` can be set to `None` to ensure that FireBench looks for the metadata file in the FireBench database (`data/fuel_models`). The default fuel models distributed within the package are listed [here](../content.md).

```python
fuel_model_name = "Anderson13" # name of the fuel model -> looking for Anderson13.json
local_path_json_fuel_db = None # 
```

## Step 3: Create a custom fuel model

You can create your custom fuel model and use it locally. First, you have to create the CSV data file that contains the data with one header line specifying the names of the variables. Each line of the file corresponds to a fuel class. Then, you have to create the metadata file `my_custom_fuel_model.json` that will contain the relative path to the datafile and information about the variables:
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

## Step 4: Using a custom fuel model in the workflow

To use the custom data, specify the path of the directory that contains the JSON file and the name of the fuel model:
```python
fuel_model_name = "my_custom_fuel_model" # name of the fuel model -> looking for my_custom_fuel_model.json
local_path_json_fuel_db = "/path/to/the/custom/fuel/models/database" # 
```
