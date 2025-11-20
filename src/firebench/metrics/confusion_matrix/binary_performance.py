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
        A 2x2 array representing the binary confusion matrix in the order
        [[TN, FP], [FN, TP]]. The array must be broadcastable to this shape.

    Returns
    -------
    float
        The accuracy value, ranging from 0.0 to 1.0.
    """ # pylint: disable=line-too-long
    tn, fp, fn, tp = bcm.ravel()
    return (tp + tn) / (tp + tn + fp + fn)