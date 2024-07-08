import firebench.ros_models as rm
import numpy as np
import pytest
from firebench import svn

# test dataset
@pytest.fixture
def dummy_fuel_data():
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
def test_compute_ros_regression(dummy_fuel_data, fuelclass, wind, slope, fmc, expected_ros):
    ros = rm.Rothermel_SFIRE.rothermel(dummy_fuel_data, fuelclass, wind, slope, fmc)

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
def test_compute_ros(input_dict, expected_ros):
    ros = rm.Rothermel_SFIRE.compute_ros(input_dict)
    assert pytest.approx(ros, rel=1e-2) == expected_ros
