# ROS validation using Anderson 2015 dataset
## Description of the benchmark
### Objectives

The goal is to assess the accuracy of various rate of spread (ROS) models by comparing their computed ROS values against observed data from the Anderson 2015 dataset.

- **Input Dataset**: Utilize Table A1 from the Anderson 2015 dataset, located at `firebench/data/ros_model_validation/Anderson_2015`. 

- **Complementary Fuel Data**: Incorporate fuel data from the Scott and Burgan 40 fuel models.

- **Handling Missing Fuel Data**: If specific fuel data is unavailable, employ the `firebench.tools.find_closest_fuel_class_by_properties` function to identify the nearest fuel category. This function uses total fuel load and fuel height, applying default weights to determine similarity.

- **Wind Reduction Factor Calculation**: Apply the `Baughman_generalized_wind_reduction_factor_unsheltered` method to compute the wind reduction factor, considering that the input wind measurements are taken above the vegetation canopy. 

### Output file

The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/).
The output file contains the expected and computed rate of spread.

## Benchmarks available

The worklow template can be found at `firebench/workflow/rate_of_spread_models_analysis/01_01_Anderson_2015_validation`.

```{toctree}
:maxdepth: 1

report_Rothermel_SFIRE.md
report_balbi_2022.md
```

If you don't find the content in the `data` directory, try `git lfs pull`.