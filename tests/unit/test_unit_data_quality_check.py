import firebench.tools as ft
import pytest
from firebench import svn, ureg
from pint import Quantity


def test_extract_magnitudes_all_quantities():
    """
    Test that the function correctly extracts magnitudes when all values are Quantity objects.
    """
    input_dict = {
        "length": 10 * ureg.meter,
        "time": 5 * ureg.second,
        "mass": 2 * ureg.kilogram,
    }
    expected_output = {
        "length": 10,
        "time": 5,
        "mass": 2,
    }
    result = ft.extract_magnitudes(input_dict)
    assert result == expected_output


def test_extract_magnitudes_no_quantities(caplog):
    """
    Test that the function keeps original values when none have a magnitude attribute
    and logs warnings for each.
    """
    input_dict = {
        "length": 10,
        "time": 5.0,
        "description": "ten meters",
    }
    expected_output = input_dict.copy()
    ft.set_logging_level(ft.logging.INFO)
    with caplog.at_level(ft.logging.INFO):
        result = ft.extract_magnitudes(input_dict)
        assert result == expected_output
        # Verify that warnings are logged
        expected_warnings = [
            "Failed to get magnitude for key 'length'",
            "Failed to get magnitude for key 'time'",
            "Failed to get magnitude for key 'description'",
        ]
        logged_warnings = [record.message for record in caplog.records]
        for warning in expected_warnings:
            assert any(warning in log_msg for log_msg in logged_warnings)
