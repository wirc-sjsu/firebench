import pytest
import numpy as np
from firebench.tools import is_scalar_quantity, get_value_by_category
from firebench import Quantity


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
