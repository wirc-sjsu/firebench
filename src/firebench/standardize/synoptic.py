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
        "default_sensor_height": 2,
    },
    "relative_humidity_set_1": {
        "std_name": svn.RELATIVE_HUMIDITY.value,
        "units": "percent",
        "dtype": np.float64,
        "default_sensor_height": 2,
    },
    "wind_direction_set_1": {
        "std_name": svn.WIND_DIRECTION.value,
        "units": "degree",
        "dtype": np.float64,
        "default_sensor_height": None,
    },
    "wind_speed_set_1": {
        "std_name": svn.WIND_SPEED.value,
        "units": "m/s",
        "dtype": np.float64,
        "default_sensor_height": None,
    },
    "wind_gust_set_1": {
        "std_name": svn.WIND_GUST.value,
        "units": "m/s",
        "dtype": np.float64,
        "default_sensor_height": None,
    },
    "solar_radiation_set_1": {
        "std_name": svn.SOLAR_RADIATION.value,
        "units": "W/m^2",
        "dtype": np.float64,
        "default_sensor_height": None,
    },
    "fuel_moisture_set_1": {
        "std_name": svn.FUEL_MOISTURE_CONTENT_10H.value,
        "units": "percent",
        "dtype": np.float64,
        "default_sensor_height": 0.3,
    },
}


def standardize_synoptic_raws_from_json(
    json_path: Path,
    h5file: h5py.File,
    skip_stations: list[str] = [],
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

    nb_fully_processed = 0
    nb_partially_processed = 0
    nb_skipped = 0

    for station_dict in data["STATION"]:
        if station_dict["STID"] in skip_stations:
            nb_skipped += 1
            logger.info("Skipping station %s", station_dict["STID"])
            continue

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
        new_station.attrs["ID"] = int(station_dict["ID"])
        new_station.attrs["mnet_id"] = int(station_dict["MNET_ID"])
        new_station.attrs["state"] = station_dict["STATE"]
        new_station.attrs["timezone"] = station_dict["TIMEZONE"]
        new_station.attrs["position_lat"] = float(station_dict["LATITUDE"])
        new_station.attrs["position_lon"] = float(station_dict["LONGITUDE"])
        new_station.attrs["position_alt"] = float(station_dict["ELEVATION"])
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
                new_station.attrs["elevation_dem"] = float(station_dict["ELEV_DEM"])
                new_station.attrs["elevation_dem_units"] = station_dict["UNITS"]["elevation"]
        if "PROVIDERS" in station_dict:
            if "name" in station_dict["PROVIDERS"]:
                new_station.attrs["providers"] = station_dict["PROVIDERS"]["name"]

        fully_processed = True
        for var in station_dict["OBSERVATIONS"]:
            if var == "date_time":
                time_iso = []
                for t in station_dict["OBSERVATIONS"]["date_time"]:
                    dt = datetime.strptime(t, "%Y%m%d%H%M%S")
                    time_iso.append(datetime_to_iso8601(dt, True, tz=station_dict["TIMEZONE"]))

                new_station.create_dataset(
                    svn.TIME.value, data=time_iso, **hdf5plugin.Zstd(clevel=compression_lvl)
                )
            else:
                if var in variable_conversion:
                    logger.debug("> processing %s", var)

                    sensor_height = __get_sensor_height(station_dict["SENSOR_VARIABLES"], var)

                    if sensor_height is not None:
                        # Sensor heigth from metadata
                        __add_variable_to_group(
                            new_station,
                            station_dict["OBSERVATIONS"][var],
                            variable_conversion[var],
                            sensor_height,
                            compression_lvl,
                        )
                    else:
                        # Sensor height from default, skip if None
                        fully_processed = False
                        if variable_conversion[var]["default_sensor_height"] is None:
                            logger.warning(
                                "standardize_synoptic_raws_from_json: variable %s from station %s not processed due to lack of sensor height information. Default value is `None` for this variable.",
                                var,
                                station_dict["STID"],
                            )
                        else:
                            logger.info(
                                "standardize_synoptic_raws_from_json: variable %s from station %s uses firebench default height of %f m",
                                var,
                                station_dict["STID"],
                                variable_conversion[var]["default_sensor_height"],
                            )
                            __add_variable_to_group(
                                new_station,
                                station_dict["OBSERVATIONS"][var],
                                variable_conversion[var],
                                variable_conversion[var]["default_sensor_height"],
                                compression_lvl,
                            )

                else:
                    logger.warning(
                        "standardize_synoptic_raws_from_json: variable %s from station %s not processed. Add the variable to `variable_conversion` to process it.",
                        var,
                        station_dict["STID"],
                    )

        if fully_processed:
            new_station.attrs["sensor_height_source"] = "from_data"
            nb_fully_processed += 1
        else:
            new_station.attrs["sensor_height_source"] = "firebench_default"
            nb_partially_processed += 1

    logger.info(
        "Stats stations: %d fully processed, %d partially processed, %d skipped",
        nb_fully_processed,
        nb_partially_processed,
        nb_skipped,
    )


def __get_sensor_height(sensor_variables: dict, variable: str):
    for sensor_var in sensor_variables.values():
        if variable in sensor_var:
            return sensor_var[variable].get("position")
    return None


def __add_variable_to_group(
    group: h5py.Group, variable, info_dict: dict, sensor_height: float, compression_lvl: int
):
    var_data = np.array(variable, dtype=info_dict["dtype"])
    new_var = group.create_dataset(
        info_dict["std_name"],
        data=var_data,
        **hdf5plugin.Zstd(clevel=compression_lvl),
    )
    new_var.attrs["units"] = info_dict["units"]
    new_var.attrs["sensor_height"] = sensor_height
    new_var.attrs["sensor_height_units"] = "m"
