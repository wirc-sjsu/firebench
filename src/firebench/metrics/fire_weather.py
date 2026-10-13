"""
Fire-weather quantities computed from surface weather variables.

Every function takes arrays in fixed units (air temperature in degC, relative humidity in percent,
wind speed in m/s) and returns an array, so the same computation applies to a model output and to
observations. A NaN input gives a NaN output.
"""

import numpy as np

# Bolton (1980), eq. 10: saturation vapour pressure over liquid water, in hPa.
_ES_REFERENCE_HPA = 6.112
_ES_COEFFICIENT = 17.67
_ES_OFFSET_DEGC = 243.5
# Fosberg (1978): the index is 100 for a moisture damping of 1 and a wind speed of 30 mph.
_FOSBERG_NORMALIZATION = 0.3002
_FOSBERG_MOISTURE_REFERENCE_PERCENT = 30.0
_MPH_PER_MS = 3600.0 / 1609.344


def saturation_vapor_pressure(air_temperature):
    """
    Saturation vapour pressure over liquid water, from Bolton (1980).

    Parameters
    ----------
    air_temperature : array_like
        Air temperature [degC].

    Returns
    -------
    numpy.ndarray
        Saturation vapour pressure [hPa].
    """  # pylint: disable=line-too-long
    temperature = np.asarray(air_temperature, dtype=np.float64)
    return _ES_REFERENCE_HPA * np.exp(_ES_COEFFICIENT * temperature / (temperature + _ES_OFFSET_DEGC))


def vapor_pressure_deficit(air_temperature, relative_humidity):
    """
    Vapour pressure deficit: the saturation vapour pressure minus the actual vapour pressure.

    Parameters
    ----------
    air_temperature : array_like
        Air temperature [degC].
    relative_humidity : array_like
        Relative humidity [percent].

    Returns
    -------
    numpy.ndarray
        Vapour pressure deficit [hPa].
    """  # pylint: disable=line-too-long
    humidity = np.asarray(relative_humidity, dtype=np.float64)
    return saturation_vapor_pressure(air_temperature) * (1.0 - humidity / 100.0)


def equilibrium_moisture_content(air_temperature, relative_humidity):
    """
    Equilibrium moisture content of fine dead fuel, from Simard (1968), as the Fosberg index uses it.

    Parameters
    ----------
    air_temperature : array_like
        Air temperature [degC].
    relative_humidity : array_like
        Relative humidity [percent].

    Returns
    -------
    numpy.ndarray
        Equilibrium moisture content [percent].
    """  # pylint: disable=line-too-long
    fahrenheit = np.asarray(air_temperature, dtype=np.float64) * 1.8 + 32.0
    humidity = np.asarray(relative_humidity, dtype=np.float64)
    dry = 0.03229 + 0.281073 * humidity - 0.000578 * humidity * fahrenheit
    moderate = 2.22749 + 0.160107 * humidity - 0.01478 * fahrenheit
    moist = 21.0606 + 0.005565 * humidity**2 - 0.00035 * humidity * fahrenheit - 0.483199 * humidity
    return np.where(humidity < 10.0, dry, np.where(humidity <= 50.0, moderate, moist))


def fosberg_fire_weather_index(air_temperature, relative_humidity, wind_speed):
    """
    Fosberg fire weather index (Fosberg, 1978).

    The index combines a moisture damping term, computed from the equilibrium moisture content, with
    the wind speed. It is not capped: it exceeds 100 above 30 mph in very dry air. The original
    index uses the 20 ft wind; the caller decides which wind height is given.

    Parameters
    ----------
    air_temperature : array_like
        Air temperature [degC].
    relative_humidity : array_like
        Relative humidity [percent].
    wind_speed : array_like
        Wind speed [m/s].

    Returns
    -------
    numpy.ndarray
        Fosberg fire weather index [-].
    """  # pylint: disable=line-too-long
    moisture = (
        equilibrium_moisture_content(air_temperature, relative_humidity)
        / _FOSBERG_MOISTURE_REFERENCE_PERCENT
    )
    damping = 1.0 - 2.0 * moisture + 1.5 * moisture**2 - 0.5 * moisture**3
    mph = np.asarray(wind_speed, dtype=np.float64) * _MPH_PER_MS
    return damping * np.sqrt(1.0 + mph**2) / _FOSBERG_NORMALIZATION
