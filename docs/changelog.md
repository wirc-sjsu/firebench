# 9. Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2025 / 04 / 03
### Added 
- Urban canyon vertical wind interpolation Masson_canyon
- Fuel load per element size in Anderson Fuel Model (1h, 10h, 100h, live)
- Implementation of the `Santoni_2011` rate of spread model

## [0.3.2] - 2024 / 12 / 16
### Added 
- import_scott_burgan_40_fuel_model wrapper function to simplify import of Scott and Burgan fuel model
- import_anderson_13_fuel_model wrapper function to simplify import of Anderson fuel model
- import_wudapt_fuel_model wrapper function to simplify import of WUDAPT urban fuel model
- Sensitivity workflow scripts for rate of spread models using WUDAPT urban fuel model.

### Fixed
- Fuel moisture of extinction unit is `dimensionless` instead of `percent` in Anderson13.json

### Documentation
- Add benchmark results for:
  - Rate of spread model sensitivity using WUDAPT urban fuel model:
    - Hamada 1
    - Hamada 2
  - Rate of spread model sensitivity using Scott and Burgan 40 fuel model:
    - Rothermel_SFIRE
    - Balbi 2022
  - Rate of spread model execution time:
    - Hamada 1
    - Hamada 2
- Update benchmark results for:
  - Rate of spread model sensitivity using Anderson 13 fuel model:
    - Rothermel_SFIRE

## [0.3.1] - 2024 / 12 / 03
### Added
- Efficiency workflow scripts for rate of spread model performance evaluation using Anderson fuel model.

### Documentation
- Add benchmark results for:
  - Rate of spread model execution time:
    - Rothermel_SFIRE
    - Balbi 2022

## [0.3.0] - 2024 / 11 / 24
### Added
- `ScottandBurgan40` fuel model
- Scott and Burgan utility function
  - `add_scott_and_burgan_total_fuel_load`: aggregate the fuel load per element size to the total fuel load
  - `add_scott_and_burgan_total_savr`: calculate the total surface area to volume ratio as weighted average of the savr of the fuel elements described in SB40.
- Fuel model utility functions:
  - `find_closest_fuel_class_by_properties`: retrieve the fuel class having the closest properties to a target set of properties.
- Wind reduction factor functions
  - `use_wind_reduction_factor` from value, fuel model dictionary, or list
  - `Baughman_20ft_wind_reduction_factor_unsheltered` from Baughman, R. G., & Albini, F. A. (1980) 
  - `Baughman_generalized_wind_reduction_factor_unsheltered`: Generalized wind reduction factor derived from Albini (1979)
- Add hash of file when copying to record
- Modify the date in report automatically with copying to record

### Changed
- External management of wind reduction factor (no more present in rate of spread models)
- Management of units for rate of spread model simplified using `compute_ros_with_units`
- Record management to save workflow

### Documentation
- Add Fire Models information and Dataset and fire experiment information sections
- Add pages for:
  - Rothermel_SFIRE
  - Balbi_2022_fixed_SFIRE
  - Hamada 1
  - Hamada 2
  - Anderson13
  - ScottandBurgan40
  - WUDAPT_urban
  - Wind reduction factor methods
- Add benchmark results for:
  - Validation Anderson 2015:
    - Rotherme_SFIRE
    - Balbi 2022
  - Sensitivity to environmental variable for Anderson 13 fuel model:
    - Rotherme_SFIRE
    - Balbi 2022

## [0.2.0] - 2024 / 10 / 17
### Added
- Hamada_1 urban rate of spread
- Hamada_2 urban rate of spread
- Balbi 2022 vegetation rate of spread model
- WUDAPT_urban fuel database

### Changed
- License APACHE 2.0 is used instead of MIT

### Documentation
- Add dependencies, developers guide, and license pages
- minor fixes to fuel models tutorial

## [0.1.0] - 2024 / 07 / 09
### Added
- Documentation for the rate of spread sensitivity workflow
- Add changelog to documentation
- Archive for the rate of spread sensitivity workflow with the `Rothermel_SFIRE` model
- Change output filename for the rate of spread sensitivity workflow

### Fixes
- unit issues in the rate of spread sensitivity workflow

## [0.0.1] - 2024 / 07 / 08
### Added
- Initial release of the FireBench library.
- Implementation of the `Rothermel_SFIRE` rate of spread model.
- Fuel model `Anderson13` corresponding to Anderson 13 fuel categories
- Basic tools and utilities for fire modeling.
- Sensitivity analysis workflow for environmental variables.
  - Workflow scripts `03_01_sensitivity_env_var` for performing sensitivity analysis.
- Integration with GitHub Actions for continuous integration.
- Documentation setup using GitHub Pages.
- Initial implementation of unit tests using `pytest`.

### Features
- Support for default and custom fuel models.
- Functionality for reading and validating fuel model data.
- Utilities for converting units and checking input data quality.
- Calculation of Sobol sensitivity indices for rate of spread models.
- Saving workflow results and data to HDF5 files.
- Plotting of Sobol sensitivity indices for different fuel classes.

### Documentation
- Overview of the FireBench project.
- Tutorials for using default and custom fuel models.
- How-to guides for sensitivity analysis workflows.
- Setup instructions for the development environment.
- Contribution guidelines and code of conduct.