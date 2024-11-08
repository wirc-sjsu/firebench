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

    result = fwi.use_wind_reduction_factor(wind_speed=wind_speed, wind_reduction_factor=reduction_factor)
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_use_wind_reduction_factor_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]  # Indexed by fuel_cat
    fuel_cat = 2
    expected_speed = 8.0  # 10.0 * 0.8

    result = fwi.use_wind_reduction_factor(
        wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
    )
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"

    # Try with numpy array
    reduction_factors = np.array(reduction_factors)
    result = fwi.use_wind_reduction_factor(
        wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
    )
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_use_wind_reduction_factor_fuel_dict_and_fuelcat():
    wind_speed = 10.0
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: [0.7, 0.8, 0.9]}
    fuel_cat = 2
    expected_speed = 8.0  # 10.0 * 0.8

    result = fwi.use_wind_reduction_factor(wind_speed=wind_speed, fuel_dict=fuel_dict, fuel_cat=fuel_cat)
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_use_wind_reduction_factor_fuel_dict():
    wind_speed = 10.0
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: 0.8}
    expected_speed = 8.0  # 10.0 * 0.8

    result = fwi.use_wind_reduction_factor(
        wind_speed=wind_speed,
        fuel_dict=fuel_dict,
    )
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_missing_fuel_cat_with_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]

    with pytest.raises(ValueError, match="fuel_cat must be provided when wind_reduction_factor is a list."):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed, wind_reduction_factor=reduction_factors)


def test_invalid_fuel_cat_with_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]
    fuel_cat = 5  # Index out of range

    with pytest.raises(
        IndexError, match=f"Fuel category {fuel_cat-1} not found in wind_reduction_factor array."
    ):
        fwi.use_wind_reduction_factor(
            wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
        )


def test_fuel_dict_wrong_key_fuel_cat():
    wind_speed = 10.0
    fuel_dict = {"other": [0.7, 0.8, 0.9]}
    fuel_cat = 2

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict."):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed, fuel_dict=fuel_dict, fuel_cat=fuel_cat)


def test_invalid_fuel_cat_with_fuel_dict():
    wind_speed = 10.0
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: [0.7, 0.8, 0.9]}
    fuel_cat = 5  # Index out of range

    with pytest.raises(IndexError, match=f"Fuel category {fuel_cat-1} not found in fuel_dict."):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed, fuel_dict=fuel_dict, fuel_cat=fuel_cat)


def test_fuel_dict_wrong_key():
    wind_speed = 10.0
    fuel_dict = {"other": 0.8}

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict."):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed, fuel_dict=fuel_dict)


def test_insufficient_parameters():
    wind_speed = 10.0

    with pytest.raises(ValueError, match="Insufficient parameters provided"):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed)


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


def test_Baughman_wrf_unsheltered_fuel_dict_and_fuelcat():
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    fuel_cat = 2
    veg_height = fuel_dict[svn.FUEL_HEIGHT][fuel_cat - 1]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height, veg_height
    )

    result = fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_height, fuel_dict=fuel_dict, fuel_cat=fuel_cat
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_wrf_unsheltered_fuel_dict():
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: 2.0}
    veg_height = fuel_dict[svn.FUEL_HEIGHT]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height, veg_height
    )

    result = fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
        flame_height=flame_height, fuel_dict=fuel_dict
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_wrf_unsheltered_missing_fuel_cat_with_list():
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]

    with pytest.raises(ValueError, match="fuel_cat must be provided when vegetation_height is a list."):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, vegetation_height=vegetation_heights
        )


def test_Baughman_wrf_unsheltered_invalid_fuel_cat_with_list():
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]
    fuel_cat = 5  # Index out of range

    with pytest.raises(
        IndexError, match=f"Fuel category {fuel_cat-1} not found in vegetation_height array."
    ):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, vegetation_height=vegetation_heights, fuel_cat=fuel_cat
        )


def test_Baughman_wrf_unsheltered_fuel_dict_wrong_key_fuel_cat():
    flame_height = 6.0
    fuel_dict = {"other_key": [1.5, 2.0, 2.5]}
    fuel_cat = 2

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_HEIGHT} not found in fuel_dict."):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, fuel_dict=fuel_dict, fuel_cat=fuel_cat
        )


def test_Baughman_wrf_unsheltered_invalid_fuel_cat_with_fuel_dict():
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    fuel_cat = 5  # Index out of range

    with pytest.raises(IndexError, match=f"Fuel category {fuel_cat-1} not found in fuel_dict."):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(
            flame_height=flame_height, fuel_dict=fuel_dict, fuel_cat=fuel_cat
        )


def test_Baughman_wrf_unsheltered_fuel_dict_wrong_key():
    flame_height = 6.0
    fuel_dict = {"other_key": 2.0}

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_HEIGHT} not found in fuel_dict."):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(flame_height=flame_height, fuel_dict=fuel_dict)


def test_Baughman_wrf_unsheltered_insufficient_parameters():
    flame_height = 6.0

    with pytest.raises(ValueError, match="Insufficient parameters provided"):
        fwi.Baughman_20ft_wind_reduction_factor_unsheltered(flame_height=flame_height)


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


def test_Baughman_generalized_wrf_unsheltered_fuel_dict_and_fuelcat():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    fuel_cat = 2
    veg_height = fuel_dict[svn.FUEL_HEIGHT][fuel_cat - 1]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height, flame_height, veg_height, False
    )

    result = fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_height,
        flame_height=flame_height,
        fuel_dict=fuel_dict,
        fuel_cat=fuel_cat,
        is_source_wind_height_above_veg=False,
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_generalized_wrf_unsheltered_fuel_dict():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: 2.0}
    veg_height = fuel_dict[svn.FUEL_HEIGHT]
    expected_wrf = fwi.wind_reduction_factor.__Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height, flame_height, veg_height, False
    )

    result = fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
        input_wind_height=input_wind_height,
        flame_height=flame_height,
        fuel_dict=fuel_dict,
        is_source_wind_height_above_veg=False,
    )
    assert np.isclose(result, expected_wrf), f"Expected {expected_wrf}, got {result}"


def test_Baughman_generalized_wrf_unsheltered_missing_fuel_cat_with_list():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    vegetation_heights = [1.5, 2.0, 2.5]

    with pytest.raises(ValueError, match="fuel_cat must be provided when vegetation_height is a list."):
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

    with pytest.raises(
        IndexError, match=f"Fuel category {fuel_cat-1} not found in vegetation_height array."
    ):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            vegetation_height=vegetation_heights,
            fuel_cat=fuel_cat,
            is_source_wind_height_above_veg=False,
        )


def test_Baughman_generalized_wrf_unsheltered_fuel_dict_wrong_key_fuel_cat():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    fuel_dict = {"other_key": [1.5, 2.0, 2.5]}
    fuel_cat = 2

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_HEIGHT} not found in fuel_dict."):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            fuel_dict=fuel_dict,
            fuel_cat=fuel_cat,
            is_source_wind_height_above_veg=False,
        )


def test_Baughman_generalized_wrf_unsheltered_invalid_fuel_cat_with_fuel_dict():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    fuel_dict = {svn.FUEL_HEIGHT: [1.5, 2.0, 2.5]}
    fuel_cat = 5  # Index out of range

    with pytest.raises(IndexError, match=f"Fuel category {fuel_cat-1} not found in fuel_dict."):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            fuel_dict=fuel_dict,
            fuel_cat=fuel_cat,
            is_source_wind_height_above_veg=False,
        )


def test_Baughman_generalized_wrf_unsheltered_fuel_dict_wrong_key():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0
    fuel_dict = {"other_key": 2.0}

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_HEIGHT} not found in fuel_dict."):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height,
            flame_height=flame_height,
            fuel_dict=fuel_dict,
            is_source_wind_height_above_veg=False,
        )


def test_Baughman_generalized_wrf_unsheltered_insufficient_parameters():
    input_wind_height = 20  # Input wind height
    flame_height = 6.0

    with pytest.raises(ValueError, match="Insufficient parameters provided"):
        fwi.Baughman_generalized_wind_reduction_factor_unsheltered(
            input_wind_height=input_wind_height, flame_height=flame_height
        )
