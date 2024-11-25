---
layout: default
title: "ROS validation using Anderson 2015 dataset"
parent: "Rate of spread models workflows"
grand_parent: "Benchmarks 0D models"
nav_order: 2
---

# ROS validation using Anderson 2015 dataset
## Objectives

We want to evaluate the accuracy of rate of spread models by comparing the computed rate of spread with observation from the `Anderson 2015 dataset`.

## Description of the benchmark

- Input dataset: `firebench/data/ros_model_validation/Anderson_2015`, Table A1
- Complementary fuel data from Scott and Burgan 40.
- If fuel data is missing, use `firebench.tools.find_closest_fuel_class_by_properties` to retrieve the closest fuel category using total fuel load and fuel height with default weights.
- Use `Baughman_generalized_wind_reduction_factor_unsheltered` to compute wind reduction factor considering that the input wind height is above vegetation.

### Output file

The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the expected and computed rate of spread.

## Benchmarks available

The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/01_01_Anderson_2015_validation`.

The workflow has been run with the following models and parameters:

<!-- the name of the workflow test, commit hash of the code that generated this data, generation date, other info on the library used (with commit hash if possible), inputs  -->
- [balbi 2022](Anderson_2015_Validation/Balbi_2022/report.html)
- [Rothermel (SFIRE version)](Anderson_2015_Validation/Rothermel/report.html)

If you don't find the content in the `data` directory, try `git lfs pull`.