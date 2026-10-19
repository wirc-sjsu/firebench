import numpy as np


def multiclass_cm(y_true, y_pred, classes) -> np.ndarray:
    """
    Compute the K x K confusion matrix of two arrays of class values.

    Row ``i`` counts the elements whose true class is ``classes[i]``; column ``j`` those whose
    predicted class is ``classes[j]``. An element whose true or predicted value is not in
    ``classes`` is left out.

    Parameters
    ----------
    y_true : array_like
        True class values (e.g. observations).
    y_pred : array_like
        Predicted class values (e.g. model), of the same shape as `y_true`.
    classes : sequence
        The classes, in order. For an ordinal scale, the order of the scale.

    Returns
    -------
    numpy.ndarray
        A K x K array of integer counts.

    Raises
    ------
    ValueError
        If the two arrays do not have the same shape.

    Examples
    --------
    >>> multiclass_cm([1, 2, 3, 3], [1, 3, 3, 9], [1, 2, 3])
    array([[1, 0, 0],
           [0, 0, 1],
           [0, 0, 1]])
    """  # pylint: disable=line-too-long
    y_true = np.asarray(y_true).ravel()
    y_pred = np.asarray(y_pred).ravel()
    if y_true.shape != y_pred.shape:
        raise ValueError(f"Input shapes must match, got {y_true.shape} and {y_pred.shape}.")
    classes = np.asarray(classes)
    size = len(classes)
    known = np.isin(y_true, classes) & np.isin(y_pred, classes)
    order = np.argsort(classes)
    true_index = order[np.searchsorted(classes[order], y_true[known])]
    pred_index = order[np.searchsorted(classes[order], y_pred[known])]
    return np.bincount(true_index * size + pred_index, minlength=size * size).reshape(size, size)


def _total(cm: np.ndarray) -> float:
    return float(np.asarray(cm).sum())


def multiclass_accuracy(cm: np.ndarray) -> float:
    """
    Share of the elements whose predicted class is their true class: trace(cm) / sum(cm).

    Returns NaN for an empty matrix.
    """
    total = _total(cm)
    return float(np.trace(cm)) / total if total else float("nan")


def _class_distance(cm: np.ndarray) -> np.ndarray:
    """Distance in classes between row i and column j: j - i."""
    index = np.arange(np.asarray(cm).shape[0])
    return index[np.newaxis, :] - index[:, np.newaxis]


def within_k_accuracy(cm: np.ndarray, k: int = 1) -> float:
    """
    Share of the elements whose predicted class is at most ``k`` classes from their true class.

    The matrix must follow an ordinal scale (``classes`` of :func:`multiclass_cm` in the order of the
    scale). ``k = 0`` is :func:`multiclass_accuracy`. Returns NaN for an empty matrix.
    """
    total = _total(cm)
    if not total:
        return float("nan")
    return float(np.asarray(cm)[np.abs(_class_distance(cm)) <= k].sum()) / total


def mean_absolute_class_error(cm: np.ndarray) -> float:
    """
    Mean absolute distance, in classes, between predicted and true class, on an ordinal scale.

    0 when every element is in its class. Returns NaN for an empty matrix.
    """
    total = _total(cm)
    if not total:
        return float("nan")
    return float((np.asarray(cm) * np.abs(_class_distance(cm))).sum()) / total


def mean_class_bias(cm: np.ndarray) -> float:
    """
    Mean signed distance, in classes, from the true class to the predicted class, on an ordinal scale.

    Positive when the prediction tends to a higher class than the truth. Returns NaN for an empty
    matrix.
    """
    total = _total(cm)
    if not total:
        return float("nan")
    return float((np.asarray(cm) * _class_distance(cm)).sum()) / total


def quadratic_weighted_kappa(cm: np.ndarray) -> float:
    """
    Cohen's kappa with quadratic weights, for an ordinal scale.

    kappa = 1 - sum(w * O) / sum(w * E), with O the observed matrix, E the matrix expected by chance
    from the row and column totals, and w_ij = (i - j)^2 / (K - 1)^2. 1 is perfect agreement, 0 the
    agreement of chance, and a negative value worse than chance. Returns NaN for an empty matrix, and
    for a matrix whose expected disagreement is 0 (every element in one class on both sides).

    References
    ----------
    Cohen, J. (1968). Weighted kappa. Psychological Bulletin, 70(4), 213-220.
    """  # pylint: disable=line-too-long
    observed = np.asarray(cm, dtype=np.float64)
    total = observed.sum()
    size = observed.shape[0]
    if not total or size < 2:
        return float("nan")
    weights = _class_distance(observed).astype(np.float64) ** 2 / (size - 1) ** 2
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    disagreement = (weights * expected).sum()
    if not disagreement:
        return float("nan")
    return float(1.0 - (weights * observed).sum() / disagreement)


def macro_f1(cm: np.ndarray) -> float:
    """
    Mean of the per-class F1 scores, over the classes present in the truth or in the prediction.

    A class absent from both sides is left out of the mean. Returns NaN for an empty matrix.
    """
    matrix = np.asarray(cm, dtype=np.float64)
    true_count = matrix.sum(axis=1)
    pred_count = matrix.sum(axis=0)
    present = (true_count + pred_count) > 0
    if not present.any():
        return float("nan")
    hits = np.diag(matrix)
    f1 = 2.0 * hits[present] / (true_count[present] + pred_count[present])
    return float(f1.mean())
