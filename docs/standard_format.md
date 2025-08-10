# 4. Standard FireBench file format

- **Version**: 0.1
- **Status**: Draft
- **Last update**: 2025-08-08

This document defines the I/O format standard for benchmark datasets used in the `FireBench` benchmarking framework. The standard is based on the [HDF5 file format](https://www.hdfgroup.org/solutions/hdf5/) (`.h5`) and describes the structure, expected groups, metadata, and conventions.

## File structure

Each .h5 file must adhere to the following structure:

```
/                   (root)
├── probes/         (point-based time series)
├── 1D_raster/      (1D gridded spatial data + time)
├── 2D_raster/      (2D gridded spatial data + time)
├── 3D_raster/      (3D gridded spatial data + time)
├── unstructured/   (unstructured spatial data + time)
├── polygons/       (geopolygones)
├── fuel_models/    (fuel model classification or parameters)
├── miscellaneous/  (non-standard or project-specific data)
```

All groups are optional unless otherwise specified in a benchmark case specification.
The `/metadata` group is not defined in this version of the standard, as all metadata should normally be stored as attributes of the file, existing groups, or datasets. If additional metadata needs to be stored as dedicated datasets, the `/metadata` group is reserved for this purpose. Its structure and required fields may evolve in future versions based on user feedback and practical experience.

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
`project_name` | str | Short description of the project
`license` | str | License or terms of use
`data_source` | str | Source of the data if applicable

No `/metadata` group is required; prefer file-level attributes. The `/metadata` namespace is reserved for future versions.

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


## Group definition

### Probes
- Contains time series data from specific points in space called probes, for example, weather stations (RAWS) or local sensors.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate are placed in the same data group (*e.g.*, a sensor group). Multiple data groups that share the same spatial location are further grouped together in a location group (*e.g.*, a weather station).
- Each group containing data should be named after the probe location or ID (e.g. probe_01).
- Each dataset (temperature, wind_speed, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- The time coordinate dataset must be a dataset named `time`.
- Each time coordinate dataset must follow the global time convention (see Time format).
- Location of the probes must be defined as attributes following a spatial description convention.
- If geographic coordinates are used, a CRS must be included.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - data (temperature, wind_speed, *etc.*) -> ($N_t$)
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
- Each dataset (wind_speed, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- The coordinate arrays may be 1D, or time-dependent 1D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - z -> ($N_z$) or ($N_t$, $N_z$) for time varying z coordinate
    - data (wind_speed, wind_direction, *etc.*) -> ($N_t$, $N_z$)

```
/                               (root)
├── 1D_raster/                  (1D gridded spatial data + time)
│    ├── wind_profiler_1        (group all data from the wind profiler)
│    │    ├── time              (time dataset)
│    │    ├── z                 (vertical spatial coordinate for profile)
│    │    ├── wind_speed        (wind profiler data)
│    │    ├── wind_direction    (wind profiler data)
```

### 2D raster
- Contains time series data from a dataset associated with two-dimensional spatial data. "2D raster" in this standard means any two spatial dimensions, whether horizontal, vertical, or arbitrary section, and that coordinate naming (x, y, z) will follow the Spatial Information Convention.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group. For example, `fire_arrival_time` and `rate_of_spread` share the same x, y, and time coordinates, so they are stored in the same group.
- The spatial coordinate dataset (x, y in the example) must follow a spatial description convention for a two-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Each dataset (rate_of_spread, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- The coordinate arrays may be 1D, 2D, or time-dependent 2D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - x of wrfoutput_1 group -> ($N_x$) or ($N_y$, $N_x$) or ($N_t$, $N_y$, $N_x$) or ($N_t$, $N_x$)
    - y -> ($N_y$) or ($N_y$, $N_x$) or ($N_t$, $N_y$, $N_x$) or ($N_t$, $N_y$)
    - data of wrfoutput_1 group(fire_arrival_time, *etc.*) -> ($N_t$, $N_y$, $N_x$)
    - x of wrfoutput_cs_1 group -> ($N_x$) or ($N_z$, $N_x$) or ($N_t$, $N_z$, $N_x$) or ($N_t$, $N_x$)
    - z -> ($N_z$) or ($N_z$, $N_x$) or ($N_t$, $N_z$, $N_x$) or ($N_t$, $N_z$)
    - data of wrfoutput_cs_1 group(wind_u, *etc.*) -> ($N_t$, $N_z$, $N_x$)

```
/                                  (root)
├── 2D_raster/                     (2D gridded spatial data + time)
│    ├── wrfoutput_1               (group outputs from a WRF-SFIRE simulation for surface x-y plane)
│    │    ├── time                 (time dataset)
│    │    ├── x                    (x spatial coordinate)
│    │    ├── y                    (y spatial coordinate)
│    │    ├── fire_arrival_time    (fire arrival time output from WRF-SFIRE simulation)
│    │    ├── rate_of_spread       (rate of spread output from WRF-SFIRE simulation)
│    ├── wrfoutput_cs_1            (group outputs from a WRF-SFIRE simulation for a x-z cross section)
│    │    ├── time                 (time dataset)
│    │    ├── x                    (x spatial coordinate)
│    │    ├── z                    (z spatial coordinate)
│    │    ├── wind_u               (zonal wind output from WRF-SFIRE simulation)
│    │    ├── wind_w               (vertical wind output from WRF-SFIRE simulation)
```

### 3D raster
- Contains time series data from a dataset associated with three-dimensional spatial data.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group. For example, `wind_u` and `wind_v` share the same x, y, z, and time coordinates, so they are stored in the same group.
- The spatial coordinate dataset (x, y, z in the example) must follow a spatial description convention for a three-dimensional dataset. The spatial coordinate can be fixed in time or change in time.
- If geographic coordinates are used, a CRS must be included.
- Each dataset (temperature, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- The coordinate arrays may be 1D, 3D, or time-dependent 3D, depending on the grid type (regular, curvilinear, moving).
- In the following example, the array dimensions can be:
    - time -> ($N_t$)
    - x -> ($N_x$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_x$)
    - y -> ($N_y$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_y$)
    - z -> ($N_z$) or ($N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$, $N_y$, $N_x$) or ($N_t$, $N_z$)
    - data (temperature, wind_u, *etc.*) -> ($N_t$, $N_z$, $N_y$, $N_x$)

```
/                            (root)
├── 3D_raster/               (3D gridded spatial data + time)
│    ├── wrfoutput_1         (group outputs from a WRF-SFIRE simulation)
│    │    ├── time           (time dataset)
│    │    ├── x              (x spatial coordinate)
│    │    ├── y              (y spatial coordinate)
│    │    ├── z              (z spatial coordinate)
│    │    ├── wind_u         (U wind output from WRF-SFIRE simulation)
│    │    ├── wind_v         (V wind output from WRF-SFIRE simulation)
│    │    ├── wind_w         (W wind output from WRF-SFIRE simulation)
│    │    ├── temperature    (temperature output from WRF-SFIRE simulation)
```

### unstructured
- Contains data with unstructured spatial coordinates (*i.e* not associated with a regular grid). It includes trajectories, or unstructured meshes.
- Datasets must be grouped at the lowest common level that minimizes data duplication. Variables sharing the same time coordinate and the same spatial coordinate are placed in the same data group.
- All spatial coordinates must follow the Spatial Information Convention, including CRS where applicable.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- Each dataset (temperature, wind_u, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- The following example proposes a structure for a particle trajectories dataset, an output of a model using an unstructured mesh, and a dataset containing building positions and information about buildings.

```
/                                           (root)
├── unstructured/                           (unstructured spatial data + time)
│    ├── ptcl_trajectories_1                (group data from a particle trajectory model)
│    │    ├── time
│    │    ├── x
│    │    ├── y
│    │    ├── z
│    ├── unstructured_mesh_1                (group data from a model using a unstructured mesh)
│    │    ├── time
│    │    ├── position_nodes                (Nnodes x3)
│    │    ├── connectivity                  (Nelements x Nvertices)
│    │    ├── temperature
│    │    ├── wind_u
│    │    ├── wind_v
│    │    ├── wind_w
```

**Note**: This part of the standard is in an early stage and intentionally allows significant flexibility to accommodate diverse unstructured data types. The structure and required fields may evolve in future versions based on user feedback and practical experience.


### polygons
- Contains data stored as polygons with an explicit coordinate reference system (CRS), such as those derived from .kml or shapefiles.
- All spatial coordinates must follow the Spatial Information Convention, including a required `crs` attribute at the group level. Optional attributes or datasets for holes/multipolygons can be added.
- Each polygon is stored as a separate dataset within a group. This dataset contains the polygon geometry (list of vertices) and has its own attributes for time, CRS, and other metadata. Multipolygons (island, holes) can be stored in the same dataset as long as they share the same attributes.
- Polygons that have a specific time stamp must contain an attribute `time` following the time format convention (each polygon dataset has its own time attribute).
- Per-polygon attributes (e.g., building type, perimeter source) should be stored as attributes at the lowest common level. Group attributes are considered common to all datasets contained in the group. If information is specific to a polygon, it should be stored as a dataset attribute.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
- Each dataset (fire perimeter, buildings, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- Polygons are stored as (Nvertices, 2) or (Nvertices, 3) arrays following a Spatial Information Convention.

```
/                                   (root)
├── polygons/                       (geopolygones)
│    ├── fire_perimeters            (group containing fire perimeter polygons and related metadata)
│    │    ├── perimeter_1           (polygons describing the perimeter at time 1)
│    │    ├── perimeter_2           (polygons describing the perimeter at time 2)
│    │    ├── perimeter_3           (polygons describing the perimeter at time 3)
│    ├── buildings_info_1           (group data from a building dataset)
│    │    ├── position_structure
│    │    ├── roof_type
```
**Note**: This part of the standard is in an early stage and intentionally allows significant flexibility to accommodate diverse geopolygons data types. The structure and required fields may evolve in future versions based on user feedback and practical experience.


### fuel_models
- Contains data from a Fuel Model (Anderson/Albini, Scott and Burgan).
- Datasets must be grouped per fuel model. Fuel model extensions (new properties for an existing fuel model) must be added separately and be named with the suffix `_extension_*`.
- Each fuel property (fuel load, fuel height, *etc.*) must be named using the [Standard Variable Namespace](./namespace.md). If the name of the variable is not present, use a variable name as descriptive as possible and open a pull request to add the variable name to the Standard Variable Namespace. Units must be defined as an attribute `units` compatible with [Pint library](https://pint.readthedocs.io/en/stable/) terminology.
- Each fuel property dataset must contain the attributes `long_name` describing the property, `unit`, and `type` describing the variable type in the numpy array (*e.g.* float64, object, int32). String variables will be using the object type.
- Users are encouraged to add an attribute `description` to groups and datasets for information/context about the data.
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