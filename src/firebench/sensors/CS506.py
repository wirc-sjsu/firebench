def CS506_rms(value: float, age: float = None) -> float:
    """
    Return the root-mean-square (RMS) measurement error of the Campbell Scientific CS506
    Fuel Moisture Sensor, using a 26601 10-hour fuel moisture stick.

    Parameters
    ----------
    value : float
        Fuel moisture content, in percent (% by dry weight).
        Must be between 0 and 50 inclusive.
    age : float, optional
        Age of the fuel stick, in years. This parameter is currently unused because
        no age-dependent sensitivity is documented for the CS506 sensor.

    Returns
    -------
    float
        RMS error in fuel moisture measurement, in percentage points of moisture content.

    Raises
    ------
    ValueError
        If the input fuel moisture value is outside the supported range [0, 50].

    Reference
    ---------
    CS506 Manual:
    https://s.campbellsci.com/documents/ca/manuals/cs506_man.pdf

    Notes
    -----
    The sensor uses piecewise equations depending on the fuel moisture content range,
    and a discontinuity may occur around 5% as noted in the documentation:
    "A sudden small increase or decrease in the measured water content near 5% is to be
    expected as the datalogger changes from one equation to the other." No specific
    uncertainty is provided for this transition, so standard RMS values are returned.
    """  # pylint: disable=line-too-long
    _ = age  # Placeholder for future age-dependent uncertainty
    if value < 0 or value > 50:
        raise ValueError("Fuel moisture value must be between 0 and 50 percent (inclusive).")

    if value < 10:
        return 0.74
    if value < 20:
        return 0.90
    if value < 30:
        return 1.94
    return 2.27


def CS506_range90(value: float, age: float = None) -> float:
    """
    Return the 90% confidence range of measurement error for the Campbell Scientific CS506
    Fuel Moisture Sensor, using a 26601 10-hour fuel moisture stick.

    This value represents the absolute error bounds within which 90% of sensor measurements
    are expected to fall, based on documented performance in specified fuel moisture intervals.

    Parameters
    ----------
    value : float
        Fuel moisture content, in percent (% by dry weight).
        Must be between 0 and 50 inclusive.
    age : float, optional
        Age of the fuel stick, in years. This parameter is currently unused because
        no age-dependent sensitivity is documented for the CS506 sensor.

    Returns
    -------
    float
        Half-width of the 90% confidence interval for measurement error, in percentage points
        of fuel moisture content. The total interval is +/- this value.

    Raises
    ------
    ValueError
        If the input fuel moisture value is outside the supported range [0, 50].

    Reference
    ---------
    CS506 Manual:
    https://s.campbellsci.com/documents/ca/manuals/cs506_man.pdf

    Notes
    -----
    This function uses piecewise constant uncertainty values for different fuel moisture
    intervals. The documentation indicates a discontinuity in the measurement behavior near 5%,
    but no specific confidence range is given for that effect.
    """  # pylint: disable=line-too-long
    _ = age  # Placeholder for future age-dependent uncertainty
    if value < 0 or value > 50:
        raise ValueError("Fuel moisture value must be between 0 and 50 percent (inclusive).")

    if 0 <= value < 10:
        return 1.25
    if value < 20:
        return 2.00
    if value < 30:
        return 3.40
    return 4.11
