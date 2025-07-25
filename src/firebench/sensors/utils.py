from scipy.stats import norm


def z_from_cl(cl: float) -> float:
    """
    Compute the two-sided z-score corresponding to a given confidence level.

    This function returns the z-score `z` such that the interval
    [-z, +z] covers the specified confidence level `cl` under a standard
    normal distribution.

    Parameters
    ----------
    cl : float
        Two-sided confidence level in the interval (0, 1).

    Returns
    -------
    float
        z-score corresponding to the confidence level.

    Raises
    ------
    ValueError
        If `cl` is not in the open interval (0, 1).

    Examples
    --------
    >>> z_from_cl(0.90)
    1.644853...
    """  # pylint: disable=line-too-long
    if not 0 < cl < 1:
        raise ValueError("Confidence level cl must be between 0 and 1")
    return norm.ppf(0.5 + cl / 2.0)
