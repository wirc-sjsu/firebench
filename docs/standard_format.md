# 4. Standard FireBench file format

- **Version**: 1.0
- **Status**: PreRelease
- **Last update**: 2026-01-02

This document defines the I/O format standard for benchmark datasets used in the `FireBench` benchmarking framework. The standard is based on the [HDF5 file format](https://www.hdfgroup.org/solutions/hdf5/) (`.h5`) and describes the structure, expected groups, metadata, and conventions.

## File structure

Each .h5 file must adhere to the following structure:

```
/                   (root)
├── points/         (0D datasets)
├── time_series/    (point-based time series)
├── spatial_1d/     (1D gridded spatial data + time)
├── spatial_2d/     (2D gridded spatial data + time)
├── spatial_3d/     (3D gridded spatial data + time)
├── unstructured/   (unstructured spatial data + time)
├── polygons/       (geopolygons)
├── fuel_models/    (fuel model classification or parameters)
├── miscellaneous/  (non-standard or project-specific data)
```

All groups are optional unless otherwise specified in a benchmark case specification.
The `/metadata` group is not defined in this version of the standard, as all metadata should normally be stored as attributes of the file, existing groups, or datasets. If additional metadata needs to be stored as dedicated datasets, the `/metadata` group is reserved for this purpose. Its structure and required fields may evolve in future versions based on user feedback and practical experience.

## File Attributes

The HDF5 file must contain the following root-level attributes:

Attributes | Type | Description
:--------- | :----: | :-----------
`FireBench_io_version` | str | Version of the I/O standard used
`created_on` | str | ISO 8601 date-time of file creation
`created_by` | str | Creator identifier (name, affiliation). `created_by` is a `;`-separated list; whitespace around entries should be ignored; entries must not contain `;`.


Suggested additional attributes:
Attributes | Type | Description
:--------- | :----: | :-----------
`benchmark_id` | str | Unique ID of the benchmark scenario
`model_name` | str | Name of the model producing the data
`model_version` | str | Version of the model
`description` | str | Short description of the dataset
`project_name` | str | Short description of the project
`license` | str | License or terms of use (or specified at group/dataset level). SPDX identifier when possible (*e.g.*, CC-BY-4.0), otherwise a URL.
`data_source` | str | Source of the data if applicable.

No `/metadata` group is required; prefer file-level attributes. The `/metadata` namespace is reserved for future versions.

## Compression

Compression of datasets is done using Zstandard. It is included in the python library `hdf5plugin` so no external dependency is needed. Compression level can go from 1 (low compression, faster) to 22 (highest compression, slower). Zstandard has been chosen for its better I/O and better compression performance than more classic gzip compression.
As most benchmarking processes are not time sensitive, the recommended compression level is **20**.

## Units
**No units is implicitly assumed.** 
Units are described as strings that are compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

Units must be specified:
1. For attributes, by adding a new attribute with the suffix `_units` added to the associated attribute name.
For example, the attribute `position_lat` in a group will have an associated attribute `position_lat_units` containing `"degree"`. Only numeric attributes representing physical quantities should use the `*_units` suffix. Do not add `_units` for identifiers, names, CRS, hashes, *etc.*.

2. For datasets, using an attribute `units`. For example, a dataset `air_temperature` will have an attribute `units` containing `"K"`.

## Time format

### Absolute time variable

All datetime variables must follow the **ISO 8601** standard:
```
YYYY-MM-DDTHH:MM:SS±HH:MM
```
Examples:
- **2025-07-30T15:45:00+00:00** which corresponds to July 30, 2025 at 15h 45min 00s UTC.
- **1995-03-27T12:00+01:00** is acceptable if seconds are irrelevant.

Using this encoding, the dataset `time` is an array of ISO 8601 strings (UTC offset included).

### Relative time variable

If time is expressed relative to a reference point (*e.g.* "time since ignition"), the dataset/group **must** include the attributes:
```
time_origin = "YYYY-MM-DDTHH:MM:SS±HH:MM"
time_units = "min"
```
The attribute `time_origin` must follow the ISO 8601 format.
The attribute `time_units` must be compliant with [Pint](https://pint.readthedocs.io/en/stable/) standard. The default unit registry (*i.e.* the list of acceptable units) can be found [here](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

Using this encoding, the dataset `time` is numeric (float/int) with required attributes `time_origin` (ISO) and `time_units` (Pint).

## Spatial Information Convention

Spatial position must be defined using one and only one of the following representations. Each representation comes with a required set of datasets or attributes. The group or dataset containing the position data must follow the conventions below.
For geographic grids, coordinates should be stored as *position_lat/position_lon* (and optionally *position_alt*). For projected grids, use *position_x/position_y* with a CRS (if applicable).
Position fields may be stored as datasets or attributes. If varying across samples/time, they must be datasets; if constant for the group, they should be attributes.

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
- `position_x`: x coordinate relative to origin
- `position_y`: y coordinate relative to origin
- `position_z`: z coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Cross-Section with geographic reference point

Use when data is aligned along a 2D cross-section that does not follow cardinal (lat/lon/alt) directions.
Vectors are unitless direction vectors in the same coordinate basis as the origin CRS.
They do not need to be normalized, but must be non-colinear.

**Required fields**
- `position_origin_lat`: latitude of origin
- `position_origin_lon`: longitude of origin
- `position_origin_alt`: altitude of origin
- `position_plane_vector_1`: components of the first vector of the cross section plane (`x_cs` direction). Components are given as (x, y, z).
- `position_plane_vector_2`: components of the second vector of the cross section plane (`y_cs` direction). Components are given as (x, y, z).
- `position_x_cs`: x_cs coordinate relative to origin
- `position_y_cs`: y_cs coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 


### Cross-Section with cartesian reference point

Use when data is aligned along a 2D cross-section that does not follow cardinal (x/y/z) directions.
Vectors are unitless direction vectors in the same coordinate basis as the origin CRS.
They do not need to be normalized, but must be non-colinear.

**Required fields**
- `position_origin_x`: x coordinate of origin
- `position_origin_y`: y coordinate of origin
- `position_origin_z`: z coordinate of origin
- `position_plane_vector_1`: components of the first vector of the cross section plane (`x_cs` direction). Components are given as (x, y, z).
- `position_plane_vector_2`: components of the second vector of the cross section plane (`y_cs` direction). Components are given as (x, y, z). The second vector must not be colinear to the first vector.
- `position_x_cs`: x_cs coordinate relative to origin
- `position_y_cs`: y_cs coordinate relative to origin

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

### Spherical coordinates

Use when describing direction and distance from a known observation origin (*e.g.*, LIDAR scan origin).

**Required fields**
- `position_origin_lat`: latitude of origin
- `position_origin_lon`: longitude of origin
- `position_origin_alt`: altitude of origin
- `position_r`: radial distance from the origin
- `position_theta`: polar angle from z-axis
- `position_phi`: azimuthal angle from x-axis

Units attributes must be set for each field.

**Coordinate Reference System (CRS)**
- The group containing these fields must have an attribute `crs` identifying the CRS (*e.g.*, "EPSG:4326") 

## Recommended array dimension
- If a dataset depends on time, time is the first dimension.
- For gridded data, recommended order:
    - 1D: (time, z) or (time, x)
    - 2D: (time, y, x) or (time, z, x) for cross-sections
    - 3D: (time, z, y, x)

## Group definition

### Points
- Contains point-based datasets (single points or collections of points) 
- Datasets must be grouped at the lowest common level that minimizes data duplication.
- Each group containing data should be named after the probe location or ID (e.g. probe_01).
- Each dataset must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- In the following example, the array dimensions can be:
    - data (position_lat, position_lon, building_damage) -> ($N$)
```
/                                    (root)
├── points/                          (0D datasets)
│    ├── building_damage             (group containing the main dataset)
│    │    ├── position_lat           (latitude of data point)
│    │    ├── position_lon           (longitude of data point)
│    │    ├── building_damage         (building status index)
```

### Time Series
- Contains time series data from specific points in space, for example, weather stations (RAWS) or local sensors.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate are placed in the same data group (*e.g.*, a sensor group). Multiple data groups that share the same spatial location are further grouped together in a location group (*e.g.*, a weather station).
- Each group containing data should be named after the probe location or ID (e.g. probe_01).
- Each dataset (temperature, wind_speed, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Identification information for weather stations (ID, MNET ID, provider, name) should be included as attributes if the information is accessible.
- Sensor height must be included at dataset level (*e.g.* temperature, wind_speed) as an attribute `sensor_height`, along with `sensor_height_units` specifying the unit of the sensor height. The source of the sensor height information must be included in an attribute `sensor_height_source`.
- Location of the dataset must be defined as attributes following a spatial description convention.
- If geographic coordinates are used, a CRS must be included.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - data (temperature, wind_speed, *etc.*) -> ($N_t$)
```
/                                    (root)
├── time_series/                     (point-based time series)
│    ├── station_1                   (group all sensors from weather station 1)
│    │    ├── time                   (time dataset)
│    │    ├── temperature            (temperature data)
│    │    ├── wind_speed             (wind speed)
│    │    ├── wind_direction         (wind direction)
│    ├── sensor_3                    (group all data from sensor_3)
│    │    ├── time                   (time dataset)
│    │    ├── wind_u                 (U wind data from sensor_3)
│    │    ├── wind_v                 (V wind data from sensor_3)
│    │    ├── wind_w                 (W wind data from sensor_3)
```

### Spatial 1D
- Contains time series data from a dataset associated with one-dimensional spatial data.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group.
- The spatial coordinate dataset (*z* in the example) must follow a spatial description convention for a one-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Each dataset (wind_speed, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- The coordinate arrays may be 1D, or time-dependent 1D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - z -> ($N_z$) or ($N_t$, $N_z$) for time varying z coordinate
    - data (wind_speed, wind_direction, *etc.*) -> ($N_t$, $N_z$)
- Coordinate datasets must be either static or time-dependent, and must be broadcast-compatible with dependent variables

```
/                               (root)
├── spatial_1d/                 (1D gridded spatial data + time)
│    ├── wind_profiler_1        (group all data from the wind profiler)
│    │    ├── time              (time dataset)
│    │    ├── position_z        (vertical spatial coordinate for profile)
│    │    ├── wind_speed        (wind profiler data)
│    │    ├── wind_direction    (wind profiler data)
```

### Spatial 2D
- Contains time series data from a dataset associated with two-dimensional spatial data. It means any two spatial dimensions, whether horizontal, vertical, or arbitrary section, and that coordinate naming (x, y, z) will follow the Spatial Information Convention.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group. For example, `fire_arrival_time` and `rate_of_spread` share the same x, y, and time coordinates, so they are stored in the same group.
- The spatial coordinate dataset (*x*, *y* in the example) must follow a spatial description convention for a two-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Each dataset (rate_of_spread, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- The coordinate arrays may be 1D, 2D, or time-dependent 2D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - x of wrfoutput_1 group -> ($N_x$) or ($N_y$, $N_x$) or ($N_t$, $N_y$, $N_x$) or ($N_t$, $N_x$)
    - y -> ($N_y$) or ($N_y$, $N_x$) or ($N_t$, $N_y$, $N_x$) or ($N_t$, $N_y$)
    - data of wrfoutput_1 group(fire_arrival_time, *etc.*) -> ($N_t$, $N_y$, $N_x$)
    - x of wrfoutput_cs_1 group -> ($N_x$) or ($N_z$, $N_x$) or ($N_t$, $N_z$, $N_x$) or ($N_t$, $N_x$)
    - z -> ($N_z$) or ($N_z$, $N_x$) or ($N_t$, $N_z$, $N_x$) or ($N_t$, $N_z$)
    - data of wrfoutput_cs_1 group(wind_u, *etc.*) -> ($N_t$, $N_z$, $N_x$)
- Coordinate datasets must be either static or time-dependent, and must be broadcast-compatible with dependent variables

```
/                                  (root)
├── spatial_2d/                    (2D gridded spatial data + time)
│    ├── wrfoutput_1               (group outputs from a WRF-SFIRE simulation for surface x-y plane)
│    │    ├── time                 (time dataset)
│    │    ├── position_x           (x spatial coordinate)
│    │    ├── position_y           (y spatial coordinate)
│    │    ├── fire_arrival_time    (fire arrival time output from WRF-SFIRE simulation)
│    │    ├── rate_of_spread       (rate of spread output from WRF-SFIRE simulation)
│    ├── wrfoutput_cs_1            (group outputs from a WRF-SFIRE simulation for a x-z cross section)
│    │    ├── time                 (time dataset)
│    │    ├── position_x           (x spatial coordinate)
│    │    ├── position_z           (z spatial coordinate)
│    │    ├── wind_u               (zonal wind output from WRF-SFIRE simulation)
│    │    ├── wind_w               (vertical wind output from WRF-SFIRE simulation)
```

### Spatial 3D
- Contains time series data from a dataset associated with three-dimensional spatial data.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group. For example, `wind_u` and `wind_v` share the same x, y, z, and time coordinates, so they are stored in the same group.
- The spatial coordinate dataset (x, y, z in the example) must follow a spatial description convention for a three-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Each dataset (temperature, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- The coordinate arrays may be 1D, 3D, or time-dependent 3D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - x -> ($N_x$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_x$)
    - y -> ($N_y$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_y$)
    - z -> ($N_z$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$)
    - data (temperature, wind_u, *etc.*) -> ($N_t$, $N_z$, $N_y$, $N_x$)
- Coordinate datasets must be either static or time-dependent, and must be broadcast-compatible with dependent variables

```
/                            (root)
├── spatial_3d/              (3D gridded spatial data + time)
│    ├── wrfoutput_1         (group outputs from a WRF-SFIRE simulation)
│    │    ├── time           (time dataset)
│    │    ├── position_x     (x spatial coordinate)
│    │    ├── position_y     (y spatial coordinate)
│    │    ├── position_z     (z spatial coordinate)
│    │    ├── wind_u         (U wind output from WRF-SFIRE simulation)
│    │    ├── wind_v         (V wind output from WRF-SFIRE simulation)
│    │    ├── wind_w         (W wind output from WRF-SFIRE simulation)
│    │    ├── temperature    (temperature output from WRF-SFIRE simulation)
```

### polygons
- As HDF5 is not a file format that is practical to use for vectorized dataset, the polygons are stored using the `KML` file format.
- The HDF5 file contains the necessary metadata to point to the KML file containing the polygons dataset in a group registered in the `/polygons` main group.
- Each group contains a reference to one and only one KML file.
- Each KML reference corresponds to a single logical polygon layer (*e.g.*, a perimeter at a timestamp).
- The mandatory attributes are the following
    - `rel_path` (str): relative path to the KML file (relative to the HDF5 file directory)
    - `file_size_bytes` (int): KML file size in bytes (*e.g.*, using `os.path.getsize`)
    - `sha256` (str): hash of the KML file using `firebench.tools.calculate_sha256`
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.

In the following example, we have a standard file `dataset.h5`, containing one polygons dataset. We also have a directory `kml` containing one KML file `polygons_2022_07_14.kml`.
In the HDF5 file, the group `/polygons/fire_perimeter_2022_07_14` has the attribute `rel_path="kml/polygons_2022_07_14.kml"`. 
```
dataset.h5
/                                   (root)
├── polygons/                       (geopolygons)
│    ├── fire_perimeter_2022_07_14  (group containing kml metadata)

kml/polygons_2022_07_14.kml
```
**Note**: This part of the standard is in an early stage and intentionally allows some flexibility to accommodate diverse geopolygons data types. The structure and required fields may evolve in future versions based on user feedback and practical experience.


### unstructured
- Contains data with unstructured spatial coordinates (*i.e.* not associated with a regular grid). It includes trajectories, or unstructured meshes.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group.
- All spatial coordinates must follow the Spatial Information Convention, including CRS where applicable.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- Each dataset (temperature, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- The following example proposes a structure for a particle trajectories dataset, an output of a model using an unstructured mesh, and a dataset containing building positions and information about buildings.
- Coordinate datasets must be either static or time-dependent, and must be broadcast-compatible with dependent variables

```
/                                           (root)
├── unstructured/                           (unstructured spatial data + time)
│    ├── ptcl_trajectories_1                (group data from a particle trajectory model)
│    │    ├── time
│    │    ├── position_x
│    │    ├── position_y
│    │    ├── position_z
│    ├── unstructured_mesh_1                (group data from a model using a unstructured mesh)
│    │    ├── time
│    │    ├── position_x                    (position of node on the x axis)
│    │    ├── position_y                    (position of node on the y axis)
│    │    ├── position_z                    (position of node on the z axis)
│    │    ├── connectivity                  (Nelements x Nvertices)
│    │    ├── temperature
│    │    ├── wind_u
│    │    ├── wind_v
│    │    ├── wind_w
```

**Note**: This part of the standard is in an early stage and intentionally allows significant flexibility to accommodate diverse unstructured data types. The structure and required fields may evolve in future versions based on user feedback and practical experience.


### fuel_models
- Contains data from a Fuel Model (Anderson/Albini, Scott and Burgan).
- Datasets must be grouped per fuel model. Fuel model extensions (new properties for an existing fuel model) must be added separately and be named with the suffix `_extension_*`.
- Each fuel property (fuel load, fuel height, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint](https://pint.readthedocs.io/en/stable/) terminology.
- Each fuel property dataset must contain the attributes `long_name` describing the property, and `units`. Strings must be stored as UTF-8 variable-length strings.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- The number of fuel categories contained in a fuel model must be specified by the attribute `nb_fuel_cat` of the fuel model group.
- In the following example, the array dimensions must share one dimension size defined by the attribute `nb_fuel_cat` of `Anderson13` and `WUDAPT10` groups. The size of the first dimension of all category-dependent datasets must match `nb_fuel_cat`. For example the dataset for a fuel parameter can have the shape ($N$) or ($N$, $N_2$) if $N$ is the number of fuel categories (`nb_fuel_cat`) and $N_2$ a parameter specific dimension (*e.g.*, size classes, depth layers).

```
/                                           (root)
├── fuel_models/                            (fuel model classification or parameters)
│    ├── Anderson13                         (group parameters for the Anderson Fuel Model)
│    │    ├── fuel_load_dry_total           (total dry fuel load)
│    │    ├── fuel_density                  (fuel density)
│    │    ├── fuel_moisture_extinction      (moisture of extinction)
│    ├── WUDAPT10                           (group parameters for the WUDAPT Fuel Model)
│    │    ├── building_length_side          (building side length)
│    │    ├── building_length_separation    (building separation length)
```

### miscellaneous

- The `/miscellaneous` group is intended for non-standard, project-specific, or experimental datasets that do not yet fall under any defined category of this standard.
- All datasets in `/miscellaneous` must include clear metadata:
    - description attribute explaining the purpose and origin of the data.
    - units attribute (Pint-compatible) if the dataset contains physical quantities.
    - Spatial and temporal metadata following the relevant conventions in this standard, if applicable.
- Naming of datasets should remain descriptive and avoid collisions with reserved names in the standard.
- Use of `/miscellaneous` should be temporary whenever possible; data types that become common should be proposed for inclusion in future versions of the standard.
- The structure of `/miscellaneous` is unconstrained, but good practice is to group related datasets together to improve clarity.
- The time coordinate dataset must be a dataset named `time`, and must use only one time encoding (absolute or relative); do not mix string and numeric (see Time format).
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- If missing values exist, the dataset must either:
    - use `NaN` (float types) or
    - define `_FillValue` attribute (any dtype) and ensure missing entries equal `_FillValue`. If `_FillValue` is present, it must match the dataset dtype.
- `time`, `position_*`, `connectivity`, `crs`, `units`, `_FillValue` are reserved with their standard meanings.

### Metadata

- If `/metadata` is present, it must contain only datasets (no nested groups) and each dataset must have a `description` attribute.