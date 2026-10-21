# FireBench Standard File Format

- **Version**: 1.0
- **Status**: Pre-release
- **Last update**: 2026-10-16

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
├── benchmark_case/ (the definition of a benchmark case, optional)
├── certificates/   (FireBench certificates)
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

FireBench validators accept the current standard version and versions explicitly listed as
compatible with it. Files with missing, malformed, unknown, or unsupported
`FireBench_io_version` values are rejected.


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

Datasets use Zstandard compression through the Python package `hdf5plugin`, so no separate system
library is required. Compression levels range from 1 (faster, less compression) to 22 (slower,
more compression). The recommended level is **20** for workflows where file size matters more than
write time.

## Units
**No unit is assumed implicitly.**
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


### Cross-Section with Cartesian Reference Point

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
- Sensor height must be included at dataset level (*e.g.* temperature, wind_speed) as an attribute
  `sensor_height`, along with `sensor_height_units` specifying the unit of the sensor height. The
  source of the sensor height information must be included in an attribute
  `sensor_height_source`.
- Observational weather datasets used for trust-based station selection must include the following
  sensor-height confidence attributes:

  Attribute | Type | Description
  --------- | ---- | -----------
  `sensor_height_source_confidence_lvl` | scalar integer | `0` unknown, guessed, or missing metadata; `1` provider default not verified for the station; `2` verified measurement or accepted trusted record
  `sensor_height_source_confidence_description` | str | Human-readable meaning of the numeric confidence; informational only
  `sensor_height_provider` | str | Provider associated with the selected height
  `sensor_height_source_reference` | str | Source URL, resource reference, or source filename plus SHA-256
  `sensor_height_source_date` | `YYYY-MM-DD` str | Source date, when available
  `sensor_height_verification_date` | `YYYY-MM-DD` str | Date the evidence or metadata was accepted
  `sensor_height_reviewer_or_authority` | str | Reviewer or authority responsible for the source
  `sensor_height_notes` | str | Optional provenance or limitation notes
  `sensor_height_record_id` | str | Installed resource record ID, when a resource supplied the height

  The numeric attribute is the canonical value used for selection. The description must never be
  parsed to determine behavior. A missing, malformed, or unknown confidence is treated as level 0
  and produces a warning identifying the station and variable. Newly standardized files must
  always write a valid numeric value. Files written before FireBench 0.10 stored the level as a
  combined `"<level> - <description>"` string, and stored `sensor_height` as a decimal string when
  the height came from provider metadata; a reader still recognizes those exact historical
  confidence values and reads a decimal-string observational height, while any other string stays
  level 0. See
  [Weather Sensor Height and Trust](reference/weather_sensor_height.md) for source precedence,
  the versioned trusted-height resources, station-set definitions, and model-preparation
  requirements. New Synoptic standardization records the available provenance attributes;
  `sensor_height_source_date` and resource-specific optional fields can be absent when unavailable.
- A model weather-variable dataset used by a Trusted Sources Only (TSO) KPI must record numeric
  `sensor_height` and Pint-compatible `sensor_height_units`. The model value must have been
  prepared at the corresponding trusted observational height. FireBench converts compatible units
  and requires the model and observation heights to agree within an absolute tolerance of 0.01 m.
  A missing, dimensionally incompatible, or mismatched model height excludes that station from the
  TSO KPI.
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

#### fire_total

A model output gives the fire radiative power it expects over an area in the group
`/time_series/fire_total`, as a band (benchmark cases, family `fire_radiative_power`):

Dataset | Units | Description
:------ | :---: | :----------
`time` | | Output time, absolute or relative (see Time format)
`fire_radiative_power_lower` | power (`MW`) | Lowest FRP the model's heat release gives at that time
`fire_radiative_power_upper` | power (`MW`) | Highest FRP; equal to the lower bound when the model computes FRP itself
`heat_release_rate_sensible` | power (`MW`) | Optional: the sensible heat the band was derived from

- The group carries the area it covers as `frame_west`, `frame_south`, `frame_east`, `frame_north`
  (with `*_units` = `degree`), copied from the case's template.
- An adapter that converts a heat flux records how as group attributes, e.g. `frp_conversion`,
  `conversion_factor_min`, and `conversion_factor_max`.

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

#### terrain_elevation

The ground elevation of a box on a regular longitude-latitude grid, under
`/spatial_2d/terrain_elevation`:

- `position_lat` (`n_lat`, south to north) and `position_lon` (`n_lon`): the cell centres, `degree`.
- `terrain_elevation` (`n_lat`, `n_lon`) float32: m above mean sea level, NaN where no source has a value.
- `elevation_source` (`n_lat`, `n_lon`) uint8: `0` none, `1` LANDFIRE's elevation (bare earth, from
  USGS 3DEP, NAVD88), `2` the Copernicus DEM GLO-30 (a surface model, EGM2008). LANDFIRE is used
  wherever it has a value, the Copernicus DEM elsewhere (`flag_values`, `flag_meanings`).
- Attributes: `crs` (`EPSG:4326`), `step` (`degree`, one arc-second unless the box is large),
  `vertical_reference`, `sources` (JSON: the LANDFIRE file and the Copernicus tiles with their
  SHA-256, and the cells each gave), the frame. `/spatial_2d` carries no attribute.

`firebench.standardize.terrain_elevation_grid` makes the grid and `ground_elevation` gives one point.

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

#### radar

Weather radar volumes are stored as polar sweeps, the way the radar observed them, under
`/spatial_3d/radar`, one group per **site** (the ICAO identifier, *e.g.* `KDAX`). Nothing is gridded
at standardization: a reader grids or cuts what it needs.

```
/spatial_3d/radar/<SITE>/
├── azimuth, range       (fixed axes of the site)
├── time, elevation, volume_index, azimuth_resolution, nyquist_velocity   (one row per sweep)
├── radar_reflectivity, ...   (n_sweep, n_azimuth, n_range)
└── volumes/             (one row per volume scan read)
```

- Position follows the [spherical convention](#spherical-coordinates): the origin is the antenna
  (`position_origin_lat`, `position_origin_lon`, `position_origin_alt`), and a cell is given by its
  azimuth (clockwise from true north), its elevation, and its slant range.
- **Axes.** `azimuth` holds the centres of 0.5 degree bins and `range` the slant ranges of 250 m
  gates. Both are cropped to the cells that can fall inside the frame: a cell is kept when the beam
  centre of some elevation from 0 to 19.75 degree lies above the frame, at most `max_height` above
  mean sea level, with the 4/3 effective Earth radius. The azimuth axis is the smallest arc that
  holds those cells and may cross north (*e.g.* 350.25 to 10.25); a radar inside the frame keeps
  the whole circle. Values of a kept cell outside the frame are stored as observed.
- **Rows.** One row per sweep, in time order. A split cut (a surveillance cut, then a Doppler cut at
  the same elevation) is one row: reflectivity and the dual-polarization fields of the first,
  radial velocity of the second, the time of the first. A tilt scanned again within a volume
  (SAILS) is a row of its own. A sweep scanned with 1 degree rays fills two bins per ray. The value
  of a bin is the one of the ray nearest its centre, NaN when no ray is within 0.75 times the ray
  width.
- Values below the signal threshold and range-folded values are NaN. Radial velocity is stored as
  observed, aliased beyond `nyquist_velocity`.
- `/spatial_3d` and `/spatial_3d/radar` carry no attributes, so files that each hold some sites
  merge without conflict.

Site group attributes:

Attributes | Type | Description
:--------- | :----: | :-----------
`site`, `instrument`, `provider`, `product` | str | *e.g.* `KDAX`, `WSR-88D`, `NOAA NEXRAD`, `NEXRAD Level II`
`data_source` | str | The archive the volumes came from, *e.g.* `s3://unidata-nexrad-level2`
`crs` | str | `EPSG:4326`
`position_origin_lat`, `position_origin_lon`, `position_origin_alt` | float | The antenna, with `*_units` (`degree`, `m` above mean sea level)
`beam_width`, `azimuth_step`, `gate_spacing` | float | 0.95 degree, 0.5 degree, 250 m, with `*_units`
`effective_earth_radius` | float | The radius of the beam geometry (4/3 of 6,371 km), `*_units` = `m`
`max_height` | float | The ceiling of the crop, `*_units` = `m` above mean sea level
`frame_west`, `frame_south`, `frame_east`, `frame_north` | float | The frame requested, `*_units` = `degree`
`time_start`, `time_end` | str | The window requested and the end of the last volume read, ISO 8601
`fields` | str | JSON list of the field datasets present
`time_step`, `time_step_units` | int, str | The selection step, `min`; 0 keeps every volume
`volumes_complete` | bool | False when some volume of the selection could not be fetched or read
`failed` | str | JSON list of the volumes not read: `key`, `reason`
`source_files` | str | JSON: the bucket and the number of volumes read

Sweep rows, every dataset of length `n_sweep`:

Dataset | Units | Description
:------ | :---: | :----------
`time` | `s` | Start of the sweep, relative to `time_origin` (the window start), `time_units` = `s`
`elevation` | `degree` | Fixed angle of the sweep, from the scan pattern
`volume_index` | `1` | Row of `volumes/` the sweep belongs to
`azimuth_resolution` | `degree` | 0.5 or 1, the width of the rays scanned
`nyquist_velocity` | `m/s` | NaN when the sweep has no velocity

Fields, each `(n_sweep, n_azimuth, n_range)` float32, named in the [namespace](./namespace.md):
`radar_reflectivity` (`dBZ`), `radar_correlation_coefficient` (`1`),
`radar_differential_reflectivity` (`dB`), `radar_radial_velocity` (`m/s`). Attribute
`source_moment` gives the Level II name (`DBZH`, `RHOHV`, `ZDR`, `VRADH`).

`volumes/`, every dataset of length `n_volume`: `time` and `time_end` (`s`, same origin), `vcp`
(the volume coverage pattern, `_FillValue` -1), `n_sweeps`, `source_key` and `source_sha256` (the S3
key and SHA-256 of the volume file).

`firebench.standardize.radar_echo_top_series` reads the height of the plume gates of each volume,
`firebench.standardize.radar_composite` the column maximum of a field over them, and
`firebench.standardize.radar_points` the gates themselves.

##### Cross sections

A site may hold cross sections, its volumes read on a plane, under `sections/<name>` (`name`: 1 to
40 letters, digits, hyphens, and underscores). `sections/` carries no attribute.

```
/spatial_3d/radar/<SITE>/sections/<name>/
├── u, v                                       (n_u), (n_v)
├── position_lat, position_lon, position_alt   (n_v, n_u)
├── azimuth, beam_elevation                    (n_v, n_u)
├── time                                       (n_volume)
├── radar_reflectivity, ...                    (n_volume, n_v, n_u)
└── elevation, nyquist_velocity                (n_volume, n_v, n_u)
```

- **The plane.** Three points `point_1`, `point_2`, `point_3` (attributes: latitude, longitude in
  degree, altitude in m above mean sea level). In a local frame, east and north of an azimuthal
  equidistant projection centred on `point_1` and the altitude, the section is the rectangle from
  `point_1` along `point_1`→`point_2` (`u`) and across towards `point_3` (`v`), with nodes every
  `spacing` m. A vertical section has `point_1` and `point_2` at its floor and `point_3` above
  `point_1` at its top.
- **Nodes.** `position_*` is each node; `azimuth` (from the radar, clockwise from true north) and
  `beam_elevation` are those of the beam through it, with the effective Earth radius of the site.
- **Values.** Each node takes the value of the nearest azimuth bin and range gate of the tilts of a
  volume: linear in elevation between the two tilts that bracket it (reflectivity in linear units),
  NaN when either has no value or they are more than `max_elevation_gap` apart; the outermost tilt
  within half a beam width outside them. Radial velocity is never interpolated: it is read on the
  nearest tilt, whose `elevation` and `nyquist_velocity` the section stores. A tilt scanned twice in
  a volume is read from its first scan.
- `time` is the start of each volume (`s`, the origin of `volumes/time`). Attributes: `spacing`,
  `parameters` (the version of `resources/radar.toml`), `computed_by`, `description`.

`firebench.standardize.radar_cross_section` cuts a section, `write_radar_sections` stores it, and
`read_radar_section` reads it back. The limits of a section are in `resources/radar.toml`.

A model output scored on the sections (the `radar_plume` family of the generic cases) gives its plume
at the radar's own times and places, under `/spatial_3d/plume` by default
(`firebench.benchmarks.fire_case_radar_model`):

```
/spatial_3d/plume/
├── sections/<SITE>/<name>/
│   ├── time                                       (n_volume)  start of each volume, as the section's
│   ├── position_lat, position_lon, position_alt   (n_v, n_u)  the section's nodes
│   └── passive_tracer, wind_u, wind_v, wind_w     (n_volume, n_v, n_u)
├── frame/<SITE>/                                  (frame_west, ... attributes: the site's frame)
│   ├── time                                       (n_volume)
│   ├── height_bins                                (n_bin + 1)  edges, m above mean sea level
│   ├── plume_cells                                (n_volume, n_bin)  tracer_relative_threshold attribute
│   ├── position_lat, position_lon                 (n_lat), (n_lon)  the radar's map grid, north to south
│   ├── plume_top                                  (n_volume, n_lat, n_lon)  m above mean sea level
│   └── lowest_beam, highest_beam                  (n_volume, n_lat, n_lon)  template only
└── points/                                        optional, for figures; never scored
    ├── time, offset, count                        (n_time)
    └── position_lon, position_lat, position_z, passive_tracer   (n_point)
```

`passive_tracer` is on any scale (its `units` are kept, never converted); the wind is earth-relative,
in m/s. Over a site's frame, the model's plume is its cells the radar can see, between the lowest and
the highest beam over their map cell (`lowest_beam`, `highest_beam`, from
`firebench.standardize.radar_beam_bands`; `visible_cells`), where its tracer reaches
`tracer_relative_threshold` of its largest value over those cells. `plume_cells` counts them in each
bin of height (each cell weighted by its area when the model's grids differ in resolution), and
`plume_top` is the highest of them over each cell of the radar's map grid (`radar_map_axes`,
`map_resolution` of `[radar_plume]`; `column_tops`, `tops_on_map`), NaN where there is none. A value
the model cannot give is NaN, and a time it cannot give is NaN throughout `plume_cells`. The model-output template of a case
holds these groups with NaN values; `fire_case_template.plume_targets` reads them, or computes them
from an observation file holding the case, and the adapter fills them in with `ColumnSampler` (the
nearest model column, then linear in height), `beam_band_at`, `visible_cells`, `plume_cell_counts`,
`column_tops`, `tops_on_map`, `write_plume_section`, and `write_plume_frame`.

#### lidar

Doppler wind lidar scans are stored the way the lidar observed them, under `/spatial_3d/lidar`, one
group per **instrument** (*e.g.* `HALO_19`, a Halo Photonics StreamLine of system ID 19): one row
per ray, a fixed axis of gates, and one row per scan file. Nothing is gridded or filtered at
standardization.

```
/spatial_3d/lidar/<INSTRUMENT>/
├── range                                              (fixed axis: gate centres)
├── time, azimuth, elevation, pitch, roll, scan_index  (one row per ray)
├── lidar_radial_velocity, lidar_intensity, lidar_attenuated_backscatter   (n_ray, n_range)
└── scans/                                             (one row per scan file)
```

- Position follows the [spherical convention](#spherical-coordinates): the origin is the lidar, and a
  gate is given by its azimuth, its elevation, and its range along the ray. The lidar is static: its
  position is the group's `position_origin_*`, repeated in every row of `scans/`. Its latitude and
  longitude are entered (`position_source` = `entered`) or the median of the GPS fixes around its
  scans (`gps`); its altitude is entered or taken from an elevation model (`altitude_source`, *e.g.*
  `entered`, `LANDFIRE`), else the median GPS height (`gps`).
- **Azimuths are stored as recorded**, clockwise from the instrument's 0 degree. The attribute
  `azimuth_offset` is the azimuth of that 0 clockwise from true north (the heading), so the true
  azimuth of a ray is `azimuth + azimuth_offset`. Pitch and roll are stored and not applied.
- **Gates.** The centre of gate `k` is at `(k + 0.5)` times the gate spacing. In an overlapping scan
  a gate starts every point, so the spacing is the range gate length divided by its length in
  points; otherwise it is the range gate length.
- **Values** are stored as observed, NaN where none. Readers apply quality thresholds (*e.g.*
  `firebench.standardize.lidar_points`, with the thresholds of `resources/lidar.toml`).
- `/spatial_3d` and `/spatial_3d/lidar` carry no attributes, so files that each hold some lidars
  merge without conflict.

Instrument group attributes:

Attributes | Type | Description
:--------- | :----: | :-----------
`instrument`, `system_id` | str, int | *e.g.* `Halo Photonics StreamLine`, `19`
`data_source` | str | `file`: scans a member supplied
`crs` | str | `EPSG:4326`
`position_origin_lat`, `position_origin_lon`, `position_origin_alt` | float | The lidar, with `*_units` (`degree`, `m` above mean sea level)
`position_source`, `altitude_source` | str | Where the position and the altitude come from: `entered`, `gps`, or the elevation model
`position_fixes`, `position_spread` | int, float | The GPS fixes used, and the farthest one from the position (`*_units` = `m`)
`azimuth_offset` | float | The heading, `*_units` = `degree`
`gate_length`, `gate_points`, `gate_spacing`, `n_gates` | float, int, float, int | The range gate length (`m`), its length in points, the spacing of gate centres (`m`), the gates of a ray
`frame_west`, `frame_south`, `frame_east`, `frame_north` | float | The frame requested, `*_units` = `degree`
`time_start`, `time_end` | str | The window start and the last ray read, ISO 8601
`fields` | str | JSON list of the field datasets present
`failed` | str | JSON list of the files not written: `file`, `reason`
`source_files` | str | JSON list of the files written: `name`, `rays`

Ray rows, every dataset of length `n_ray`: `time` (`s` from `time_origin`, the window start),
`azimuth`, `elevation`, `pitch`, `roll` (`degree`), and `scan_index` (the row of `scans/`).

Fields, each `(n_ray, n_range)` float32, named in the [namespace](./namespace.md):
`lidar_radial_velocity` (`m/s`, positive away from the lidar), `lidar_intensity` (`1`, the
signal-to-noise ratio plus one), `lidar_attenuated_backscatter` (`1/m/sr`).

`scans/`, every dataset of length `n_scan`: `time` and `time_end` (first and last ray, same origin),
`n_rays`, `first_ray`, `position_origin_lat`, `position_origin_lon`, `position_origin_alt`,
`position_source` (`gps`: the fix of the lidar's `Time_Sync` file nearest the scan; `entered`: given
by the person who standardized), `scan_type`, `focus_range`, `pulses_per_ray`,
`velocity_resolution`, `source_file`, and `source_sha256`. Strings are fixed-length ASCII.

`firebench.standardize.lidar_scans` lists the scans of a lidar, and
`firebench.standardize.lidar_points` gives the gates of one scan as east, north, and up from the
lidar.

### polygons
- As HDF5 is not a file format that is practical to use for vectorized dataset, the polygons are stored using the `KML` file format.
- The HDF5 file contains the necessary metadata to point to the KML file containing the polygons dataset in a group registered in the `/polygons` main group.
- Each group contains a reference to one and only one KML file.
- Each KML reference corresponds to a single logical polygon layer (*e.g.*, a perimeter at a timestamp).
- The mandatory attributes are the following
    - `rel_path` (str): relative path to the KML file (relative to the HDF5 file directory)
    - `file_size_bytes` (int): KML file size in bytes (*e.g.*, using `os.path.getsize`)
    - `sha256` (str): hash of the KML file using `firebench.tools.calculate_sha256`
- Validation resolves `rel_path` relative to the HDF5 file and rejects missing files or files whose
  current size or SHA-256 digest differs from these attributes.
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


#### fire_detections

Satellite active-fire detections, with their fire radiative power (FRP), are stored under
`/unstructured/fire_detections`, one group per **stream**: one satellite of one product family.

```
/unstructured/fire_detections/<stream>/
├── detections/          (N rows, one per fire pixel)
└── observations/        (M rows, one per time the sensor looked at the frame)
```

- Streams: `viirs_snpp`, `viirs_noaa20`, `viirs_noaa21`, `modis_terra`, `modis_aqua` (NASA FIRMS),
  and `goes16`, `goes17`, `goes18`, `goes19` (NOAA GOES-R ABI fire product, CONUS).
- The observations tell a time the sensor looked and saw no fire from a time it did not look: a
  reader computes an FRP total of 0 for the first and no value for the second.
- `/unstructured` and `/unstructured/fire_detections` carry no attributes, so files that each hold
  some streams merge without conflict.
- Every detection the product reports is stored with its product-native confidence. Filtering by
  confidence is a choice of the reader.

Stream group attributes:

Attributes | Type | Description
:--------- | :----: | :-----------
`satellite` | str | `Suomi NPP`, `NOAA-20`, `NOAA-21`, `Terra`, `Aqua`, `GOES-16` to `GOES-19`
`instrument` | str | `VIIRS`, `MODIS`, `ABI`
`provider` | str | `NASA FIRMS` or `NOAA`
`product` | str | JSON list of the products used (`VIIRS_SNPP_SP`, `VIIRS_SNPP_NRT`, `ABI-L2-FDCC`, ...)
`product_version` | str | FIRMS: the distinct values of the `version` column, `;`-separated
`data_source` | str | The service the data came from. Never a key.
`crs` | str | `EPSG:4326`
`frame_west`, `frame_south`, `frame_east`, `frame_north` | float | The frame requested, with `*_units` = `degree`
`time_start`, `time_end` | str | The window requested, ISO 8601
`observation_source` | str | `cmr` (NASA CMR overpasses), `goes_scans`, or `detections` (observations rebuilt from detections)
`observations_complete` | bool | False when some observations are missing or rebuilt
`failed` | str | JSON list of what failed: FIRMS days (`day`, `reason`) or GOES scans (`key`, `reason`)
`time_step`, `time_step_units` | int, str | GOES: the selection step, `min`
`source_files` | str | JSON: the SHA-256 of the FIRMS bundle and the CMR collections, or the GOES bucket and scan count

`detections/`, every dataset of length N:

Dataset | Units | Description
:------ | :---: | :----------
`time` | `s` | Acquisition time, relative to `time_origin` (the window start), `time_units` = `s`
`position_lat`, `position_lon` | `degree` | Pixel centre
`fire_radiative_power` | `MW` | NaN when the product gives none
`fire_detection_confidence` | `1` | Product-native value, attribute `confidence_scale` (`viirs_lnh`: 0 low, 1 nominal, 2 high; `modis_percent`: 0 to 100; `goes_fdc_mask`: FDC mask code), `_FillValue` -1
`brightness_temperature_mir`, `brightness_temperature_tir` | `K` | FIRMS: VIIRS I4 and I5, MODIS bands 21/22 and 31
`fire_temperature` | `K` | GOES: retrieved fire temperature
`pixel_size_scan`, `pixel_size_track` | `m` | FIRMS: pixel size along scan and track
`footprint_lat`, `footprint_lon` | `degree` | GOES: (N, 4) pixel corners, SW, SE, NE, NW in scan-angle space
`day_night_flag` | `1` | 1 day, 0 night, `_FillValue` -1 (GOES)
`observation_index` | `1` | Row of `observations/` the detection belongs to

`observations/`, every dataset of length M:

Dataset | Units | Description
:------ | :---: | :----------
`time`, `time_end` | `s` | Start and end of the overpass or scan, same origin
`observed_fraction` | `1` | Attribute `method`: `swath` (share of the frame inside the swath outlines of the overpass) or `assessed_pixels` (share of the frame's GOES pixels the algorithm cleared or found burning). NaN when unknown
`granule_ids` | | FIRMS: the CMR granule ids of the overpass, `;`-separated
`source_key`, `source_sha256` | | GOES: S3 key and SHA-256 of the scan

`firebench.standardize.frp_time_series` reads a stream as one FRP total per observation.

#### lightning

Lightning that reached the ground (cloud-to-ground) is stored under `/unstructured/lightning`, one
group per **stream**, with one table:

```
/unstructured/lightning/<stream>/
└── strikes/             (N rows, one per record)
```

- Streams: `nldn_tiles` (NOAA NCEI's daily counts of Vaisala NLDN cloud-to-ground strikes per 0.1°
  cell, `aggregation` = `cell_day`) and `strokes` (the cloud-to-ground strokes of a network's stroke
  file, `aggregation` = `stroke`).
- A record has a start and an end time, a position, and a number of strikes, so a reader treats a
  cell-day and a stroke the same way. A stroke's `time_end` equals its `time`.
- Only discharges that reached the ground are stored. A cell with no row had no strike that day.
- `/unstructured` and `/unstructured/lightning` carry no attributes, so files merge without conflict.

Stream group attributes:

Attributes | Type | Description
:--------- | :----: | :-----------
`network` | str | `NLDN`, or the network a stroke file came from
`provider` | str | `NOAA NCEI`, or the network
`product` | str | JSON list: `nldn-tiles` or `strokes`
`data_source` | str | The directory the tiles came from, or `file`. Never a key.
`discharge` | str | `cloud_to_ground`
`aggregation` | str | `cell_day` or `stroke`
`cell_size`, `cell_size_units` | float, str | `nldn_tiles`: 0.1, `degree`
`period`, `period_units` | int, str | `nldn_tiles`: 86400, `s`
`crs` | str | `EPSG:4326`
`frame_west`, `frame_south`, `frame_east`, `frame_north` | float | The frame requested, with `*_units` = `degree`
`time_start`, `time_end` | str | The window requested, ISO 8601
`complete` | bool | False when some months of the window have no published tile file
`missing` | str | JSON list of the months (`YYYY-MM`) no tile file covers
`source_files` | str | JSON: each tile file with its SHA-256 and the rows kept, or the stroke file's name, rows, and cloud rows dropped

`strikes/`, every dataset of length N:

Dataset | Units | Description
:------ | :---: | :----------
`time`, `time_end` | `s` | Start and end of the record, relative to `time_origin` (00 UTC of the first day for `nldn_tiles`, the window start for `strokes`), `time_units` = `s`
`position_lat`, `position_lon` | `degree` | Cell centre or stroke position
`lightning_stroke_count` | `1` | Strikes the record counts (1 for a stroke)
`lightning_peak_current` | `kA` | `strokes`: signed peak current, NaN when the file gives none

`firebench.standardize.lightning_time_series` counts the strikes of a stream per time step.

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

### Benchmark case

- `/benchmark_case/definition` holds the definition of a benchmark case defined outside FireBench
  (schema `fb-case-v1`): its canonical JSON (sorted keys, no spaces, UTF-8) as a **fixed-length**
  byte string, with the attributes `schema` and `sha256` (the SHA-256 of the JSON, which names the
  definition). A variable-length string would not do: the signing digest hashes it as pointers.
- The group is optional. A file that holds a definition can be scored with
  `firebench case run FILE MODEL` and needs no FireBench code for its case. See
  [Define a benchmark case from a dataset](how_to/define_benchmark_case.md).
- Write it with `write_case_definition` and read it with `read_case_definition`
  (`firebench.benchmarks.fire_case_definition`), before the file is signed: the certificate covers it.

### Model-output template

- A file whose root has `firebench_template = "model-output"` is the template of a model output for
  one benchmark case (`firebench case template`): the observation file's layout for the groups the
  case scores, with its `case_definition_sha256` and its definition at `/benchmark_case/definition`.
- It holds no observed value: perimeter groups have their `time` and no file reference or burnt
  area, the CBI and canopy cover loss grids are their `_FillValue`, building damage is `""` (except
  `"Inaccessible"`), station variables are NaN, and the radar plume and FRP groups are empty. Positions, grids, times, units, sensor heights, and licence attributes
  are kept.
- A template is never an observation file: the generic cases refuse one. A model output written on
  it is a new file, without the attribute. See
  [Prepare a model output for a benchmark case](how_to/prepare_model_output.md).

### Certificates

- Reserved namespace for FireBench certificates. See the signing and verification guide.
