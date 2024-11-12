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
        (20.0, 6.0, 2.0, False, 0.5892891329244908),  # example value, replace with known expected output
        (20.0, 6.0, 2.0, True, 0.5756265984603116),  # example value, replace with known expected output
        (15.0, 5.0, 1.5, False, 0.6075278401473907),  # example value, replace with known expected output
        (15.0, 5.0, 1.5, True, 0.5934424454061547),  # example value, replace with known expected output
        (10.0, 4.0, 1.0, False, 0.64002283721826),  # example value, replace with known expected output
        (10.0, 4.0, 1.0, True, 0.6251840533636174),  # example value, replace with known expected output
        # Add more test cases as necessary
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
