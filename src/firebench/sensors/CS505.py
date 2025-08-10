import numpy as np

from .utils import z_from_cl


def _cs505_scalar(value: float) -> float:
    """
    Return the RMS error for a single fuel moisture value.
    """  # pylint: disable=line-too-long
    if not 0 <= value <= 50:
        raise ValueError("Fuel moisture value must be between 0 and 50 percent")
    if value < 10:
        return 1.22
    if value < 20:
        return 1.82
    if value < 30:
        return 3.04
    return 3.65


def CS505_cl(values: float | int | np.ndarray, cl: float = 95.45, age: float = None) -> float | np.ndarray:
    """
    Compute the half-width of the confidence interval for measurement error
    of the Campbell Scientific CS505 Fuel Moisture Sensor.

    This function uses documented RMS and 90% error bounds for the CS505. The confidence interval
    is estimated assuming normally distributed errors, using:

        max(RMS, d90 / 1.644853) * z

    where `z` is the two-sided z-score corresponding to the specified confidence level.

    Parameters
    ----------
    values : float or int or np.ndarray
        Fuel moisture content value(s), in percent (% by dry weight).
        Must be in the range [0, 50].
    cl : float, optional
        Desired two-sided confidence level, in the range ]0, 100[. Default is 95.45% (2 sigma).
    age : float, optional
        Age of the fuel stick in years. Currently unused; reserved for future support.

    Returns
    -------
    float or np.ndarray
        Half-width of the `cl`% confidence interval for measurement error, in the same
        shape as the input. For scalar input, returns a scalar. For array input, returns
        an array. The total interval is +/- this value.

    Raises
    ------
    ValueError
        If any input value is outside the supported range [0, 50], or if `cl` is not
        in the range ]0, 100[.

    References
    ----------
    CS505 Manual:
    https://s.campbellsci.com/documents/us/manuals/cs505.pdf

    Notes
    -----
    - Measurement uncertainty increases with fuel moisture.
    - Error model assumes bias is negligible.
    """  # pylint: disable=line-too-long
    _ = age  # Placeholder for future use

    if not 0 < cl < 100:
        raise ValueError("Confidence level cl must be between 0 and 100")

    z = z_from_cl(0.01 * cl)

    if isinstance(values, (float, int)):
        rms = _cs505_scalar(values)
        return rms * z

    values = np.asarray(values)
    return np.array([_cs505_scalar(v) * z for v in values])
