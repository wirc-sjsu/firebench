# Standard I/O file format: Probes dataset

This guide gives examples of the stucture of the standard IO file format for probes datasets.

## Local sensor
You want to store data from a sonic anemometer R.M. Young 81000. The dataset contains the wind speed for each cardinal direction. You know the relative location of the sensor relative to a reference point. The time series are given as seconds after a reference time.

The structure of the HDF5 file is the following:
### File level attributes

See [Standard file format description](../standard_format.md) for mandatory file level attributes.

### Groups and dataset
```
/
├── probes
│   └── Sonic_1
│       ├── time           (1D dataset)
│       ├── wind_speed_u   (1D dataset)
│       ├── wind_speed_v   (1D dataset)
│       └── wind_speed_w   (1D dataset)
```
### Group: `/probes/Sonic_1`
**Attributes**
Attribute | Type | Description
--------- | ---- | -----------
`time_origin` | str | ISO 8601 date-time for the origin of time series
`position_origin_lat` | float | Reference position latitude
`position_origin_lon` | float | Reference position longitude
`position_origin_alt` | float | Reference position altitude
`position_rel_x` | float | Relative position in x direction (West-East)
`position_rel_y` | float | Relative position in y direction (South-North)
`position_rel_z` | float | Relative elevation
`position_rel_units` | str | units of relative position
`sensor_type` | str | Name of the sensor

### Group: `/probes/Sonic_1/time`
**Attributes**
Attribute | Type | Description
--------- | ---- | -----------
`units` | str | pint compatible unit

### Group: `/probes/Sonic_1/wind_speed_u`
**Attributes**
Attribute | Type | Description
--------- | ---- | -----------
`units` | str | pint compatible unit

### Group: `/probes/Sonic_1/wind_speed_v`
**Attributes**
Attribute | Type | Description
--------- | ---- | -----------
`units` | str | pint compatible unit

### Group: `/probes/Sonic_1/wind_speed_w`
**Attributes**
Attribute | Type | Description
--------- | ---- | -----------
`units` | str | pint compatible unit