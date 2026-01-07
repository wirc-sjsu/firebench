from pathlib import Path
import numpy as np
import hdf5plugin
import h5py
import json
import pytz
from datetime import datetime
from ..tools import StandardVariableNames as svn
from ..tools import logger, calculate_sha256
from .std_file_info import TIME_SERIES
from .time import datetime_to_iso8601
from .synoptic_data import (
    DEFAULT_SENSOR_HEIGHT_UNIT,
    SH_TRUST_HIGHEST,
    SH_TRUST_LVL,
    VARIABLE_CONVERSION,
    load_sensor_height_stations,
    load_sensor_height_providers,
    load_sensor_height_trusted_history,
)


def standardize_synoptic_raws_from_json(
    json_path: Path,
    h5file: h5py.File,
    skip_stations: list[str] = [],
    overwrite: bool = False,
    fb_var_info: dict = VARIABLE_CONVERSION,
    compression_lvl: int = 3,
    export_trusted_history: bool = False,
):
    sha_source_file = calculate_sha256(json_path.resolve())
    with open(json_path.resolve(), "r") as f:
        data = json.load(f)

    if TIME_SERIES in h5file["/"]:
        probes = h5file[f"/{TIME_SERIES}"]
    else:
        probes = h5file.create_group(TIME_SERIES)

    fb_sh_hist = load_sensor_height_trusted_history()
    fb_sh_trusted_stations = load_sensor_height_stations()
    fb_sh_providers = load_sensor_height_providers()

    # for statistics
    nb_fully_processed = 0
    nb_partially_processed = 0
    nb_skipped = 0
    nb_var_from_data = 0
    nb_var_from_stations = 0
    nb_var_from_hist = 0
    nb_var_from_provider = 0
    nb_var_from_default = 0
    if export_trusted_history:
        trusted_stations_new = {}

    for station_dict in data["STATION"]:
        if station_dict["STID"] in skip_stations:
            nb_skipped += 1
            logger.info("Skipping station %s", station_dict["STID"])
            continue

        logger.info("Processing station %s", station_dict["STID"])

        group_name = f"station_{station_dict['STID']}"
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
        try:
            new_station.attrs["elevation_dem"] = float(station_dict["ELEV_DEM"])
            new_station.attrs["elevation_dem_units"] = station_dict["UNITS"]["elevation"]
        except:
            logger.info("elevation_dem not found for station %s.", station_dict["STID"])
        try:
            provider = station_dict["PROVIDERS"][0]["name"]
        except:
            provider = None
            logger.warning(
                "No provider found for station %s. Limited import options.", station_dict["STID"]
            )
        new_station.attrs["providers"] = str(provider)

        fully_processed = True
        for var in station_dict["OBSERVATIONS"]:
            if var == "date_time":
                tz = pytz.timezone(station_dict["TIMEZONE"])
                dts = [
                    tz.localize(datetime.strptime(t, "%Y%m%d%H%M%S"))
                    for t in station_dict["OBSERVATIONS"]["date_time"]
                ]
                dt0 = dts[0]
                first_time_iso = datetime_to_iso8601(dt0, True)
                rel_minutes = [(dt - dt0).total_seconds() / 60.0 for dt in dts]

                time_ds = new_station.create_dataset(
                    svn.TIME.value, data=rel_minutes, **hdf5plugin.Zstd(clevel=compression_lvl)
                )
                time_ds.attrs["time_origin"] = first_time_iso
                time_ds.attrs["time_units"] = "min"
            else:
                if var in fb_var_info:
                    logger.debug("Processing %s", var)

                    sensor_height = __get_sensor_height(station_dict["SENSOR_VARIABLES"], var)

                    if sensor_height is not None:
                        # Sensor heigth from metadata
                        __add_sh_to_group(
                            new_station,
                            station_dict["OBSERVATIONS"][var],
                            fb_var_info[var],
                            sensor_height,
                            DEFAULT_SENSOR_HEIGHT_UNIT,
                            "from_data",
                            SH_TRUST_HIGHEST,
                            compression_lvl,
                        )
                        nb_var_from_data += 1
                        if export_trusted_history:
                            try:
                                trusted_stations_new[f"{station_dict['STID']}"][var] = sensor_height
                                trusted_stations_new[f"{station_dict['STID']}"]["provider"] = str(provider)
                            except:
                                trusted_stations_new[f"{station_dict['STID']}"] = {}
                                trusted_stations_new[f"{station_dict['STID']}"][var] = sensor_height
                                trusted_stations_new[f"{station_dict['STID']}"]["provider"] = str(provider)
                    else:
                        logger.warning(
                            "Missing sensor height info for variable %s from station %s . Looking for values in FireBench databases.",
                            var,
                            station_dict["STID"],
                        )
                        # Sensor height from default, skip if None
                        fully_processed = False

                        # 1. Use Default value for sensor height form FireBench
                        sh_from_fb = fb_var_info[var]["default_sensor_height"]
                        sh_source = "firebench_default"
                        sh_source_trusted = 0
                        sh_info_found = False
                        nb_var_from_default += 1

                        # Try find sensor height in stations (highest trust)
                        try:
                            sh_from_fb = fb_sh_trusted_stations[f"{station_dict['STID']}"][var]
                            sh_source = "firebench_trusted_stations"
                            sh_source_trusted = SH_TRUST_HIGHEST
                            sh_info_found = True
                            nb_var_from_stations += 1
                            logger.debug("Sensor height value found in trusted stations database.")
                        except:
                            pass

                        if not sh_info_found:
                            # Try find sensor height in history (high trust)
                            try:
                                sh_from_fb = fb_sh_hist[f"{station_dict['STID']}"][var]
                                sh_source = "firebench_trusted_history"
                                sh_source_trusted = SH_TRUST_HIGHEST
                                sh_info_found = True
                                nb_var_from_hist += 1
                                logger.debug(
                                    "Sensor height value found in history of trusted information database."
                                )
                            except:
                                pass

                        if not sh_info_found:
                            # Try find sensor height in providers (low trust)
                            try:
                                sh_from_fb = fb_sh_providers[provider][var]
                                sh_source = "firebench_providers_default"
                                sh_source_trusted = 1
                                sh_info_found = True
                                nb_var_from_provider += 1
                                logger.debug("Sensor height value found in providers database.")
                            except:
                                pass

                        if sh_info_found:
                            nb_var_from_default -= 1

                        __add_sh_to_group(
                            new_station,
                            station_dict["OBSERVATIONS"][var],
                            fb_var_info[var],
                            sh_from_fb,
                            DEFAULT_SENSOR_HEIGHT_UNIT,
                            sh_source,
                            sh_source_trusted,
                            compression_lvl,
                        )

                else:
                    logger.warning(
                        "> Variable %s from station %s not processed. Add the variable to `variable_conversion` to process it.",
                        var,
                        station_dict["STID"],
                    )

        if fully_processed:
            nb_fully_processed += 1
        else:
            nb_partially_processed += 1

    logger.info(
        "Stats stations: %d fully processed, %d partially processed, %d skipped",
        nb_fully_processed,
        nb_partially_processed,
        nb_skipped,
    )
    logger.info(
        "Stats sensor height source: %d from json data, %d from trusted stations db, %d from trusted history db, %d from providers db, %d from FireBench default. %d trusted, %d untrusted.",
        nb_var_from_data,
        nb_var_from_stations,
        nb_var_from_hist,
        nb_var_from_provider,
        nb_var_from_default,
        nb_var_from_data + nb_var_from_stations + nb_var_from_hist,
        nb_var_from_provider + nb_var_from_default,
    )
    if export_trusted_history:
        with open("tmp_sh_history.json", "w") as f:
            json.dump(trusted_stations_new, f, sort_keys=True, indent=4)


def __get_sensor_height(sensor_variables: dict, variable: str):
    for sensor_var in sensor_variables.values():
        if variable in sensor_var:
            return sensor_var[variable].get("position")
    return None


def __add_sh_to_group(
    group: h5py.Group,
    variable,
    info_dict: dict,
    sensor_height: float,
    sensor_height_units: str,
    sensor_height_source: str,
    trusted_source: int,
    compression_lvl: int,
):
    var_data = np.array(variable, dtype=info_dict["dtype"])
    new_var = group.create_dataset(
        info_dict["std_name"],
        data=var_data,
        **hdf5plugin.Zstd(clevel=compression_lvl),
    )
    new_var.attrs["units"] = info_dict["units"]
    new_var.attrs["sensor_height_source_confidence_lvl"] = SH_TRUST_LVL[trusted_source]
    new_var.attrs["sensor_height"] = sensor_height
    new_var.attrs["sensor_height_units"] = sensor_height_units
    new_var.attrs["sensor_height_source"] = sensor_height_source
