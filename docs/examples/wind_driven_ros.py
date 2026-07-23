"""Minimal custom rate-of-spread model used by the documentation."""

from pint import Quantity

import firebench.tools as ft
from firebench.ros_models import RateOfSpreadModel


class WindDrivenROS(RateOfSpreadModel):
    """Minimal wind-driven rate-of-spread model."""

    metadata = {
        "wind_speed": {
            "std_name": ft.StandardVariableNames.WIND_SPEED,
            "units": ft.ureg.meter / ft.ureg.second,
            "range": (0.0, 100.0),
            "type": ft.ParameterType.input,
        },
        "wind_factor": {
            "std_name": ft.StandardVariableNames.ALPHA,
            "units": ft.ureg.dimensionless,
            "range": (0.0, 1.0),
            "type": ft.ParameterType.optional,
            "default": 0.04,
        },
        "rate_of_spread": {
            "std_name": ft.StandardVariableNames.RATE_OF_SPREAD,
            "units": ft.ureg.meter / ft.ureg.second,
            "range": (0.0, float("inf")),
            "type": ft.ParameterType.output,
        },
    }

    @staticmethod
    def wind_driven_ros(wind_speed: float, wind_factor: float) -> float:
        """Return rate of spread in metres per second."""
        return wind_factor * wind_speed

    @staticmethod
    def compute_ros(input_dict: dict, fuel_cat: int = 0, **opt) -> float:
        """Compute ROS from magnitudes expressed in the metadata units."""
        del opt
        model_inputs = RateOfSpreadModel.prepare_fuel_properties(
            input_dict=input_dict,
            metadata=WindDrivenROS.metadata,
            fuel_cat=fuel_cat,
        )
        return WindDrivenROS.wind_driven_ros(**model_inputs)

    @staticmethod
    def compute_ros_with_units(input_dict: dict, fuel_cat: int = 0, **opt) -> Quantity:
        """Convert and validate quantities before computing ROS."""
        converted_inputs = ft.check_data_quality_ros_model(input_dict, WindDrivenROS)
        input_magnitudes = ft.extract_magnitudes(converted_inputs)
        ros = WindDrivenROS.compute_ros(input_magnitudes, fuel_cat=fuel_cat, **opt)
        return ft.ureg.Quantity(ros, WindDrivenROS.metadata["rate_of_spread"]["units"])
