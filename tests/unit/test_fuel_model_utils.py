import firebench.tools as ft
import numpy as np
import pytest
from firebench import svn
from pint import Quantity


# add_scott_and_burgan_total_fuel_load
# -------------------------------
def test_add_total_fuel_load_success():
    """
    Test that the function correctly sums the individual fuel loads and adds
    'FUEL_LOAD_DRY_TOTAL' to the dictionary when it doesn't already exist.
    """
    fuel_loads = {
        svn.FUEL_LOAD_DRY_1H: 1.0,
        svn.FUEL_LOAD_DRY_10H: 2.0,
        svn.FUEL_LOAD_DRY_100H: 3.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 4.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 5.0,
    }
    fuel_data_dict = fuel_loads.copy()
    expected_total = sum(fuel_data_dict.values())
    ft.add_scott_and_burgan_total_fuel_load(fuel_data_dict)
    assert svn.FUEL_LOAD_DRY_TOTAL in fuel_data_dict
    assert np.isclose(fuel_data_dict[svn.FUEL_LOAD_DRY_TOTAL], expected_total)


def test_add_total_fuel_load_overwrite_false():
    """
    Test that the function raises a ValueError when 'FUEL_LOAD_DRY_TOTAL' exists
    and overwrite is False.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_10H: 0.2,
        svn.FUEL_LOAD_DRY_100H: 0.3,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.4,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.5,
        svn.FUEL_LOAD_DRY_TOTAL: 1.5,
    }
    with pytest.raises(ValueError, match="already exists in fuel_data_dict"):
        ft.add_scott_and_burgan_total_fuel_load(fuel_data_dict, overwrite=False)


def test_add_total_fuel_load_overwrite_true(caplog):
    """
    Test that the function overwrites 'FUEL_LOAD_DRY_TOTAL' when overwrite is True
    and logs an informational message.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_10H: 0.2,
        svn.FUEL_LOAD_DRY_100H: 0.3,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.4,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.5,
        svn.FUEL_LOAD_DRY_TOTAL: 999.0,  # Existing incorrect total
    }
    expected_total = sum(
        [
            fuel_data_dict[svn.FUEL_LOAD_DRY_1H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_10H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_100H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB],
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY],
        ]
    )
    ft.set_logging_level(ft.logging.INFO)
    with caplog.at_level(ft.logging.INFO):
        ft.add_scott_and_burgan_total_fuel_load(fuel_data_dict, overwrite=True)
        assert svn.FUEL_LOAD_DRY_TOTAL in fuel_data_dict
        assert np.isclose(fuel_data_dict[svn.FUEL_LOAD_DRY_TOTAL], expected_total)
        # Check if the log message is present
        assert any("exists and will be overwritten" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "missing_key",
    [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_10H,
        svn.FUEL_LOAD_DRY_100H,
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
    ],
)
def test_add_total_fuel_load_missing_keys(missing_key):
    """
    Test that the function raises a KeyError when any of the required individual
    fuel load keys are missing.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_10H: 0.2,
        svn.FUEL_LOAD_DRY_100H: 0.3,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.4,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.5,
    }
    fuel_data_dict.pop(missing_key)
    with pytest.raises(KeyError, match=f"Missing required key '{missing_key}'"):
        ft.add_scott_and_burgan_total_fuel_load(fuel_data_dict)


# add_scott_and_burgan_total_savr
# -------------------------------
def test_add_total_savr_success():
    """
    Test that the function correctly calculates and adds the total SAVR when it doesn't already exist.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.2,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.3,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
    }
    expected_num = (
        fuel_data_dict[svn.FUEL_LOAD_DRY_1H] * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB]
        * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY]
        * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY]
    )
    expected_denom = (
        fuel_data_dict[svn.FUEL_LOAD_DRY_1H]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY]
    )
    expected_total_savr = expected_num / expected_denom

    ft.add_scott_and_burgan_total_savr(fuel_data_dict)

    assert svn.FUEL_SURFACE_AREA_VOLUME_RATIO in fuel_data_dict
    assert np.isclose(fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO], expected_total_savr)


def test_add_total_savr_overwrite_false():
    """
    Test that the function raises a ValueError when 'FUEL_SURFACE_AREA_VOLUME_RATIO' exists
    and overwrite is False.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.2,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.3,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO: 9999,  # Existing total SAVR
    }
    with pytest.raises(
        ValueError,
        match=f"Key '{svn.FUEL_SURFACE_AREA_VOLUME_RATIO}' already exists in fuel_data_dict",
    ):
        ft.add_scott_and_burgan_total_savr(fuel_data_dict, overwrite=False)


def test_add_total_savr_overwrite_true(caplog):
    """
    Test that the function overwrites 'FUEL_SURFACE_AREA_VOLUME_RATIO' when overwrite is True
    and logs an informational message.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.2,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.3,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO: 9999,  # Existing incorrect total SAVR
    }
    expected_num = (
        fuel_data_dict[svn.FUEL_LOAD_DRY_1H] * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB]
        * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY]
        * fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY]
    )
    expected_denom = (
        fuel_data_dict[svn.FUEL_LOAD_DRY_1H]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB]
        + fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY]
    )
    expected_total_savr = expected_num / expected_denom

    ft.logger.setLevel(ft.logging.INFO)
    with caplog.at_level(ft.logging.INFO):
        ft.add_scott_and_burgan_total_savr(fuel_data_dict, overwrite=True)
        assert svn.FUEL_SURFACE_AREA_VOLUME_RATIO in fuel_data_dict
        assert np.isclose(fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO], expected_total_savr)
        # Check if the log message is present
        assert any(
            f"Key '{svn.FUEL_SURFACE_AREA_VOLUME_RATIO}' exists and will be overwritten." in record.message
            for record in caplog.records
        )


@pytest.mark.parametrize(
    "missing_key",
    [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY,
    ],
)
def test_add_total_savr_missing_keys(missing_key):
    """
    Test that the function raises a KeyError when any of the required keys are missing.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.1,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.2,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.3,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
    }
    fuel_data_dict.pop(missing_key)
    with pytest.raises(
        KeyError,
        match=f"Missing required key '{missing_key}' in fuel_data_dict",
    ):
        ft.add_scott_and_burgan_total_savr(fuel_data_dict)


def test_add_total_savr_zero_denominator():
    """
    Test that the function raises ZeroDivisionError when the total fuel load is zero.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 0.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 0.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 0.0,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_DEAD_1H: 2000,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_HERB: 1500,
        svn.FUEL_SURFACE_AREA_VOLUME_RATIO_LIVE_WOODY: 1800,
    }
    with pytest.raises(ZeroDivisionError):
        ft.add_scott_and_burgan_total_savr(fuel_data_dict)


# find_closest_fuel_class_by_properties
# -------------------------------------
def test_find_closest_fuel_class_success():
    """
    Test that the function correctly identifies the closest fuel class based on the properties provided.
    """
    # Define the fuel model dictionary with properties for each fuel class
    fuel_model_dict = {
        "density": Quantity(
            [
                100,
                150,
                200,
            ],
            "kg/m^3",
        ),
        "moisture_content": Quantity(
            [
                10,
                15,
                20,
            ],
            "percent",
        ),
    }

    # Define the target properties
    properties_to_test = {
        "density": Quantity(160, "kg/m^3"),
        "moisture_content": Quantity(14, "percent"),
    }

    # Expected index (1-based) of the closest fuel class
    expected_index = 2  # Second fuel class is closest

    result_index = ft.find_closest_fuel_class_by_properties(fuel_model_dict, properties_to_test)

    assert result_index == expected_index


def test_find_closest_fuel_class_missing_property_key():
    """
    Test that the function raises a KeyError when a property key in properties_to_test
    is not found in fuel_model_dict.
    """
    fuel_model_dict = {
        "density": Quantity(
            [
                100,
                150,
            ],
            "kg/m^3",
        ),
    }

    properties_to_test = {
        "density": Quantity(120, "kg/m^3"),
        "moisture_content": Quantity(15, "percent"),  # Missing in fuel_model_dict
    }

    with pytest.raises(KeyError, match="Property 'moisture_content' not found in fuel_model_dict."):
        ft.find_closest_fuel_class_by_properties(fuel_model_dict, properties_to_test)


def test_find_closest_fuel_class_incompatible_units():
    """
    Test that the function raises a ValueError when units cannot be converted between
    fuel_model_dict and properties_to_test.
    """
    fuel_model_dict = {
        "density": Quantity(
            [
                100,
                150,
            ],
            "kg/m^3",
        ),
    }

    properties_to_test = {
        "density": Quantity(120, "joule"),  # Incompatible unit
    }

    with pytest.raises(ValueError, match="Cannot convert units for property 'density'"):
        ft.find_closest_fuel_class_by_properties(fuel_model_dict, properties_to_test)


def test_find_closest_fuel_class_with_weights():
    """
    Test that the function correctly identifies the closest fuel class when custom weights are provided.
    """
    fuel_model_dict = {
        "density": Quantity(
            [
                100,
                200,
            ],
            "kg/m^3",
        ),
        "moisture_content": Quantity(
            [
                5,
                25,
            ],
            "percent",
        ),
    }

    properties_to_test = {
        "density": Quantity(125, "kg/m^3"),
        "moisture_content": Quantity(20, "percent"),
    }

    # Expected index (1-based) of the closest fuel class
    expected_index = 2  # Second fuel class is closer when defautl weights are applied
    result_index = ft.find_closest_fuel_class_by_properties(
        fuel_model_dict, properties_to_test, weights=None
    )
    assert result_index == expected_index

    # Custom weights emphasizing density over moisture_content
    weights = {
        "density": 2,
        "moisture_content": 1,
    }
    # Expected index (1-based) of the closest fuel class
    expected_index = 1  # First fuel class is closer when density is weighted more
    result_index = ft.find_closest_fuel_class_by_properties(
        fuel_model_dict, properties_to_test, weights=weights
    )
    assert result_index == expected_index


def test_find_closest_fuel_class_weights_key_mismatch():
    """
    Test that the function raises a ValueError when the weights keys do not match
    the properties_to_test keys.
    """
    fuel_model_dict = {
        "density": Quantity(
            [
                100,
                200,
            ],
            "kg/m^3",
        ),
    }

    properties_to_test = {
        "density": Quantity(150, "kg/m^3"),
    }

    # Weights key does not match properties_to_test
    weights = {
        "moisture_content": 1.0,
    }

    with pytest.raises(ValueError, match="Weights must have the same keys as properties_to_test."):
        ft.find_closest_fuel_class_by_properties(fuel_model_dict, properties_to_test, weights=weights)


def test_find_closest_fuel_class_zero_magnitude():
    """
    Test that the function handles properties with zero magnitude without division by zero errors.
    """
    fuel_model_dict = {
        "density": Quantity(
            [
                0,
                50,
            ],
            "kg/m^3",
        ),
    }

    properties_to_test = {
        "density": Quantity(0, "kg/m^3"),
    }

    # Expected index (1-based)
    expected_index = 1

    result_index = ft.find_closest_fuel_class_by_properties(fuel_model_dict, properties_to_test)

    assert result_index == expected_index


# add_scott_and_burgan_dead_fuel_ratio
# -------------------------------


def test_add_dead_fuel_ratio_success():
    """
    Test that the function correctly calculates the dead fuel load ratio and
    adds 'FUEL_LOAD_DEAD_RATIO' to the dictionary when it doesn't already exist.
    """
    fuel_loads = {
        svn.FUEL_LOAD_DRY_1H: 1.0,
        svn.FUEL_LOAD_DRY_10H: 2.0,
        svn.FUEL_LOAD_DRY_100H: 3.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 4.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 5.0,
    }
    fuel_data_dict = fuel_loads.copy()
    dead_load = sum(
        [
            fuel_data_dict[svn.FUEL_LOAD_DRY_1H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_10H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_100H],
        ]
    )
    live_load = sum(
        [
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB],
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY],
        ]
    )
    expected_ratio = dead_load / (dead_load + live_load)
    ft.add_scott_and_burgan_dead_fuel_ratio(fuel_data_dict)
    assert svn.FUEL_LOAD_DEAD_RATIO in fuel_data_dict
    assert np.isclose(fuel_data_dict[svn.FUEL_LOAD_DEAD_RATIO], expected_ratio)


def test_add_dead_fuel_ratio_overwrite_false():
    """
    Test that the function raises a ValueError when 'FUEL_LOAD_DEAD_RATIO' exists
    and overwrite is False.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 1.0,
        svn.FUEL_LOAD_DRY_10H: 2.0,
        svn.FUEL_LOAD_DRY_100H: 3.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 4.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 5.0,
        svn.FUEL_LOAD_DEAD_RATIO: 0.5,
    }
    with pytest.raises(ValueError, match="already exists in fuel_data_dict"):
        ft.add_scott_and_burgan_dead_fuel_ratio(fuel_data_dict, overwrite=False)


def test_add_dead_fuel_ratio_overwrite_true(caplog):
    """
    Test that the function overwrites 'FUEL_LOAD_DEAD_RATIO' when overwrite is True
    and logs an informational message.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 1.0,
        svn.FUEL_LOAD_DRY_10H: 2.0,
        svn.FUEL_LOAD_DRY_100H: 3.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 4.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 5.0,
        svn.FUEL_LOAD_DEAD_RATIO: 0.999,  # Incorrect existing ratio
    }
    dead_load = sum(
        [
            fuel_data_dict[svn.FUEL_LOAD_DRY_1H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_10H],
            fuel_data_dict[svn.FUEL_LOAD_DRY_100H],
        ]
    )
    live_load = sum(
        [
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_HERB],
            fuel_data_dict[svn.FUEL_LOAD_DRY_LIVE_WOODY],
        ]
    )
    expected_ratio = dead_load / (dead_load + live_load)
    ft.set_logging_level(ft.logging.INFO)
    with caplog.at_level(ft.logging.INFO):
        ft.add_scott_and_burgan_dead_fuel_ratio(fuel_data_dict, overwrite=True)
        assert svn.FUEL_LOAD_DEAD_RATIO in fuel_data_dict
        assert np.isclose(fuel_data_dict[svn.FUEL_LOAD_DEAD_RATIO], expected_ratio)
        # Check if the log message is present
        assert any("exists and will be overwritten" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "missing_key",
    [
        svn.FUEL_LOAD_DRY_1H,
        svn.FUEL_LOAD_DRY_10H,
        svn.FUEL_LOAD_DRY_100H,
        svn.FUEL_LOAD_DRY_LIVE_HERB,
        svn.FUEL_LOAD_DRY_LIVE_WOODY,
    ],
)
def test_add_dead_fuel_ratio_missing_keys(missing_key):
    """
    Test that the function raises a KeyError when any of the required individual
    fuel load keys are missing.
    """
    fuel_data_dict = {
        svn.FUEL_LOAD_DRY_1H: 1.0,
        svn.FUEL_LOAD_DRY_10H: 2.0,
        svn.FUEL_LOAD_DRY_100H: 3.0,
        svn.FUEL_LOAD_DRY_LIVE_HERB: 4.0,
        svn.FUEL_LOAD_DRY_LIVE_WOODY: 5.0,
    }
    fuel_data_dict.pop(missing_key)
    with pytest.raises(KeyError, match=f"Missing required key '{missing_key}'"):
        ft.add_scott_and_burgan_dead_fuel_ratio(fuel_data_dict)
