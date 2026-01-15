from importlib.resources import files
import numpy as np
import json
from ..tools import StandardVariableNames as svn

DEFAULT_SENSOR_HEIGHT_UNIT = "m"

SH_TRUST_HIGHEST = 2
SH_TRUST_LVL = [
    "0 - unknown (guessed or missing metadata)",
    "1 - provider default (not verified)",
    "2 - verified measurement",
]

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
        "default_sensor_height": 10,
    },
    "wind_speed_set_1": {
        "std_name": svn.WIND_SPEED.value,
        "units": "m/s",
        "dtype": np.float64,
        "default_sensor_height": 10,
    },
    "wind_gust_set_1": {
        "std_name": svn.WIND_GUST.value,
        "units": "m/s",
        "dtype": np.float64,
        "default_sensor_height": 10,
    },
    "solar_radiation_set_1": {
        "std_name": svn.SOLAR_RADIATION.value,
        "units": "W/m^2",
        "dtype": np.float64,
        "default_sensor_height": 2,
    },
    "fuel_moisture_set_1": {
        "std_name": svn.FUEL_MOISTURE_CONTENT_10H.value,
        "units": "percent",
        "dtype": np.float64,
        "default_sensor_height": 0.3,
    },
}


# station trusted sensor height information. Best source of information
def load_sensor_height_stations() -> dict:
    path = files("firebench").joinpath("resources/wx_sensor_height_stations.json")
    return json.loads(path.read_text(encoding="utf-8"))


# station trusted history. Contains only trusted information from previous json parsing
def load_sensor_height_trusted_history() -> dict:
    path = files("firebench").joinpath("resources/wx_sensor_height_trusted_history.json")
    return json.loads(path.read_text(encoding="utf-8"))


# Provider based information. Not reliable.
def load_sensor_height_providers() -> dict:
    path = files("firebench").joinpath("resources/wx_sensor_height_providers.json")
    return json.loads(path.read_text(encoding="utf-8"))
