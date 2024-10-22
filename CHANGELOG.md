# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2024 / -- / --

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