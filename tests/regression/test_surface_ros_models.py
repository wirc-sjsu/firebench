import firebench.ros_models as rm
import numpy as np
import pytest
from firebench import Quantity, svn


## Rothermel
@pytest.mark.parametrize(
    "fgi,fueldepthm,fueldens,savr,fuelmce,st,se,ichap,wind,slope,fmc,expected_ros",
    [
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 0, 0, 0.1, 0.020630697262906682),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 1, 0, 0, 0.1, 0.03333),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, -1, 0, 0.1, 0.020630697262906682),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 2, 0, 0.1, 0.30339676498092233),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 2, 10, 0.1, 0.31978349285057384),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 2, -10, 0.1, 0.30339676498092233),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 2, 0, 0.5, 0.28811909268223007),
        (0.8, 0.3, 32, 1500, 0.3, 0.01, 0.055, 0, 25, 20, 0.1, 6),
    ],
)
def test_compute_ros_regression_rothermel(
    fgi, fueldepthm, fueldens, savr, fuelmce, st, se, ichap, wind, slope, fmc, expected_ros
):
    ros = rm.Rothermel_SFIRE.rothermel(
        fgi, fueldepthm, fueldens, savr, fuelmce, st, se, ichap, wind, slope, fmc
    )
    assert np.isclose(ros, expected_ros)


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: 0.5,
                svn.FUEL_HEIGHT: 1.0,
                svn.FUEL_DENSITY: 32.0,
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: 1500.0,
                svn.FUEL_MOISTURE_EXTINCTION: 20.0,
                svn.FUEL_MINERAL_CONTENT_TOTAL: 0.0555,
                svn.FUEL_MINERAL_CONTENT_EFFECTIVE: 0.01,
                svn.FUEL_CHAPARRAL_FLAG: 0,
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
                "fuel_cat": None,
            },
            0.436663860541543,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: [0.5],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY: [32.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [1500.0],
                svn.FUEL_MOISTURE_EXTINCTION: [20.0],
                svn.FUEL_MINERAL_CONTENT_TOTAL: [0.0555],
                svn.FUEL_MINERAL_CONTENT_EFFECTIVE: [0.01],
                svn.FUEL_CHAPARRAL_FLAG: [0],
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
                "fuel_cat": 1,
            },
            0.436663860541543,  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_rothermel(input_dict, expected_ros):
    ros = rm.Rothermel_SFIRE.compute_ros(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros, expected_ros, atol=1e-4)


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: Quantity(0.5, "kg/m^2"),
                svn.FUEL_HEIGHT: Quantity(1.0, "m"),
                svn.FUEL_DENSITY: Quantity(32.0, "lb/ft^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: Quantity(1500.0, "1/ft"),
                svn.FUEL_MOISTURE_EXTINCTION: Quantity(20.0, "percent"),
                svn.FUEL_MINERAL_CONTENT_TOTAL: Quantity(0.0555, "dimensionless"),
                svn.FUEL_MINERAL_CONTENT_EFFECTIVE: Quantity(0.01, "dimensionless"),
                svn.FUEL_CHAPARRAL_FLAG: Quantity(0, "dimensionless"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degree"),
                svn.FUEL_MOISTURE_CONTENT: Quantity(10.0, "percent"),
                "fuel_cat": None,
            },
            Quantity(0.436663860541543, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: Quantity([0.5], "kg/m^2"),
                svn.FUEL_HEIGHT: Quantity([1.0], "m"),
                svn.FUEL_DENSITY: Quantity([32.0], "lb/ft^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: Quantity([1500.0], "1/ft"),
                svn.FUEL_MOISTURE_EXTINCTION: Quantity([20.0], "percent"),
                svn.FUEL_MINERAL_CONTENT_TOTAL: Quantity([0.0555], "dimensionless"),
                svn.FUEL_MINERAL_CONTENT_EFFECTIVE: Quantity([0.01], "dimensionless"),
                svn.FUEL_CHAPARRAL_FLAG: Quantity([0], "dimensionless"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degree"),
                svn.FUEL_MOISTURE_CONTENT: Quantity(10.0, "percent"),
                "fuel_cat": 1,
            },
            Quantity(0.436663860541543, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_with_units_rothermel(input_dict, expected_ros):
    ros = rm.Rothermel_SFIRE.compute_ros_with_units(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros.magnitude, expected_ros.magnitude, atol=1e-4)


## Balbi
@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: 0.8,
                svn.FUEL_LOAD_DRY_TOTAL: 1,
                svn.FUEL_HEIGHT: 1.0,
                svn.FUEL_DENSITY: 300.0,
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: 4500.0,
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
                "fuel_cat": None,
            },
            0.4441852112687365,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: [0.8],
                svn.FUEL_LOAD_DRY_TOTAL: [1],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY: [300.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [4500.0],
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
                "fuel_cat": 1,
            },
            0.4441852112687365,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: [0.8],
                svn.FUEL_LOAD_DRY_TOTAL: [1],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY: [300.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [4500.0],
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
                svn.IGNITION_LENGTH: 50,
                "fuel_cat": 1,
            },
            0.4441852112687365,  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_balbi(input_dict, expected_ros):
    ros = rm.Balbi_2022_fixed_SFIRE.compute_ros(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros, expected_ros, atol=1e-4)
    ros = rm.Balbi_2022_fixed_SFIRE.compute_ros(input_dict, fuel_cat=input_dict["fuel_cat"], max_ite=1)
    assert ros == 0


## Balbi
@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: Quantity(0.8, "dimensionless"),
                svn.FUEL_LOAD_DRY_TOTAL: Quantity(1, "kg/m^2"),
                svn.FUEL_HEIGHT: Quantity(1.0, "m"),
                svn.FUEL_DENSITY: Quantity(300.0, "kg/m^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: Quantity(4500.0, "1/m"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degree"),
                svn.FUEL_MOISTURE_CONTENT: Quantity(10.0, "percent"),
                "fuel_cat": None,
            },
            Quantity(0.4441852112687365, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: Quantity([0.8], "dimensionless"),
                svn.FUEL_LOAD_DRY_TOTAL: Quantity([1], "kg/m^2"),
                svn.FUEL_HEIGHT: Quantity([1.0], "m"),
                svn.FUEL_DENSITY: Quantity([300.0], "kg/m^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: Quantity([4500.0], "1/m"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degree"),
                svn.FUEL_MOISTURE_CONTENT: Quantity(10.0, "percent"),
                "fuel_cat": 1,
            },
            Quantity(0.4441852112687365, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DEAD_RATIO: Quantity([0.8], "dimensionless"),
                svn.FUEL_LOAD_DRY_TOTAL: Quantity([1], "kg/m^2"),
                svn.FUEL_HEIGHT: Quantity([1.0], "m"),
                svn.FUEL_DENSITY: Quantity([300.0], "kg/m^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: Quantity([4500.0], "1/m"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degree"),
                svn.FUEL_MOISTURE_CONTENT: Quantity(10.0, "percent"),
                svn.IGNITION_LENGTH: Quantity(50, "m"),
                "fuel_cat": 1,
            },
            Quantity(0.4441852112687365, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_with_units_balbi(input_dict, expected_ros):
    ros = rm.Balbi_2022_fixed_SFIRE.compute_ros_with_units(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros.magnitude, expected_ros.magnitude, atol=1e-4)
    ros = rm.Balbi_2022_fixed_SFIRE.compute_ros_with_units(
        input_dict, fuel_cat=input_dict["fuel_cat"], max_ite=1
    )
    assert ros.magnitude == 0


@pytest.mark.parametrize(
    "dead_fuel_ratio,fgi,fueldepthm,fueldens,temp_ign,temp_air,dens_air,savr,w0,wind,slope,fmc,expected_ros",
    [
        (0.8, 0.7, 1, 300, 600, 300, 1.125, 4500, 50, 1, 0, 10, 0.4643753930790799),
        (0.8, 0.7, 1, 300, 600, 300, 1.125, 4500, 30, 1, 0, 10, 0.3881006880449338),
        (0.8, 0.7, 1, 300, 600, 300, 1.125, 4500, 50, 0, 0, 10, 0.3455042235417564),
        (0.8, 0.7, 1, 300, 600, 300, 1.125, 4500, 50, -1, 0, 10, 0.3455042235417564),
        (0.8, 0.7, 1, 300, 600, 300, 1.125, 4500, 50, 0, 10, 10, 0.3387330641766883),
    ],
)
def test_compute_ros_regression_balbi(
    dead_fuel_ratio,
    fgi,
    fueldepthm,
    fueldens,
    temp_ign,
    temp_air,
    dens_air,
    savr,
    w0,
    wind,
    slope,
    fmc,
    expected_ros,
):
    ros = rm.Balbi_2022_fixed_SFIRE.balbi_2022_fixed(
        dead_fuel_ratio,
        fgi,
        fueldepthm,
        fueldens,
        temp_ign,
        temp_air,
        dens_air,
        savr,
        w0,
        wind,
        slope,
        fmc,
    )
    assert np.isclose(ros, expected_ros)


## Santoni 2011
@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: 1,
                svn.FUEL_LOAD_DEAD_RATIO: 0.8,
                svn.FUEL_HEIGHT: 1.0,
                svn.FUEL_DENSITY_DEAD: 300.0,
                svn.FUEL_DENSITY_LIVE: 300.0,
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD: 4500.0,
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE: 4500.0,
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT_DEAD: 10.0,
                svn.FUEL_MOISTURE_CONTENT_LIVE: 100.0,
                "fuel_cat": None,
            },
            0.5086438204142792,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: [1],
                svn.FUEL_LOAD_DEAD_RATIO: [0.8],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY_DEAD: [300.0],
                svn.FUEL_DENSITY_LIVE: [300.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD: [4500.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE: [4500.0],
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT_DEAD: 10.0,
                svn.FUEL_MOISTURE_CONTENT_LIVE: 100.0,
                "fuel_cat": 1,
            },
            0.5086438204142792,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: [1],
                svn.FUEL_LOAD_DEAD_RATIO: [0.8],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY_DEAD: [300.0],
                svn.FUEL_DENSITY_LIVE: [300.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD: [4500.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE: [4500.0],
                svn.WIND_SPEED: 1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT_DEAD: 10.0,
                svn.FUEL_MOISTURE_CONTENT_LIVE: 100.0,
                svn.AIR_TEMPERATURE: 330,
                "fuel_cat": 1,
            },
            0.5972921793806639,  # Expected ROS value (adjust this to the expected value)
        ),
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: [1],
                svn.FUEL_LOAD_DEAD_RATIO: [0.8],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY_DEAD: [300.0],
                svn.FUEL_DENSITY_LIVE: [300.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD: [4500.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE: [4500.0],
                svn.WIND_SPEED: -1.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT_DEAD: 10.0,
                svn.FUEL_MOISTURE_CONTENT_LIVE: 100.0,
                svn.AIR_TEMPERATURE: 330,
                "fuel_cat": 1,
            },
            0.34929049626422026,  # Expected ROS value (adjust this to the expected value)
        ),
    ],
)
def test_compute_ros_santoni2011(input_dict, expected_ros):
    ros = rm.Santoni_2011.compute_ros(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros, expected_ros, atol=1e-4)


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_LOAD_DRY_TOTAL: Quantity(1, "kg/m^2"),
                svn.FUEL_LOAD_DEAD_RATIO: Quantity(0.8, "dimensionless"),
                svn.FUEL_HEIGHT: Quantity(1.0, "m"),
                svn.FUEL_DENSITY_DEAD: Quantity(300.0, "kg/m^3"),
                svn.FUEL_DENSITY_LIVE: Quantity(300.0, "kg/m^3"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD: Quantity(4500.0, "1/m"),
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE: Quantity(4500.0, "1/m"),
                svn.WIND_SPEED: Quantity(1.0, "m/s"),
                svn.SLOPE_ANGLE: Quantity(0.0, "degrees"),
                svn.FUEL_MOISTURE_CONTENT_DEAD: Quantity(10.0, "percent"),
                svn.FUEL_MOISTURE_CONTENT_LIVE: Quantity(100.0, "percent"),
                "fuel_cat": None,
            },
            Quantity(0.5086438204142792, "m/s"),  # Expected ROS value (adjust this to the expected value)
        ),
    ],
)
def test_compute_ros_with_units_santoni(input_dict, expected_ros):
    ros = rm.Santoni_2011.compute_ros_with_units(input_dict, fuel_cat=input_dict["fuel_cat"])
    assert np.isclose(ros.magnitude, expected_ros.magnitude, atol=1e-4)
