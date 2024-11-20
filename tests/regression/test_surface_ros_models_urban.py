import firebench.ros_models as rm
import numpy as np
import pytest
from firebench import Quantity, svn


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.BUILDING_LENGTH_SIDE: [20],
                svn.BUILDING_LENGTH_SEPARATION: [5],
                svn.WIND_SPEED_U: 1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
                "fuel_cat": 1,
            },
            0.04063334223171382,  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: 20,
                svn.BUILDING_LENGTH_SEPARATION: 5,
                svn.WIND_SPEED_U: 1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
                "fuel_cat": 1,
            },
            0.04063334223171382,  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: 20,
                svn.BUILDING_LENGTH_SEPARATION: 5,
                svn.WIND_SPEED_U: 1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
                svn.BUILDING_RATIO_FIRE_RESISTANT: 0.7,
                "fuel_cat": 1,
            },
            0.038711215666327584,  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: [20],
                svn.BUILDING_LENGTH_SEPARATION: [5],
                svn.WIND_SPEED_U: -1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
                "fuel_cat": 1,
            },
            0.015458558815152377,  # Expected ROS value
        ),
    ],
)
def test_compute_ros_hamada_1(input_dict, expected_ros):
    ros = rm.Hamada_1.compute_ros(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert pytest.approx(ros, rel=1e-2) == expected_ros

@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.BUILDING_LENGTH_SIDE: Quantity([20], "m"),
                svn.BUILDING_LENGTH_SEPARATION: Quantity([5], "m"),
                svn.WIND_SPEED_U: Quantity(1.0, "m/s"),
                svn.WIND_SPEED_V: Quantity(0.0, "m/s"),
                svn.NORMAL_SPREAD_DIR_X: Quantity(1.0, "dimensionless"),
                svn.NORMAL_SPREAD_DIR_Y: Quantity(0.0, "dimensionless"),
                "fuel_cat": 1,
            },
            Quantity(0.04063334223171382, "m/s"),  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: Quantity(20, "m"),
                svn.BUILDING_LENGTH_SEPARATION: Quantity(5, "m"),
                svn.WIND_SPEED_U: Quantity(1.0, "m/s"),
                svn.WIND_SPEED_V: Quantity(0.0, "m/s"),
                svn.NORMAL_SPREAD_DIR_X: Quantity(1.0, "dimensionless"),
                svn.NORMAL_SPREAD_DIR_Y: Quantity(0.0, "dimensionless"),
                "fuel_cat": 1,
            },
            Quantity(0.04063334223171382, "m/s"),  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: Quantity([20], "m"),
                svn.BUILDING_LENGTH_SEPARATION: Quantity([5], "m"),
                svn.WIND_SPEED_U: Quantity(1.0, "m/s"),
                svn.WIND_SPEED_V: Quantity(0.0, "m/s"),
                svn.NORMAL_SPREAD_DIR_X: Quantity(1.0, "dimensionless"),
                svn.NORMAL_SPREAD_DIR_Y: Quantity(0.0, "dimensionless"),
                svn.BUILDING_RATIO_FIRE_RESISTANT: Quantity(0.7, "dimensionless"),
                "fuel_cat": 1,
            },
            Quantity(0.038711215666327584, "m/s"),  # Expected ROS value
        ),
    ],
)
def test_compute_ros_with_units_hamada_1(input_dict, expected_ros):
    ros = rm.Hamada_1.compute_ros_with_units(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert pytest.approx(ros.magnitude, rel=1e-2) == expected_ros.magnitude

@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.BUILDING_LENGTH_SIDE: [20],
                svn.BUILDING_LENGTH_SEPARATION: [5],
                svn.FUEL_CLASS: 1,
                svn.WIND_SPEED_U: 1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
            },
            0.011761758777087185,  # Expected ROS value
        ),
        (
            {
                svn.BUILDING_LENGTH_SIDE: [20],
                svn.BUILDING_LENGTH_SEPARATION: [5],
                svn.FUEL_CLASS: 1,
                svn.WIND_SPEED_U: -1.0,
                svn.WIND_SPEED_V: 0.0,
                svn.NORMAL_SPREAD_DIR_X: 1.0,
                svn.NORMAL_SPREAD_DIR_Y: 0.0,
            },
            0.005445817028744205,  # Expected ROS value
        ),
    ],
)
def test_compute_ros_hamada_2(input_dict, expected_ros):
    ros = rm.Hamada_2.compute_ros(input_dict)
    assert pytest.approx(ros, rel=1e-2) == expected_ros
