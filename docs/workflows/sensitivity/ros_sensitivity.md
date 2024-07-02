---
layout: default
title: "ROS Sensitivity to Environmental Variables"
parent: "Sensitivity"
grand_parent: "Workflows"
nav_order: 1
---

# ROS Sensitivity to Environmental Variables
## Objectives

This workflow aims to evaluate the sensitivity of a specific rate of spread (ROS) model to its environemental inputs.
Detailed information about ROS sensitivity to environmental variables.


## Inputs

The inputs (using the standard variable namespace) for this workflow are:
- `FUEL_MOISTURE_CONTENT`: Fuel total moisture content
- `SLOPE_ANGLE`: Angle of the slope
- `WIND`: wind in the spread direction

As the range and units are specified within the workflow, they can be modified by the user.

## Scripts

### Computation of the Sobol indices
path: `workflows/rate_of_spread_models/03_01_C_sensitivity_env_vars.py`

This script will create a directory in the local data directory

### Post processing
path: `workflows/rate_of_spread_models/03_01_P_sensitivity_env_vars.py`

## Data

The workflow has been run with the following models and parameters:

<!-- name of the workflow test, commit hash of the code thaht generated this data, generation date, other info on library used (with commit hash if possible), inputs  -->
- Rothermel (SFIRE version) - commit hash of the code that generated this data: ??