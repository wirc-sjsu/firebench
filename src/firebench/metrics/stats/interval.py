import numpy as np


def _share(selected: np.ndarray) -> float:
    return float(selected.mean()) if selected.size else float("nan")


def band_position(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0) -> np.ndarray:
    """
    Where each value of ``x`` lies against its band ``[lower, upper]``: ``"in"`` (bounds included),
    ``"above"``, or ``"below"``, and ``""`` where any of the three is NaN.

    The value and both bounds are first raised to ``limit``, the smallest value an instrument tells
    apart from nothing: a value under it is "in" a band whose lower bound is under it too.

    The fractions of this module are the shares of these positions over the elements that have one.

    Parameters
    ----------
    x : np.ndarray
        Values (e.g. observations).
    lower, upper : np.ndarray
        Bounds of the band of each value, of the same shape as `x`.
    limit : float | np.ndarray
        Detection limit, one for all or one per value (default 0: none).

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
    x, lower, upper = _floored(x, lower, upper, limit)
    valid = np.isfinite(x) & np.isfinite(lower) & np.isfinite(upper)
    position = np.full(x.shape, "", dtype="<U5")
    position[valid & (x < lower)] = "below"
    position[valid & (x > upper)] = "above"
    position[valid & (x >= lower) & (x <= upper)] = "in"
    return position


def _floored(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit):
    limit = np.broadcast_to(np.asarray(limit, dtype=np.float64), x.shape)
    if np.any(limit < 0):
        raise ValueError("The detection limit must be 0 or more.")
    return (np.maximum(item, limit) for item in (x, lower, upper))


def _fraction(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, where: str, limit) -> float:
    position = band_position(x, lower, upper, limit)
    return _share(position[position != ""] == where)


def fraction_in_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0) -> float:
    """
    Share of the values of ``x`` inside their band ``[lower, upper]``, bounds included.

    Each value has its own band (e.g. an observation and the range a model gives at its time). An
    element where any of the three is NaN is left out. See :func:`band_position` for ``limit``.

    Parameters
    ----------
    x : np.ndarray
        Values (e.g. observations).
    lower, upper : np.ndarray
        Bounds of the band of each value, of the same shape as `x`.
    limit : float | np.ndarray
        Detection limit, one for all or one per value (default 0: none).

    Returns
    -------
    float
        The share, from 0 to 1; NaN when no element is left.

    Raises
    ------
    ValueError
        If the shapes differ, or if a lower bound is above its upper bound.
    """  # pylint: disable=line-too-long
    return _fraction(x, lower, upper, "in", limit)


def fraction_above_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0) -> float:
    """
    Share of the values of ``x`` above the upper bound of their band. See :func:`fraction_in_band`.
    """
    return _fraction(x, lower, upper, "above", limit)


def fraction_below_band(x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0) -> float:
    """
    Share of the values of ``x`` below the lower bound of their band. See :func:`fraction_in_band`.
    """
    return _fraction(x, lower, upper, "below", limit)


def band_log_errors(
    x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0, cap: float = 1.0
) -> np.ndarray:
    """
    How far each value of ``x`` lies outside its band, in decades: ``log10(x / upper)`` above it,
    ``log10(lower / x)`` below it, 0 inside, and at most ``cap``. NaN where :func:`band_position`
    gives no position.

    The value and the bounds are raised to ``limit`` first (see :func:`band_position`), so a value of
    0 under a band whose lower bound is 0 is inside, and a band of 0 under a value is ``cap`` away.

    Parameters
    ----------
    x : np.ndarray
        Values (e.g. observations), 0 or more.
    lower, upper : np.ndarray
        Bounds of the band of each value, 0 or more, of the same shape as `x`.
    limit : float | np.ndarray
        Detection limit, one for all or one per value (default 0: none).
    cap : float
        Largest error counted, in decades (default 1: ten times off).

    Returns
    -------
    np.ndarray
        Errors from 0 to ``cap``, of the shape of `x`.

    Raises
    ------
    ValueError
        If the shapes differ, a lower bound is above its upper bound, or ``cap`` is not above 0.
    """
    if not cap > 0:  # pylint: disable=unnecessary-negation  # NaN is refused too
        raise ValueError(f"The cap must be above 0, got {cap}.")
    position = band_position(x, lower, upper, limit)
    x, lower, upper = _floored(*(np.asarray(item, dtype=np.float64) for item in (x, lower, upper)), limit)
    with np.errstate(divide="ignore", invalid="ignore"):
        above, below = np.log10(x / upper), np.log10(lower / x)
    error = np.full(position.shape, np.nan)
    error[position == "in"] = 0.0
    error[position == "above"] = np.minimum(cap, above[position == "above"])
    error[position == "below"] = np.minimum(cap, below[position == "below"])
    return error


def mean_band_log_error(
    x: np.ndarray, lower: np.ndarray, upper: np.ndarray, limit=0.0, cap: float = 1.0
) -> float:
    """
    Mean of :func:`band_log_errors` over the elements that have one; NaN when none has.
    """
    error = band_log_errors(x, lower, upper, limit, cap)
    error = error[np.isfinite(error)]
    return float(error.mean()) if error.size else float("nan")
