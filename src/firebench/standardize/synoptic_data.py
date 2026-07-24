import numpy as np

from ..tools import StandardVariableNames as svn
from .sensor_height import SensorHeightConfidence

DEFAULT_SENSOR_HEIGHT_UNIT = "m"

SH_TRUST_HIGHEST = SensorHeightConfidence.VERIFIED

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
