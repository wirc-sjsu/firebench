from datetime import datetime
from pathlib import Path
import pytz

import json
import h5py
import numpy as np
from pyproj import CRS, Transformer

from ..tools import StandardVariableNames as svn
from ..tools import current_datetime_iso8601, datetime_to_iso8601
from .tools import VERSION_STD, check_std_version
from ..tools.logging_config import logger

tz = pytz.timezone('America/Denver')

variable_units = {
    "air_temp": "degC",
    "wind_speed": "m/s",
    "relative_humidity": "%",
    "precipitation": "mm",
    "wind_direction": "deg",
    "wind_gust": "m/s",
    "solar_radiation": "W/m2"
}

def weather_station(
    path: str,
    dst: str,
    group_name: str | None = None,
    authors: str = "",
    std_file_description: str = "auto",
    overwrite: bool = False,
):
    """
    Convert a weather station data to Firebench HDF5 standard file.

    Parameters
    ----------
    path : str
        Path to the weather station file (ending with *.json).
    dst : str
        Path to target HDF5 file (created or appended).
    group_name : str | None
        HDF5 group path. If None, auto-derive from filename, e.g. '2D_raster/<basename>'.
    authors: str
        Add the names of the authors in the standard file in the file attribute `created_by`.
    std_file_description: str
        Add custom description of the mtbs group. If description is "auto" the description will be "\n- weather data from weather stations".
    overwrite: bool
        Overwrite the group in the HDF5 file. Default: False

    Returns
    -------
    str
        The actual HDF5 group written (with suffix if collision).
    """  # pylint: disable=line-too-long

    # Choose your target CRS:
    #   - WGS84 geographic:
    epsg_code = 32610
    tgt_crs = CRS.from_epsg(epsg_code)  # lon/lat
    #   - OR NAD83 geographic:
    # tgt_crs = CRS.from_epsg(4269) # lon/lat

    # --- Read JSON file ---
    with open(path, "r") as f:
        data = json.load(f)

    stations = data["STATION"]

    # --- Create HDF5 file ---
    with h5py.File(dst, "w") as h5:
        if check_std_version(h5):
            h5.attrs["FireBench_io_version"] = VERSION_STD

        h5.attrs["created_on"] = current_datetime_iso8601(include_seconds=False, tz="America/Denver")

        if "created_by" in h5.attrs.keys():
            if authors is not None:
                h5.attrs["created_by"] = h5.attrs["created_by"] + f", {authors}"
        else:
            h5.attrs["created_by"] = authors

        if std_file_description == "auto":
            std_file_description = "\n- weather data from weather stations"
        if "description" in h5.attrs.keys():
            h5.attrs["description"] = h5.attrs["description"] + "\n- weather data from weather stations"
        else:
            h5.attrs["description"] = "This file contains:\n- weather data from weather stations"

        group_name = f"/probes/{group_name}"
        if group_name in h5.keys():
            if overwrite:
                del h5[group_name]
            else:
                logger.warning(
                    "group name %s already exists in file %s. Group not updated. Set `overwrite` to True to update the dataset.",
                    group_name,
                    path,
                )
                return

        g = h5.create_group(group_name)
        g.attrs["data_source"] = f"weather stations {path}"
        g.attrs["crs"] = f"EPSG:{epsg_code}"

        for station in stations:
            station_id = station["ID"]
        
        # Create a group for this station
            grp = g.create_group("weather station - " + station_id)
        
        # --- Save OBSERVATIONS as subgroup ---
            observations = station.get("OBSERVATIONS", {})
            datetime_keys = [k for k in observations.keys() if "date" in k.lower() or "time" in k.lower() or "date_time" in k.lower()]
            for dt_key in datetime_keys:
                obs_values = observations[dt_key]
                if not obs_values:
                    continue
            # Convert each entry to ISO8601 format
            iso_date_time = [tz.localize(datetime.strptime(dt, "%Y%m%d%H%M%S")).isoformat() for dt in obs_values]
            # Replace original format with converted format
            observations[dt_key] = iso_date_time
            
            for obs_key, obs_values in observations.items():
                if not obs_values:  # skip empty arrays
                    continue
                if isinstance(obs_values[0], str):  
                    arr = np.array(obs_values, dtype=f"S{len(obs_values[0])}")
                else:
                    arr = np.array(obs_values, dtype=np.float32)
                grp.create_dataset(obs_key, data=arr)

        # --- Add relevant UNITS for sensor variables ---
        sensor_vars = station.get("SENSOR_VARIABLES", {})
        if sensor_vars is not None:
            existing_sensor_vars = list(sensor_vars.keys())
        else:
            existing_sensor_vars = []

        relevant_units = {
            var: unit for var, unit in variable_units.items()
            if var in existing_sensor_vars or unit in ["position", "elevation"]
        }

        existing_units_attr = grp.attrs.get("UNITS")
        units_string = str(relevant_units)
        grp.attrs["UNITS"] = units_string
        