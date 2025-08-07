# 4. Standard FireBench file format

- **Version**: 0.1
- **Status**: Draft
- **Last update**: 2025-08-06

This document defines the I/O format standard for benchmark datasets used in the `FireBench` benchmarking framework. The standard is based on the [HDF5 file format](https://www.hdfgroup.org/solutions/hdf5/) (`.h5`) and describes the structure, expected groups, metadata, and conventions.

## File structure

Each .h5 file must adhere to the following structure:

```
/                   (root)
├── probes/         (point-based time series)
├── 1D_raster/      (1D gridded spatial data + time)
├── 2D_raster/      (2D gridded spatial data + time)
├── 3D_raster/      (3D gridded spatial data + time)
├── polygons/       (geopolygones)
├── fuel_models/    (fuel model classification or parameters)
├── metadata/       (high-level metadata and descriptions)
├── miscellaneous/  (non-standard or project-specific data)
```

All groups are optional unless otherwise specified in a benchmark case specification.

## Time format

### Absolute time variable

All datetime variables must follow the **ISO 8601** standard:
```
YYYY-MM-DDTHH:MM:SS±HH:MM
```
Examples:
- **2025-07-30T15:45:00+00:00** which correspond to July 30th 2025 at 15h45:00s UTC.
- **1995-03-27T12:00+01:00** is acceptable is seconds are irrelevant.

### Relative time variable

If time is expressed relative to a reference point (*e.g.* "time since ignition"), the dataset must include an attribute:
```
time_origin = "YYYY-MM-DDTHH:MM:SS±HH:MM"
```
This attribute must follow the ISO 8601 format.

## Spatial Information Convention

Spatial position must be defined using one and only one of the following representations. Each representation comes with a required set of datasets or attributes. The group or dataset containing the position data must follow the conventions below.

### Geographic coordinates

Use when position is expressed in geographic coordinates (Latitude, Longitude, Altitude).

**Required fields**
- `position_lat`: latitude
- `position_lon`: longitude
- `position_alt`: altitude (ASL)

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Absolute Cartesian Coordinates

Use when position is expressed in absolute Cartesian coordinates, *e.g.*, for idealized or synthetic cases.

**Required fields**
- `position_x`: x coordinate
- `position_y`: y coordinate
- `position_z`: z coordinate

### Relative Cartesian Coordinates with Geographic Origin

Use when position is defined relative to a known geographic origin.

**Required fields**
- `position_origin_lat`: latitude of origin
- `position_origin_lon`: longitude of origin
- `position_origin_alt`: altitude of origin
- `position_rel_x`: x coordinate relative to origin
- `position_rel_y`: y coordinate relative to origin
- `position_rel_z`: z coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Cross-Section with geographic reference point

Use when data is aligned along a 2D cross-section that does not follow cardinal (lat/lon/alt) directions.

**Required fields**
- `position_origin_lat`: latitude of origin
- `position_origin_lon`: longitude of origin
- `position_origin_alt`: altitude of origin
- `position_plane_vector_1`: components of the first vector of the cross section plane (`x_cs` direction). Components are given as (x, y, z).
- `position_plane_vector_2`: components of the second vector of the cross section plane (`y_cs` direction). Components are given as (x, y, z). The second vector must not be colinear to the first vector.
- `position_rel_x_cs`: x_cs coordinate relative to origin
- `position_rel_y_cs`: y_cs coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 


### Cross-Section with cartesian reference point

Use when data is aligned along a 2D cross-section that does not follow cardinal (x/y/z) directions.

**Required fields**
- `position_origin_x`: x coordinate of origin
- `position_origin_y`: y coordinate of origin
- `position_origin_z`: z coordinate of origin
- `position_plane_vector_1`: components of the first vector of the cross section plane (`x_cs` direction). Components are given as (x, y, z).
- `position_plane_vector_2`: components of the second vector of the cross section plane (`y_cs` direction). Components are given as (x, y, z). The second vector must not be colinear to the first vector.
- `position_rel_x_cs`: x_cs coordinate relative to origin
- `position_rel_y_cs`: y_cs coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Spherical coordinates

Use when describing direction and distance from a known observation origin (*e.g.*, LIDAR scan origin).

**Required fields**
- `position_origin_lat`: latitude of origin
- `position_origin_lon`: longitude of origin
- `position_origin_alt`: altitude of origin
- `position_r`: radial distance from the origin
- `position_theta`: polar angle (from z-axis)
- `position_phi`: azimuthal angle (from x-axis)

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Units
No units is implicitely assumed. 
Units must be specified within the group containing the spacial information (attributes and/or datasets). 
Units are described as string that are compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).
Units can be specified per field by adding the suffix `_units` to the field (*e.g.* `position_lat_units` will attach a unit to the attribute/dataset `position_lat`). Units can be specified by group of fields by adding the suffix `_units` to the group of fields name (*e.g.* `position_units` will attach a unit to the attribute/dataset `position_x`, `position_y` and `position_z`). 
If a field has its own `_units` attribute, that overrides any group‑wide unit

The possible units fields are the following:
- `position_alt_units`
- `position_lat_units`
- `position_lon_units`
- `position_origin_x_units`
- `position_origin_y_units`
- `position_origin_z_units`
- `position_origin_lat_units`
- `position_origin_lon_units`
- `position_origin_alt_units`
- `position_origin_units`
- `position_phi_units`
- `position_r_units`
- `position_rel_x_units`
- `position_rel_y_units`
- `position_rel_z_units`
- `position_rel_units`
- `position_theta_units`
- `position_units`
- `position_x_units`
- `position_y_units`
- `position_z_units`


## File Attributes

The HDF5 file must contain the following root-level attributes:

Attributs | Type | Description
:--------- | :----: | :-----------
`FireBench_io_version` | str | Version of the I/O standard used
`created_on` | str | ISO 8601 date-time of file creation
`created_by` | str | Creator identifier (name, email, etc)


Suggested additional attributes:
Attributs | Type | Description
:--------- | :----: | :-----------
`benchmark_id` | str | Unique ID of the benchmark scenario
`model_name` | str | Name of the model producing the data
`model_version` | str | Version of the model
`description` | str | Short description of the dataset

## Group definition

### Probes
- Contains time series data from specific points in space called probes, for example weather stations (RAWS) or local sensors.
- Each probe dataset is organized in a group containing the time series of all sensors that are at the same location.
- Each dataset should be named after the probe location or ID (e.g. probe_01)
- Time dimension must be clearly identified and follow the time format standard.
- Location of the probes must be defined as attributes following a spacial description convention.

```
/                           (root)
├── probes/                 (point-based time series)
│    ├── weather_station_1  (group all sensors from weather station 1)
│    │    ├── sensor_1      (group all data from sensor_1)
│    │    │    ├── time     (time dataset)
│    │    │    ├── data_1   (data from sensor_1 dataset)
│    │    ├── sensor_2      (group all data from sensor_2)
│    │    │    ├── time     (time dataset)
│    │    │    ├── data_2   (data from sensor_2 dataset)
│    │    │    ├── data_3   (data from sensor_2 dataset)
│    ├── sensor_3           (group all data from sensor_3)
│    │    ├── time          (time dataset)
│    │    ├── data_4        (data from sensor_3 dataset)
│    │    ├── data_5        (data from sensor_3 dataset)
```
