import numpy as np


def binary_accuracy(bcm: np.ndarray):
    """
    Compute the binary classification accuracy from a 2x2 confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    where:
    - TN: True Negatives
    - FP: False Positives
    - FN: False Negatives
    - TP: True Positives

    Accuracy is defined as the proportion of correct predictions out of all
    predictions:

        accuracy = (TP + TN) / (TP + TN + FP + FN)

    Parameters
    ----------
    bcm : numpy.ndarray

    Returns
    -------
    float
        The accuracy value, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    return (tp + tn) / (tp + tn + fp + fn)


def binary_precision(bcm: np.ndarray):
    """
    Compute the precision from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    where:
    - TN: True Negatives
    - FP: False Positives
    - FN: False Negatives
    - TP: True Positives

    Precision (also called Positive Predictive Value, PPV) measures the proportion
    of positive predictions that are correct:

        precision = TP / (TP + FP)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The precision value, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    if tp + fp == 0:
        return 0
    return tp / (tp + fp)


def binary_false_positive_rate(bcm: np.ndarray):
    """
    Compute the false positive rate (FPR) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    False Positive Rate measures how often negative samples are incorrectly
    classified as positive:

        FPR = FP / (FP + TN)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The false positive rate, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    if fp + tn == 0:
        return 0
    return fp / (fp + tn)


def binary_negative_predicted_value(bcm: np.ndarray):
    """
    Compute the negative predictive value (NPV) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    Negative Predictive Value measures the proportion of predicted negatives
    that are actually negative:

        NPV = TN / (TN + FN)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The negative predictive value, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    if fn + tn == 0:
        return 0
    return tn / (fn + tn)


def binary_recall_rate(bcm: np.ndarray):
    """
    Compute the recall rate (true positive rate, TPR) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    Recall, also called sensitivity, measures how many actual positives are
    correctly identified:

        recall = TP / (TP + FN)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The recall value, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    if tp + fn == 0:
        return 0
    return tp / (tp + fn)


def binary_specificity(bcm: np.ndarray):
    """
    Compute the specificity (true negative rate, TNR) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    Specificity measures the proportion of actual negatives that are correctly
    identified:

        specificity = TN / (TN + FP)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The specificity value, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    if tn + fp == 0:
        return 0
    return tn / (tn + fp)


def binary_f_score(bcm: np.ndarray):
    """
    Compute the F1-score from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    The F1-score is the harmonic mean of precision and recall:

        F1 = 2 * (precision * recall) / (precision + recall)

    It provides a single metric that balances false positives and false negatives.

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The F1-score, ranging from 0.0 to 1.0.
    """  # pylint: disable=line-too-long
    pr = binary_precision(bcm)
    rc = binary_recall_rate(bcm)
    if pr + rc == 0:
        return 0
    return 2.0 * (pr * rc) / (pr + rc)


def binary_false_alarm_ratio(bcm: np.ndarray):
    """
    Compute the false alarm ratio (FAR) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    The false alarm ratio is the share of the predicted positives that did not occur:

        FAR = FP / (FP + TP)

    It is not the false positive rate, which divides by the actual negatives.

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The false alarm ratio, ranging from 0.0 to 1.0. Returns 0 when nothing is predicted positive.
    """  # pylint: disable=line-too-long
    _, fp, _, tp = bcm.ravel()
    if fp + tp == 0:
        return 0
    return fp / (fp + tp)


def binary_critical_success_index(bcm: np.ndarray):
    """
    Compute the critical success index (CSI, or threat score) from a 2x2 binary confusion matrix.

    This function expects a confusion matrix of the form:

        [[TN, FP],
         [FN, TP]]

    The critical success index is the share of hits among the events that were observed or
    predicted. Correct negatives do not count:

        CSI = TP / (TP + FP + FN)

    Parameters
    ----------
    bcm : numpy.ndarray
        A 2x2 array representing the binary confusion matrix.

    Returns
    -------
    float
        The critical success index, ranging from 0.0 to 1.0. Returns 0 when no event is observed or predicted.
    """  # pylint: disable=line-too-long
    _, fp, fn, tp = bcm.ravel()
    if tp + fp + fn == 0:
        return 0
    return tp / (tp + fp + fn)
