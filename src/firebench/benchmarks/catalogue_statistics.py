"""
Statistics of a KPI across the events of a collection: the median, the interquartile range, and a
percentile bootstrap interval of the median. The settings are those of ``[statistics]`` in
``event_catalogue.toml``. They are the site's and the library's own statistics over per-event
results (never a score of a single event), shown with the number of samples.
"""

import numpy as np

from .catalogue_parameters import StatisticsParameters

BOOTSTRAP_CHUNK = 100


def summarize(values, statistics: StatisticsParameters) -> dict:
    """
    ``{"median", "q1", "q3", "ci_low", "ci_high", "interval_reason"}`` of the non-null ``values``.

    The interval is the percentile interval, at ``confidence``, of the median of ``bootstrap_resamples``
    resamples drawn with ``numpy.random.default_rng(bootstrap_seed)``, so the same values always give
    the same interval. Under ``min_samples_interval`` values the interval is null and says why; with no
    value everything is null.
    """
    sample = np.asarray([value for value in values if value is not None], dtype=float)
    sample = sample[np.isfinite(sample)]
    summary = {"median": None, "q1": None, "q3": None, "ci_low": None, "ci_high": None}
    if sample.size == 0:
        return {**summary, "interval_reason": "no sample"}
    q1, median, q3 = (float(item) for item in np.percentile(sample, [25, 50, 75]))
    summary.update(median=median, q1=q1, q3=q3)
    if sample.size < statistics.min_samples_interval:
        reason = f"fewer than {statistics.min_samples_interval} samples"
        return {**summary, "interval_reason": reason}
    rng = np.random.default_rng(statistics.bootstrap_seed)
    medians = []
    for start in range(0, statistics.bootstrap_resamples, BOOTSTRAP_CHUNK):
        count = min(BOOTSTRAP_CHUNK, statistics.bootstrap_resamples - start)
        draws = rng.integers(0, sample.size, size=(count, sample.size))
        medians.append(np.median(sample[draws], axis=1))
    tail = (1 - statistics.confidence) / 2 * 100
    low, high = np.percentile(np.concatenate(medians), [tail, 100 - tail])
    return {**summary, "ci_low": float(low), "ci_high": float(high), "interval_reason": None}
