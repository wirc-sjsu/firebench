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
    return 2.0 * (pr * rc) / (pr + rc)
