import numpy as np

from ..tools.namespace import StandardVariableNames as svn
from ..tools.units import ureg
from ..tools.input_info import ParameterType

from .rate_of_spread_model import RateOfSpreadModel


class Rothermel_SFIRE(RateOfSpreadModel):
    """
    A class to represent the Rothermel's model for fire spread rate calculation used in SFIRE code.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Attributes
    ----------
    metadata : dict
        A dictionary containing metadata for various fuel properties such as wind reduction factor, dry fuel load, fuel height,
        fuel density, surface area to volume ratio, fuel moisture content, total mineral content, effective mineral content,
        and Chaparral flag. Each entry in the dictionary provides a description, units, and acceptable range for the property.

    Methods
    -------
    compute_ros(fueldata, fuelclass, wind, slope, fmc, **opt) -> float
        Compute the rate of spread of fire using Rothermel's model.
    """  # pylint: disable=line-too-long

    metadata = {
        "fgi": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.kilogram / ureg.meter**2,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldepthm": {
            "std_name": svn.FUEL_HEIGHT,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldens": {
            "std_name": svn.FUEL_DENSITY,
            "units": ureg.pound / ureg.foot**3,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "savr": {
            "std_name": svn.FUEL_SURFACE_AREA_VOLUME_RATIO,
            "units": 1 / ureg.foot,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fuelmce": {
            "std_name": svn.FUEL_MOISTURE_EXTINCTION,
            "units": ureg.percent,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "st": {
            "std_name": svn.FUEL_MINERAL_CONTENT_TOTAL,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "se": {
            "std_name": svn.FUEL_MINERAL_CONTENT_EFFECTIVE,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "ichap": {
            "std_name": svn.FUEL_CHAPARRAL_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (-90, 90),
            "type": ParameterType.input,
        },
        "fmc": {
            "std_name": svn.FUEL_MOISTURE_CONTENT,
            "units": ureg.percent,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def rothermel(
        fgi: float,
        fueldepthm:float,
        fueldens: float,
        savr:float,
        fuelmce: float,
        st: float,
        se: float,
        ichap: int,
        wind: float,
        slope: float,
        fmc: float,
        **opt,
    ) -> float:
        """
    Compute the rate of spread using Rothermel's model.

    This function calculates the forward rate of spread of a fire in a uniform fuel bed using
    Rothermel's (1972) fire spread model. The model considers fuel properties, wind speed, slope,
    and fuel moisture content to estimate the rate at which a fire will spread through wildland fuels.

    Parameters
    ----------
    fgi : float
        Total fuel load (dry weight) per unit area [kg m-2].
        Represents the total mass of combustible material available to the fire.

    fueldepthm : float
        Fuel bed depth [m].
        The vertical depth of the fuel bed perpendicular to the ground surface.

    fueldens : float
        Oven-dry fuel particle density [lb ft-3].
        The density of individual fuel particles when completely dry.

    savr : float
        Surface-area-to-volume ratio [ft-1].
        A measure of the fineness of the fuel particles; higher values indicate finer fuels.

    fuelmce : float
        Moisture content of extinction [%].
        The fuel moisture content at which a fire will no longer spread.

    st : float
        Total mineral content [unitless, between 0 and 1].
        The proportion of the fuel that is composed of mineral (inorganic) material.

    se : float
        Effective mineral content [unitless, between 0 and 1].
        The proportion of mineral content that effectively absorbs heat.

    ichap : int
        Chaparral flag (0 or 1).
        Indicator for chaparral fuel type: set to 1 if the fuel is chaparral, otherwise 0.

    wind : float
        Wind speed at midflame height or average wind over flame height [m s-1].
        The wind speed influencing the fire spread at the height of the flames.

    slope : float
        Slope steepness [degrees].
        The angle of the terrain slope; positive for uphill, negative for downhill.

    fmc : float
        Fuel moisture content [%].
        The actual moisture content of the fuel affecting combustion.

    **opt : dict, optional
        Additional optional parameters.

    Returns
    -------
    float
        Rate of spread [m/s].
        The estimated forward rate of spread of the fire.

    References
    ----------
    Rothermel, R. C. (1972).
    *A mathematical model for predicting fire spread in wildland fuels*.
    USDA Forest Service Research Paper INT-115. Ogden, UT.
    """  # pylint: disable=line-too-long
        # Fuel category values
        cmbcnst = 17.433e06  # [J/kg]
        tanphi = np.tan(np.deg2rad(slope))

        fuelmc_g = fmc * 0.01
        fuelheat = cmbcnst * 4.30e-04  # Convert J/kg to BTU/lb

        # Convert units
        fuelload = fgi * 0.3048**2 * 2.205  # to lb/ft^2
        fueldepth = fueldepthm / 0.3048  # to ft
        betafl = fuelload / (fueldepth * fueldens)  # Packing ratio

        # Calculate various coefficients
        betaop = 3.348 * savr ** (-0.8189)  # Optimum packing ratio
        qig = 250.0 + 1116.0 * fuelmc_g  # Heat of preignition, BTU/lb
        epsilon = np.exp(-138.0 / savr)  # Effective heating number
        rhob = fuelload / fueldepth  # Ovendry bulk density, lb/ft^3
        c = 7.47 * np.exp(-0.133 * savr ** 0.55)  # Wind coefficient constant
        bbb = 0.02526 * savr ** 0.54  # Wind coefficient constant
        e = 0.715 * np.exp(-3.59e-4 * savr)  # Wind coefficient constant
        phiwc = c * (betafl / betaop) ** (-e)
        rtemp2 = savr ** 1.5
        gammax = rtemp2 / (495.0 + 0.0594 * rtemp2)  # Maximum reaction velocity, 1/min
        a = 1.0 / (
            4.774 * savr ** 0.1 - 7.27
        )  # Coefficient for optimum reaction velocity
        ratio = betafl / betaop
        gamma = gammax * (ratio**a) * np.exp(a * (1.0 - ratio))  # Optimum reaction velocity, 1/min
        wn = fuelload / (1.0 + st)  # Net fuel loading, lb/ft^2
        rtemp1 = fuelmc_g / fuelmce
        etam = min(
            1, max(0, 1.0 - 2.59 * rtemp1 + 5.11 * rtemp1**2 - 3.52 * rtemp1**3)
        )  # Moisture damping coefficient
        etas = 0.174 * se ** (-0.19)  # Mineral damping coefficient
        ir = gamma * wn * fuelheat * etam * etas  # Reaction intensity, BTU/ft^2 min
        irm = ir * 1055.0 / (0.3048**2 * 60.0) * 1e-6  # For MW/m^2 (set but not used)
        xifr = np.exp((0.792 + 0.681 * savr ** 0.5) * (betafl + 0.1)) / (
            192.0 + 0.2595 * savr
        )  # Propagating flux ratio
        r_0 = ir * xifr / (rhob * epsilon * qig)  # Default spread rate in ft/min

        if ichap == 0:
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

        # Default
        return min(ros, 6.0)

    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        fuel_cat: int = None,
        **opt,
    ) -> float:
        """
    Compute the rate of spread of fire using Rothermel's model.

    This function serves as a wrapper that prepares the fuel data dictionary and calls the `rothermel` method.
    It extracts the necessary fuel properties from `input_dict`, optionally selecting a specific fuel category,
    and computes the rate of spread (ROS) of the fire.

    Parameters
    ----------
    input_dict : dict
        Dictionary containing the input data for various fuel properties.
        The keys should be the standard variable names as defined in `Rothermel_SFIRE.metadata`.
        Each value can be a single float/int or a list/array of floats/ints.

    fuel_cat : int, optional
        Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
        and the function will extract the properties corresponding to the specified fuel category.
        If not provided, fuel properties are expected to be scalar values.

    **opt : dict
        Additional optional parameters to be passed to the `rothermel` method.

    Returns
    -------
    float
        The computed rate of spread of fire [m/s].

    Notes
    -----
    - `fuel_cat` uses one-based indexing to align with natural fuel category numbering.
      When accessing lists or arrays in `input_dict`, the index is adjusted accordingly (i.e., `index = fuel_cat - 1`).
    - This function assumes that all necessary error handling (such as checking for missing keys,
      valid indices, or correct data types) has been performed prior to calling it.
    - The function expects that the keys in `input_dict` correspond to the standard variable names
      defined in `Rothermel_SFIRE.metadata` for each fuel property.
    - The `rothermel` method computes the rate of spread using the provided fuel properties,
      wind speed (`wind`), slope angle (`slope`), and fuel moisture content (`fmc`).

    Examples
    --------
    **Example with scalar fuel properties:**

    ```python
    input_data = {
        svn.FUEL_LOAD_DRY_TOTAL: 0.5,           # fgi
        svn.FUEL_HEIGHT: 0.3,                   # fueldepthm
        svn.FUEL_DENSITY: 32.0,                 # fueldens
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO: 2000.0,  # savr
        svn.FUEL_MOISTURE_EXTINCTION: 30.0,     # fuelmce
        svn.FUEL_MINERAL_CONTENT_TOTAL: 0.0555, # st
        svn.FUEL_MINERAL_CONTENT_EFFECTIVE: 0.01,    # se
        svn.FUEL_CHAPARRAL_FLAG: 0,             # ichap
        svn.WIND_SPEED: 2.0,
        svn.SLOPE_ANGLE: 15.0,
        svn.FUEL_MOISTURE_CONTENT: 10.0,
    }
    ros = Rothermel_SFIRE.compute_ros(input_data)
    print(f"The rate of spread is {ros:.4f} m/s")
    ```

    **Example with fuel categories:**

    ```python
    input_data = {
        svn.FUEL_LOAD_DRY_TOTAL: [0.4, 0.5, 0.6],           # fgi
        svn.FUEL_HEIGHT: [0.2, 0.3, 0.4],                   # fueldepthm
        svn.FUEL_DENSITY: [30.0, 32.0, 34.0],               # fueldens
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [1800.0, 2000.0, 2200.0],  # savr
        svn.FUEL_MOISTURE_EXTINCTION: [25.0, 30.0, 35.0],   # fuelmce
        svn.FUEL_MINERAL_CONTENT_TOTAL: [0.05, 0.0555, 0.06],     # st
        svn.FUEL_MINERAL_CONTENT_EFFECTIVE: [0.009, 0.01, 0.011],  # se
        svn.FUEL_CHAPARRAL_FLAG: [0, 0, 1],                 # ichap
        svn.WIND_SPEED: 2.0,
        svn.SLOPE_ANGLE: 15.0,
        svn.FUEL_MOISTURE_CONTENT: 10.0,
    }
    fuel_category = 2  # One-based index
    ros = Rothermel_SFIRE.compute_ros(input_data, fuel_cat=fuel_category)
    print(f"The rate of spread for fuel category {fuel_category} is {ros:.4f} m/s")
    ```

    """
        # list properties linked to fuel category
        fuel_properties_list = [
            "fgi",
            "fueldepthm",
            "fueldens",
            "savr",
            "fuelmce",
            "st",
            "se",
            "ichap",
        ]
        fuel_properties_dict = {}
        for var in fuel_properties_list:
            if fuel_cat is not None:
                # get the property of the fuel category
                fuel_properties_dict[var] = input_dict[Rothermel_SFIRE.metadata[var]["std_name"]][fuel_cat-1]
            else:
                # get the property from dict
                fuel_properties_dict[var] = input_dict[Rothermel_SFIRE.metadata[var]["std_name"]]

        return Rothermel_SFIRE.rothermel(
            **fuel_properties_dict,
            wind=input_dict[svn.WIND_SPEED],
            slope=input_dict[svn.SLOPE_ANGLE],
            fmc=input_dict[svn.FUEL_MOISTURE_CONTENT],
            **opt,
        )


class Balbi_2022_fixed_SFIRE(RateOfSpreadModel):
    """
    A class to represent the Balbi's model for fire spread rate calculation used in SFIRE code.

    This version is based on Chatelon et al. 2022.
    To prevent negative value of rate of spread, the following modifications have been applied:
        - the tile angle gamma is bouded to 0
        - the radiative contribution to ros Rc is bounded to 0

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Attributes
    ----------
    metadata : dict
        A dictionary containing metadata for various fuel properties such as wind reduction factor, dry fuel load, fuel height,
        fuel density, surface area to volume ratio, fuel moisture content, total mineral content, effective mineral content,
        and Chaparral flag. Each entry in the dictionary provides a description, units, and acceptable range for the property.

    Methods
    -------
    compute_ros(fueldata, fuelclass, wind, slope, fmc, **opt) -> float
        Compute the rate of spread of fire using Rothermel's model.
    """  # pylint: disable=line-too-long

    metadata = {
        "windrf": {
            "std_name": svn.FUEL_WIND_REDUCTION_FACTOR,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "fgi": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.kilogram / ureg.meter**2,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldepthm": {
            "std_name": svn.FUEL_HEIGHT,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fueldens": {
            "std_name": svn.FUEL_DENSITY,
            "units": ureg.kilogram / ureg.meter**3,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "savr": {
            "std_name": svn.FUEL_SURFACE_AREA_VOLUME_RATIO,
            "units": 1 / ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (-90, 90),
            "type": ParameterType.input,
        },
        "fmc": {
            "std_name": svn.FUEL_MOISTURE_CONTENT,
            "units": ureg.percent,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def balbi_2022_fixed(
        fueldata: dict[str, list[float]],
        fuelclass: int,
        wind: float,
        slope: float,
        fmc: float,
        **opt,
    ) -> float:
        """
        Compute the rate of spread using the Balbi's model from SFIRE code.

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
        dead_fuel_load_ratio : float, optional
            dead fuel load ratio, ie sigma_d/sigma_t, between 0 and 1 (default 1).
        max_ite : int, optional
            maximum number of iteration for the fixed point method.

        Returns
        -------
        float
            Rate of spread [m/s]
        """  # pylint: disable=line-too-long
        ## Physical parameters
        boltz = 5.670373e-8  # Stefan-Boltzman constant         [W m-2 K-4]
        tau0 = 75591.0  # Anderson's residence time coefficient [s m-1]
        Cpa = 1150.0  # Specific heat of air                    [J kg-1 K-1]
        Tvap = 373.15  # Liquid water evaporation temperature   [K]
        g = 9.81  # Gravitational acceleration                  [m s-2]
        Cp = 1200  # Specific heat of fuel                      [J kg-1 K-1]
        Cpw = 4180.0  # Specific heat of liquid water           [J kg-1 K-1]
        delta_h = 2.3e6  # Heat of latent evaporation           [J kg-1]
        delta_H = 1.7433e07  # Heat of combustion               [J kg-1]
        Ti = 600.0  # Ignition temperature                      [K]
        ## Model parameter
        st = 17.0  # Stoichiometric coefficient                 [-]
        scal_am = 0.025  # scaling factor am                    [-]
        tol = 1e-4  # tolerance for fixed point method          [-]
        r00 = 2.5e-5  # Model parameter
        chi0 = 0.3  # Radiative factor                          [-]
        w0 = 50  # Ignition line width                           [m]
        ## Atm
        Ta = 300.0  # Air temperature                           [K]
        rhoa = 1.125  # Air density                             [kg m-3]

        # index starts at 0
        fuelclass -= 1

        # fmc from percent to real
        fmc *= 0.01

        # Add moisture to oven dry fuel load
        sigma_t = fueldata["fgi"][fuelclass] * (1 + fmc)

        # dead fuel load
        sigma_d = sigma_t * opt.get("dead_fuel_load_ratio", 1)

        # max number of iteration
        maxite = opt.get("max_ite", 20)

        ## preliminary
        alpha_rad = np.deg2rad(slope)

        # Packing ratios
        beta = sigma_d / (fueldata["fueldepthm"][fuelclass] * fueldata["fueldens"][fuelclass])  # dead fuel
        beta_t = sigma_t / (
            fueldata["fueldepthm"][fuelclass] * fueldata["fueldens"][fuelclass]
        )  # total fuel

        # Leaf areas
        lai = fueldata["savr"][fuelclass] * fueldata["fueldepthm"][fuelclass] * beta  # dead fuel
        lai_t = fueldata["savr"][fuelclass] * fueldata["fueldepthm"][fuelclass] * beta_t  # total fuel

        ## Heat sink
        q = Cp * (Ti - Ta) + fmc * (delta_h + Cpw * (Tvap - Ta))

        # Flame temperature
        Tflame = Ta + (delta_H * (1 - chi0)) / (Cpa * (1 + st))

        # Base flame radiation
        Rb = (
            min(lai_t / (2 * np.pi), 1)
            * (lai / lai_t) ** 2
            * boltz
            * Tflame**4
            / (beta * fueldata["fueldens"][fuelclass] * q)
        )

        # Radiant factor
        A = min(lai / (2 * np.pi), lai / lai_t) * chi0 * delta_H / (4 * q)

        # vertical velocity
        u0 = (
            2
            * (st + 1)
            * fueldata["fueldens"][fuelclass]
            * Tflame
            * min(lai, 2 * np.pi * lai / lai_t)
            / (tau0 * rhoa * Ta)
        )

        # tilt angle
        gamma = max(0, np.arctan(np.tan(alpha_rad) + wind / u0))

        # flame height and length
        flame_height = (u0**2) / (g * (Tflame / Ta - 1) * np.cos(alpha_rad) ** 2)
        flame_length = flame_height / np.cos(gamma - alpha_rad)

        # view factor
        view_factor = 1 - np.sin(gamma) + np.cos(gamma)

        # Rr denom term
        denom_term_Rr = np.cos(gamma) / (fueldata["savr"][fuelclass] * r00)

        # main term Rc
        main_term_Rc = (
            scal_am
            * min(w0 / 50, 1)
            * delta_H
            * rhoa
            * Ta
            * fueldata["savr"][fuelclass]
            * np.sqrt(fueldata["fueldepthm"][fuelclass])
            / (2 * q * (1 + st) * fueldata["fueldens"][fuelclass] * Tflame)
        )

        # second term
        scd_term_Rc = (
            min(2 * np.pi * lai / lai_t, lai)
            * np.tan(gamma)
            * (1 + st)
            * fueldata["fueldens"][fuelclass]
            * Tflame
            / (rhoa * Ta * tau0)
        )

        # exp term
        exp_term_Rc = -beta_t / (min(w0 / 50, 1))

        # Solve the fixed point algo with starting point Rb
        ros = Rb
        failstatus = True
        for i in range(maxite):
            # compute Rr
            Rr = A * ros * view_factor / (1 + ros * denom_term_Rr)

            # Compute Rc
            Rc = max(0, main_term_Rc * (scd_term_Rc + wind * np.exp(exp_term_Rc * ros)))

            # Update ros
            tmp_ros = Rb + Rc + Rr
            err = abs(tmp_ros - ros)
            ros = tmp_ros

            # Check for convergence
            if err < tol:
                failstatus = False
                break

        # Set ros to NaN if the algorithm did not converge
        if failstatus:
            ros = 0

        return min(ros, 6.0)

    @staticmethod
    def compute_ros(
        input_dict: dict[str, list[float]],
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using the Balbi's 2022 model.

        This is a wrapper function that prepares the fuel data dictionary and calls the `balbi_2022_fixed` method.

        Parameters
        ----------
        input_dict : dict[str, list[float]]
            Dictionary containing the input data for various fuel properties.

        Optional Parameters
        -------------------
        **opt : dict
            Optional parameters for the `balbi_2022_fixed` method.

        Returns
        -------
        float
            The computed rate of spread of fire [m/s].
        """
        fuel_dict_list_vars = [
            "windrf",
            "fgi",
            "fueldepthm",
            "fueldens",
            "savr",
        ]
        fuel_dict = {}
        for var in fuel_dict_list_vars:
            fuel_dict[var] = input_dict[Balbi_2022_fixed_SFIRE.metadata[var]["std_name"]]

        return Balbi_2022_fixed_SFIRE.balbi_2022_fixed(
            fueldata=fuel_dict,
            fuelclass=input_dict[svn.FUEL_CLASS],
            wind=input_dict[svn.WIND_SPEED],
            slope=input_dict[svn.SLOPE_ANGLE],
            fmc=input_dict[svn.FUEL_MOISTURE_CONTENT],
            **opt,
        )
