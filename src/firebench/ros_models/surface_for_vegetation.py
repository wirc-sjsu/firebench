import sys
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

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``fgi``
        - Standard name: ``FUEL_LOAD_DRY_TOTAL``
        - Units: ``kilogram / meter ** 2``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fueldepthm``
        - Standard name: ``FUEL_HEIGHT``
        - Units: ``meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fueldens``
        - Standard name: ``FUEL_DENSITY``
        - Units: ``pound / foot ** 3``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``savr``
        - Standard name: ``FUEL_SURFACE_AREA_VOLUME_RATIO``
        - Units: ``1 / foot``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fuelmce``
        - Standard name: ``FUEL_MOISTURE_EXTINCTION``
        - Units: ``percent``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``st``
        - Standard name: ``FUEL_MINERAL_CONTENT_TOTAL``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``se``
        - Standard name: ``FUEL_MINERAL_CONTENT_EFFECTIVE``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``ichap``
        - Standard name: ``FUEL_CHAPARRAL_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``meter / second``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``-90 to 90``
        - Type: ``input``

    - ``fmc``
        - Standard name: ``FUEL_MOISTURE_CONTENT``
        - Units: ``percent``
        - Range: ``0 to 200``
        - Type: ``input``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``meter / second``
        - Range: ``0 to inf``
        - Type: ``output``
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
        Compute the rate of spread of fire using ``Rothermel``'s model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the ROS. Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``Rothermel_SFIRE.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

        **opt : dict
            Additional optional parameters to be passed to the ``rothermel`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----
        - ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering.
          When accessing lists or arrays in `input_dict`, the index is adjusted accordingly (i.e., `index = fuel_cat - 1`).

        - This function assumes ``input_dict`` contains values in standard units (e.g., no ``pint.Quantity`` objects), compliant with units specified in the metadata dictionary.

        Examples
        --------
        **Example with scalar fuel properties:**

        .. code-block:: python

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

        **Example with fuel categories:**

        .. code-block:: python

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

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``dead_fuel_ratio``
        - Standard name: ``FUEL_LOAD_DEAD_RATIO``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``fgi``
        - Standard name: ``FUEL_LOAD_DRY_TOTAL``
        - Units: ``kilogram / meter ** 2``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fueldepthm``
        - Standard name: ``FUEL_HEIGHT``
        - Units: ``meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fueldens``
        - Standard name: ``FUEL_DENSITY``
        - Units: ``kilogram / meter ** 3``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``savr``
        - Standard name: ``FUEL_SURFACE_AREA_VOLUME_RATIO``
        - Units: ``1 / meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``w0``
        - Standard name: ``IGNITION_LENGTH``
        - Units: ``meter``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``50``

    - ``temp_ign``
        - Standard name: ``FUEL_TEMPERATURE_IGNITION``
        - Units: ``kelvin``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``600``

    - ``temp_air``
        - Standard name: ``AIR_TEMPERATURE``
        - Units: ``kelvin``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``300``

    - ``dens_air``
        - Standard name: ``AIR_DENSITY``
        - Units: ``kilogram / meter ** 3``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``1.125``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``meter / second``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``-90 to 90``
        - Type: ``input``

    - ``fmc``
        - Standard name: ``FUEL_MOISTURE_CONTENT``
        - Units: ``percent``
        - Range: ``0 to 200``
        - Type: ``input``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``meter / second``
        - Range: ``0 to inf``
        - Type: ``output``
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
        Compute the rate of spread of fire using the ``Balbi's 2022`` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the rate of spread (ROS) of fire using the ``balbi_2022_fixed`` method.
        Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use ``compute_ros_with_units``.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``Balbi_2022_fixed_SFIRE.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

        **opt : dict
            Additional optional parameters to be passed to the ``balbi_2022_fixed`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----
        - ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering.
          When accessing lists or arrays in ``input_dict``, the index is adjusted accordingly (i.e., ``index = fuel_cat - 1``).

        - This function assumes ``input_dict`` contains values in standard units (e.g., no ``pint.Quantity`` objects),
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

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``fuel_load_dry_total``
        - Standard name: ``FUEL_LOAD_DRY_TOTAL``
        - Units: ``kilogram / meter ** 2``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``dead_fuel_ratio``
        - Standard name: ``FUEL_LOAD_DEAD_RATIO``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``fueldepth``
        - Standard name: ``FUEL_HEIGHT``
        - Units: ``meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fuel_dens_dead``
        - Standard name: ``FUEL_DENSITY_DEAD``
        - Units: ``kilogram / meter ** 3``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``fuel_dens_live``
        - Standard name: ``FUEL_DENSITY_LIVE``
        - Units: ``kilogram / meter ** 3``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``temp_ign``
        - Standard name: ``FUEL_TEMPERATURE_IGNITION``
        - Units: ``kelvin``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``600``

    - ``temp_air``
        - Standard name: ``AIR_TEMPERATURE``
        - Units: ``kelvin``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``300``

    - ``dens_air``
        - Standard name: ``AIR_DENSITY``
        - Units: ``kilogram / meter ** 3``
        - Range: ``0 to inf``
        - Type: ``optional``
        - Default: ``1.125``

    - ``savr_dead``
        - Standard name: ``FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD``
        - Units: ``1 / meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``savr_live``
        - Standard name: ``FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE``
        - Units: ``1 / meter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``meter / second``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``-90 to 90``
        - Type: ``input``

    - ``fmc_dead``
        - Standard name: ``FUEL_MOISTURE_CONTENT_DEAD``
        - Units: ``percent``
        - Range: ``0 to 200``
        - Type: ``input``

    - ``fmc_live``
        - Standard name: ``FUEL_MOISTURE_CONTENT_LIVE``
        - Units: ``percent``
        - Range: ``0 to 500``
        - Type: ``input``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``meter / second``
        - Range: ``0 to inf``
        - Type: ``output``
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
        Compute the rate of spread of fire using the ``Santoni's 2011`` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the rate of spread (ROS) of fire using the ``santoni_2011`` method.
        Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use ``compute_ros_with_units``.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``santoni_2011.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

        **opt : dict
            Additional optional parameters to be passed to the ``santoni_2011`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----
        - ``fuel_cat`` uses one-based indexing to align with natural fuel category numbering.
          When accessing lists or arrays in ``input_dict``, the index is adjusted accordingly (i.e., ``index = fuel_cat - 1``).

        - This function assumes ``input_dict`` contains values in standard units (e.g., no ``pint.Quantity`` objects),
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
            Keys should match the variable names defined in `Santoni_2011.metadata`.

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

class McArthur(RateOfSpreadModel):
    """
    A class to represent the McArthur's model for fire spread rate calculation.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``fgi``
        - Standard name: ``FUEL_LOAD_DRY_TOTAL``
        - Units: ``tonne / hectare``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``igrass``
        - Standard name: ``FUEL_GRASSLAND_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``kilometer / hour``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``0 to 30``
        - Type: ``input``

    - ``temp_air``
        - Standard name: ``AIR_TEMPERATURE``
        - Units: ``celsius``
        - Range: ``0 to inf``
        - Type: ``input``
        - Default: ``30``

    - ``rel_humid``
        - Standard name: ``RELATIVE_HUMIDITY``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``input``

    - ``precip``
        - Standard name: ``PRECIPITATION``
        - Units: ``millimeter``
        - Range: ``0 to inf``
        - Type: ``optional``

    - ``deg_curing``
        - Standard name: ``DEGREE_OF_CURING``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``input``

    - ``drought_index``
        - Standard name: ``DROUGHT_INDEX``
        - Units: ``millimeter``
        - Range: ``0 to inf``
        - Type: ``optional``

    - ``time_since_rain``
        - Standard name: ``TIME_SINCE_RAIN``
        - Units: ``days``
        - Range: ``0 to inf``
        - Type: ``optional``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``kilometer / hour``
        - Range: ``0 to inf``
        - Type: ``output``
    """  # pylint: disable=line-too-long

    metadata = {
        "fgi": {
            "std_name": svn.FUEL_LOAD_DRY_TOTAL,
            "units": ureg.tonne / ureg.hectare,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "igrass": {
            "std_name": svn.FUEL_GRASSLAND_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.kilometer / ureg.hour,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (0, 30),
            "type": ParameterType.input,
        },
        "temp_air": {
            "std_name": svn.AIR_TEMPERATURE,
            "units": ureg.celsius,
            "range": (0, np.inf),
            "type": ParameterType.input,
            "default": 30,
        },
        "rel_humid": {
            "std_name": svn.RELATIVE_HUMIDITY,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "precip": {
            "std_name": svn.PRECIPITATION,
            "units": ureg.millimeter,
            "range": (0, np.inf),
            "type": ParameterType.optional,
        },
        "deg_curing": {
            "std_name": svn.DEGREE_OF_CURING,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "drought_index": {
            "std_name": svn.DROUGHT_INDEX,
            "units": ureg.millimeter,
            "range": (0, np.inf),
            "type": ParameterType.optional,
        },
        "time_since_rain": {
            "std_name": svn.TIME_SINCE_RAIN,
            "units": ureg.days,
            "range": (0, np.inf),
            "type": ParameterType.optional,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.kilometer / ureg.hour,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def McArthur(
        fgi: float,
        igrass: int,
        wind: float,
        slope: float,
        temp_air: float,
        rel_humid: float,
        precip: float,
        deg_curing: float,
        drought_index: float,
        time_since_rain: float,
    ) -> float:
        """
        Compute the rate of spread using McArthur's model.

        This function calculates the forward rate of spread of a fire in grassland fuels and in forest fires using
        McArthur's (1980) fire spread model. The model considers fuel load, fuel type, wind speed, slope, ambient air 
        temperatrure, precipitation, degree of curing, drought index, time since last rain, and relative humidity, 
        to estimate the rate of spread.

        Parameters
        ----------
        fgi : float
            Total fuel load (dry weight) per unit area [t ha-1].
            Represents the total mass of combustible material available to the fire.

        igrass : int
            Grassland flag (0 or 1).
            Indicator for grass fuel type: set to 1 if the fuel is grass, otherwise 0.

        wind : float
            Wind speed at 10 m height [km h-1].

        slope : float
            Slope steepness [degrees].
            The angle of the terrain slope.

        temp_air : float
            Ambiant air temperature [C]

        rel_humid : float
            Relative humidity of ambient air [%].

        precip : float
            Precipitaion [mm].

        deg_curing : float
            Degree of curing [%].

        drought_index : float
            Keetch-Byram drought index [mm].

        time_since_rain : float
            Time since the last rain [days].

        **opt : dict, optional
            Additional optional parameters.

        Returns
        -------
        float
            Rate of spread [km/h].
            The estimated forward rate of spread of the fire.

        References
        ----------
        I. R. NOBLE, G. A. V. BARY, A. M. GILL (1980).
        *McArthur's fire-danger meters expressed as equations*.
        Australian Journal of Ecology, 5, 201-203.
        """  # pylint: disable=line-too-long

        # Calculate various coefficients
        # Drought factor for forest fuel, Max value is 10
        # Fuel load, Max Value is 5 t ha-1
        # Slope, Max Value is 30 degrees upslope

        I = drought_index # Keetch-Byram drought index (mm)
        N = time_since_rain # Time since the last rain 
        d_factor = 0.191 * (I + 104) * np.power((N + 1) , 1.5) / (3.52 * np.power((N + 1) , 1.5) + precip - 1.0)

        if igrass == 0:
            fdi = 2.0 * np.exp(-0.450 + 0.987 * np.log(d_factor) - 0.0345 * rel_humid + 0.0338 * temp_air
                               + 0.0234 * wind)   # Fire danger index for forest fires
            r_0 = 0.0012 * fdi * fgi  # Spread rate at zero slope, km/h
            ros = r_0 * np.exp(0.069 * slope)    # Spread rate, km/h

        else:
            fmc = (97.7 + 4.06 * rel_humid)/(temp_air + 6.0) - (0.00854 * rel_humid) + (3000.0 / deg_curing) - 30.0 
            # Fuel moisture content for grass fuel, Max value is 30
            if fmc < 18.8:
                fdi = 3.35 * fgi * np.exp(-0.0897 * fmc + 0.0403 * wind)            # Fire danger index 
            elif fmc >= 18.8 and fmc <= 30:
                fdi = 0.299 * fgi * np.exp(-1.686 + 0.0403 * wind) * (30.0 - fmc)   # Fire danger index 
            else:
                fdi = 0

            if fgi <= 2:
            # light fuel load or grazed pastures.
                ros = 0.06 * fdi   # Spread rate, km/h
            else:
            # high fuel load
                ros = 0.13 * fdi   # Spread rate, km/h

        # Default
        return min(ros, 6.0)

    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using ``McArthur``'s model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the ROS. Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``McArthur.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        **opt : dict
            Additional optional parameters to be passed to the ``McArthur`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Examples
        --------
        **Example with scalar fuel properties:**

        .. code-block:: python

            input_data = {
                svn.FUEL_LOAD_DRY_TOTAL: 4,                  # fgi
                svn.FUEL_GRASSLAND_FLAG: 1.0,
                svn.WIND_SPEED: 10.0,
                svn.SLOPE_ANGLE: 30,
                svn.AIR_TEMPEATURE: 30,
                svn.RELATIVE_HUMIDITY: 40,
                svn.PRECIPITATION: 2,
                svn.DEGREE_OF_CURING: 50,
                svn.DROUGHT_INDEX: 1,
                svn.TIME_SINCE_RAIN: 30,
            }
            ros = McArthur.compute_ros(input_data)
            print(f"The rate of spread is {ros:.4f}")
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=McArthur.metadata
        )

        # Calculate the rate of spread
        return McArthur.McArthur(**fuel_properties)

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using McArthur's model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `McArthur.metadata`.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., kilometers per hour).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `McArthur.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            McArthur.compute_ros(input_dict_no_units, **opt),
            McArthur.metadata["rate_of_spread"]["units"],
        )
    
class Cheney(RateOfSpreadModel):
    """
    A class to represent the Cheney's model for fire spread rate calculation.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``fhs_s``
        - Standard name: ``FUEL_HAZARD_SCORE_SURFACE_FUEL``
        - Units: ``dimensionless``
        - Range: ``0 to 4``
        - Type: ``input``

    - ``fhs_ns``
        - Standard name: ``FUEL_HAZARD_SCORE_NEAR_SURFACE_FUEL``
        - Units: ``dimensionless``
        - Range: ``0 to 4``
        - Type: ``input``

    - ``hf_ns``
        - Standard name: ``FUEL_HEIGHT_SURFACE_FUEL``
        - Units: ``centimeter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``igrass``
        - Standard name: ``FUEL_GRASSLAND_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``igrass_state``
        - Standard name: ``FUEL_GRASSLAND_STATE_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``ieuca``
        - Standard name: ``FUEL_EUCALYPTUS_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``ieuca_ros``
        - Standard name: ``FUEL_EUCALYPTUS_ROS_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``fmoist_period``
        - Standard name: ``FUEL_MOISTURE_CONTENT_PERIOD_FLAG``
        - Units: ``dimensionless``
        - Range: ``0 to 1``
        - Type: ``input``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``kilometer / hour``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``0 to 30``
        - Type: ``input``

    - ``temp_air``
        - Standard name: ``AIR_TEMPERATURE``
        - Units: ``celsius``
        - Range: ``0 to inf``
        - Type: ``input``
        - Default: ``30``

    - ``rel_humid``
        - Standard name: ``RELATIVE_HUMIDITY``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``input``

    - ``deg_curing``
        - Standard name: ``DEGREE_OF_CURING``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``input``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``kilometer / hour``
        - Range: ``0 to inf``
        - Type: ``output``
    """  # pylint: disable=line-too-long

    metadata = {
        "fhs_s": {
            "std_name": svn.FUEL_HAZARD_SCORE_SURFACE_FUEL,
            "units": ureg.dimensionless,
            "range": (0, 4),
            "type": ParameterType.input,
        },
        "fhs_ns": {
            "std_name": svn.FUEL_HAZARD_SCORE_NEAR_SURFACE_FUEL,
            "units": ureg.dimensionless,
            "range": (0, 4),
            "type": ParameterType.input,
        },
        "hf_ns": {
            "std_name": svn.FUEL_HEIGHT_NEAR_SURFACE_FUEL,
            "units": ureg.centimeter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "igrass": {
            "std_name": svn.FUEL_GRASSLAND_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "igrass_state": {
            "std_name": svn.FUEL_GRASSLAND_STATE_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "ieuca": {
            "std_name": svn.FUEL_EUCALYPTUS_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "ieuca_ros": {
            "std_name": svn.FUEL_EUCALYPTUS_ROS_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "fmoist_period": {
            "std_name": svn.FUEL_MOISTURE_CONTENT_PERIOD_FLAG,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.kilometer / ureg.hour,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (0, 30),
            "type": ParameterType.input,
        },
        "temp_air": {
            "std_name": svn.AIR_TEMPERATURE,
            "units": ureg.celsius,
            "range": (0, np.inf),
            "type": ParameterType.input,
            "default": 30,
        },
        "rel_humid": {
            "std_name": svn.RELATIVE_HUMIDITY,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "deg_curing": {
            "std_name": svn.DEGREE_OF_CURING,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.minute,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def Cheney(
        fhs_s: float,
        fhs_ns: float,
        hf_ns: float,
        igrass: int,
        igrass_state: int,
        ieuca: int,
        ieuca_ros: int,
        fmoist_period: int,
        wind: float,
        slope: float,
        temp_air: float,
        rel_humid: float,
        deg_curing: float,
    ) -> float:
        """
        Compute the rate of spread using Cheney's model.

        This function calculates the forward rate of spread of a fire in grassland fuels using Cheney's (1998) model 
        and in eucalyptus fuels using Cheney's (2012) model. The model considers fuel hazard score for surface fuels, 
        fuel hazard score for near surface fuels, height of near surface fuels, fuel type, state of grass fuel, fuel moisture 
        evaluation period, wind speed, ambient air temperatrure, degree of curing, and relative humidity, to estimate the rate of spread.

        Parameters
        ----------
        fhs_s : float
            Fuel hazard score for surface fuels (0 - 4).

        fhs_ns : float
            Fuel hazard score for near surface fuels (0 - 4).

        hf_ns : float
            Height of near surface fuels [cm].

        igrass : int
            Grassland flag (0 or 1).
            Indicator for grass fuel type: set to 1 if the fuel is grass, otherwise 0.

        igrass_state : int
            Grassland state flag (0 or 1 or 2).
            Indicator for state of grass fuel: set to 0 if the grass is undisturbed, 
            set to 1 if the grass is cut/grazed, set to 2 if the grass is eaten out.

        ieuca : int
            Eucalyptus flag (0 or 1).
            Indicator for eucalyptus fuel type: set to 1 if the fuel is dry eucalyptus, otherwise 0.

        ieuca_ros : int
            Eucalyptus ros flag (0 or 1).
            Indicator for ros model for eucalyptus fuel: set to 0 if ros is calculated using Fire Hazard Score (FHS), 
            set to 1 if ros is calculated using Fire Hazard Rating (FHR).

        fmoist_period : int
            Fuel moisture evaluation period flag (0 or 1 or 2).
            Indicator for the period during which fuel moisture is calculated: set to 0 if the period is between
            12.00 - 17.00 (daylight savings time, October - March), set to 1 if the period is otherwise for daylight
            hours, set to 2 if the period is nighttime.

        wind : float
            Wind speed at 10 m height [km h-1].

        slope : float
            Slope steepness [degrees].
            The angle of the terrain slope.

        temp_air : float
            Ambiant air temperature [C]

        rel_humid : float
            Relative humidity of ambient air [%].

        deg_curing : float
            Degree of curing [%].

        **opt : dict, optional
            Additional optional parameters.

        Returns
        -------
        float
            Rate of spread [m/min].
            The estimated forward rate of spread of the fire.

        References
        ----------
        1. N. P. Cheney, J. S. Gould, W. R. Catchpole (1998).
        *Prediction of Fire Spread in Grasslands*
        International Journal of Wildland Fire 8(l), 1-13.

        2. N. P. Cheney, J. S. Gould, W. L. McCawb, W. R. Anderson (2012).
        *Predicting fire behaviour in dry eucalypt forest in southern Australias*.
        Forest Ecology and Management, 280, 120–131.
        """  # pylint: disable=line-too-long     

        if igrass == 1:
            # Calculate various coefficients
            phi_c = 1.12 / (1 + 59.2 * np.exp(-0.124 * (deg_curing - 50))) # Min input value greater than 50
            fmc = 9.58 - 0.205 * temp_air + 0.138 * rel_humid
            # Fuel moisture content for grass fuel, Input value range is 2% - 24%
            if fmc < 12.0:
                phi_m = np.exp(-0.108 * fmc)        
            else:
                if wind < 10:
                    phi_m = 0.684 - 0.0342 * fmc
                else:
                    phi_m = 0.547 - 0.0228 * fmc

            if igrass_state == 0:
                if wind < 5:
                    ros = (0.054 + 0.269 * wind) * phi_m * phi_c  # Spread rate, m/min
                else:
                    ros = (1.4 + 0.838 * np.power((wind - 5.0) , 0.844)) * phi_m * phi_c  # Spread rate, m/min
            elif igrass_state == 1:
                if wind < 5:
                    ros = (0.054 + 0.209 * wind) * phi_m * phi_c  # Spread rate, m/min
                else:
                    ros = (1.1 + 0.705 * np.power((wind - 5.0) , 0.844)) * phi_m * phi_c  # Spread rate, m/min
            else:
                ros = (0.55 + 0.357 * np.power((wind - 5.0) , 0.844)) * phi_m * phi_c  
                # Spread rate, m/min, Mininum wind speed is 5 km/h  
        
        if ieuca == 1:    
            # Calculate various coefficients
            if fmoist_period == 0:    #  between 12.00 - 17.00 (daylight savings time, OCtober - March)
                fmc = 2.76 + 0.124 * rel_humid - 0.0187 * temp_air
            elif fmoist_period == 1:  #  Other daylight time 
                fmc = 3.60 + 0.169 * rel_humid - 0.0450 * temp_air
            else:      # Night time
                fmc = 3.08 + 0.198 * rel_humid - 0.0483 * temp_air  

            phi_m = 18.35 * np.power(fmc , -1.495)
            B1 = 1.03 # Model correction for bias (FHS based)
            B2 = 1.02 # Model correction for bias (FHR based)

            if ieuca_ros == 0:
                # Spread rate calculated using Fuel Hazard Score
                ros = (30.0 + 1.531 * np.power((wind - 5.0) , 0.8576) * np.power(fhs_s , 0.9301) 
                * np.power((fhs_ns * hf_ns) , 0.6366) * B1 * phi_m) * 60.0 # Spread rate at zero slope, m/min
                ros = ros * np.exp(0.069*slope*np.pi/180.0) # Spread rate, m/min
            else:
                # Spread rate calculated using Fuel Hazard Rating
                # Surface and near-surface fuel hazard rating - regression constants
                # Max value for fhs_s and fhs_ns input is 4
                if fhs_s <= 1.5: fhr_s = 0  
                if fhs_s > 1.5 and fhs_s <= 2.5: fhr_s = 1.5608 
                if fhs_s > 2.5 and fhs_s <= 3.5: fhr_s = 2.1412
                if fhs_s > 3.5 and fhs_s <= 3.75: fhr_s = 2.0548
                if fhs_s > 3.75: fhr_s = 2.3251                   

                if fhs_ns <= 1.5: fhr_ns = 0.4694  
                if fhs_ns > 1.5 and fhs_ns <= 2.5: fhr_ns = 0.7070 
                if fhs_ns > 2.5 and fhs_ns <= 3.5: fhr_ns = 1.2772
                if fhs_ns > 3.5 and fhs_ns <= 3.75: fhr_ns = 1.7492
                if fhs_ns > 3.75: fhr_ns = 1.2446 

                ros = (30.0 + 2.311 * np.power((wind - 5.0) , 0.8364) * np.exp(fhr_s + fhr_ns) 
                * B2 * phi_m) * 60.0 # Spread rate at zero slope, m/min
                ros = ros * np.exp(0.069*slope*np.pi()/180.0) # Spread rate, m/min
        # Default
        return min(ros, 6.0)

    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using ``Cheney's`` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the ROS. Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``Cheney.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        **opt : dict
            Additional optional parameters to be passed to the ``Cheney`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Examples
        --------
        **Example with scalar fuel properties:**

        .. code-block:: python

            input_data = {
                svn.FUEL_HAZARD_SCORE_SURFACE_FUEL: 2.0
                svn.FUEL_HAZARD_SCORE_NEAR_SURFACE_FUEL: 3.0
                svn.FUEL_HEIGHT_NEAR_SURFACE_FUEL: 30.0
                svn.FUEL_GRASSLAND_FLAG: 0.0,
                svn.FUEL_GRASSLAND_STATE_FLAG: 0.0,
                svn.FUEL_EUCALYPTUS_FLAG: 1.0,
                svn.FUEL_EUCALYPTUS_ROS_FLAG: 1.0,
                svn.FUEL_MOISTURE_CONTENT_PERIOD_FLAG: 2.0,
                svn.WIND_SPEED: 10.0,
                svn.AIR_TEMPEATURE: 30,
                svn.RELATIVE_HUMIDITY: 40,
                svn.DEGREE_OF_CURING: 50,
            }
            ros = Cheney.compute_ros(input_data)
            print(f"The rate of spread is {ros:.4f}")
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=Cheney.metadata
        )

        # Calculate the rate of spread
        return Cheney.Cheney(**fuel_properties)

    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using Cheney's model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `Cheney.metadata`.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., meters per minute).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `Cheney.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            Cheney.compute_ros(input_dict_no_units, **opt),
            Cheney.metadata["rate_of_spread"]["units"],
        )
    
class VanWagner(RateOfSpreadModel):
    """
    A class to represent the Van Wagner's model for fire spread rate calculation used in Canadian Fire Behavior Prediction
    System (FBP).

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS).
    The metadata includes descriptions, units, and acceptable ranges for each property.

    Metadata
    --------
    The model uses the following fuel parameters:

    - ``fclass``
        - Standard name: ``FUEL_CLASS``
        - Units: ``dimensionless``
        - Range: ``0 to 17``
        - Type: ``input``

    - ``fcon``
        - Standard name: ``FUEL_CONIFER_CONTENT``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``optional``

    - ``fhard``
        - Standard name: ``FUEL_HARDWOOD_CONTENT``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``optional``

    - ``fdfir``
        - Standard name: ``FUEL_DEAD_FIR_CONTENT``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``optional``

    - ``sh``
        - Standard name: ``STAND_HEIGHT``
        - Units: ``m``
        - Range: ``0 to inf``
        - Type: ``optional``

    - ``sd``
        - Standard name: ``STAND_DENSITY``
        - Units: ``stems/ha``
        - Range: ``0 to inf``
        - Type: ``optional``

    - ``month``
        - Standard name: ``MONTH``
        - Units: ``dimensionless``
        - Range: ``1 to 12``
        - Type: ``input``

    - ``Dj``
        - Standard name: ``JULIAN_DATE``
        - Units: ``dimensionless``
        - Range: ``1 to 366``
        - Type: ``input``

    - ``lat``
        - Standard name: ``LATITUDE``
        - Units: ``degree``
        - Range: ``-90 to 90``
        - Type: ``input``

    - ``lon``
        - Standard name: ``LONGITUDE``
        - Units: ``degree``
        - Range: ``-180 to 180``
        - Type: ``input``

    - ``wind``
        - Standard name: ``WIND_SPEED``
        - Units: ``meter / second``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``wind_dir``
        - Standard name: ``WIND_DIRECTION``
        - Units: ``degree``
        - Range: ``-inf to inf``
        - Type: ``input``

    - ``slope``
        - Standard name: ``SLOPE_ANGLE``
        - Units: ``degree``
        - Range: ``0 to 60``
        - Type: ``input``

    - ``elev``
        - Standard name: ``ELEVATION``
        - Units: ``meter``
        - Range: ``0 to np.inf``
        - Type: ``input``

    - ``ffmci``
        - Standard name: ``FINE_FUEL_MOISTURE_CODE_INITIAL``
        - Units: ``dimensionless``
        - Range: ``0 to 200``
        - Type: ``input``
        - Default: ``85``

    - ``dmci``
        - Standard name: ``DUFF_MOISTURE_CODE_INITIAL``
        - Units: ``dimensionless``
        - Range: ``0 to 200``
        - Type: ``input``
        - Default: ``20``

    - ``dci``
        - Standard name: ``DROUGHT_CODE_INITIAL``
        - Units: ``dimensionless``
        - Range: ``0 to 200``
        - Type: ``input``
        - Default: ``20``

    - ``temp_air``
        - Standard name: ``AIR_TEMPERATURE``
        - Units: ``celsius``
        - Range: ``0 to inf``
        - Type: ``input``
        - Default: ``30``

    - ``rel_humid``
        - Standard name: ``RELATIVE_HUMIDITY``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``input``

    - ``precip``
        - Standard name: ``PRECIPITATION``
        - Units: ``millimeter``
        - Range: ``0 to inf``
        - Type: ``input``

    - ``deg_curing``
        - Standard name: ``DEGREE_OF_CURING``
        - Units: ``percent``
        - Range: ``0 to 100``
        - Type: ``optional``

    - ``rate_of_spread``
        - Standard name: ``RATE_OF_SPREAD``
        - Units: ``meter / minute``
        - Range: ``0 to inf``
        - Type: ``output``
    """  # pylint: disable=line-too-long

    metadata = {
        "fclass": {
            "std_name": svn.FUEL_CLASS,
            "units": ureg.dimensionless,
            "range": (0, 17),
            "type": ParameterType.input,
        },
        "fcon": {
            "std_name": svn.FUEL_CONIFER_CONTENT,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.optional,
        },
        "fhard": {
            "std_name": svn.FUEL_HARDWOOD_CONTENT,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.optional,
        },
        "fdfir": {
            "std_name": svn.FUEL_DEAD_FIR_CONTENT,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.optional,
        },
        "sh": {
            "std_name": svn.STAND_HEIGHT,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.optional,
        },
        "sd": {
            "std_name": svn.STAND_DENSITY,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.optional,
        },
        "Dj": {
            "std_name": svn.JULIAN_DATE,
            "units": ureg.int,
            "range": (1, 366),
            "type": ParameterType.input,
        },
        "month": {
            "std_name": svn.MONTH,
            "units": ureg.int,
            "range": (1, 12),
            "type": ParameterType.input,
        },
        "lat": {
            "std_name": svn.LATITUDE,
            "units": ureg.degree,
            "range": (-90, 90),
            "type": ParameterType.input,
        },
        "lon": {
            "std_name": svn.LONGITUDE,
            "units": ureg.degree,
            "range": (-180, 180),
            "type": ParameterType.input,
        },
        "wind": {
            "std_name": svn.WIND_SPEED,
            "units": ureg.kilometer / ureg.hour,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "wind_dir": {
            "std_name": svn.WIND_DIRECTION,
            "units": ureg.degree,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "slope": {
            "std_name": svn.SLOPE_ANGLE,
            "units": ureg.degree,
            "range": (-90, 90),
            "type": ParameterType.input,
        },
        "elev": {
            "std_name": svn.ELEVATION,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "ffmci": {
            "std_name": svn.FINE_FUEL_MOISTURE_CODE_INITIAL,
            "units": ureg.dimensionless,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "dmci": {
            "std_name": svn.DUFF_MOISTURE_CODE_INITIAL,
            "units": ureg.dimensionless,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "dci": {
            "std_name": svn.DROUGHT_CODE_INITIAL,
            "units": ureg.dimensionless,
            "range": (0, 200),
            "type": ParameterType.input,
        },
        "temp_air": {
            "std_name": svn.AIR_TEMPERATURE,
            "units": ureg.celsius,
            "range": (0, np.inf),
            "type": ParameterType.input,
            "default": 30,
        },
        "rel_humid": {
            "std_name": svn.RELATIVE_HUMIDITY,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "precip": {
            "std_name": svn.PRECIPITATION,
            "units": ureg.millimeter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "deg_curing": {
            "std_name": svn.DEGREE_OF_CURING,
            "units": ureg.percent,
            "range": (0, 100),
            "type": ParameterType.input,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.minute,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def VanWagner(
        fclass: int,
        fcon: float,
        fhard: float,
        fdfir: float,
        sh: float,
        sd: float,
        Dj: int,
        month: int,
        lat: float,
        lon: float,
        wind: float,
        wind_dir: float,
        slope: float,
        elev: float,
        ffmci: float,
        dmci: float,
        dci: float, 
        temp_air: float,
        rel_humid: float,
        precip: float,
        deg_curing: float,
    ) -> float:
        """
        Compute the rate of spread using VanWagner's model.

        This function calculates the forward rate of spread of a fire in a uniform fuel bed using
        VanWagner's (1992) fire spread model. The model considers fuel properties, wind speed, slope,
        and fuel moisture content to estimate the rate at which a fire will spread through wildland fuels.

        Parameters
        ----------
        fclass : int
            Fuel class (1 - 17).

        fcon : float
            Fuel conifer content [%].

        fhard : float
            Fuel hardwood content [%].

        fdfir : float
            Fuel dead fir content [%].

        sh : float
            Stand height [m].

        sd : float
            Stand density [stems/ha].

        Dj : int
            Julian date (1 - 366)

        month : int
            Month (1 - 12).

        lat : float
            Latitude [degrees].

        lon : int
            Longitude [degrees].

        wind : float
            Wind speed at midflame height or average wind over flame height [m s-1].

        wind_dir : float
            Wind direction [degrees].

        slope : float
            Slope steepness [degrees].
            The angle of the terrain slope.

        elev : float
            Elevation [degrees].

        ffmci : float
            fine fuel moisture code initial value [%].

        dmci : float
            duff moistrue code initial value [%].
    
        dci : float
            drought code initial value [%].

        temp_air : float
            Ambiant air temperature [C]

        rel_humid : float
            Relative humidity of ambient air [%].

        precip : float
            precipitation [mm].
            
        deg_curing : float
            Degree of curing [%].

        **opt : dict, optional
            Additional optional parameters.

        Returns
        -------
        float
            Rate of spread [m/min].
            The estimated forward rate of spread of the fire.

        References
        ----------
        Forestry Canada. 1992. *Development and structure of the Canadian Forest Fire Behavior Prediction System*. 
        Forestry Canada, Headquarters, Fire Danger Group and Science and Sustainable Development Directorate, Ottawa. 
        Information Report ST-X-3. 64 p.
        """  
        # pylint: disable=line-too-long
        if fclass > 17: 
            raise ValueError("Fuel class must not be higher than 17. See fire_models_info for more details")
            sys.exit()

        # Slope flag and slope factor (zero slope)
        sflag = 0
        sf = 0
        isf = 0

        # Calculation of different indices
        ffmc = VanWagner.fine_fuel_moisture_code  # Fine fuel moisture code (FFMC)
        dmc = VanWagner.duff_moisture_code        # Duff moisture code (DMC)
        dc = VanWagner.drought_code               # Drought code (DC)

        # Buildup index (BUI)
        if dmc <= 0.4 * dc:
            bui = 0.8 * (dmc * dc) / (dmc + 0.4 * dc)
        else:
            bui = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (0.92 + np.power((0.0114 * dmc) , 1.7)) 

        # Initial Spread Index (ISI) (zero slope, zero wind)
        m = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
        f_F = 91.9 * np.exp(-0.1386 * m) * (1.0 + np.power(m , 5.31) / 49300000)        # Fine Fuel Moisture function, f_F
        isi = 0.208 * f_F   # Initial spread index

        # Rate of spead for zero slope and zero wind
        if slope == 0 and wind == 0:
            ros , _ = VanWagner.ros

        # Effect of Slope
        # Initial Spread Index with Slope (ISF) (Zero wind)
        if slope != 0:
            sflag = 1
            gs = 100 * np.tan(slope)   # Ground slope, slope angle max value 60 deg
            if gs < 70:
                sf = np.exp(3.533 * np.power((gs / 100.0) , 1.2))  
            else:
                sf = 10.0   
            ros , isf = VanWagner.ros  
            wind_eq = np.log(isf / (0.208 * f_F)) / 0.05039   # Calculate equivalent wind speed due to slope

            if wind_eq <= 40:
                wind_eq = wind_eq
            else:
                k = 0.999 * 2.496 * f_F
                if isf < k:
                    wind_eq = 28.0 - np.log(1.0 - isf / (2.496 * f_F)) / 0.0818
                else:
                    wind_eq = 112.45
        else:
            sfalg = 0, sf = 0, wind_eq = 0      

        # Wind Speed Calculations (km/h)
        if wind != 0 or slope != 0:
            wind = wind + wind_eq  # Resultant vector magnitude 
            if wind > 40:          # Wind function, f_W
                f_w = 12.0 * (1.0 - np.exp(-0.0818 * wind - 28.0))
            else:
                f_w = np.exp(0.05039 * wind)            
            sflag = 0   # Setting the slope flag to zero after including wind effect due to slope
            # Initial Spread Index with slope and (or) wind
            isi = isi * f_w
            # Rate of spead for non-zero slope and (or) non-zero wind
            ros , _ = VanWagner.ros

        # Default
        return min(ros , 6.0)
    
    @staticmethod
    def ros(
        fclass: int,
        fcon: float,
        fhard: float,
        fdfir: float,
        sh: float,
        sd: float,
        deg_curing: float,
        isi: float,
        sflag: float,
        sf: float,
        bui: float,
    ) -> float:
               
        # Rate of Spread Coefficients
        a = [90 , 110 , 110 , 110 , 30 , 30 , 45 , 30 , 75 , 40 , 55 , 190 , 250 , 0 , 0 , 120 , 100]
        b = [0.0649 , 0.0282 , 0.0444 , 0.0293 , 0.0697 , 0.08 , 0.0305 , 0.0232 , 0.0297 , 0.0438 , 0.0829 , 0.031 , 0.035 , 0 , 0 , 0.0572 , 0.0404]
        c = [4.5 , 1.5 , 3.0 , 1.5 , 4.0 , 3.0 , 2.0 , 1.6 , 1.3 , 1.7 , 3.2 , 1.4 , 1.7 , 0 , 0 , 1.4 , 1.48]
        q = [0.9 , 0.7 , 0.75 , 0.8 , 0.8 , 0.8 , 0.85 , 0.9 , 0.75 , 0.75 , 0.75 , 1.0 , 1.0 , 0.8 , 0.8 , 0.8 , 0.8]
        
        # Buildup Index (BUI)
        bui0 = [72 , 64 , 62 , 66 , 56 , 62 , 106 , 32 , 38 , 63 , 31 , 0 , 0 , 50 , 50 , 50 , 50]
        
        # Max Buildup Effect
        max_be  = [1.076 , 1.321 , 1.261 , 1.184 , 1.22 , 1.197 , 1.134 , 1.179 , 1.46 , 1.256 , 1.59 , 1.0 , 1.0 , 1.25 , 1.25 , 1.25 , 1.25]
        
        # Max ISF
        max_isf = [71 , 163 , 103 , 157 , 66 , 58 , 151 , 198 , 155 , 105 , 56 , 148 , 132 ]
 
        # Fuel class C-1 (Spruce-lichen woodland)
        # Fuel class C-2 (Boreal spruce)
        # Fuel class C-3 (Mature jack or lodgepole pine)
        # Fuel class C-4 (Immature jack or lodgepole pine)
        # Fuel class C-5 (Red and white pine)
        # Fuel class C-6 (Conifer plantation)
        # Fuel class C-7 (Ponderosa pine - Douglas fir)
        # Fuel class D-1 (Leafless aspen)
        # Fuel class S-1 (Jack or lodgepole pine slash)
        # Fuel class S-2 (White spruce - balsam slash)
        # Fuel class S-3 (Coastal cedar - hemlock - Douglas - fir slash)
        # Fuel class O-1a (Grass)
        # Fuel class O-1b (Grass)
        # Fuel class M-1 (Boreal mixedwood - leafless) 
        # Fuel class M-2 (Boreal mixedwood - green)
        # Fuel class M-3 (Dead balsam fir mixedwood - leafless) 
        # Fuel class M-4 (Dead balsam fir mixedwood - green)

        # Buildup effect (BE)
        be = np.exp(50.0 * np.log(q[fclass - 1]) * ((1.0 / bui) - (1.0 / bui0[fclass - 1])))
        if be >= max_be[fclass - 1]: be = max_be[fclass - 1]

        # Rate of Spread Calculations (m/min)
        if fclass != 6 or fclass != 12 or fclass != 13 or fclass != 14 or fclass != 15 or fclass != 16 or fclass != 17:
            ros = a[fclass - 1] * np.power((1.0 - np.exp(-b[fclass - 1] * isi)) , c[fclass - 1]) * be

        if fclass == 6:
            fmc = VanWagner.foliar_moisture_content 
            fme = np.power((1.5 - 0.000275 * fmc) , 4) * 1000.0 / (460.0 + 25.9 * fmc)   # Foliar moisture effect
            cfb = -11.2 + 1.06 * sh + 0.00170 * sd
            ros = a[fclass - 1] * np.power((1.0 - np.exp(-b[fclass - 1] * isi)) , c[fclass - 1])
            rss = ros * be
            rsc = 60.0 * np.power((1.0 - np.exp(-0.0497 * isi)) , 1.0) * fme / 0.778
            ros = rss + cfb * (rsc - rss)  

        if fclass == 12 or fclass == 13:
            if deg_curing < 58.8:
                cf = 0.005 * np.exp(0.061 * deg_curing - 1.0)
            else:
                cf = 0.176 + 0.02 * (deg_curing - 58.8)
            ros = a[fclass - 1] * np.power((1.0 - np.exp(-b[fclass - 1] * isi)) , c[fclass - 1]) * be

        if fclass == 14 or fclass == 15:
            ros_c2 = a[1] * np.power((1.0 - np.exp(-b[1] * isi)) , c[1])
            ros_d1 = a[7] * np.power((1.0 - np.exp(-b[7] * isi)) , c[7])            
            if fclass == 14:
                ros = (fcon / 100.0) * ros_c2 + (fhard / 100.0) * ros_d1 
            else:
                ros = (fcon / 100.0) * ros_c2 + 0.2 * (fhard / 100.0) * ros_d1 * be
            ros = ros * be

        if fclass == 16 or fclass == 17:
            ros_d1 = a[7] * np.power((1.0 - np.exp(-b[7] * isi)) , c[7])    
            ros_m = a[fclass - 1] * np.power((1.0 - np.exp(-b[fclass - 1] * isi)) , c[fclass - 1])      
            ros = (fdfir / 100.0) * ros_m + (1.0 - fdfir / 100.0) * ros_d1
            ros = ros * be

        if sflag == 1:
            rsf = ros * sf
            if fclass != 14 or fclass != 15 or fclass != 16 or fclass != 17:
                if fclass == 12 or fclass == 13:
                    p = 1.0 - np.power((rsf / (cf * a[fclass - 1])) , 1.0 / c[fclass - 1])
                else:
                    p = 1.0 - np.power((rsf / a[fclass - 1]) , 1.0 / c[fclass - 1])

                if p >= 0.01:
                    isf = np.log(p) / -b[fclass - 1]
                else:
                    isf = np.log(0.01) / -b[fclass - 1]
                if isf > max_isf[fclass - 1]:
                    isf = max_isf

            if fclass == 14 or fclass == 15 or fclass == 16 or fclass == 17:
                p2 = 1.0 - np.power((rsf / a[7]) , 1.0 / c[7])
                if p2 >= 0.01: 
                    isf_d1 = np.log(p2) / -b[7] 
                else: 
                    isf_d1 = np.log(0.01) / -b[7]    
                if isf_d1 > max_isf[7]: 
                    isf_d1 = max_isf[7]
                
                if fclass == 14 or fclass == 15:
                    p1 = 1.0 - np.power((rsf / a[1]) , 1.0 / c[1])
                    if p1 >= 0.01: 
                        isf_c2 = np.log(p1) / -b[1] 
                    else: 
                        isf_c2 = np.log(0.01) / -b[1]    
                    if isf_c2 > max_isf[1]: 
                        isf_c2 = max_isf[1]
                    isf = (fcon / 100.0) * isf_c2 + (1.0 - fcon / 100.0) * isf_d1

                if fclass == 16 or fclass == 17:
                    m = 1.0 - np.power((rsf / a[fclass - 1]) , 1.0 / c[fclass - 1])
                    if m >= 0.01: 
                        isf_m = np.log(m) / -b[fclass - 1] 
                    else: 
                        isf_m = np.log(0.01) / -b[fclass - 1]    
                    if isf_m > max_isf[fclass - 1]: 
                        isf_m = max_isf[fclass - 1]
                    isf = (fdfir / 100.0) * isf_m + (1.0 - fdfir / 100.0) * isf_d1                
        else:
            isf = 0  

        # Default
        return min(ros, 6.0) , isf
        
    @staticmethod
    def foliar_moisture_content(
        fclass: int,
        Dj: int,
        lat: float,
        lon: float,
        elev: float,
    ) -> float:

        # Foliar Moisture Content Calculations (FMC)
        if fclass == 6:
            latn = 46.0 + 23.4 * np.exp(-0.0360 * (150.0 - lon))
            D0 = 151.0 * (lat / latn)
            ND = np.mod(Dj - D0)
        elif fclass == 6 and elev != 0:
            latn = 43.0 + 33.7 * np.exp(-0.0351 * (150.0 - lon))
            D0 = 142.1 * (lat / latn) + 0.0172 * elev
            ND = np.mod(Dj - D0)
        else:
            ND = -1

        if ND > 0 and ND < 30:
            fmc = 85.0 + 0.0189 * np.power(ND , 2.0)
        elif ND >= 30 and ND < 50:
            fmc = 32.9 + 3.17 * ND - 0.0288 * np.power(ND , 2.0)
        else:
            fmc = 120    

        return fmc

    @staticmethod
    def fine_fuel_moisture_code(
        fclass: int,
        wind: float,
        temp_air: float,
        rel_humid: float,
        precip: float,
        ffmci: float,
        deg_curing: float,
    ) -> float:
    
        # Calculation of Coefficients
        m0 = 147.2 * (101 - ffmci) / (59.5 + ffmci)
        precip_f = precip - 0.5  # Precipitation Min value 0.5, measured at noon every day 
        
        if precip > 0.5:
            if m0 <= 150:
                mr = m0 + 42.5 * precip_f * np.exp(-100.0 / (251.0 - m0)) * (1.0 - np.exp(-6.93 / precip_f))
            else:
                mr = m0 + 42.5 * precip_f * np.exp(-100.0 / (251.0 - m0)) * (1.0 - np.exp(-6.93 / precip_f)) 
                + 0.0015 * np.power((m0 - 150.0) , 2) * np.power(precip_f , 0.5)

            if mr > 250:
                mr = 250

            m0 = mr

        Ed = 0.942 * np.power(rel_humid , 0.679) + 11 * np.exp((rel_humid - 100.0) / 10.0) + 0.18 * \
        (21.1 - temp_air) * (1.0 - np.exp(-0.115 * rel_humid))

        if m0 > Ed:
            k0 = 0.424 * (1.0 - np.power((rel_humid / 100.0) , 1.7)) + 0.0694 * np.power(wind , 0.5) * (1.0 - np.power((rel_humid / 100) , 8.0))
            kd = k0 * 0.581 * np.exp(0.0365 * temp_air)
            m = Ed + (m0 - Ed) * np.power(10 , -kd)
        else:
            Ew = 0.618 * np.power(rel_humid , 0.753) + 10 * np.exp((rel_humid - 100.0) / 10.0) + 0.18 * \
            (21.1 - temp_air) * (1.0 - np.exp(-0.115 * rel_humid))

        if m0 < Ew:
            k1 = 0.424 * (1.0 - np.power(((100.0 - rel_humid) / 100.0) , 1.7)) + 0.0694 * np.power(wind , 0.5) * \
            (1.0 - np.power(((100.0 - rel_humid) / 100) , 8.0))
            kw = k1 * 0.581 * np.exp(0.0365 * temp_air)
            m = Ew + (Ew - m0) * np.power(10 , -kw)

        if Ed >= m0 >= Ew:
            m = m0

        ffmc = 59.5 * (250.0 - m) / (147.2 + m)

        return ffmc

    @staticmethod
    def duff_moisture_code(
        month: float,
        temp_air: float,
        rel_humid: float,
        precip: float,
        dmci: float,
    ) -> float:

        if temp_air < -1.1: temp_air = -1.1     
        
        # Calculation of Coefficients
        Le = [6.5 , 7.5 , 9.0 , 12.8 , 13.9 , 13.9 , 12.4 , 10.9 , 9.4 , 8.0 , 7.0 , 6.0]  # Day length factor
        K = 1.894 * (temp_air + 1.1) * (100.0 - rel_humid) * Le[month - 1] * 0.000001   #Calculate log drying rate
   
        if precip > 1.5:
            Pe = 0.92 * precip - 1.27    # Calculate effective rainfall
            mc0 = 20.0 + np.exp(5.6348 - dmci / 43.43)  # Duff moisture content from previous day
            
            if dmci <= 33:      # Calculating slope variable in DMC rain effect
                b = 100.0 / (0.5 + 0.3 * dmci)
            elif dmci > 33 and dmci <= 65:
                b = 14.0 - 1.3 * np.log(dmci) 
            else:
                b = 6.2 * np.log(dmci) - 17.2

            mcr = mc0 + 1000 * Pe / (48.77 + b * Pe)   # Duff moisture content after rain
            dmcr = 244.72 - 43.43 * np.log(mcr - 20.0)   # Duff moisture code after rain
            if dmcr < 0: dmcr = 0.0

            dmc = dmcr + K * 100.0   # Duff moisture code with rain effect (P > 1.5)
        else:
            dmc = dmci + K * 100.0   # Duff moisture code without rain effect

        return dmc

    @staticmethod
    def drought_code(
        month: float,
        temp_air: float,
        rel_humid: float,
        precip: float,
        dci: float,
    ) -> float:

        if temp_air < -2.8: temp_air = -2.8     
        
        # Calculation of Coefficients
        Le = [-1.6 , -1.6 , -1.6 , 0.9 , 3.8 , 5.8 , 6.4 , 5.0 , 2.4 , 0.4 , -1.6 , -1.6]  # Day length factor
        V = 0.36 * (temp_air + 2.8) + Le   # Calculate evapotranspiration factor
        if V < 0: V = 0

        if precip > 2.8:
            Pe = 0.83 * precip - 1.27    # Calculate effective rainfall
            mc0 = 800.0 * np.exp(-dci / 400.0)  # Moisture equivalent of previous day         
            mcr = mc0 + 3.937 * Pe   # Moisture equivalent after rain
            dcr = 400.0 * np.log(800.0 / mcr)   # Drought code after rain
            if dcr < 0: dcr = 0.0

            dc = dcr + V * 0.5   # Drought code with rain effect (P > 1.5)
        else:
            dc = dci + V * 0.5   # Drought code without rain effect

        return dc
    
    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using ``VanWagner's`` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the ROS. Input data must be provided in standard units without ``pint.Quantity`` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should be the standard variable names as defined in ``VanWagner.metadata``.
            Each value can be a single float/int or a list/array of floats/ints.

        **opt : dict
            Additional optional parameters to be passed to the ``rothermel`` method.

        Returns
        -------
        float
            The computed rate of spread of fire.

        Notes
        -----

        Examples
        --------
        **Example with scalar fuel properties:**

        .. code-block:: python

            input_data = {
                svn.FUEL_CLASS: 13,
                svn.FUEL_CONIFER_CONTENT: 25.0, 
                svn.FUEL_HARDWOOD_CONTENT: 10.0, 
                svn.FUEL_DEAD_FIR_CONTENT: 50.0, 
                svn.STAND_HEIGHT: 15.0, 
                svn.STAND_DENSITY: 1000.0,
                svn.JULIAN_DATE: 30, 
                svn.MONTH: 1, 
                svn.LATITUDE: 45.0, 
                svn.LONGITUDE: 45.0, 
                svn.WIND_SPEED: 10.0, 
                svn.WIND_DIRECTION: 10.0, 
                svn.SLOPE_ANGLE: 10.0, 
                svn.ELEVATION: 0.0, 
                svn.FINE_FUEL_MOISTURE_CODE_INITIAL: 85.0, 
                svn.DUFF_MOISTURE_CODE_INITIAL: 25.0, 
                svn.DROUGHT_CODE_INITIAL: 10.0, 
                svn.AIR_TEMPERATURE: 35.0,
                svn.PRECIPITATION: 1.0,
                svn.RELATIVE_HUMIDITY: 40.0, 
                svn.DEGREE_OF_CURING: 60.0,
            }
            ros = VanWagner.compute_ros(input_data)
            print(f"The rate of spread is {ros:.4f}")
        """  # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=VanWagner.metadata
        )

        # Calculate the rate of spread
        return VanWagner.VanWagner(**fuel_properties)

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
            Keys should match the variable names defined in `VanWagner.metadata`.

        **opt : dict
            Additional optional parameters passed to `compute_ros`.

        Returns
        -------
        ureg.Quantity
            Computed rate of spread (ROS) with units (e.g., meters per minute).

        Notes
        -----
        - Use this function when working with `pint.Quantity` objects in `input_dict`.
        - Units for the ROS are defined in `VanWagner.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            VanWagner.compute_ros(input_dict_no_units, **opt),
            VanWagner.metadata["rate_of_spread"]["units"],
        )