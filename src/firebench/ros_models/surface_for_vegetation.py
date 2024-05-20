import numpy as np
import pint


def rothermel_wrf(
    fueldata: dict[str, list[float]],
    fuelclass: int,
    wind: float,
    slope: float,
    fmc: float,
    **opt,
) -> float:
    """
    Compute the rate of spread using Rothermel's model from SFIRE code.

    Parameters
    ----------
    fueldata : dict[str, list[float]]
        Dictionary containing fuel properties. Keys are fuel properties, and values are lists of floats corresponding to different fuel classes.
    fuelclass : int
        Selected fuel class (1-based index).
    wind : float
        Wind speed in the normal direction at 6.1m (20ft) [m/s].
    slope : float
        Slope angle [degrees].
    fmc : float
        Fuel moisture content [%].

    Optional Parameters
    -------------------
    output_opt : int, optional
        Format of output (default: 0, meaning rate of spread value only as float).
    use_wind_reduction_factor : bool, optional
        Flag to use wind reduction factor from fuel data (default: True).

    Returns
    -------
    float
        Rate of spread [m/s]. If output_opt is 1, returns a list containing rate of spread, backing rate of spread, wind coefficient, and slope factor.
    """
    fuelclass -= 1  # Convert to 0-based index

    # Optional parameters
    output_opt = opt.get("output_opt", 0)
    use_wind_reduction_factor = opt.get("use_wrf", True)

    # Fuel category values
    cmbcnst = 17.433e06  # [J/kg]
    tanphi = np.tan(np.deg2rad(slope))
    if use_wind_reduction_factor:
        wind *= fueldata["windrf"][fuelclass]

    fuelmc_g = fmc / 100.0
    fuelheat = cmbcnst * 4.30e-04  # Convert J/kg to BTU/lb
    fuelloadm = fueldata["fgi"][fuelclass]  # Fuel load without moisture

    # Convert units
    fuelload = fuelloadm * 0.3048**2 * 2.205  # to lb/ft^2
    fueldepth = fueldata["fueldepthm"][fuelclass] / 0.3048  # to ft
    betafl = fuelload / (fueldepth * fueldata["fueldens"][fuelclass])  # Packing ratio

    # Calculate various coefficients
    betaop = 3.348 * fueldata["savr"][fuelclass] ** (-0.8189)  # Optimum packing ratio
    qig = 250.0 + 1116.0 * fuelmc_g  # Heat of preignition, BTU/lb
    epsilon = np.exp(-138.0 / fueldata["savr"][fuelclass])  # Effective heating number
    rhob = fuelload / fueldepth  # Ovendry bulk density, lb/ft^3
    c = 7.47 * np.exp(-0.133 * fueldata["savr"][fuelclass] ** 0.55)  # Wind coefficient constant
    bbb = 0.02526 * fueldata["savr"][fuelclass] ** 0.54  # Wind coefficient constant
    e = 0.715 * np.exp(-3.59e-4 * fueldata["savr"][fuelclass])  # Wind coefficient constant
    phiwc = c * (betafl / betaop) ** (-e)
    rtemp2 = fueldata["savr"][fuelclass] ** 1.5
    gammax = rtemp2 / (495.0 + 0.0594 * rtemp2)  # Maximum reaction velocity, 1/min
    a = 1.0 / (4.774 * fueldata["savr"][fuelclass] ** 0.1 - 7.27)  # Coefficient for optimum reaction velocity
    ratio = betafl / betaop
    gamma = gammax * (ratio**a) * np.exp(a * (1.0 - ratio))  # Optimum reaction velocity, 1/min
    wn = fuelload / (1.0 + fueldata["st"][fuelclass])  # Net fuel loading, lb/ft^2
    rtemp1 = fuelmc_g / fueldata["fuelmce"][fuelclass]
    etam = min(1, max(0, 1.0 - 2.59 * rtemp1 + 5.11 * rtemp1**2 - 3.52 * rtemp1**3))  # Moisture damping coefficient
    etas = 0.174 * fueldata["se"][fuelclass] ** (-0.19)  # Mineral damping coefficient
    ir = gamma * wn * fuelheat * etam * etas  # Reaction intensity, BTU/ft^2 min
    irm = ir * 1055.0 / (0.3048**2 * 60.0) * 1e-6  # For MW/m^2 (set but not used)
    xifr = np.exp((0.792 + 0.681 * fueldata["savr"][fuelclass] ** 0.5) * (betafl + 0.1)) / (
        192.0 + 0.2595 * fueldata["savr"][fuelclass]
    )  # Propagating flux ratio
    r_0 = ir * xifr / (rhob * epsilon * qig)  # Default spread rate in ft/min

    if fueldata["ichap"][fuelclass] == 0:
        # If wind is 0 or into fireline, phiw = 0, and this reduces to backing rate of spread.
        spdms = max(wind, 0.0)
        umidm = min(spdms, 30.0)  # Max input wind speed is 30 m/s
        umid = umidm * 196.850  # m/s to ft/min
        phiw = umid**bbb * phiwc  # Wind coefficient
        phis = 5.275 * betafl ** (-0.3) * max(0.0, tanphi) ** 2  # Slope factor
        ros = r_0 * (1.0 + phiw + phis) * 0.00508  # Spread rate, m/s
    else:
        # Spread rate has no dependency on fuel character, only windspeed
        spdms = max(wind, 0.0)
        ros = max(0.03333, 1.2974 * spdms**1.41)  # Spread rate, m/s
        phiw, phis = np.nan, np.nan

    # Output options
    if output_opt == 1:
        return [min(ros, 6.0), r_0 * 0.00508, phiw, phis]

    # Default
    return min(ros, 6.0)