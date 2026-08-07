from pathlib import Path
import json
from datetime import datetime
from tempfile import NamedTemporaryFile

import numpy as np
import hdf5plugin
import h5py
import pytz

from ..tools import StandardVariableNames as svn
from ..tools import logger, calculate_sha256
from .std_file_info import TIME_SERIES
from .time import datetime_to_iso8601
from .synoptic_data import VARIABLE_CONVERSION
from .sensor_height import (
    SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE,
    SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE,
    parse_sensor_height_confidence,
    sensor_height_confidence_description,
)
from .sensor_height_resources import (
    SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION,
    load_sensor_height_resources,
    resolve_sensor_height,
    validate_sensor_height_resource,
)


def standardize_synoptic_raws_from_json(
    json_path: Path,
    h5file: h5py.File,
    skip_stations: list[str] = None,
    overwrite: bool = False,
    fb_var_info: dict = VARIABLE_CONVERSION,
    compression_lvl: int = 3,
):
    if not skip_stations:
        skip_stations = []

    sha_source_file = calculate_sha256(json_path.resolve())
    with open(json_path.resolve(), "r") as f:
        data = json.load(f)

    if TIME_SERIES in h5file["/"]:
        probes = h5file[f"/{TIME_SERIES}"]
    else:
        probes = h5file.create_group(TIME_SERIES)

    sensor_height_resources = load_sensor_height_resources()
    source_reference = f"{json_path.name}#sha256={sha_source_file}"
    verification_date = datetime.now().astimezone().date().isoformat()

    # for statistics
    nb_fully_processed = 0
    nb_partially_processed = 0
    nb_skipped = 0
    nb_var_from_data = 0
    nb_var_from_stations = 0
    nb_var_from_hist = 0
    nb_var_from_provider = 0
    nb_var_from_default = 0

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
                dts = []

                for t in station_dict["OBSERVATIONS"]["date_time"]:
                    # differentiates between YYYYMMDDHHMMSS or extended ISO 8601
                    if t.endswith("Z"):  # Detects if format in UTC timezone
                        fmt = "%Y%m%d%H%M%SZ" if t[:-1].isdigit() else "%Y-%m-%dT%H:%M:%SZ"
                        dt_temp = pytz.utc.localize(datetime.strptime(t, fmt)).astimezone(tz)

                    else:  # Assumes local timezone
                        fmt = "%Y%m%d%H%M%S" if t.isdigit() else "%Y-%m-%dT%H:%M:%S"
                        dt_temp = tz.localize(datetime.strptime(t, fmt))

                    dts.append(dt_temp)

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
                    if sensor_height is None:
                        logger.warning(
                            "Missing sensor height info for variable %s from station %s . Looking for values in FireBench databases.",
                            var,
                            station_dict["STID"],
                        )
                        fully_processed = False

                    resolution = resolve_sensor_height(
                        station=station_dict["STID"],
                        variable=var,
                        provider=provider,
                        synoptic_height=sensor_height,
                        synoptic_source_reference=source_reference if sensor_height is not None else None,
                        verification_date=verification_date,
                        resources=sensor_height_resources,
                    )
                    if resolution.source == "from_data":
                        nb_var_from_data += 1
                    elif resolution.source == "firebench_trusted_stations":
                        nb_var_from_stations += 1
                    elif resolution.source == "firebench_trusted_history":
                        nb_var_from_hist += 1
                    elif resolution.source == "firebench_providers_default":
                        nb_var_from_provider += 1
                    else:
                        nb_var_from_default += 1

                    __add_sh_to_group(
                        new_station,
                        station_dict["OBSERVATIONS"][var],
                        fb_var_info[var],
                        resolution.height,
                        resolution.units,
                        resolution.source,
                        resolution.confidence,
                        compression_lvl,
                        sensor_height_provenance={
                            "provider": resolution.provider,
                            "source_reference": resolution.source_reference,
                            "source_date": resolution.source_date,
                            "verification_date": resolution.verification_date,
                            "reviewer_or_authority": resolution.reviewer_or_authority,
                            "notes": resolution.notes,
                            "record_id": resolution.record_id,
                        },
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


def export_synoptic_sensor_height_proposal(
    json_path: Path,
    proposal_path: Path,
    *,
    verification_date: str,
    reviewer_or_authority: str,
    source_date: str | None = None,
    notes: str | None = None,
    overwrite: bool = False,
) -> int:
    """Export Synoptic metadata as an auditable, non-active history proposal.

    The caller supplies the review identity and dates explicitly. Records remain
    ``proposed`` until a maintainer reviews the evidence and changes their status
    to ``active`` in the trusted-history resource.
    """

    json_path = Path(json_path).resolve()
    proposal_path = Path(proposal_path).resolve()
    if proposal_path.exists() and not overwrite:
        raise FileExistsError(f"Sensor-height proposal already exists: {proposal_path}")

    sha_source_file = calculate_sha256(json_path)
    with open(json_path, "r", encoding="utf-8") as source_file:
        data = json.load(source_file)

    records = []
    for station in data["STATION"]:
        station_id = station["STID"]
        try:
            provider = str(station["PROVIDERS"][0]["name"])
        except (KeyError, IndexError, TypeError):
            provider = "Synoptic"
        for variable in station.get("OBSERVATIONS", {}):
            if variable not in VARIABLE_CONVERSION:
                continue
            sensor_height = __get_sensor_height(station.get("SENSOR_VARIABLES", {}), variable)
            if sensor_height is None:
                continue
            records.append(
                {
                    "record_id": f"synoptic-{station_id}-{variable}",
                    "station": station_id,
                    "provider": provider,
                    "variables": [variable],
                    "height": float(sensor_height),
                    "units": "m",
                    "confidence": 2,
                    "status": "proposed",
                }
            )

    proposal = {
        "schema_version": SENSOR_HEIGHT_RESOURCE_SCHEMA_VERSION,
        "record_type": "historical",
        "provenance": {
            "source_reference": f"{json_path.name}#sha256={sha_source_file}",
            "source_date": source_date,
            "verification_date": verification_date,
            "reviewer_or_authority": reviewer_or_authority,
            "notes": notes
            or "Generated from Synoptic sensor metadata; records require maintainer activation.",
        },
        "records": records,
    }
    validate_sensor_height_resource(proposal, expected_type="historical")

    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=proposal_path.parent,
            prefix=f".{proposal_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(proposal, temp_file, indent=2)
            temp_file.write("\n")
        temp_path.replace(proposal_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return len(records)


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
    sensor_height_provenance: dict | None = None,
):
    var_data = np.array(variable, dtype=info_dict["dtype"])
    new_var = group.create_dataset(
        info_dict["std_name"],
        data=var_data,
        **hdf5plugin.Zstd(clevel=compression_lvl),
    )
    new_var.attrs["units"] = info_dict["units"]
    confidence = parse_sensor_height_confidence(
        trusted_source,
        station=group.name,
        variable=info_dict["std_name"],
    )
    new_var.attrs[SENSOR_HEIGHT_CONFIDENCE_ATTRIBUTE] = int(confidence)
    new_var.attrs[SENSOR_HEIGHT_CONFIDENCE_DESCRIPTION_ATTRIBUTE] = sensor_height_confidence_description(
        confidence
    )
    new_var.attrs["sensor_height"] = sensor_height
    new_var.attrs["sensor_height_units"] = sensor_height_units
    new_var.attrs["sensor_height_source"] = sensor_height_source
    if sensor_height_provenance:
        for field, value in sensor_height_provenance.items():
            if value is not None:
                new_var.attrs[f"sensor_height_{field}"] = value
