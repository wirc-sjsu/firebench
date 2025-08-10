import numpy as np


def auto_bins(data, max_bins=40, base=10):
    """
    Automatically generate histogram bin edges for plotting, based on data range.

    The function estimates a "nice" bin width using a logarithmic base scaling and
    selects a width that produces up to `max_bins` bins while preserving human-readable spacing.
    It handles NaNs and constant data gracefully.

    Parameters
    ----------
    data : array_like
        Input array of values to be histogrammed.
    max_bins : int, optional
        Maximum number of bins to aim for (default is 40).
    base : float, optional
        Logarithmic base used to scale bin widths (default is 10).

    Returns
    -------
    bins : np.ndarray
        Array of bin edges suitable for use with `np.histogram` or `plt.hist`.

    Examples
    --------
    >>> auto_bins([0.1, 0.2, 0.3, 0.4])
    array([0. , 0.1, 0.2, 0.3, 0.4, 0.5])
    """  # pylint: disable=line-too-long
    data = np.asarray(data)
    data = data[~np.isnan(data)]  # Remove NaNs

    dmin, dmax = np.min(data), np.max(data)
    raw_range = dmax - dmin

    if raw_range == 0:
        return [dmin, dmax + 1]

    # Calculate a nice bin width
    bin_width = base ** np.floor(np.log10(raw_range / max_bins))
    steps = np.array([1, 2, 5, 10])
    best_step = steps[np.argmin(np.abs((raw_range / max_bins) - steps * bin_width))]
    final_width = bin_width * best_step

    # Define bin edges from 0 to next multiple of final_width
    upper = np.ceil(dmax / final_width) * final_width
    bins = np.arange(0, upper + final_width, final_width)

    return bins
