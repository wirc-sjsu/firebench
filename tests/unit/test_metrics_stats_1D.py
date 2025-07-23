import pytest
import numpy as np
from firebench.metrics.stats import rmse, nmse_range, nmse_power, bias
from math import sqrt


# rmse
# ----
@pytest.mark.parametrize(
    "x1, x2, expected_RMSE",
    [
        (np.array([0, 1, 2]), np.array([0, 1, 2]), 0),
        (np.array([0, 1, 2]), np.array([0, 0, 2]), sqrt(1.0 / 3.0)),
        (np.array([0, 1, 2]), np.array([0, np.nan, 2]), 0),
        (np.array([[0, 1], [2, 3]]), np.array([[1, 2], [3, 4]]), 1),
    ],
)
def test_rmse(x1, x2, expected_RMSE):
    assert np.isclose(rmse(x1, x2), expected_RMSE)


def test_rmse_raise_shape():
    x1 = np.array([0, 1, 2])
    x2 = np.array([0, 1])
    with pytest.raises(ValueError) as excinfo:
        rmse(x1, x2)
    assert "Input shapes must match, got (3,) and (2,)." in str(excinfo.value)


# nmse_range
# ----------
@pytest.mark.parametrize(
    "x1, x2, expected_NMSE_range",
    [
        (np.array([0, 1, 2]), np.array([0, 1, 2]), 0),
        (np.array([0, 1, 2]), np.array([0, 0, 2]), 0.5 * sqrt(1.0 / 3.0)),
        (np.array([0, 1, 2]), np.array([0, np.nan, 2]), 0),
        (np.array([[0, 1], [2, 3]]), np.array([[1, 2], [3, 4]]), 1.0 / 3.0),
    ],
)
def test_nmse_range(x1, x2, expected_NMSE_range):
    assert np.isclose(nmse_range(x1, x2), expected_NMSE_range)


def test_test_nmse_range_denom_zero():
    x1 = np.array([0, 1, 2])
    x2 = np.array([1, 1, 1])
    with pytest.raises(ValueError) as excinfo:
        nmse_range(x1, x2)
    assert (
        "Cannot normalize RMSE: denominator is zero (no range in reference). Use nmse_power instead."
        in str(excinfo.value)
    )


# nmse_power
# ----------
@pytest.mark.parametrize(
    "x1, x2, expected_NMSE_range",
    [
        (np.array([0, 1, 2]), np.array([0, 1, 2]), 0),
        (np.array([0, 1, 2]), np.array([0, 0, 3]), 2.0 / 3.0),
        (np.array([0, 1, 2]), np.array([0, np.nan, 2]), 0),
        (np.array([[0, 1], [2, 3]]), np.array([[1, 2], [3, 4]]), 4.0 / 15.0),
    ],
)
def test_nmse_power(x1, x2, expected_NMSE_range):
    assert np.isclose(nmse_power(x1, x2), expected_NMSE_range)


def test_nmse_power_raise_shape():
    x1 = np.array([0, 1, 2])
    x2 = np.array([0, 1])
    with pytest.raises(ValueError) as excinfo:
        nmse_power(x1, x2)
    assert "Input shapes must match, got (3,) and (2,)." in str(excinfo.value)


def test_test_nmse_power_denom_zero():
    x1 = np.array([0, 1, 2])
    x2 = np.array([1, 0, -1])
    with pytest.raises(ValueError) as excinfo:
        nmse_power(x1, x2)
    assert "Cannot normalize MSE: denominator is zero. Use nmse_range instead." in str(excinfo.value)


# bias
# ----------
@pytest.mark.parametrize(
    "x1, x2, expected_bias",
    [
        (np.array([0, 1, 2]), np.array([0, 1, 2]), 0),
        (np.array([0, 1, 2]), np.array([0, 0, 3]), 0),
        (np.array([0, 1, 2]), np.array([0, 0, 6]), -1),
        (np.array([0, 1, 2]), np.array([0, np.nan, 2]), 0),
        (np.array([[0, 1], [2, 3]]), np.array([[1, 2], [3, 4]]), -1.0),
    ],
)
def test_bias(x1, x2, expected_bias):
    assert np.isclose(bias(x1, x2), expected_bias)


def test_bias_raise_shape():
    x1 = np.array([0, 1, 2])
    x2 = np.array([0, 1])
    with pytest.raises(ValueError) as excinfo:
        bias(x1, x2)
    assert "Input shapes must match, got (3,) and (2,)." in str(excinfo.value)
