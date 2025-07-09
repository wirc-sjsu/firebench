# ROS validation using Anderson 2015 dataset

## Contributors
- Aurélien Costes, [Wildfire Interdisciplinary Research Center](https://www.wildfirecenter.org/), San Jose State University, [aurelien.costes@sjsu.edu](mailto:aurelien.costes@sjsu.edu), [ORCID](https://orcid.org/0000-0003-4543-5107)


## Tags
![metric](../../../../_static/static_badges/metric-Accuracy-4477AA.svg)
![metric](../../../../_static/static_badges/Fire_Submodel-Rate_of_Spread-cf0c21.svg)

## Short description
The goal is to assess the accuracy of various rate of spread (ROS) models by comparing their computed ROS values against observed data from the Anderson 2015 dataset.

## Detailed description

It should contain:
- Scientific background and motiviation.
- Description of the modeled process or scenario.
- Relevance of the benchmark to real-world application or theoretical exploration.
- Diagrams/schematics of the benchmark are welcome.

## Data description
### Input
- The rate of spread observations are stored in the Table A1 from the [Anderson 2015 dataset](../../../../dataset_experiments/Anderson_2015_dataset.md).
- The data required to run the rate of spread model is also contained in the Table A1 from the [Anderson 2015 dataset](../../../../dataset_experiments/Anderson_2015_dataset.md)
- If some required inputs are not available in the provided dataset, it is allowed to add complementary data from the [Scott and Burgan 40 fuel models](../../../../fire_models_info/21_fuel_models/03_SB40.md). If the required data is not present in Scott and Burgan fuel model, it is allowed to use [Anderson](../../../../fire_models_info/21_fuel_models/02_Anderson.md) fuel model.

All of the data mentionned above is available within the package `FireBench`.

### Expected output data
- The workflow generates an output file in [hdf5 format](https://www.hdfgroup.org/solutions/hdf5/). The output file contains the expected and computed rate of spread.

## Initial conditions and configuration
- To add complementary data from Scott and Burgan fuel model, you need to select the category that represents at best the fuel from the Anderson 2015 dataset. To select which fuel category to use, employ the `firebench.tools.find_closest_fuel_class_by_properties` function to identify the nearest fuel category. In this benchmark, use `FUEL_LOAD_DRY_TOTAL` and `FUEL_HEIGHT`, and apply default weights to determine similarity.
- Apply the `Baughman_generalized_wind_reduction_factor_unsheltered` method to compute the wind reduction factor, considering that the input wind measurements are taken above the vegetation canopy. 
- 

## Metrics definition
- Definition of primary metrics (RMSE, bias, runtime, etc.) and derived metrics (burned area agreement, time to ignition, statistical comparison of plumes, etc.)
- Usage of existing `FireBench` post processing tools (or need for tools)
- Units and interpretation.

## Publication status
- Is this benchmark:
    - linked to a publication (in review, published, preprint)?
    - embargoed until a specific date?
- Citation to use (if applicable)

## Licensing and Use Terms
- License for any data or code provided
- Attribution and reuse policy

## Additional notes

## Optional: Benchmark difficulty
Optional indicator for difficulty to run this benchmark:
- low: fast/approximate, educational or conceptual
- medium: realistic inputs, moderate compute
- high: high fidelity, coupled models, research grade



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