import firebench.tools as ft
import pytest
from firebench import svn, ureg
from pint import Quantity

# add_scott_and_burgan_total_fuel_load
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
    assert fuel_data_dict[svn.FUEL_LOAD_DRY_TOTAL] == expected_total


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
        assert fuel_data_dict[svn.FUEL_LOAD_DRY_TOTAL] == expected_total
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
