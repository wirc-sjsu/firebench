import firebench.wind_interpolation as fwi
import numpy as np
import pytest


@pytest.mark.parametrize(
    "flame_height, vegetation_height, expected_wrf",
    [
        (6.0, 2.0, 0.5761355663987836),
        (5.0, 1.5, 0.558326541665057),
        (4.0, 1.0, 0.5419365681707666),
        (8.0, 2.5, 0.6172075513324579),
        (10.0, 3.0, 0.6516899089092155),
    ],
)
def test_Baughman_20ft_wrf_unsheltered_regression(flame_height, vegetation_height, expected_wrf):
    result = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height, vegetation_height
    )
    assert np.isclose(result, expected_wrf, rtol=1e-5), (
        f"Failed for flame_height={flame_height}, "
        f"vegetation_height={vegetation_height}: expected {expected_wrf}, got {result}"
    )


@pytest.mark.parametrize(
    "input_wind_height, flame_height, vegetation_height, is_source_wind_height_above_veg, expected_wrf",
    [
        (20.0, 6.0, 2.0, False, 0.5892891329244908),
        (15.0, 5.0, 1.5, False, 0.6075278401473907),
        (15.0, 5.0, 1.5, True, 0.5934424454061547),
        (10.0, 4.0, 1.0, False, 0.64002283721826),
        (10.0, 4.0, 1.0, True, 0.6251840533636174),
    ],
)
def test_Baughman_generalized_wind_reduction_factor_unsheltered_regression(
    input_wind_height, flame_height, vegetation_height, is_source_wind_height_above_veg, expected_wrf
):
    result = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height, flame_height, vegetation_height, is_source_wind_height_above_veg
    )
    assert np.isclose(result, expected_wrf, rtol=1e-5), (
        f"Failed for input_wind_height={input_wind_height}, flame_height={flame_height}, "
        f"vegetation_height={vegetation_height}, is_source_wind_height_above_veg={is_source_wind_height_above_veg}: "
        f"expected {expected_wrf}, got {result}"
    )


@pytest.mark.parametrize(
    "wind_speed_atm, input_wind_height, building_height, building_separation, fuel_cat, expected_wind_canyon",
    [
        (10, 100, 20, 3, 2, 0.38410989518782196),
        (10, 100, 2, 1, 1, 0.21018870345549612),
        (10, 100, 30, 6, 3, 0.6688103823022014),
        (10, 100, 50, 15, 4, 1.2859976393496242),
    ],
)
def test_Masson_canyon_regression(
    wind_speed_atm, input_wind_height, building_height, building_separation, fuel_cat, expected_wind_canyon
):
    # dummy building classification
    building_height_cat = [2, 20, 30, 50]
    building_separation_cat = [1, 3, 6, 15]

    # Direct computation
    wind_can = fwi.Masson_canyon(wind_speed_atm, input_wind_height, building_height, building_separation)
    assert np.isclose(
        wind_can, expected_wind_canyon, rtol=1e-5
    ), f"Failed for direct computation, expected {expected_wind_canyon}, got {wind_can}"

    # Computation using categorical classification
    wind_can = fwi.Masson_canyon(
        wind_speed_atm, input_wind_height, building_height_cat, building_separation_cat, fuel_cat=fuel_cat
    )
    assert np.isclose(
        wind_can, expected_wind_canyon, rtol=1e-5
    ), f"Failed for use of classification, expected {expected_wind_canyon}, got {wind_can}"
