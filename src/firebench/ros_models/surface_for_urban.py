import numpy as np

from ..tools.namespace import StandardVariableNames as svn
from ..tools.units import ureg

from .rate_of_spread_model import RateOfSpreadModel


class Hamada_2(RateOfSpreadModel):
    """
    A class to represent the Hamada's model for urban fire spread rate calculation in its version 1.

    This class provides metadata for various fuel properties and a static method to compute the rate of spread (ROS) of fire
    using the Hamada's model. The metadata includes descriptions, units, and acceptable ranges for each property.

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
        fire_resistant_ratio: float = 0.4,
        bare_structure_ratio: float = 0.2,
        mortar_structure_ratio: float = 0.4,
        beta: float = 1,
        **options,
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
        fire_resistant_ratio : float, optional
            The ratio of fire-resistant buildings. Default is 0.4.
        bare_structure_ratio : float, optional
            The ratio of buildings with bare structural materials. Default is 0.2.
        mortar_structure_ratio : float, optional
            The ratio of buildings with mortar. Default is 0.4.
        beta : float, optional
            The beta parameter for the model. Default is 1.
        **options : dict
            Additional optional parameters.

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

        return Hamada_2.hamada_2(
            fuel_dict,
            input_dict[svn.FUEL_CLASS],
            input_dict[svn.WIND_SPEED_U],
            input_dict[svn.WIND_SPEED_V],
            input_dict[svn.NORMAL_SPREAD_DIR_X],
            input_dict[svn.NORMAL_SPREAD_DIR_Y],
            input_dict[svn.BUILDING_RATIO_FIRE_RESISTANT],
            input_dict[svn.BUILDING_RATIO_STRUCTURE_WOOD_BARE],
            input_dict[svn.BUILDING_RATIO_STRUCTURE_WOOD_MORTAR],
            input_dict[svn.BETA],
            **opt,
        )
