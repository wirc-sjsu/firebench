import firebench.ros_models as rm
import firebench.tools as ft
import pytest
from firebench import svn, ureg
from pint import Quantity


def test_check_data_quality_ros_model():
    # Prepare test data
    fuel_data = ft.read_fuel_data_file("Anderson13")
    ros_model = rm.Rothermel_SFIRE
    input_vars_info = {
        svn.WIND_SPEED: 3 * ureg.meter / ureg.second,
        svn.SLOPE_ANGLE: 0 * ureg.degree,
        svn.FUEL_MOISTURE_CONTENT: 10 * ureg.percent,
    }
    input_dict = ft.merge_dictionaries(fuel_data, input_vars_info)

    print(input_dict)

    # Run the function
    final_input = ft.check_data_quality_ros_model(input_dict, ros_model)

    print(final_input)

    # Check the completeness of the final input
    ft.check_input_completeness(input_dict, ros_model.metadata)

    # Check specific values in the final input (example)
    assert final_input[svn.WIND_SPEED] == 3, "WIND value mismatch"
    assert final_input[svn.SLOPE_ANGLE] == 0, "SLOPE_ANGLE value mismatch"
    assert final_input[svn.FUEL_MOISTURE_CONTENT] == 10, "FUEL_MOISTURE_CONTENT value mismatch"
