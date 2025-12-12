from pathlib import Path
import numpy as np
import hdf5plugin
import h5py
import json
from datetime import datetime
from ..tools import StandardVariableNames as svn
from ..tools import logger, calculate_sha256
from .std_file_info import TIME_SERIES
from .time import datetime_to_iso8601

VARIABLE_CONVERSION = {
    "air_temp_set_1": {
        "std_name": svn.AIR_TEMPERATURE.value,
        "units": "degC",
        "dtype": np.float64,
    },
    "relative_humidity_set_1": {
        "std_name": svn.RELATIVE_HUMIDITY.value,
        "units": "percent",
        "dtype": np.float64,
    },
    "wind_direction_set_1": {
        "std_name": svn.WIND_DIRECTION.value,
        "units": "degree",
        "dtype": np.float64,
    },
    "wind_speed_set_1": {
        "std_name": svn.WIND_SPEED.value,
        "units": "m/s",
        "dtype": np.float64,
    },
    "wind_gust_set_1": {
        "std_name": svn.WIND_GUST.value,
        "units": "m/s",
        "dtype": np.float64,
    },
    "solar_radiation_set_1": {
        "std_name": svn.SOLAR_RADIATION.value,
        "units": "W/m^2",
        "dtype": np.float64,
    },
    "fuel_moisture_set_1": {
        "std_name": svn.FUEL_MOISTURE_CONTENT_10H.value,
        "units": "percent",
        "dtype": np.float64,
    },
}


def standardize_synoptic_raws_from_json(
    json_path: Path,
    h5file: h5py.File,
    overwrite: bool = False,
    variable_conversion: dict = VARIABLE_CONVERSION,
    compression_lvl: int = 3,
):
    sha_source_file = calculate_sha256(json_path.resolve())
    with open(json_path.resolve(), "r") as f:
        data = json.load(f)

    if TIME_SERIES in h5file["/"]:
        probes = h5file[f"/{TIME_SERIES}"]
    else:
        probes = h5file.create_group(TIME_SERIES)

    for station_dict in data["STATION"]:
        logger.info("Processing station %s", station_dict["STID"])

        group_name = f"station_{station_dict["STID"]}"
        if group_name in h5file.keys():
            if overwrite:
                del h5file[group_name]
            else:
                logger.warning(
                    "station group name %s already exists in file %s. Group not updated. Set `overwrite` to True to update the dataset.",
                    group_name,
                    json_path,
                )
                return

        new_station = probes.create_group(group_name)
        new_station.attrs["name"] = station_dict["NAME"]
        new_station.attrs["ID"] = station_dict["ID"]
        new_station.attrs["mnet_id"] = station_dict["MNET_ID"]
        new_station.attrs["state"] = station_dict["STATE"]
        new_station.attrs["timezone"] = station_dict["TIMEZONE"]
        new_station.attrs["position_lat"] = station_dict["LATITUDE"]
        new_station.attrs["position_lon"] = station_dict["LONGITUDE"]
        new_station.attrs["position_alt"] = station_dict["ELEVATION"]
        new_station.attrs["position_lat_units"] = "degree"
        new_station.attrs["position_lon_units"] = "degree"
        new_station.attrs["position_alt_units"] = station_dict["UNITS"]["elevation"]
        new_station.attrs["license"] = "/DATA_LICENSES/Synoptic.txt"
        new_station.attrs["data_use_restrictions"] = "No commercial use allowed"
        new_station.attrs["public_access_level"] = "Restricted"
        new_station.attrs["redistribution_allowed"] = False
        new_station.attrs["source_file_sha256"] = sha_source_file
        if "ELEV_DEM" in station_dict:
            if station_dict["ELEV_DEM"] is not None:
                new_station.attrs["elevation_dem"] = station_dict["ELEV_DEM"]
                new_station.attrs["elevation_dem_units"] = station_dict["UNITS"]["elevation"]

        for var in station_dict["OBSERVATIONS"]:
            if var == "date_time":
                time_iso = []
                for t in station_dict["OBSERVATIONS"]["date_time"]:
                    dt = datetime.strptime(t, "%Y%m%d%H%M%S")
                    time_iso.append(datetime_to_iso8601(dt, True, tz=station_dict["TIMEZONE"]))

                new_var = new_station.create_dataset(
                    svn.TIME.value, data=time_iso, **hdf5plugin.Zstd(clevel=compression_lvl)
                )
            else:
                if var in variable_conversion:
                    logger.info("> processing %s", var)
                    var_data = np.array(
                        station_dict["OBSERVATIONS"][var], dtype=variable_conversion[var]["dtype"]
                    )
                    new_var = new_station.create_dataset(
                        variable_conversion[var]["std_name"],
                        data=var_data,
                        **hdf5plugin.Zstd(clevel=compression_lvl),
                    )
                    new_var.attrs["units"] = variable_conversion[var]["units"]
                else:
                    logger.warning(
                        "standardize_synoptic_raws_from_json: variable %s from station %s not processed. Add the variable to `variable_conversion` to process it.",
                        var,
                        station_dict["STID"],
                    )
