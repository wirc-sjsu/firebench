import firebench.tools as ft
import firebench.wind_interpolation as fwi
import numpy as np
import pytest
from firebench import svn


# Test functions
def test_use_wind_reduction_factor_float():
    wind_speed = 10.0
    reduction_factor = 0.8
    expected_speed = 8.0

    result = fwi.use_wind_reduction_factor(wind_speed=wind_speed, wind_reduction_factor=reduction_factor)
    assert result == expected_speed, f"Expected {expected_speed}, got {result}"


def test_use_wind_reduction_factor_list():
    wind_speed = 10.0
    reduction_factors = [0.7, 0.8, 0.9]  # Indexed by fuel_cat
    fuel_cat = 1
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
    fuel_cat = 1
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
        IndexError, match=f"Fuel category {fuel_cat} not found in wind_reduction_factor array."
    ):
        fwi.use_wind_reduction_factor(
            wind_speed=wind_speed, wind_reduction_factor=reduction_factors, fuel_cat=fuel_cat
        )


def test_fuel_dict_wrong_key_fuel_cat():
    wind_speed = 10.0
    fuel_dict = {"other": [0.7, 0.8, 0.9]}
    fuel_cat = 1

    with pytest.raises(KeyError, match=f"Key {svn.FUEL_WIND_REDUCTION_FACTOR} not found in fuel_dict."):
        fwi.use_wind_reduction_factor(wind_speed=wind_speed, fuel_dict=fuel_dict, fuel_cat=fuel_cat)


def test_invalid_fuel_cat_with_fuel_dict():
    wind_speed = 10.0
    fuel_dict = {svn.FUEL_WIND_REDUCTION_FACTOR: [0.7, 0.8, 0.9]}
    fuel_cat = 5  # Index out of range

    with pytest.raises(IndexError, match=f"Fuel category {fuel_cat} not found in fuel_dict."):
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
