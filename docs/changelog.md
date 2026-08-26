# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add standalone and period-based Caldor targets, including combinable building, perimeter, and
  weather flags discoverable through `firebench list`.
- Integrate the `firebench-adapter-common` source code into FireBench as `firebench.adapter_common`.
- Allow `firebench data get` to resolve benchmark registry short names such as `2021_Caldor`.
- Add verified PG&E station wind sensor-height fallback data.
- Add task-oriented documentation, complete CLI and API references, executable examples, and strict
  documentation CI.
- Document the weather-station QC GUI workflow, assertion semantics, JSON sessions, and exports,
  and include `wx-qc` in the CLI reference.
- Add an adaptive OpenStreetMap road basemap with an offline fallback to the weather-station QC map.
- Define the Caldor weather sensor-height, confidence-level, TSO, all-sources, and model-height
  contract.
- Add versioned, provenance-bearing weather sensor-height resources, semantic validation, a
  source-precedence resolver, and an explicit Synoptic proposal workflow.
- Add a deterministic Caldor weather release inventory bound to the observation-file hash,
  FireBench and benchmark-data versions, and trusted-height resource hashes.

### Changed

- Require `firebench run CASE TARGET MODEL_OUTPUT` and replace `-a` with benchmark targets such as `H013_P`.
- Use explicit TSO and all-sources station selection, canonical numeric sensor-height confidence,
  and shared selection logic for Caldor weather execution and CLI station counts.
- Preserve selected sensor-height provenance in standardized Synoptic variables and replace the
  temporary trusted-history side effect with reviewed proposal exports.
- Require prepared TSO model weather variables to record a sensor height matching the trusted
  observation within 0.01 m after unit conversion.
- Give TSO and all-sources weather KPIs explicit names, weight TSO at 1, and retain all sources as
  zero-weight diagnostics. This changes weather aggregation, so FireBench 0.10 weather and total
  scores are not directly comparable with FireBench 0.9 or earlier 0.10 development builds.
- Revise Caldor perimeter weights and normalization; FireBench 0.10 scores are not directly
  comparable with FireBench 0.9 scores.
- Expand benchmark discovery and target details in `firebench list` and generated reports.
- Improve score-card labels, group names, and colorblind-safe score visualization.
- Add observed-versus-modeled perimeter contours and KPI annotations to generated reports.

### Fixed

- Pin the Hatchling build backend below 1.32 so built distributions declare a metadata
  version that Twine and PyPI accept.
- Read the pre-0.10 combined `"<level> - <description>"` sensor-height confidence strings, so
  observational packages standardized before the canonical numeric attribute keep their verified
  stations in TSO instead of falling back to level 0. Only the exact historical values written by
  FireBench are recognized.
- Read the pre-0.10 decimal-string `sensor_height` attribute for observational weather data, which
  those releases wrote for exactly the provider-supplied heights that carry verified confidence.
  Model output must still record a numeric height.
- Report the period, and therefore the weather-station counts, for retained benchmark target
  aliases such as `WX1`, `WX_WH13`, and `FP_H13` in `firebench list` and generated reports.
- Render score cards and comparison score cards for runs where aggregation ignored a KPI or
  dropped a group with no eligible weighted KPI, reporting them as not scored instead of failing
  with a `KeyError`.
- Treat missing or malformed sensor-height confidence as level 0 with one contextual warning, and
  ignore empty weather station sets without adding a KPI value or aggregation contribution.
- Exclude and report only the affected TSO station when model sensor-height metadata is missing,
  dimensionally incompatible, or mismatched.
- Reject unsupported HDF5 standard versions and verify referenced polygon files by path, size, and
  SHA-256 before benchmarks run.
- Record verified observational and model referenced-file metadata in benchmark result provenance.
- Bundle runtime datasets in installed distributions and resolve default data through package
  resources instead of repository-relative paths.
- Avoid loading scientific, geospatial, plotting, and PDF dependencies when displaying CLI help.
- Resolve external polygon paths relative to their HDF5 file during benchmark requirement checks.
- Preserve established Caldor weather KPI identifiers and canonicalize combined target flags.
- Support UTC and extended ISO 8601 `date_time` values when standardizing Synoptic observations.
- Correct weather-station QC handling for contiguous frozen/dropout runs, invalid time axes, and
  longest and cumulative outage metrics.
- Apply weather-station QC issue filters consistently and prevent conflicting skipped and greenlit
  station decisions.
- Make weather-station QC exports atomic and safely serialized, and apply skipped stations and
  record removals to cleaned H5 copies.
- Replace weather-station QC pickle sessions with validated, atomic, versioned JSON sessions that
  recompute station statistics from the referenced H5 when restored.
- Support Contextily 1.6 when loading wx-QC road tiles and show complete basemap errors in a dialog
  and terminal log.

## [0.9.0] - 2026 / 05 / 18
### Added
- Add the `firebench` command line interface for benchmark discovery, data download, and benchmark execution:
  - `firebench list` lists available benchmark cases.
  - `firebench data versions` lists available data versions for a benchmark case.
  - `firebench data get` downloads benchmark data.
  - `firebench run` runs a benchmark case against a model output in FireBench standard HDF5 format.
- Add regression tests covering import, CLI, benchmark discovery, and deprecated environment-variable behavior without requiring local environment configuration.
- Added official PyPI/TestPyPI packaging and distribution support for firebench.
- Python 3.14 support

### Benchmarks
- Add the FB001 2021 Caldor Fire benchmark to the benchmark registry.
- Add Caldor benchmark data version metadata for CLI downloads.

### Documentation
- Add a CLI tutorial showing how to download the Caldor Fire case and run it.
- Update setup instructions to describe default FireBench data and local database paths instead of requiring environment variables.

### Changed
- Remove the mandatory dependency on `FIREBENCH_DATA_PATH` and `FIREBENCH_LOCAL_DB` for import, installation, CLI usage, tests, and benchmark discovery.
- Use default paths when legacy environment variables are not set:
  - FireBench data is resolved from the package or repository `data` directory.
  - The local database defaults to `~/.firebench/local_db`.
- Add explicit `data_path` and `local_db_path` arguments where local paths are needed.
- Stop using Git LFS for repository-managed files.

### Deprecated
- Deprecate `FIREBENCH_DATA_PATH`. Use the FireBench data configuration or pass `data_path` explicitly instead.
- Deprecate `FIREBENCH_LOCAL_DB`. Use the FireBench local database configuration or pass `local_db_path` explicitly instead.
- Legacy environment-variable support remains available temporarily and now emits `DeprecationWarning`.

## [0.8.1] - 2026 / 03 / 15
### Fixes
- bias metric: computes x1 mean only where x2 is not Nan

### Miscellaneous
- FireBench Standard file format 1.0
- litting
- add tests for metrics
- fix security warnings

## [0.8.0] - 2026 / 01 / 14
### Added
- 2021 Caldor case FB001 documentation and benchmarks (See Zenodo FireBench for release)
- package `metrics`: contains kpi functions, metrics functions for perimeters, 1D datasets, confusion matrix.
- package `standardize`: contains standardization functions for landfire, mtbs, ravg, synoptic, geotiff.
- package `signing`: contains functions for certification (hardware encryption) and verification of certificates (`verify_certificate_in_dict`, `verify_certificates_in_h5`). Verification functions require `gpg` (not needed for benchmarking functions).
- Public Key for certificates verification

### Documentation
- FireBench Standard file format
- Add Key Performance Indicators, Metrics, Score and Normalization information

## [0.7.0] - 2025 / 08 / 09
### Added
- `anderson_2015_stats`: Plot statistics from the Anderson 2015 dataset.
- `array_to_geopolygons`: Convert an array field into geospatial polygons at a given iso-value, preserving holes.
- `auto_bins`: Automatically generate histogram bin edges for plotting, based on data range.
- `CS505_cl`: Compute the half-width of the confidence interval for measurement error of the Campbell Scientific CS505 Fuel Moisture Sensor.
- `CS506_cl`: Compute the half-width of the confidence interval for measurement error of the Campbell Scientific CS506 Fuel Moisture Sensor.
- `current_datetime_iso8601`: Get the current datetime as an ISO 8601 formatted string (YYYY-MM-DDTHH:MM[:SS]±HH:MM).
- `datetime_to_iso8601`: Convert a given datetime to an ISO 8601 formatted string (YYYY-MM-DDTHH:MM[:SS]±HH:MM).
- `jaccard_binary`: Compute the IoU, i.e. Jaccard Index, between two fire perimeters described as 2D binary masks.
- `jaccard_polygon`: Compute the Intersection over Union (IoU), i.e. Jaccard Index, between two fire perimeters described as geospatial polygons.
- `sorensen_dice_binary`: Compute the Sorensen-Dice index between two fire perimeters described as 2D binary masks.
- `sorensen_dice_polygon`: Compute the Sorensen-Dice index between two fire perimeters described as geospatial polygons.
- `read_quantity_from_fb_dataset`: Read a dataset from an HDF5 file, group, or dataset node and return it as a Pint Quantity according to the FireBench I/O standard.
- `rmse`: Compute the Root Mean Square Error (RMSE) between two arrays, ignoring NaNs.
- `nmse_range`: Compute the Normalized Mean Square Error (NMSE) between two arrays, using the range of the reference signal as normalization.
- `nmse_power`: Compute the Normalized Mean Square Error (NMSE) between two arrays, using the product of their mean values as normalization.

### Documentation
- Updated developer documentation
- Refactoring of Benchmarks page. Benchmarks are now sorted by model context instead of metric context.
- Tags have a colorful badge.
- Add documentation for FireBench standard file format version 0.1.

### Benchmarks
- Improve Anderson 2015 Validation benchmark document.
- Refactoring of `ROS validation using Anderson 2015 dataset` to use the FireBench I/O standard.

### Miscellaneous
- Support Python 3.13
- Support numpy version >= 2.0
- Dependency to matplotlib > 3.8

### Fix
- Comma missing in two row of Anderson 2015 dataset.

## [0.6.1] - 2025 / 05 / 20
### Added
- Add citation metadata in CITATION.cff file

## [0.6.0] - 2025 / 05 / 08
### Documentation
- Add benchmark proposal and run templates
- Add Call for Benchmarks section in the main page

## [0.5.0] - 2025 / 04 / 10
### Documentation
- Remove legacy GitHub Pages & Jekyll documentation.
- Move the documentation to ReadTheDocs.
- Add API documentation using Sphinx

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
