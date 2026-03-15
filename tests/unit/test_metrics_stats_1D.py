import pytest
import numpy as np
from firebench.metrics.stats import rmse, nmse_range, nmse_power, bias, mae, circular_bias_deg
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


# mae
# ---
@pytest.mark.parametrize(
    "x1, x2, expected_mae",
    [
        (np.array([0, 1, 2]), np.array([0, 1, 2]), 0.0),
        (np.array([0, 1, 2]), np.array([1, 1, 1]), 2.0 / 3.0),
        (np.array([0, 1, 2]), np.array([0, np.nan, 4]), 1.0),
        (np.array([[0, 1], [2, 3]]), np.array([[1, 1], [1, 5]]), 1.0),
    ],
)
def test_mae(x1, x2, expected_mae):
    assert np.isclose(mae(x1, x2), expected_mae)


def test_mae_raises_on_shape_mismatch():
    x1 = np.array([0, 1, 2])
    x2 = np.array([[0, 1, 2]])
    with pytest.raises(ValueError):
        mae(x1, x2)


# circular_bias_deg
# -----------------
@pytest.mark.parametrize(
    "x1, x2, expected_bias",
    [
        (np.array([10, 20, 30]), np.array([10, 20, 30]), 0.0),  # identical
        (np.array([10]), np.array([350]), 20.0),  # wrap-around positive
        (np.array([350]), np.array([10]), -20.0),  # wrap-around negative
        (np.array([0, 10]), np.array([350, 0]), 10.0),  # circular mean offset
        (np.array([0, np.nan, 20]), np.array([10, 30, 10]), 0.0),  # joint NaN masking
    ],
)
def test_circular_bias_deg(x1, x2, expected_bias):
    assert circular_bias_deg(x1, x2) == pytest.approx(expected_bias, abs=1e-12)


def test_circular_bias_deg_returns_nan_if_all_values_are_invalid():
    x1 = np.array([np.nan, np.nan])
    x2 = np.array([np.nan, np.nan])
    assert np.isnan(circular_bias_deg(x1, x2))


def test_circular_bias_deg_raises_on_shape_mismatch():
    x1 = np.array([0, 1, 2])
    x2 = np.array([[0, 1, 2]])
    with pytest.raises(ValueError):
        circular_bias_deg(x1, x2)
