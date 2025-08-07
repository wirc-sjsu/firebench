# 4. Standard FireBench file format

- **Version**: 0.1
- **Status**: Draft
- **Last update**: 2025-08-07

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
- Contains time series data from specific points in space called probes, for example, weather stations (RAWS) or local sensors.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate are placed in the same data group (*e.g.*, a sensor group). Multiple data groups that share the same spatial location are further grouped together in a location group (*e.g.*, a weather station).
- Each group containing data should be named after the probe location or ID (e.g. probe_01).
- Each dataset (data_k) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`.
- Each time coordinate dataset must follow the global time convention (see Time format).
- Location of the probes must be defined as attributes following a spatial description convention.
- If geographic coordinates are used, a CRS must be included.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - data_k -> ($N_t$)
```
/                                    (root)
├── probes/                          (point-based time series)
│    ├── weather_station_1           (group all sensors from weather station 1)
│    │    ├── sensor_1               (group all data from sensor_1)
│    │    │    ├── time              (time dataset)
│    │    │    ├── temperature       (temperature data from sensor_1 dataset)
│    │    ├── sensor_2               (group all data from sensor_2)
│    │    │    ├── time              (time dataset)
│    │    │    ├── wind_speed        (wind speed from sensor_2 dataset)
│    │    │    ├── wind_direction    (wind direction from sensor_2 dataset)
│    ├── sensor_3                    (group all data from sensor_3)
│    │    ├── time                   (time dataset)
│    │    ├── wind_u                 (U wind data from sensor_3 dataset)
│    │    ├── wind_v                 (V wind data from sensor_3 dataset)
│    │    ├── wind_w                 (W wind data from sensor_3 dataset)
```

### 1D raster
- Contains time series data from a dataset associated with one-dimensional spatial data.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group.
- The spatial coordinate dataset (z in the example) must follow a spatial description convention for a one-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - z -> ($N_z$) or ($N_t$, $N_z$) for time varying z coordinate
    - data_k -> ($N_t$, $N_z$)

```
/                               (root)
├── 1D_raster/                  (1D gridded spatial data + time)
│    ├── wind_profiler_1        (group all sensors from weather station 1)
│    │    ├── time              (time dataset)
│    │    ├── z                 (vertical spatial coordinate for profile)
│    │    ├── wind_speed        (wind profiler data)
│    │    ├── wind_direction    (wind profiler data)
```