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

    return float(np.sqrt(np.nanmean((x1 - x2) ** 2)))


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

    return float(rmse(x1, x2) / denom)


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

    return float(np.nanmean((x1 - x2) ** 2) / denom)


def bias(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the bias between two arrays, ignoring NaNs.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction)
    x2 : np.ndarray
        Second input array of the same shape as x1 (e.g. observations)

    Returns
    -------
    float
        The bias value between x1 and x2.

    Raises
    ------
    ValueError
        If the two input arrays do not have the same shape.

    Notes
    -----
    B = E(x1) - E(x2)
    """  # pylint: disable=line-too-long
    if x1.shape != x2.shape:
        raise ValueError(f"Input shapes must match, got {x1.shape} and {x2.shape}.")

    return float(np.nanmean(x1) - np.nanmean(x2))


def mae(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the Mean Absolute Error between two arrays, ignoring NaNs.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction)
    x2 : np.ndarray
        Second input array of the same shape as x1 (e.g. observations)

    Returns
    -------
    float
        The bias value between x1 and x2.

    Raises
    ------
    ValueError
        If the two input arrays do not have the same shape.

    Notes
    -----
    MAE = E(|x1 - x2|)
    """  # pylint: disable=line-too-long
    if x1.shape != x2.shape:
        raise ValueError(f"Input shapes must match, got {x1.shape} and {x2.shape}.")

    return np.nanmean(np.abs(x1 - x2))


def circular_bias_deg(x1: np.ndarray, x2: np.ndarray) -> float:
    """
    Compute the bias between two angular arrays in degrees (0-360),
    accounting for circularity and ignoring NaNs.

    Parameters
    ----------
    x1 : np.ndarray
        First input array (e.g. prediction), in degrees [0, 360)
    x2 : np.ndarray
        Second input array (e.g. observations), in degrees [0, 360)

    Returns
    -------
    float
        Circular bias in degrees, in the range (-180, 180].

    Raises
    ------
    ValueError
        If the two input arrays do not have the same shape.
    """
    if x1.shape != x2.shape:
        raise ValueError(f"Input shapes must match, got {x1.shape} and {x2.shape}.")

    # Mask NaNs jointly
    mask = np.isfinite(x1) & np.isfinite(x2)
    if not np.any(mask):
        return np.nan

    # Convert to radians
    theta1 = np.deg2rad(x1[mask])
    theta2 = np.deg2rad(x2[mask])

    # Circular means
    mean1 = np.arctan2(np.mean(np.sin(theta1)), np.mean(np.cos(theta1)))
    mean2 = np.arctan2(np.mean(np.sin(theta2)), np.mean(np.cos(theta2)))

    # Difference, wrapped to (-pi, pi]
    dtheta = mean1 - mean2
    dtheta = (dtheta + np.pi) % (2 * np.pi) - np.pi

    return float(np.rad2deg(dtheta))
