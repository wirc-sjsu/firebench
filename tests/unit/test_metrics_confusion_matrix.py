import pytest
import numpy as np
from firebench.metrics.confusion_matrix import (
    binary_accuracy,
    binary_precision,
    binary_false_positive_rate,
    binary_negative_predicted_value,
    binary_recall_rate,
    binary_specificity,
    binary_f_score,
    binary_cm,
)


# binary_accuracy
# ---------------
@pytest.mark.parametrize(
    "bcm, expected_accuracy",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect classification
        (np.array([[0, 5], [5, 0]]), 0.0),  # Completely wrong classification
        (np.array([[8, 2], [1, 9]]), 17.0 / 20.0),  # General case
        (np.array([[3, 1], [2, 4]]), 7.0 / 10.0),  # Mixed outcomes
    ],
)
def test_binary_accuracy(bcm, expected_accuracy):
    assert binary_accuracy(bcm) == pytest.approx(expected_accuracy, abs=1e-12)


# binary_precision
# ----------------
@pytest.mark.parametrize(
    "bcm, expected_precision",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect precision
        (np.array([[5, 5], [0, 0]]), 0.0),  # No true positives
        (np.array([[3, 2], [1, 4]]), 4.0 / 6.0),  # General case
        (np.array([[10, 0], [5, 0]]), 0.0),  # tp + fp = 0 edge case
    ],
)
def test_binary_precision(bcm, expected_precision):
    assert binary_precision(bcm) == pytest.approx(expected_precision, abs=1e-12)


# binary_false_positive_rate
# --------------------------
@pytest.mark.parametrize(
    "bcm, expected_fpr",
    [
        (np.array([[5, 0], [0, 5]]), 0.0),  # No false positives
        (np.array([[0, 5], [0, 5]]), 1.0),  # All negatives misclassified
        (np.array([[8, 2], [1, 9]]), 2.0 / 10.0),  # General case
        (np.array([[0, 0], [3, 4]]), 0.0),  # fp + tn = 0 edge case
    ],
)
def test_binary_false_positive_rate(bcm, expected_fpr):
    assert binary_false_positive_rate(bcm) == pytest.approx(expected_fpr, abs=1e-12)


# binary_negative_predicted_value
# -------------------------------
@pytest.mark.parametrize(
    "bcm, expected_npv",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect NPV
        (np.array([[0, 5], [5, 0]]), 0.0),  # No correct negatives
        (np.array([[8, 2], [1, 9]]), 8.0 / 9.0),  # General case
        (np.array([[0, 3], [0, 4]]), 0.0),  # fn + tn = 0 edge case
    ],
)
def test_binary_negative_predicted_value(bcm, expected_npv):
    assert binary_negative_predicted_value(bcm) == pytest.approx(expected_npv, abs=1e-12)


# binary_recall_rate
# ------------------
@pytest.mark.parametrize(
    "bcm, expected_recall",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect recall
        (np.array([[5, 0], [5, 0]]), 0.0),  # No true positives
        (np.array([[3, 2], [1, 4]]), 4.0 / 5.0),  # General case
        (np.array([[4, 2], [0, 0]]), 0.0),  # tp + fn = 0 edge case
    ],
)
def test_binary_recall_rate(bcm, expected_recall):
    assert binary_recall_rate(bcm) == pytest.approx(expected_recall, abs=1e-12)


# binary_specificity
# ------------------
@pytest.mark.parametrize(
    "bcm, expected_specificity",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect specificity
        (np.array([[0, 5], [0, 5]]), 0.0),  # All negatives misclassified
        (np.array([[8, 2], [1, 9]]), 8.0 / 10.0),  # General case
        (np.array([[0, 0], [2, 4]]), 0.0),  # tn + fp = 0 edge case
    ],
)
def test_binary_specificity(bcm, expected_specificity):
    assert binary_specificity(bcm) == pytest.approx(expected_specificity, abs=1e-12)


# binary_f_score
# --------------
@pytest.mark.parametrize(
    "bcm, expected_f1",
    [
        (np.array([[5, 0], [0, 5]]), 1.0),  # Perfect classification
        (np.array([[5, 5], [5, 0]]), 0.0),  # No TP → F1 = 0
        (np.array([[3, 2], [1, 4]]), 2 * (4 / 6 * 4 / 5) / ((4 / 6) + (4 / 5))),  # General case
        (np.array([[10, 0], [5, 0]]), 0.0),  # precision + recall = 0 edge case
    ],
)
def test_binary_f_score(bcm, expected_f1):
    assert binary_f_score(bcm) == pytest.approx(expected_f1, abs=1e-12)


# binary_cm
# ---------
@pytest.mark.parametrize(
    "y_true, y_pred, expected_cm",
    [
        # Perfect classification
        (
            np.array([0, 1, 1, 0]),
            np.array([0, 1, 1, 0]),
            np.array([[2, 0], [0, 2]]),
        ),
        # Example from docstring
        (
            np.array([0, 1, 1, 0]),
            np.array([0, 1, 0, 0]),
            np.array([[2, 0], [1, 1]]),
        ),
        # Completely wrong classification
        (
            np.array([0, 0, 1, 1]),
            np.array([1, 1, 0, 0]),
            np.array([[0, 2], [2, 0]]),
        ),
        # Mixed case
        (
            np.array([0, 1, 0, 1, 1]),
            np.array([0, 1, 1, 0, 1]),
            np.array([[1, 1], [1, 2]]),
        ),
        # Boolean inputs
        (
            np.array([False, True, True, False]),
            np.array([False, True, False, False]),
            np.array([[2, 0], [1, 1]]),
        ),
    ],
)
def test_binary_cm(y_true, y_pred, expected_cm):
    result = binary_cm(y_true, y_pred)
    assert np.array_equal(result, expected_cm)
