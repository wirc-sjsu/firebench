import numpy as np
import pytest

from firebench.metrics.confusion_matrix import (
    macro_f1,
    mean_absolute_class_error,
    mean_class_bias,
    multiclass_accuracy,
    multiclass_cm,
    quadratic_weighted_kappa,
    within_k_accuracy,
)
from firebench.metrics.stats import (
    band_position,
    fraction_above_band,
    fraction_below_band,
    fraction_in_band,
)

# Three ordinal classes, every miss one class too high: worked out by hand in the tests below.
OFF_BY_ONE = np.array([[1, 1, 0], [0, 1, 1], [0, 0, 1]])


def test_multiclass_cm_counts_known_classes_only():
    cm = multiclass_cm([1, 2, 3, 3, 0], [1, 3, 3, 9, 1], [1, 2, 3])
    np.testing.assert_array_equal(cm, [[1, 0, 0], [0, 0, 1], [0, 0, 1]])


def test_multiclass_cm_follows_the_order_of_classes():
    cm = multiclass_cm([5, 1, 1], [5, 5, 1], [5, 1])
    np.testing.assert_array_equal(cm, [[1, 0], [1, 1]])


def test_multiclass_cm_refuses_different_shapes():
    with pytest.raises(ValueError):
        multiclass_cm([1, 2], [1], [1, 2])


def test_perfect_matrix():
    cm = np.diag([3, 2, 4])
    assert multiclass_accuracy(cm) == 1.0
    assert within_k_accuracy(cm, 0) == 1.0
    assert quadratic_weighted_kappa(cm) == pytest.approx(1.0)
    assert macro_f1(cm) == pytest.approx(1.0)
    assert mean_absolute_class_error(cm) == 0.0
    assert mean_class_bias(cm) == 0.0


def test_off_by_one_matrix():
    assert multiclass_accuracy(OFF_BY_ONE) == pytest.approx(3 / 5)
    assert within_k_accuracy(OFF_BY_ONE, 0) == pytest.approx(3 / 5)
    assert within_k_accuracy(OFF_BY_ONE, 1) == pytest.approx(1.0)
    assert mean_absolute_class_error(OFF_BY_ONE) == pytest.approx(2 / 5)
    assert mean_class_bias(OFF_BY_ONE) == pytest.approx(2 / 5)
    assert mean_class_bias(OFF_BY_ONE.T) == pytest.approx(-2 / 5)
    # sum(w O) = 0.5; sum(w E) = 8 / 5.
    assert quadratic_weighted_kappa(OFF_BY_ONE) == pytest.approx(1 - 0.5 / 1.6)
    assert macro_f1(OFF_BY_ONE) == pytest.approx((2 / 3 + 1 / 2 + 2 / 3) / 3)


def test_kappa_of_chance_agreement_is_zero():
    assert quadratic_weighted_kappa(np.ones((3, 3))) == pytest.approx(0.0)


def test_kappa_below_chance_is_negative():
    assert quadratic_weighted_kappa(np.array([[0, 5], [5, 0]])) < 0


def test_macro_f1_leaves_out_absent_classes():
    cm = np.array([[2, 0, 0], [0, 0, 0], [0, 0, 2]])
    assert macro_f1(cm) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "func",
    [
        multiclass_accuracy,
        within_k_accuracy,
        quadratic_weighted_kappa,
        macro_f1,
        mean_absolute_class_error,
        mean_class_bias,
    ],
)
def test_empty_matrix_is_nan(func):
    assert np.isnan(func(np.zeros((3, 3), dtype=int)))


def test_kappa_with_one_class_on_both_sides_is_nan():
    assert np.isnan(quadratic_weighted_kappa(np.array([[4, 0], [0, 0]])))


def test_band_fractions():
    x = np.array([1.0, 2.0, 5.0, 10.0, np.nan])
    lower = np.array([1.0, 3.0, 1.0, 1.0, 0.0])
    upper = np.array([2.0, 4.0, 4.0, 10.0, 1.0])
    assert fraction_in_band(x, lower, upper) == pytest.approx(2 / 4)
    assert fraction_above_band(x, lower, upper) == pytest.approx(1 / 4)
    assert fraction_below_band(x, lower, upper) == pytest.approx(1 / 4)
    assert band_position(x, lower, upper).tolist() == ["in", "below", "above", "in", ""]


def test_band_fractions_without_values_are_nan():
    assert np.isnan(fraction_in_band(np.array([np.nan]), np.array([0.0]), np.array([1.0])))


def test_band_refuses_inverted_bounds():
    with pytest.raises(ValueError):
        fraction_in_band(np.array([1.0]), np.array([2.0]), np.array([1.0]))
