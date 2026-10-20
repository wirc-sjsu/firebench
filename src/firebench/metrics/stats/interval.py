import numpy as np


def _share(selected: np.ndarray) -> float:
    return float(selected.mean()) if selected.size else float("nan")


def band_position(x: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    """
    Where each value of ``x`` lies against its band ``[lower, upper]``: ``"in"`` (bounds included),
    ``"above"``, or ``"below"``, and ``""`` where any of the three is NaN.

    The fractions of this module are the shares of these positions over the elements that have one.

    Parameters
    ----------
    x : np.ndarray
        Values (e.g. observations).
    lower, upper : np.ndarray
        Bounds of the band of each value, of the same shape as `x`.

    Returns
    -------
    np.ndarray
        An array of strings of the shape of `x`.

    Raises
    ------
    ValueError
        If the shapes differ, or if a lower bound is above its upper bound.
    """
    x, lower, upper = (np.asarray(item, dtype=np.float64) for item in (x, lower, upper))
    if not x.shape == lower.shape == upper.shape:
        raise ValueError(f"Input shapes must match, got {x.shape}, {lower.shape} and {upper.shape}.")
    if np.any(lower > upper):
        raise ValueError("The lower bound of the band is above its upper bound somewhere.")
    valid = np.isfinite(x) & np.isfinite(lower) & np.isfinite(upper)
    position = np.full(x.shape, "", dtype="<U5")
    position[valid & (x < lower)] = "below"
    position[valid & (x > upper)] = "above"
    position[valid & (x >= lower) & (x <= upper)] = "in"
    return position


def _fraction(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, where: str) -> float:
    position = band_position(x, lower, upper)
    return _share(position[position != ""] == where)


def fraction_in_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """
    Share of the values of ``x`` inside their band ``[lower, upper]``, bounds included.

    Each value has its own band (e.g. an observation and the range a model gives at its time). An
    element where any of the three is NaN is left out.

    Parameters
    ----------
    x : np.ndarray
        Values (e.g. observations).
    lower, upper : np.ndarray
        Bounds of the band of each value, of the same shape as `x`.

    Returns
    -------
    float
        The share, from 0 to 1; NaN when no element is left.

    Raises
    ------
    ValueError
        If the shapes differ, or if a lower bound is above its upper bound.
    """  # pylint: disable=line-too-long
    return _fraction(x, lower, upper, "in")


def fraction_above_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """
    Share of the values of ``x`` above the upper bound of their band. See :func:`fraction_in_band`.
    """
    return _fraction(x, lower, upper, "above")


def fraction_below_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """
    Share of the values of ``x`` below the lower bound of their band. See :func:`fraction_in_band`.
    """
    return _fraction(x, lower, upper, "below")
