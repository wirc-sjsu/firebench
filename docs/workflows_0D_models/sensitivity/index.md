# ROS Sensitivity to Environmental Variables
## Objectives

This workflow aims to evaluate the sensitivity of a specific rate of spread (ROS) model to its environmental inputs.
The environmental parameters are defined as all the non-internal parameters that are not present in a Fuel Model.
These parameters can vary from one rate of spread model to the other.
It computes the `First and Total Order Sobol indices` with respect to environmental variable for each fuel class in a specific [Fuel Model](../../tutorials/change_fuel_model_ros.md).
Environmental variables can be fuel moisture content, terrain slope angle in the spread direction, midflame wind speed in the spread direction, air temperature and density, or fuel ignition temperature. 

**Fig.1**  shows an example of the benchmark for `Anderson13` fuel model, `Rothermel_SFIRE` with three environmental parameters (moisture, slope, wind).
![blockdiagram](../../_static/images/Benchmark_0d_sensitivity_ros.png)
<p style="text-align: center;">
    <strong>
        Fig. 1
    </strong>
    :
    <em>
        Sensitivity analysis of Rothermel_SFIRE rate of spread model for Anderson 13 fuel model. 
    </em>
</p>

## Description of the benchmark

Based on a specific fuel model, the use choose a rate of spread model and the relevant environmental parameters for the rate of spread model.
Each environmental variable must have a unit attached and a range that will be used to create the Sobol sequence. Units are managed using the [Pint library](https://pint.readthedocs.io/en/stable/) standard. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

Then, a Sobol sequence is generated for the environmental parameters according to ranges specified for each variable.
The number of points in the sequence can be modified using `num_sobol_points`. It is recommended that this value is a power of 2. The number of model calls for `N` points is `N * (2D + 2)`, where `D` is the number of parameters (here D=3, leading to `8N` rate of spread model calls).
The standard value for `num_sobol_points` is 8192.
The same sequence will be used for each fuel class of the fuel model. 

A log file called `firebench.log` will be generated throughout the workflow and will be saved in the record directory. You can change the [logging level](https://docs.python.org/3/library/logging.html#logging-levels) by changing `logging_level`.

### Output file

The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the Fuel Model data, the raw output of the rate of spread model, the Sobol sequence, and the output from the Sobol analysis. First and Total Order indices are computed as well as confidence intervals.

## Benchmarks available

### Using Anderson fuel model
The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/03_01_Environmental_parameters_sensitivity_Anderson`.

### Using Scott and Burgan fuel model
The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/03_01_Environmental_parameters_sensitivity_Anderson`.

### Using WUDAPT fuel model
The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/03_02_Environmental_parameters_sensitivity_WUDAPT`.

```{toctree}
:maxdepth: 1

Rothermel_SFIRE_A13.md
Rothermel_SFIRE_SB40.md
Balbi_2022_A13.md
Balbi_2022_SB40.md
Hamada_1_wudapt.md
Hamada_2_wudapt.md
```

If you don't find the content in the `data` directory, try `git lfs pull`.