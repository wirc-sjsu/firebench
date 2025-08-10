# Rate of spread model execution time
## Description of the benchmark
### Objectives

The goal is to estimate the execution time of the rate of spread model for specific fuel models.
It allows to estimate the overall performance of the rate of spread model implementation and assess discrepancies in performances for different fuel classes within a fuel model.

- **Performance evaluation** uses `time.perf_counter()` to measure execution time of the rate of spread function only (`firebench.ros_models.Rothermel_SFIRE.rothermel` for example).

- **Fuel model**: Uses `Anderson13` or `ScottandBurgan40` fuel models. 

- **Sampling method**: This workflow uses Sobol sequence sampling similarly to sensitivity workflow. It defines the fuel related properties from fuel model and sample the environmental variable space using Sobol sequence. This way, the performance of the model is estimated covering the whole validity domain of the rate of spread model for each fuel class.

### Output file

The workflow generates an output file in [HDF5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the rate of spread and the execution time.

## Benchmarks available

The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/02_01_execution_time_Anderson` for Anderson fuel model.

```{toctree}
:maxdepth: 1

efficiency_Balbi_2022.md
efficiency_Rothermel_SFIRE.md
efficiency_Hamada_1.md
efficiency_Hamada_2.md
```

If you don't find the content in the `data` directory, try `git lfs pull`.