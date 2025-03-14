import re

import firebench.tools as ft
import firebench.wind_interpolation as fwi
import numpy as np
import pytest
from firebench import svn


## use_wind_reduction_factor test
def test_use_wind_reduction_factor_float():
    wind_speed = 10.0
    reduction_factor = 0.8
    expected_speed = 8.0

    result = fwi.apply_wind_reduction_factor(wind_speed=wind_speed, wind_reduction_factor=reduction_factor)
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_use_wind_reduction_factor_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]  # Indexed by fuel_cat
    fuel_cat = 2
    expected_speed = 8.0  # 10.0 * 0.8

    result = fwi.apply_wind_reduction_factor(
        wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
    )
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"

    # Try with numpy array
    reduction_factors = np.array(reduction_factors)
    result = fwi.apply_wind_reduction_factor(
        wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
    )
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_missing_fuel_cat_with_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]

    with pytest.raises(ValueError, match="category_index must be an integer greater than or equal to 1."):
        fwi.apply_wind_reduction_factor(wind_speed=wind_speed, wind_reduction_factor=reduction_factors)


def test_invalid_fuel_cat_with_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]
    fuel_cat = 5  # Index out of range
    expected_message = f"One-based index {fuel_cat} not found in {reduction_factors}."

    with pytest.raises(IndexError, match=re.escape(expected_message)):
        fwi.apply_wind_reduction_factor(
            wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
        )


## Baughman_wrf_unsheltered
def test_Baughman_wrf_unsheltered_float():
    flame_height = 6.0  # Midflame height
    vegetation_height = 2.0  # Vegetation height
    expected_wrf = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height, vegetation_height
    )

    result = fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_height, vegetation_height=vegetation_height
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_wrf_unsheltered_list():
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]  # Indexed by fuel_cat
    fuel_cat = 2
    veg_height = vegetation_heights[fuel_cat - 1]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height, veg_height
    )

    result = fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_height, vegetation_height=vegetation_heights, fuel_cat=fuel_cat
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"

    # Try with numpy array
    vegetation_heights = np.array(vegetation_heights)
    result = fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_height, vegetation_height=vegetation_heights, fuel_cat=fuel_cat
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_wrf_unsheltered_missing_fuel_cat_with_list():
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]

    with pytest.raises(ValueError, match="category_index must be an integer greater than or equal to 1."):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, vegetation_height=vegetation_heights
        )


def test_Baughman_wrf_unsheltered_invalid_fuel_cat_with_list():
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]
    fuel_cat = 5  # Index out of range
    expected_message = f"One-based index {fuel_cat} not found in {vegetation_heights}."

    with pytest.raises(IndexError, match=re.escape(expected_message)):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, vegetation_height=vegetation_heights, fuel_cat=fuel_cat
        )


## Baughman_20ft_wrf_unsheltered validation
def test_Baughman_20ft_validation():
    # data from Baughman and Albini (1980)
    fuel_height = [1.0, 1.0, 2.5, 6.0, 2.0, 2.5, 2.5, 0.2, 0.2, 1.0, 1.0, 2.3, 3.0]
    # wind_red_fac = [0.36, 0.36, 0.44, 0.55, 0.42, 0.44, 0.44, 0.36, 0.36, 0.36, 0.36, 0.43, 0.46] # Issue with cat 7, 8 compared to original paper
    wind_red_fac = [0.36, 0.36, 0.44, 0.55, 0.42, 0.44, 0.44, 0.28, 0.28, 0.36, 0.36, 0.43, 0.46]
    # ratio flame length / fuel height
    ratio_fl_fh = 1  # according to Baughman and Albini (1980)

    for k in range(13):
        wrf = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
            ratio_fl_fh * fuel_height[k], fuel_height[k]
        )
        assert np.round(wrf, 2) == wind_red_fac[k]


## Baughman_generalized_wrf_unsheltered
def test_Baughman_generalized_wrf_unsheltered_float():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0  # Flame height
    vegetation_height = 2.0  # Vegetation height
    expected_wrf = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height, flame_height, vegetation_height, False
    )

    result = fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_height,
        flame_height=flame_height,
        vegetation_height=vegetation_height,
        is_source_wind_height_above_veg=False,
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_generalized_wrf_unsheltered_list():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]  # Indexed by fuel_cat
    fuel_cat = 2
    veg_height = vegetation_heights[fuel_cat - 1]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height, flame_height, veg_height, False
    )

    result = fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_height,
        flame_height=flame_height,
        vegetation_height=vegetation_heights,
        fuel_cat=fuel_cat,
        is_source_wind_height_above_veg=False,
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"

    # Try with numpy array
    vegetation_heights = np.array(vegetation_heights)
    result = fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_height,
        flame_height=flame_height,
        vegetation_height=vegetation_heights,
        fuel_cat=fuel_cat,
        is_source_wind_height_above_veg=False,
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_generalized_wrf_unsheltered_missing_fuel_cat_with_list():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]

    with pytest.raises(ValueError, match="category_index must be an integer greater than or equal to 1."):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            vegetation_height=vegetation_heights,
            is_source_wind_height_above_veg=False,
        )


def test_Baughman_generalized_wrf_unsheltered_invalid_fuel_cat_with_list():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]
    fuel_cat = 5  # Index out of range

    expected_message = f"One-based index {fuel_cat} not found in {vegetation_heights}."

    with pytest.raises(IndexError, match=re.escape(expected_message)):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            vegetation_height=vegetation_heights,
            fuel_cat=fuel_cat,
            is_source_wind_height_above_veg=False,
        )


## Baughman_generalized_wrf_unsheltered validation
def test_Baughman_generalization_validation():
    # data from Baughman and Albini (1980)
    fuel_height = [1.0, 1.0, 2.5, 6.0, 2.0, 2.5, 2.5, 0.2, 0.2, 1.0, 1.0, 2.3, 3.0]
    # wind_red_fac = [0.36, 0.36, 0.44, 0.55, 0.42, 0.44, 0.44, 0.36, 0.36, 0.36, 0.36, 0.43, 0.46] # Issue with cat 7, 8 compared to original paper
    wind_red_fac = [0.36, 0.36, 0.44, 0.55, 0.42, 0.44, 0.44, 0.27, 0.27, 0.36, 0.36, 0.43, 0.46]
    # ratio flame length / fuel height
    ratio_fl_fh = 1  # according to Baughman and Albini (1980)

    for k in range(13):
        wrf = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
            20, ratio_fl_fh * fuel_height[k], fuel_height[k], True
        )
        # print(wrf, np.round(wrf, 2), wind_red_fac[k])
        assert np.round(wrf, 2) == wind_red_fac[k]


def test_primitive_log_profile():
    # Define test inputs and expected output
    z = 10.0
    d_0 = 1.0
    z_0 = 0.5
    expected_output = (z - d_0) * np.log((z - d_0) / z_0) - z

    # Calculate output using the function
    result = fwi.wind_reduction_factor.__primitive_log_profile(z, d_0, z_0)

    # Assert that the result matches the expected output within a tolerance
    assert np.isclose(result, expected_output, atol=1e-6), f"Expected {expected_output}, got {result}"
