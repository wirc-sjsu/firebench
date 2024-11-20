import numpy as np
from pint import Quantity

from ..tools.check_data_quality import extract_magnitudes
from ..tools.input_info import ParameterType
from ..tools.namespace import StandardVariableNames as svn
from ..tools.rate_of_spread_model import RateOfSpreadModel
from ..tools.units import ureg


class Hamada_1(RateOfSpreadModel):
    """
    A class to represent the Hamada's model for urban fire spread rate calculation in its version 1.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS) of fire
    using the Hamada's model. The metadata includes descriptions, units, and acceptable ranges for each property.

    Attributes
    ----------
    metadata : dict
        A dictionary containing metadata for various fuel properties such as building separation and side_length.
        Each entry in the dictionary provides a description, units, and acceptable range for the property.

    Methods
    -------
    compute_ros
        Compute the rate of spread of fire using Hamada's model.
    """  # pylint: disable=line-too-long

    metadata = {
        "side_length": {
            "std_name": svn.BUILDING_LENGTH_SIDE,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "separation": {
            "std_name": svn.BUILDING_LENGTH_SEPARATION,
            "units": ureg.meter,
            "range": (0, np.inf),
            "type": ParameterType.input,
        },
        "wind_u": {
            "std_name": svn.WIND_SPEED_U,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "wind_v": {
            "std_name": svn.WIND_SPEED_V,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
            "type": ParameterType.input,
        },
        "normal_vector_x": {
            "std_name": svn.NORMAL_SPREAD_DIR_X,
            "units": ureg.dimensionless,
            "range": (-1, 1),
            "type": ParameterType.input,
        },
        "normal_vector_y": {
            "std_name": svn.NORMAL_SPREAD_DIR_Y,
            "units": ureg.dimensionless,
            "range": (-1, 1),
            "type": ParameterType.input,
        },
        "fire_resistant_ratio": {
            "std_name": svn.BUILDING_RATIO_FIRE_RESISTANT,
            "units": ureg.dimensionless,
            "range": (0, 1),
            "type": ParameterType.optional,
            "default": 0.6,
        },
        "rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
            "type": ParameterType.output,
        },
    }

    @staticmethod
    def hamada_1(
        side_length: float,
        separation: float,
        wind_u: float,
        wind_v: float,
        normal_vector_x: float,
        normal_vector_y: float,
        fire_resistant_ratio: float,
    ) -> float:
        """
        Compute the urban rate of spread using the Hamada model.

        Parameters
        ----------
        side_length : float
            Building side length [m].
        separation : float
            Buildings separation [m].
        wind_u : float
            The U component of the wind speed [m s-1].
        wind_v : float
            The V component of the wind speed [m s-1].
        normal_vector_x : float
            The X component of the normalized spread direction vector [-].
        wind_direction_y : float
            The Y component of the normalized spread direction vector [-].
        fire_resistant_ratio : float
            The ratio of fire-resistant buildings [-].

        Returns
        -------
        float
            The computed urban rate of spread in meters per second.
        """
        # norm of the wind
        wind = np.hypot(wind_u, wind_v)
        # rate of spread along specific directions
        t_d = (
            (1 - fire_resistant_ratio)
            * (
                3
                + 0.375 * side_length
                + 8 * separation / (25 + 2.5 * wind)
            )
            + fire_resistant_ratio
            * (
                5
                + 0.625 * side_length
                + 16 * separation / (25 + 2.5 * wind)
            )
        ) / (1.5 * (1 + 0.1 * wind + 0.007 * wind**2))
        t_o = (
            (1 - fire_resistant_ratio)
            * (
                3
                + 0.375 * side_length
                + 8 * separation / (5 + 0.25 * wind)
            )
            + fire_resistant_ratio
            * (
                5
                + 0.625 * side_length
                + 16 * separation / (5 + 0.25 * wind)
            )
        ) / (1 + 0.005 * wind**2)
        t_u = (
            (1 - fire_resistant_ratio)
            * (
                3
                + 0.375 * side_length
                + 8 * separation / (5 + 0.2 * wind)
            )
            + fire_resistant_ratio
            * (
                5
                + 0.625 * side_length
                + 16 * separation / (5 + 0.2 * wind)
            )
        ) / (1 + 0.002 * wind**2)
        # downwind ros
        ros_d = (
            side_length + separation
        ) / t_d
        # orthogonal ros
        ros_o = (
            side_length + separation
        ) / t_o
        # upwind ros
        ros_u = (
            side_length + separation
        ) / t_u

        # ellipse parameters as a function of spread direction
        k = 1
        if wind > 0:
            k = (normal_vector_x * wind_u + normal_vector_y * wind_v) / wind
        # check on which ellispe we are
        if k >= 0:
            eccentricity = (ros_d - ros_o) / ros_d
            a_ellipse = ros_d**2 / (2 * ros_d - ros_o)
            return a_ellipse * (1 - eccentricity**2) / (1 - eccentricity * k) / 60

        return ros_o * ros_u / np.sqrt(ros_u**2 * (1 - k**2) + ros_o**2 * k**2) / 60

    @staticmethod
    def compute_ros(
        input_dict: dict[str, float | int | list[float] | list[int]],
        fuel_cat: int = 0,
    ) -> float:
        """
        Compute the rate of spread of fire using the `Hamada's` model.

        This function processes input fuel properties, optionally selects a specific fuel category,
        and calculates the rate of spread (ROS) of fire using the `hamada_1` method.
        Missing keys in the input dictionary are replaced with their default values, 
        as specified in `Hamada_1.metadata`. Input data must be provided in standard units 
        without `pint.Quantity` objects.
        For unit-aware calculations, use `compute_ros_with_units`.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing the input data for various fuel properties.
            The keys should match the standard variable names as defined in `Hamada_1.metadata`.
            Each value can be a single float/int or a list/array of floats/ints.

        fuel_cat : int, optional
            Fuel category index (one-based). If provided, fuel properties are expected to be lists or arrays,
            and the function will extract the properties corresponding to the specified fuel category.
            If not provided, fuel properties are expected to be scalar values.

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
        """ # pylint: disable=line-too-long
        # Prepare fuel properties using the base class method
        fuel_properties = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict, metadata=Hamada_1.metadata, fuel_cat=fuel_cat
        )

        # Calculate the rate of spread
        return Hamada_1.hamada_1(**fuel_properties)
    
    @staticmethod
    def compute_ros_with_units(
        input_dict: dict[str, float | int | list[float] | list[int] | Quantity],
        fuel_cat: int = 0,
        **opt,
    ) -> Quantity:
        """
        Compute the rate of spread (ROS) of fire using Hamada's 2022 model with unit handling.

        This function extracts magnitudes from input data (removing `pint.Quantity` wrappers),
        computes the ROS using `compute_ros`, and attaches the appropriate unit to the result.

        Parameters
        ----------
        input_dict : dict
            Dictionary containing input fuel properties as `pint.Quantity` objects or standard values.
            Keys should match the variable names defined in `Hamada.metadata`.

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
        - Units for the ROS are defined in `Hamada_1.metadata["rate_of_spread"]["units"]`.
        """  # pylint: disable=line-too-long
        input_dict_no_units = extract_magnitudes(input_dict)

        return ureg.Quantity(
            Hamada_1.compute_ros(input_dict_no_units, fuel_cat, **opt),
            Hamada_1.metadata["rate_of_spread"]["units"],
        )


class Hamada_2(RateOfSpreadModel):
    """
    A class to represent the Hamada's model for urban fire spread rate calculation in its version 2.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS) of fire
    using the Hamada's model. The metadata includes descriptions, units, and acceptable ranges for each property.

    Attributes
    ----------
    metadata : dict
        A dictionary containing metadata for various fuel properties such as as building separation and side_length.
        Each entry in the dictionary provides a description, units, and acceptable range for the property.

    Methods
    -------
    compute_ros
        Compute the rate of spread of fire using Hamada's model.
    """  # pylint: disable=line-too-long

    metadata = {
        "side_length": {
            "std_name": svn.BUILDING_LENGTH_SIDE,
            "units": ureg.meter,
            "range": (0, np.inf),
        },
        "separation": {
            "std_name": svn.BUILDING_LENGTH_SEPARATION,
            "units": ureg.meter,
            "range": (0, np.inf),
        },
        "wind_u": {
            "std_name": svn.WIND_SPEED_U,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
        },
        "wind_v": {
            "std_name": svn.WIND_SPEED_V,
            "units": ureg.meter / ureg.second,
            "range": (-np.inf, np.inf),
        },
        "normal_vector_x": {
            "std_name": svn.NORMAL_SPREAD_DIR_X,
            "units": ureg.dimensionless,
            "range": (-1, 1),
        },
        "normal_vector_y": {
            "std_name": svn.NORMAL_SPREAD_DIR_Y,
            "units": ureg.dimensionless,
            "range": (-1, 1),
        },
        "fire_resistant_ratio": {
            "std_name": svn.BUILDING_RATIO_FIRE_RESISTANT,
            "units": ureg.dimensionless,
            "range": (0, 1),
        },
        "bare_structure_ratio": {
            "std_name": svn.BUILDING_RATIO_STRUCTURE_WOOD_BARE,
            "units": ureg.dimensionless,
            "range": (0, 1),
        },
        "mortar_structure_ratio": {
            "std_name": svn.BUILDING_RATIO_STRUCTURE_WOOD_MORTAR,
            "units": ureg.dimensionless,
            "range": (0, 1),
        },
        "beta": {
            "std_name": svn.BETA,
            "units": ureg.dimensionless,
            "range": (0, np.inf),
        },
        "output_rate_of_spread": {
            "std_name": svn.RATE_OF_SPREAD,
            "units": ureg.meter / ureg.second,
            "range": (0, np.inf),
        },
    }

    @staticmethod
    def hamada_2(
        fuel_data: dict,
        fuel_class_index: int,
        wind_u: float,
        wind_v: float,
        normal_vector_x: float,
        normal_vector_y: float,
        fire_resistant_ratio: float,
        bare_structure_ratio: float,
        mortar_structure_ratio: float,
        beta: float,
    ) -> float:
        """
        Compute the urban rate of spread using the Hamada model.

        Parameters
        ----------
        fuel_data : dict
            A dictionary containing fuel properties such as side length and separation.
        fuel_class_index : int
            The fuel class index (1-based) to be used for the computation.
        wind_u : float
            The U component of the wind speed.
        wind_v : float
            The V component of the wind speed.
        normal_vector_x : float
            The X component of the normalized spread direction vector.
        wind_direction_y : float
            The Y component of the normalized spread direction vector.
        fire_resistant_ratio : float
            The ratio of fire-resistant buildings.
        bare_structure_ratio : float
            The ratio of buildings with bare structural materials.
        mortar_structure_ratio : float
            The ratio of buildings with mortar.
        beta : float
            The beta parameter for the model (>2 for stability).

        Returns
        -------
        float
            The computed urban rate of spread in meters per second.
        """
        # Convert 1-based index to 0-based
        fuel_class_index -= 1

        # Calculate wind speed magnitude
        wind_speed = np.hypot(wind_u, wind_v)

        # Calculate downwind rate of spread
        downwind_ros = (
            (bare_structure_ratio + mortar_structure_ratio)
            * (1 - fire_resistant_ratio)
            * (fuel_data["side_length"][fuel_class_index] + fuel_data["separation"][fuel_class_index])
            * (1 + 0.1 * wind_speed + 0.007 * wind_speed**2)
            / (
                (bare_structure_ratio + 5 * mortar_structure_ratio / 3)
                * (
                    3
                    + 3 * fuel_data["side_length"][fuel_class_index] / 8
                    + 8 * fuel_data["separation"][fuel_class_index] / (1.15 * beta * (5 + 0.5 * wind_speed))
                )
            )
        )

        # Calculate orthogonal rate of spread
        orthogonal_ros = (
            (bare_structure_ratio + mortar_structure_ratio)
            * (1 - fire_resistant_ratio)
            * (fuel_data["side_length"][fuel_class_index] + fuel_data["separation"][fuel_class_index])
            * (1 + 0.002 * wind_speed**2)
            / (
                (bare_structure_ratio + 5 * mortar_structure_ratio / 3)
                * (
                    3
                    + 3 * fuel_data["side_length"][fuel_class_index] / 8
                    + 8 * fuel_data["separation"][fuel_class_index] / (1.15 * (5 + 0.5 * wind_speed))
                )
            )
        )
        cos_theta = 0
        if wind_speed > 0:
            cos_theta = (normal_vector_x * wind_u + normal_vector_y * wind_v) / wind_speed
        eccentricity = (downwind_ros - orthogonal_ros) / downwind_ros
        a_ellipse = downwind_ros**2 / (2 * downwind_ros - orthogonal_ros)
        # c_ellipse = downwind_ros * (downwind_ros - orthogonal_ros) / (2 *downwind_ros - orthogonal_ros)
        return a_ellipse * (1 - eccentricity**2) / (1 - eccentricity * cos_theta) / 60

    @staticmethod
    def compute_ros(
        input_dict: dict[str, list[float]],
        **opt,
    ) -> float:
        """
        Compute the rate of spread of fire using the Hamada's model.

        This is a wrapper function that prepares the fuel data dictionary and calls the `hamada_1` method.

        If the one or more of the following keys are missing from the input dict, the default value are used:
        - svn.BUILDING_RATIO_FIRE_RESISTANT: 0.6
        - svn.BUILDING_RATIO_STRUCTURE_WOOD_BARE: 0.2
        - svn.BUILDING_RATIO_STRUCTURE_WOOD_MORTAR: 0.2
        - svn.BETA: 5

        Parameters
        ----------
        input_dict : dict[str, list[float]]
            Dictionary containing the input data for various fuel properties.

        Optional Parameters
        -------------------
        **opt : dict
            Optional parameters for the `rothermel` method.

        Returns
        -------
        float
            The computed rate of spread of fire [m/s].
        """
        fuel_dict_list_vars = [
            "side_length",
            "separation",
        ]
        fuel_dict = {}
        for var in fuel_dict_list_vars:
            fuel_dict[var] = input_dict[Hamada_2.metadata[var]["std_name"]]

        # Set default values for low importance inputs
        fire_resistant_ratio = input_dict.get(svn.BUILDING_RATIO_FIRE_RESISTANT, 0.6)
        bare_structure_ratio = input_dict.get(svn.BUILDING_RATIO_STRUCTURE_WOOD_BARE, 0.2)
        mortar_structure_ratio = input_dict.get(svn.BUILDING_RATIO_STRUCTURE_WOOD_MORTAR, 0.2)
        beta = input_dict.get(svn.BETA, 5)

        return Hamada_2.hamada_2(
            fuel_dict,
            input_dict[svn.FUEL_CLASS],
            input_dict[svn.WIND_SPEED_U],
            input_dict[svn.WIND_SPEED_V],
            input_dict[svn.NORMAL_SPREAD_DIR_X],
            input_dict[svn.NORMAL_SPREAD_DIR_Y],
            fire_resistant_ratio=fire_resistant_ratio,
            bare_structure_ratio=bare_structure_ratio,
            mortar_structure_ratio=mortar_structure_ratio,
            beta=beta,
            **opt,
        )
