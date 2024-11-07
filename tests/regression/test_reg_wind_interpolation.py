import firebench.wind_interpolation as fwi
import numpy as np
import pytest

@pytest.mark.parametrize("interpolation_height, vegetation_height, expected_wrf", [
    (6.0, 2.0, 0.5761355663987836),
    (5.0, 1.5, 0.558326541665057),
    (4.0, 1.0, 0.5419365681707666),
    (8.0, 2.5, 0.6172075513324579),
    (10.0, 3.0, 0.6516899089092155),
])
def test_Baughman_20ft_wrf_unsheltered_regression(interpolation_height, vegetation_height, expected_wrf):
    result = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        interpolation_height,
        vegetation_height
    )
    assert np.isclose(result, expected_wrf, rtol=1e-5), (
        f"Failed for interpolation_height={interpolation_height}, "
        f"vegetation_height={vegetation_height}: expected {expected_wrf}, got {result}"
    )