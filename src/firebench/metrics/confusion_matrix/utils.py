import numpy as np


def binary_cm(y_true, y_pred):
    """
    Compute the binary confusion matrix for two boolean-compatible arrays.

    This function compares predicted binary values against ground-truth binary values
    and computes the 2x2 confusion matrix in the conventional layout:

        [[TN, FP],
         [FN, TP]]

    Both inputs must be broadcastable to the same shape and must contain values that
    can be interpreted as booleans (e.g., {0,1}, {False,True}, or arrays castable to bool).

    The logic is as follows:
    - True Negative (TN): elements where both `y_true` and `y_pred` are False.
    - False Positive (FP): elements where `y_true` is False but `y_pred` is True.
    - False Negative (FN): elements where `y_true` is True but `y_pred` is False.
    - True Positive (TP): elements where both `y_true` and `y_pred` are True.

    Parameters
    ----------
    y_true : array_like
        Ground-truth binary values. Must be castable to a boolean NumPy array.
    y_pred : array_like
        Predicted binary values. Must be castable to a boolean NumPy array.

    Returns
    -------
    numpy.ndarray
        A 2x2 NumPy array of integers arranged as:
            [[TN, FP],
             [FN, TP]]

    Examples
    --------
    >>> binary_confusion_matrix_matrix([0, 1, 1, 0], [0, 1, 0, 0])
    array([[2, 0],
           [1, 1]])
    """  # pylint: disable=line-too-long
    y_true = np.asarray(y_true).astype(bool)
    y_pred = np.asarray(y_pred).astype(bool)

    tp = np.sum(y_true & y_pred)
    tn = np.sum(~y_true & ~y_pred)
    fp = np.sum(~y_true & y_pred)
    fn = np.sum(y_true & ~y_pred)

    return np.array([[tn, fp], [fn, tp]])
