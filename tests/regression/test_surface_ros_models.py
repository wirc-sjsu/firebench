import firebench.ros_models as rm
import numpy as np
import pytest
from firebench import svn

# test dataset
@pytest.fixture
def dummy_fuel_data_rothermel():
    return {
        "windrf": [0.5, 0.6, 0.5, 1],
        "fgi": [0.2, 1, 2, 1],
        "fueldepthm": [0.3, 1, 1.5, 1],
        "fueldens": [32.0, 32.0, 32, 32],
        "savr": [3000, 2000, 1700, 2000],
        "fuelmce": [40.0, 30.0, 30, 30],
        "st": [0.05, 0.05, 0.05, 0.05],
        "se": [0.01, 0.01, 0.01, 0.01],
        "ichap": [0, 0, 0, 1],
    }


@pytest.mark.parametrize(
    "fuelclass, wind, slope, fmc, expected_ros",
    [
        (1, 0, 0, 10, 0.028314841074642185),
        (2, 0, 0, 10, 0.06408485130331253),
        (3, 0, 0, 10, 0.08775528075542277),
        (4, 0, 0, 10, 0.03333),
        (1, -5, 0, 10, 0.028314841074642185),
        (1, 5, 0, 10, 0.7728050572886503),
        (1, 0, -20, 10, 0.028314841074642185),
        (1, 0, 20, 10, 0.17356099974334135),
        (1, 3, 10, 15, 0.2967349404168692),
        (1, 3, 10, 20, 0.26090285525387974),
        (1, 20, 45, 5, 6.0),
    ],
)
def test_compute_ros_rothermel_regression(
    dummy_fuel_data_rothermel, fuelclass, wind, slope, fmc, expected_ros
):
    ros = rm.Rothermel_SFIRE.rothermel(dummy_fuel_data_rothermel, fuelclass, wind, slope, fmc)

    assert np.isclose(ros, expected_ros)


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_WIND_REDUCTION_FACTOR: [0.3],
                svn.FUEL_LOAD_DRY_TOTAL: [0.5],
                svn.FUEL_HEIGHT: [1.0],
                svn.FUEL_DENSITY: [32.0],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [1500.0],
                svn.FUEL_MOISTURE_EXTINCTION: [20.0],
                svn.FUEL_MINERAL_CONTENT_TOTAL: [0.0555],
                svn.FUEL_MINERAL_CONTENT_EFFECTIVE: [0.01],
                svn.FUEL_CHAPARRAL_FLAG: [0],
                svn.FUEL_CLASS: 1,
                svn.WIND_SPEED: 5.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
            },
            0.7176587116405758,  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_rothermel(input_dict, expected_ros):
    ros = rm.Rothermel_SFIRE.compute_ros(input_dict)
    assert pytest.approx(ros, rel=1e-2) == expected_ros


@pytest.mark.parametrize(
    "input_dict, expected_ros",
    [
        (
            {
                svn.FUEL_WIND_REDUCTION_FACTOR: [0.3],
                svn.FUEL_LOAD_DRY_TOTAL: [0.5],
                svn.FUEL_HEIGHT: [1],
                svn.FUEL_DENSITY: [500],
                svn.FUEL_SURFACE_AREA_VOLUME_RATIO: [5000],
                svn.FUEL_CLASS: 1,
                svn.WIND_SPEED: 5.0,
                svn.SLOPE_ANGLE: 0.0,
                svn.FUEL_MOISTURE_CONTENT: 10.0,
            },
            0.8882486476176378,  # Expected ROS value (adjust this to the expected value)
        ),
        # Add more test cases as needed
    ],
)
def test_compute_ros_balbi(input_dict, expected_ros):
    ros = rm.Balbi_2022_fixed_SFIRE.compute_ros(input_dict)
    assert pytest.approx(ros, rel=1e-2) == expected_ros


@pytest.fixture
def dummy_fuel_data_balbi():
    return {
        "windrf": [0.44, 0.6, 0.5, 1],
        "fgi": [0.5, 1, 2, 1],
        "fueldepthm": [0.5, 1, 1.5, 1],
        "fueldens": [500, 500, 500, 500],
        "savr": [5000, 5500, 4500, 5000],
    }


@pytest.mark.parametrize(
    "fuelclass, wind, slope, fmc, use_wind_reduction_factor, expected_ros",
    [
        (1, 10, 0, 10, False, 1.0255006280365424),
        (2, 0, 0, 10, False, 0.5080291664333749),
        (3, 0, 0, 10, False, 0.4112658432897564),
        (4, 0, 0, 10, False, 0.4676783259268038),
        (1, -5, 0, 10, False, 0.39599878435328895),
        (1, 5, 0, 10, False, 0.6649416102966412),
        (1, 0, -20, 10, False, 0.39599878435328895),
        (1, 0, 20, 10, False, 0.3658781276924766),
        (1, 3, 10, 15, False, 0.4473273380736792),
        (1, 3, 10, 20, True, 0.383234609787183),
        (1, 20, 45, 5, False, 2.364154054547705),
    ],
)
def test_compute_ros_balbi_regression(
    dummy_fuel_data_balbi, fuelclass, wind, slope, fmc, use_wind_reduction_factor, expected_ros
):
    ros = rm.Balbi_2022_fixed_SFIRE.balbi_2022_fixed(
        dummy_fuel_data_balbi,
        fuelclass,
        wind,
        slope,
        fmc,
        opt={"use_wind_reduction_factor": use_wind_reduction_factor},
    )
    print(ros)
    assert np.isclose(ros, expected_ros)
