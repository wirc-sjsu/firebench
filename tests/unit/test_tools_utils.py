import hashlib
import os
import tempfile

import numpy as np
import pytest
from firebench import Quantity, logger
from firebench.tools import get_value_by_category, is_scalar_quantity, logging, set_logging_level
from firebench.tools.utils import calculate_sha256


@pytest.mark.parametrize(
    "input_value, expected_output",
    [
        (1.0, True),  # float
        (1, True),  # int
        ([1.0, 2.0], False),  # list
        (np.array([1.0, 2.0]), False),  # 1D NumPy array
        (Quantity(1.0, "m"), True),  # pint.Quantity with float
        (Quantity(1, "m"), True),  # pint.Quantity with int
        (Quantity([1.0, 2.0], "m"), False),  # pint.Quantity with list
        (Quantity(np.array([1.0, 2.0]), "m"), False),  # pint.Quantity with NumPy array
    ],
)
def test_test_type(input_value, expected_output):
    assert is_scalar_quantity(input_value) == expected_output


@pytest.mark.parametrize(
    "category_index",
    [
        1,
        2,
        None,
    ],
)
def test_scalar_x(category_index):
    x = 10
    assert get_value_by_category(x, category_index=category_index) == 10


def test_array_x_with_valid_category_index():
    x = [10, 20, 30]
    assert get_value_by_category(x, category_index=2) == 20


def test_array_x_with_invalid_category_index():
    x = [10, 20, 30]
    with pytest.raises(IndexError) as excinfo:
        get_value_by_category(x, category_index=5)
    assert f"One-based index 5 not found in {x}." in str(excinfo.value)


def test_array_x_with_zero_category_index():
    x = [10, 20, 30]
    with pytest.raises(ValueError) as excinfo:
        get_value_by_category(x, category_index=0)
    assert "category_index must be an integer greater than or equal to 1" in str(excinfo.value)


def test_scalar_quantity_x():
    x = Quantity(10, "m")
    result = get_value_by_category(x, category_index=1)
    assert result == x


def test_array_quantity_with_valid_category_index():
    x = Quantity([10, 20, 30], "m")
    result = get_value_by_category(x, category_index=2)
    assert result == Quantity(20, "m")


def test_array_quantity_with_invalid_category_index():
    x = Quantity([10, 20, 30], "m")
    with pytest.raises(IndexError) as excinfo:
        get_value_by_category(x, category_index=4)
    assert f"One-based index 4 not found in {x}." in str(excinfo.value)


def test_array_quantity_with_negative_category_index():
    x = Quantity([10, 20, 30], "m")
    with pytest.raises(ValueError) as excinfo:
        get_value_by_category(x, category_index=-2)
    assert "category_index must be an integer greater than or equal to 1" in str(excinfo.value)


def test_calculate_sha256_valid_file():
    """
    Test that the function correctly calculates the SHA-256 hash of a valid file.
    """
    content = b"Test content for hashing"
    expected_hash = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name

    try:
        result_hash = calculate_sha256(temp_file_path)
        assert result_hash == expected_hash, "The calculated hash does not match the expected hash."
    finally:
        os.remove(temp_file_path)


def test_calculate_sha256_file_not_found(caplog):
    """
    Test that the function returns an empty string and logs an error when the file does not exist.
    """
    non_existent_path = "/path/to/nonexistent/file.txt"
    set_logging_level(logging.WARNING)

    with caplog.at_level(logging.ERROR):
        result = calculate_sha256(non_existent_path)
        assert result == "", "Expected empty string when file is not found."
        # Verify that the appropriate error message was logged
        expected_message = f"File not found: '{non_existent_path}'. Unable to calculate SHA-256 hash."
        logged_messages = [record.message for record in caplog.records]
        assert expected_message in logged_messages, "Expected 'File not found' error message not logged."


def test_calculate_sha256_permission_error(caplog):
    """
    Test that the function returns an empty string and logs an error when access to the file is denied.
    """
    set_logging_level(logging.WARNING)
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file_path = temp_file.name

    try:
        # Set file permissions to zero to trigger a PermissionError
        os.chmod(temp_file_path, 0)

        with caplog.at_level(logging.ERROR):
            result = calculate_sha256(temp_file_path)
            assert result == "", "Expected empty string when permission is denied."
            # Verify that the appropriate error message was logged
            expected_message = f"Permission denied when accessing file: '{temp_file_path}'. Unable to calculate SHA-256 hash."
            logged_messages = [record.message for record in caplog.records]
            assert (
                expected_message in logged_messages
            ), "Expected 'Permission denied' error message not logged."
    finally:
        os.chmod(temp_file_path, 0o644)  # Restore permissions before deletion
        os.remove(temp_file_path)


def test_calculate_sha256_os_error(caplog):
    """
    Test that the function returns an empty string and logs an error when a general OS error occurs.
    """
    set_logging_level(logging.WARNING)
    # Simulate an OSError by trying to open a directory as a file
    with tempfile.TemporaryDirectory() as temp_dir:
        with caplog.at_level(logging.ERROR):
            result = calculate_sha256(temp_dir)
            assert result == "", "Expected empty string when an OS error occurs."
            # Verify that the appropriate error message was logged
            expected_message_prefix = f"OS error occurred while processing file '{temp_dir}':"
            logged_messages = [record.message for record in caplog.records]
            assert any(
                msg.startswith(expected_message_prefix) for msg in logged_messages
            ), "Expected 'OS error occurred' error message not logged."
