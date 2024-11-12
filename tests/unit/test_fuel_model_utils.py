import firebench.tools as ft
import pytest
from firebench import svn, ureg
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
    assert fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO] == expected_total_savr


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
        assert fuel_data_dict[svn.FUEL_SURFACE_AREA_VOLUME_RATIO] == expected_total_savr
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
