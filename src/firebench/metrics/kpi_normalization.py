from math import exp, log, isclose


def kpi_norm_bounded_linear(x, a, b, rtol=1e-12, atol=1e-15):
    """
    Linearly normalize a KPI that has a fully bounded acceptable range [a, b].

    This function maps:
        - x = a -> score = 0
        - x = b -> score = 100
    with a strictly linear transformation.

    Use this normalization when the KPI is known to lie within a finite closed interval.

    Parameters
    ----------
    x : float
        KPI value to normalize.
    a : float
        Lower bound of the acceptable range (score = 0).
    b : float
        Upper bound of the acceptable range (score = 100). Must satisfy a < b.

    Returns
    -------
    float
        Normalized score in the range with 0 at `a` and 100 at `b`.

    Raises
    ------
    ValueError
        If `x < a` or if `x > b`.
    """
    if x < a and not isclose(x, a, rel_tol=rtol, abs_tol=atol):
        raise ValueError(f"KPI value {x} smaller than lower limit {a}")
    if x > b and not isclose(x, b, rel_tol=rtol, abs_tol=atol):
        raise ValueError(f"KPI value {x} greater than upper limit {b}")
    return 100.0 * (x - a) / (b - a)


def kpi_norm_half_open_linear(x, a, m, rtol=1e-12, atol=1e-15):
    """
    Linearly normalize a KPI defined on the half-open interval [a, \infty).

    This function applies a linear decay starting from:
        - x = a -> score = 100
        - x = m -> score = 0
    Values above `m` yield a score of 0 through clipping.

    Use this normalization when the KPI has a minimum acceptable value `a`
    but no finite upper bound, and when the degradation beyond `a` can be
    meaningfully represented by a linear decline over the scale [a, m].

    Parameters
    ----------
    x : float
        KPI value to normalize. Must satisfy x >= a.
    a : float
        Minimum acceptable (or optimal) value at which the score is 100.
    m : float
        Threshold at which the score reaches 0. Must satisfy m > a.

    Returns
    -------
    float
        Normalized score in the range [0, 100], with linear decay from
        100 at `a` to 0 at `m`.

    Raises
    ------
    ValueError
        If `x < a` or if `m <= a`.
    """
    if x < a and not isclose(x, a, rel_tol=rtol, abs_tol=atol):
        raise ValueError(f"KPI value {x} smaller than lower limit {a}")
    if m <= a:
        raise ValueError(f"Parameter m ({m}) smaller than lower limit a ({a})")
    return 100.0 * max(0, 1 - (x - a) / (m - a))


def kpi_norm_half_open_exponential(x, a, m, rtol=1e-12, atol=1e-15):
    """
    Exponentially normalize a KPI defined on the half-open interval [a, \infty).

    This function applies a smooth exponential decay such that:
        - x = a -> score = 100
        - x = m -> score = 50
        - x -> \infty -> score -> 0
    ensuring a monotonic and asymptotic decline.

    Use this normalization when the KPI has a minimum acceptable value `a`
    but no finite upper bound, and when deviations beyond `a` should be
    penalized progressively rather than linearly. The parameter `m` defines
    the characteristic decay scale at which performance is reduced by half.

    Parameters
    ----------
    x : float
        KPI value to normalize. Must satisfy x >= a.
    a : float
        Minimum acceptable (or optimal) value at which the score is 100.
    m : float
        Value at which the score reaches 50. Must satisfy m > a.

    Returns
    -------
    float
        Normalized score in the range (0, 100], decaying exponentially
        from 100 at `a` toward 0 as `x` increases.

    Raises
    ------
    ValueError
        If `x < a` or if `m <= a`.
    """
    if x < a and not isclose(x, a, rel_tol=rtol, abs_tol=atol):
        raise ValueError(f"KPI value {x} smaller than lower limit {a}")
    if m <= a:
        raise ValueError(f"Parameter m ({m}) smaller than lower limit a ({a})")
    return 100.0 * exp(-log(2) * (x - a) / (m - a))


def kpi_norm_symmetric_open_linear(x, m):
    """
    Linearly normalize a KPI defined on the open interval (-\infty, \infty).

    This function applies a smooth exponential decay such that:
        - x = 0 -> score = 100
        - |x| >= m -> score = 0

    Use this normalization when deviations should be penalized linearly.

    Parameters
    ----------
    x : float
        KPI value to normalize.
    m : float
        Value at which the score reaches 0. Must satisfy m > 0.

    Returns
    -------
    float
        Normalized score in the range (0, 100], dlinear decay from
        100 at `a` to 0 at `m`.

    Raises
    ------
    ValueError
        If `m <= 0`.
    """
    if m <= 0:
        raise ValueError(f"Parameter m ({m}) smaller than lower limit 0")
    return 100.0 * max(0, 1 - abs(x) / m)


def kpi_norm_symmetric_open_exponential(x, m):
    """
    Exponentially normalize a KPI defined on the open interval (-\infty, \infty).

    This function applies a smooth exponential decay such that:
        - x = 0 -> score = 100
        - x = +/- m -> score = 50
        - x -> \infty -> score -> 0
    ensuring a monotonic and asymptotic decline.

    Use this normalization when deviations should be
    penalized progressively rather than linearly. The parameter `m` defines
    the characteristic decay scale at which performance is reduced by half.

    Parameters
    ----------
    x : float
        KPI value to normalize.
    m : float
        Value at which the score reaches 50. Must satisfy m > 0.

    Returns
    -------
    float
        Normalized score in the range (0, 100], decaying exponentially
        from 100 at `0` toward 0 as `x` increases.

    Raises
    ------
    ValueError
        If `m <= 0`.
    """
    if m <= 0:
        raise ValueError(f"Parameter m ({m}) smaller than lower limit 0")
    return 100.0 * exp(-log(2) * abs(x) / m)
