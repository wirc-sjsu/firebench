---
layout: default
title: "ROS Sensitivity to Environmental Variables"
parent: "Rate of spread models workflows"
grand_parent: "0D models"
nav_order: 1
---

# ROS Sensitivity to Environmental Variables
## Objectives

This workflow aims to evaluate the sensitivity of a specific rate of spread (ROS) model to its environmental inputs. It computes the `First and Total Order Sobol indices` with respect to environmental variable for each fuel class in a specific [Fuel Model](../../../../tutorials/change_fuel_model_ros.md).
The environmental variables are:
- Total fuel moisture content
- Terrain slope angle in the spread direction
- Wind speed in the spread direction (considered at mid-flame height for most rate of spread models)

The following figure shows the workflow architecture:
<div style="text-align: center;">
    <img src="/images/Benchmark_0d_sensitivity_ros.png" alt="workflow rate of spread sensitivity to environmental variables" style="width: 100%; max-width: 1200px;"/>
</div>


The workflow is organized around two Python scripts:
- `calc` (`firebench/workflows/rate_of_spread_models/03_01_calc_sensitivity_env_vars.py`): Computation of the Sobol indices
- `post`(`firebench/workflows/rate_of_spread_models/03_01_post_sensitivity_env_vars.py`): Post-processing


## Computation of the Sobol indices (calc script)

### Workflow record setup

The workflow outputs will be stored in a local database’s directory called a `record`. The path to the local database has been set up through the environment variable `FIREBENCH_LOCAL_DB` (See [Installation](../../../../index.md)).
The record directory name is set using `workflow_record_name`. You can force the overwriting of files in the record through `overwrite_files_in_record`.

### Import fuel model data

The fuel properties necessary to compute the rate of spread are generally stored in a database called a Fuel Model. `FireBench` contains some popular [Fuel Models](../../../../content.md).
To load a Fuel Model available in `FireBench`, use its name for `fuel_model_name`.
If you want to use a custom Fuel Model ([How to Use Fuel Models](../../../../tutorials/change_fuel_model_ros.md)), you have to define the path to the `json` metadata file representing the Fuel Model in `local_path_json_fuel_db`.

### Select the rate of spread model

To select the rate of spread model for the analysis, you can change the `ros_model` variable in the setup section. This variable should be a `firebench.ros_models.surface_for_vegetation.RateOfSpreadModel` class ([How to customize a rate of spread model](../../../../tutorials/new_ros_model.md)).

### Generate Sobol sequence for environmental inputs

The inputs (using the [standard variable namespace](../../../../namespace.md)) for this workflow are:
- `FUEL_MOISTURE_CONTENT`: Total fuel moisture content
- `SLOPE_ANGLE`: Terrain slope angle in the spread direction
- `WIND_SPEED`: Wind speed in the spread direction

Each variable should have a unit attached and a range that will be used to create the Sobol sequence. Units are managed using the [Pint library](https://pint.readthedocs.io/en/stable/) standard. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

The number of points in the sequence can be modified using `num_sobol_points`. It is recommended that this value is a power of 2. The number of model calls for `N` points is `N * (2D + 2)`, where `D` is the number of parameters (here D=3, leading to `8N` rate of spread model calls).

### Logging

A log file called `firebench.log` will be generated throughout the workflow and will be saved in the record directory. You can change the [logging level](https://docs.python.org/3/library/logging.html#logging-levels) by changing `ft.logger.setLevel(0)`.

### Setup

The setup section in the Python script is:
```python
#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
workflow_record_name = "Sensitivity_env_var_Anderson13_Rothermel"
overwrite_files_in_record = True
output_filename = "Rothermel_SFIRE"

# Fuel Model Configuration
fuel_model_name = "Anderson13"
local_path_json_fuel_db = None

# Rate of Spread Model
ros_model = rm.Rothermel_SFIRE

# Sobol Sequence Configuration
num_sobol_points = 2**13  # Number of points for Sobol sequence, better if 2^N

# Input Variables Configuration
input_vars_info = {
    svn.WIND_SPEED: {"unit": ureg.meter / ureg.second, "range": [-15, 15]},
    svn.SLOPE_ANGLE: {"unit": ureg.degree, "range": [-45, 45]},
    svn.FUEL_MOISTURE_CONTENT: {"unit": ureg.percent, "range": [1, 50]},
}

# Logging Configuration
# set logging level, from lower to higher: NOTSET (0), DEBUG (10), INFO (20), WARNING (30), ERROR (40), CRITICAL (50)
ft.logger.setLevel(20)
```

### Output file

The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the Fuel Model data, the raw output of the rate of spread model, the Sobol sequence, and the output from the Sobol analysis. First and Total Order indices are computed as well as confidence intervals.
The content is organized as follows (using `Anderson13` Fuel Model).
The output filename is `output_{output_filename}.h5`.

```
output_record_name.h5
├── fuel
│   ├── fuel_chaparral_flag
│   ├── fuel_density
│   ├── fuel_fraction_consumed_flame_zone
│   ├── fuel_height
│   ├── fuel_load_dry_total
│   ├── fuel_mineral_content_effective
│   ├── fuel_mineral_content_total
│   ├── fuel_moisture_extinction
│   ├── fuel_roughness_height
│   ├── fuel_sfireburnup_consumption_cst
│   ├── fuel_surface_area_volume_ratio
│   ├── fuel_thermal_conductivity
│   ├── fuel_wind_height
│   ├── fuel_wind_reduction_factor
│   └── nb_fuel_classes
├── outputs
│   ├── Sobol_first_order
│   ├── Sobol_first_order_confidence
│   ├── Sobol_total_order
│   ├── Sobol_total_order_confidence
│   └── rate_of_spread
└── sensitivity_vars
    ├── fuel_moisture_content
    ├── slope_angle
    └── wind_speed
```

## Post-processing and plotting (post script)

The `post` script is designed to load the data generated by the `calc` script and plot the First and Total Order Sobol indices for each fuel class.
This script provides an example of post-processing, and users are encouraged to explore the data produced and share different post-processing and analysis scripts with the community.


### Setup

The setup section in the Python script is:
```python
#######################################################################################
#                             SETUP SECTION
# This section is for setting up parameters. Change these parameters as needed.
#######################################################################################

# Workflow Configuration
workflow_record_name = "Sensitivity_env_var_Anderson13_Rothermel"
output_filename = "Rothermel_SFIRE"
figure_name = "sobol_index.png"
overwrite_figure = True
```

## Data

The workflow has been run with the following models and parameters:

<!-- the name of the workflow test, commit hash of the code that generated this data, generation date, other info on the library used (with commit hash if possible), inputs  -->
- Rothermel (SFIRE version): `firebench/data/workflow/Sensitivity_env_var_Anderson13_Rothermel.zip`

If you don't find the content in the `data` directory, try `git lfs pull`.