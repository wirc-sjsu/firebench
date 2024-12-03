---
layout: default
title: "Rate of spread model execution time"
parent: "Rate of spread models workflows"
grand_parent: "Benchmarks 0D models"
nav_order: 3
---

# Rate of spread model execution time
## Objectives

The goal is to estimate the execution time of the rate of spread model for specific fuel models.
It allows to estimate the overall performance of the rate of spread model implementation and assess discrepancies in performances for different fuel classes within a fuel model.

## Description of the benchmark

- **Performance evaluation** uses `time.perf_counter()` to measure execution time of the rate of spread function only (`firebench.ros_models.Rothermel_SFIRE.rothermel` for example).

- **Fuel model**: Uses `Anderson13` or `ScottandBurgan40` fuel models. 

- **Sampling method**: This workflow uses Sobol sequence sampling similarly to sensitivity workflow. It defines the fuel related properties from fuel model and sample the environmental variable space using Sobol sequence. This way, the performance of the model is estimated covering the whole validity domain of the rate of spread model for each fuel class.

### Output file

The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the rate of spread and the execution time.

## Benchmarks available

The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/02_01_execution_time_Anderson` for Anderson fuel model.

The workflow has been run with the following models and parameters:

<!-- the name of the workflow test, commit hash of the code that generated this data, generation date, other info on the library used (with commit hash if possible), inputs  -->

If you don't find the content in the `data` directory, try `git lfs pull`.