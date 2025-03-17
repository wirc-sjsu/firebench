import numpy as np
from pint import Quantity

from ..tools.check_data_quality import extract_magnitudes
from ..tools.input_info import ParameterType
from ..tools.namespace import StandardVariableNames as svn
from ..tools.rate_of_spread_model import RateOfSpreadModel
from ..tools.units import ureg


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
        fueldepthm: float,
        fueldens: float,
        savr: float,
        fuelmce: float,
        st: float,
        se: float,
        ichap: int,
        wind: float,
        slope: float,
        fmc: float,
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
        c = 7.47 * np.exp(-0.133 * savr**0.55)  # Wind coefficient constant
        bbb = 0.02526 * savr**0.54  # Wind coefficient constant
        e = 0.715 * np.exp(-3.59e-4 * savr)  # Wind coefficient constant
        phiwc = c * (betafl / betaop) ** (-e)
        rtemp2 = savr**1.5
        gammax = rtemp2 / (495.0 + 0.0594 * rtemp2)  # Maximum reaction velocity, 1/min
        a = 1.0 / (4.774 * savr**0.1 - 7.27)  # Coefficient for optimum reaction velocity
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
        xifr = np.exp((0.792 + 0.681 * savr**0.5) * (betafl + 0.1)) / (
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
        fuel_cat: int = 0,
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using `Rothermel`'s model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the ROS. Input data must be provided in standard units without `pint.Quantity` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

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
            The computed rate of spread of fire.

        Notes
        -----
        - `fuel_cat` uses one-based indexing to align with natural fuel category numbering.
          When accessing lists or arrays in `input_dict`, the index is adjusted accordingly (i.e., `index = fuel_cat - 1`).
        - This function assumes `input_dict` contains values in standard units (e.g., no `pint.Quantity` objects), compliant with units specified in the metadata dictionary.

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
        print(f"The rate of spread is {ros:.4f}")
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
        print(f"The rate of spread for fuel category {fuel_category} is {ros:.4f}")
        ```
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=Rothermel_SFIRE.metadata, fuel_cat=fuel_cat
        )

        # Calculate the rate of spread
        return Rothermel_SFIRE.rothermel(**fuel_properties)

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        fuel_cat: int = 0,
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using Rothermel's model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `Rothermel_SFIRE.metadata`.

        fuel_cat : int, optional
            One-based index for selecting a specific fuel category from lists in `input_dict`.
            Defaults to 0, indicating scalar inputs.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., meters per second).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `Rothermel_SFIRE.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            Rothermel_SFIRE.compute_ros(input_dict_no_units, fuel_cat, **opt),
            Rothermel_SFIRE.metadata["rate_of_spread"]["units"],
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
        "dead_fuel_ratio": {
            "std_name": svn.FUEL_LOAD_DEAD_RATIO,
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
        "w0": {
            "std_name": svn.IGNITION_LENGTH,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 50,
        },
        "temp_ign": {
            "std_name": svn.FUEL_TEMPERATURE_IGNITION,
            "units": ureg.kelvin,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 600,
        },
        "temp_air": {
            "std_name": svn.AIR_TEMPERATURE,
            "units": ureg.kelvin,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 300,
        },
        "dens_air": {
            "std_name": svn.AIR_DENSITY,
            "units": ureg.kilogram / ureg.meter**3,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 1.125,
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
        dead_fuel_ratio: float,
        fgi: float,
        fueldepthm: float,
        fueldens: float,
        temp_ign: float,
        temp_air: float,
        dens_air: float,
        savr: float,
        w0: float,
        wind: float,
        slope: float,
        fmc: float,
        **opt,
    ) -> float:
        """
        Compute the rate of spread using the Balbi's model from SFIRE code.

        Parameters
        ----------
        wind : float
            Wind speed in the normal direction at 6.1m (20ft) [m/s].
        slope : float
            Slope angle [degrees].
        fmc : float
            Fuel moisture content [%].
        w0 : float
            Ignition line width [m].

        Optional Parameters
        -------------------
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
        ## Model parameter
        st = 17.0  # Stoichiometric coefficient                 [-]
        scal_am = 0.025  # scaling factor am                    [-]
        tol = 1e-4  # tolerance for fixed point method          [-]
        r00 = 2.5e-5  # Model parameter
        chi0 = 0.3  # Radiative factor                          [-]

        # fmc from percent to real
        fmc *= 0.01

        # Add moisture to oven dry fuel load
        sigma_t = fgi * (1 + fmc)

        # dead fuel load
        sigma_d = sigma_t * dead_fuel_ratio

        # max number of iteration
        maxite = opt.get("max_ite", 20)

        ## preliminary
        alpha_rad = np.deg2rad(slope)

        # Packing ratios
        beta = sigma_d / (fueldepthm * fueldens)  # dead fuel
        beta_t = sigma_t / (fueldepthm * fueldens)  # total fuel

        # Leaf areas
        lai = savr * fueldepthm * beta  # dead fuel
        lai_t = savr * fueldepthm * beta_t  # total fuel

        ## Heat sink
        q = Cp * (temp_ign - temp_air) + fmc * (delta_h + Cpw * (Tvap - temp_air))

        # Flame temperature
        Tflame = temp_air + (delta_H * (1 - chi0)) / (Cpa * (1 + st))

        # Base flame radiation
        Rb = min(lai_t / (2 * np.pi), 1) * (lai / lai_t) ** 2 * boltz * Tflame**4 / (beta * fueldens * q)

        # Radiant factor
        A = min(lai / (2 * np.pi), lai / lai_t) * chi0 * delta_H / (4 * q)

        # vertical velocity
        u0 = (
            2
            * (st + 1)
            * fueldens
            * Tflame
            * min(lai, 2 * np.pi * lai / lai_t)
            / (tau0 * dens_air * temp_air)
        )

        # tilt angle
        gamma = max(0, np.arctan(np.tan(alpha_rad) + wind / u0))

        # flame height and length
        flame_height = (u0**2) / (g * (Tflame / temp_air - 1) * np.cos(alpha_rad) ** 2)
        flame_length = flame_height / np.cos(gamma - alpha_rad)

        # view factor
        view_factor = 1 - np.sin(gamma) + np.cos(gamma)

        # Rr denom term
        denom_term_Rr = np.cos(gamma) / (savr * r00)

        # main term Rc
        main_term_Rc = (
            scal_am
            * min(w0 / 50, 1)
            * delta_H
            * dens_air
            * temp_air
            * savr
            * np.sqrt(fueldepthm)
            / (2 * q * (1 + st) * fueldens * Tflame)
        )

        # second term
        scd_term_Rc = (
            min(2 * np.pi * lai / lai_t, lai)
            * np.tan(gamma)
            * (1 + st)
            * fueldens
            * Tflame
            / (dens_air * temp_air * tau0)
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
        input_dict: dict[str, float | int | list[float] | list[int]],
        fuel_cat: int = 0,
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using the `Balbi's 2022` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the rate of spread (ROS) of fire using the `balbi_2022_fixed` method.
        Input data must be provided in standard units without `pint.Quantity` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in `Balbi_2022_fixed_SFIRE.metadata`.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

        **opt : dict
            Additional optional parameters to be passed to the `balbi_2022_fixed` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----
        - `fuel_cat` uses one-based indexing to align with natural fuel category numbering.
        When accessing lists or arrays in `input_dict`, the index is adjusted accordingly (i.e., `index = fuel_cat - 1`).
        - This function assumes `input_dict` contains values in standard units (e.g., no `pint.Quantity` objects),
        compliant with units specified in the metadata dictionary.
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties_dict = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=Balbi_2022_fixed_SFIRE.metadata, fuel_cat=fuel_cat
        )

        return Balbi_2022_fixed_SFIRE.balbi_2022_fixed(
            **fuel_properties_dict,
            **opt,
        )

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        fuel_cat: int = 0,
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using Balbi's 2022 model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `Balbi_2022_fixed_SFIRE.metadata`.

        fuel_cat : int, optional
            One-based index for selecting a specific fuel category from lists in `input_dict`.
            Defaults to 0, indicating scalar inputs.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., meters per second).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `Balbi_2022_fixed_SFIRE.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            Balbi_2022_fixed_SFIRE.compute_ros(input_dict_no_units, fuel_cat, **opt),
            Balbi_2022_fixed_SFIRE.metadata["rate_of_spread"]["units"],
        )


class Santoni_2011(RateOfSpreadModel):
    """
    A class to represent the Santoni's model for fire spread rate calculation.

    This version is based on Santoni et al. 2011.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Attributes
    ----------
    metadata : dict
        A dictionary containing metadata for various fuel properties.

    Methods
    -------
    compute_ros(fueldata, fuelclass, wind, slope, fmc, **opt) -> float
        Compute the rate of spread of fire using Rothermel's model.
    """  # pylint: disable=line-too-long

    metadata = {
        "fuel_load_dry_total": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.kilogram / ureg.meter**2,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "dead_fuel_ratio": {
            "std_name": svn.FUEL_LOAD_DEAD_RATIO,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "fueldepth": {
            "std_name": svn.FUEL_HEIGHT,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fuel_dens_dead": {
            "std_name": svn.FUEL_DENSITY_DEAD,
            "units": ureg.kilogram / ureg.meter**3,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "fuel_dens_live": {
            "std_name": svn.FUEL_DENSITY_LIVE,
            "units": ureg.kilogram / ureg.meter**3,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "temp_ign": {
            "std_name": svn.FUEL_TEMPERATURE_IGNITION,
            "units": ureg.kelvin,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 600,
        },
        "temp_air": {
            "std_name": svn.AIR_TEMPERATURE,
            "units": ureg.kelvin,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 300,
        },
        "dens_air": {
            "std_name": svn.AIR_DENSITY,
            "units": ureg.kilogram / ureg.meter**3,
            "range": (0, np.inf),
            "type": ParameterType.optional,
            "default": 1.125,
        },
        "savr_dead": {
            "std_name": svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD,
            "units": 1 / ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "savr_live": {
            "std_name": svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE,
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
        "fmc_dead": {
            "std_name": svn.FUEL_MOISTURE_CONTENT_DEAD,
            "units": ureg.percent,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "fmc_live": {
            "std_name": svn.FUEL_MOISTURE_CONTENT_LIVE,
            "units": ureg.percent,
            "range": (0, 500),
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
    def santoni_2011(
        fuel_load_dry_total: float,
        dead_fuel_ratio: float,
        fueldepth: float,
        fuel_dens_dead: float,
        fuel_dens_live: float,
        temp_ign: float,
        temp_air: float,
        dens_air: float,
        savr_dead: float,
        savr_live: float,
        wind: float,
        slope: float,
        fmc_dead: float,
        fmc_live: float,
    ) -> float:
        """
        Compute the rate of spread using the Santoni's model.

        Parameters
        ----------
        fuel_load_dry_total : float
            total dry fuel load [kg m-2]
        dead_fuel_ratio : float
            ratio of dead fuel load to total fuel load [-]
        fuel_dens_dead : float
            dead fuel density [kg m-3]
        fuel_dens_live : float
            live fuel density [kg m-3]
        temp_ign : float
            fuel ignition temperature [K]
        temp_air : float
            ambiant air temperature [K]
        dens_air : float
            ambiant air density [kg m-3]
        savr_dead : float
            dead fuel surface area to volume ratio [m-1]
        savr_live : float
            live fuel surface area to volume ratio [m-1]
        wind : float
            midflame wind speed [m s-1]
        slope : float
            slope angle [degrees]
        fmc_dead : float
            dead fuel moisture content [%]
        fmc_live : float
            live fuel moisture content [%]

        Returns
        -------
        float
            Rate of spread [m s-1]
        """  # pylint: disable=line-too-long
        ## Physical parameters
        boltz = 5.670373e-8  # Stefan-Boltzman constant         [W m-2 K-4]
        tau0 = 75591.0  # Anderson's residence time coefficient [s m-1]
        Cpa = 1150.0  # Specific heat of air                    [J kg-1 K-1]
        Cp = 1200  # Specific heat of fuel                      [J kg-1 K-1]
        delta_h = 2.3e6  # Heat of latent evaporation           [J kg-1]
        delta_H = 1.7433e07  # Heat of combustion               [J kg-1]

        ## Model parameter
        r00 = 2.5e-5  # Model parameter
        chi0 = 0.3  # Radiant heat transfer fraction            [-]
        stoich_coeff = 8.3  # Stoichiometric coefficient         [-]
        base_LAI = 4.0  # Base leaf area index                   [-]

        # fmc from percent to real
        fmc_dead *= 0.01
        fmc_live *= 0.01

        # dead fuel load
        sigma_d = fuel_load_dry_total * dead_fuel_ratio
        sigma_l = fuel_load_dry_total - sigma_d

        S_l = savr_live * sigma_l / fuel_dens_live
        S_d = savr_dead * sigma_d / fuel_dens_dead

        xi = (fmc_live - fmc_dead) * S_l * delta_h / (S_d * delta_H)

        # nominal radiant temperature
        T_n = temp_air + delta_H * (1 - chi0) * (1 - xi) / (Cpa * (1 + stoich_coeff))

        # Flame tilt angle
        nu = min(S_d / base_LAI, 1.0)  # absorption coeff
        v_vertical = (
            2.0 * nu * base_LAI * (1 + stoich_coeff) * T_n * fuel_dens_dead / (dens_air * temp_air * tau0)
        )  # flame gas velocity
        alpha_rad = np.deg2rad(slope)
        tan_gamma = np.tan(alpha_rad) + wind / v_vertical  # tan of tilt angle
        gamma = np.arctan(tan_gamma)

        # no wind no slope ros
        a = delta_h / (Cp * (temp_ign - temp_air))
        ros_00 = boltz * T_n**4 / (Cp * (temp_ign - temp_air))
        ros_0 = fueldepth * ros_00 / (sigma_d * (1 + a * fmc_dead)) * (S_d / (S_d + S_l)) ** 2

        if gamma > 0:
            # positive tilt angle
            A_0 = 0.25 * chi0 * delta_H / (Cp * (temp_ign - temp_air))
            A = nu * A_0 * (1 - xi) / (1 + a * fmc_dead)
            r_0 = savr_dead * r00
            G = r_0 * (1 + np.sin(gamma) - np.cos(gamma)) / np.cos(gamma)
            ros_t = ros_0 + A * G - r_0 / np.cos(gamma)
            ros = 0.5 * (ros_t + np.sqrt(ros_t**2 + 4 * r_0 * ros_0 / np.cos(gamma)))
        else:
            ros = ros_0

        return min(ros, 6.0)

    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        fuel_cat: int = 0,
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using the `Santoni's 2011` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the rate of spread (ROS) of fire using the `santoni_2011` method.
        Input data must be provided in standard units without `pint.Quantity` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in `santoni_2011.metadata`.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

        **opt : dict
            Additional optional parameters to be passed to the `santoni_2011` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----
        - `fuel_cat` uses one-based indexing to align with natural fuel category numbering.
        When accessing lists or arrays in `input_dict`, the index is adjusted accordingly (i.e., `index = fuel_cat - 1`).
        - This function assumes `input_dict` contains values in standard units (e.g., no `pint.Quantity` objects),
        compliant with units specified in the metadata dictionary.
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties_dict = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=Santoni_2011.metadata, fuel_cat=fuel_cat
        )

        return Santoni_2011.santoni_2011(
            **fuel_properties_dict,
            **opt,
        )

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        fuel_cat: int = 0,
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using Santoni's 2011 model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `Balbi_2022_fixed_SFIRE.metadata`.

        fuel_cat : int, optional
            One-based index for selecting a specific fuel category from lists in `input_dict`.
            Defaults to 0, indicating scalar inputs.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., meters per second).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `Balbi_2022_fixed_SFIRE.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            Santoni_2011.compute_ros(input_dict_no_units, fuel_cat, **opt),
            Santoni_2011.metadata["rate_of_spread"]["units"],
        )
