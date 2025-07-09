import numpy as np


def rmse(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the Root Mean Square Error (RMSE) between two arrays, ignoring NaNs.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction)
    x2 : np.ndarray
        Second input array of the same shape as x1 (e.g. observations)

    Returns
    -------
    float
        The RMSE value between x1 and x2.

    Raises
    ------
    ValueError
        If the two input arrays do not have the same shape.

    Notes
    -----
    RMSE is a commonly used metric to measure the average magnitude of
    the error between two datasets. It is always non-negative, and a
    value of 0 indicates a perfect match.
    """  # pylint: disable=line-too-long
    if x1.shape != x2.shape:
        raise ValueError(f"Input shapes must match, got {x1.shape} and {x2.shape}.")

    return np.sqrt(np.nanmean((x1 - x2) ** 2))


def nmse_range(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the Normalized Mean Square Error (NMSE) between two arrays,
    using the range of the reference signal as normalization.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction)
    x2 : np.ndarray
        Second input array of the same shape as x1 (e.g. observations)

    Returns
    -------
    float
        The NMSE value computed as RMSE divided by the range
        `nanmax(x2) - nanmin(x2)`.

    Raises
    ------
    ValueError
        If the input arrays do not have the same shape, or if the normalization
        denominator is zero (i.e., no range in the reference values).

    Notes
    -----
    - NaNs are ignored when computing both RMSE and the range.
    - This version of NMSE is useful when the absolute variation of the signal
      is meaningful and should be accounted for.
    - If the range is zero, this metric is ill-defined. Consider using `nmse_power`
      in such cases.
    """  # pylint: disable=line-too-long
    denom = np.nanmax(x2) - np.nanmin(x2)
    if denom == 0:
        raise ValueError(
            "Cannot normalize RMSE: denominator is zero (no range in reference). Use nmse_power instead."
        )

    return rmse(x1, x2) / denom


def nmse_power(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the Normalized Mean Square Error (NMSE) between two arrays,
    using the product of their mean values as normalization.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction)
    x2 : np.ndarray
        Second input array of the same shape as x1 (e.g. observations)

    Returns
    -------
    float
        The NMSE value computed as:
        MSE(x1, x2) / (mean(x1) * mean(x2)), with NaNs ignored.

    Raises
    ------
    ValueError
        If the input arrays do not have the same shape, or if the product
        of means is zero, making normalization undefined.

    Notes
    -----
    - This form is often used in signal processing and model calibration,
      where it expresses the error relative to the average magnitude of the signal.
    - NaNs are ignored when computing both MSE and the means.
    - If the product of means is zero, consider using `nmse_range` instead.
    """  # pylint: disable=line-too-long
    if x1.shape != x2.shape:
        raise ValueError(f"Input shapes must match, got {x1.shape} and {x2.shape}.")

    denom = np.nanmean(x1) * np.nanmean(x2)
    if denom == 0:
        raise ValueError("Cannot normalize MSE: denominator is zero. Use nmse_range instead.")

    return np.nanmean((x1 - x2) ** 2) / denom
