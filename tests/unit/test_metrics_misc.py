import pytest
import numpy as np
from firebench.metrics.kpi_normalization import (
    kpi_norm_bounded_linear,
    kpi_norm_half_open_linear,
    kpi_norm_half_open_exponential,
    kpi_norm_symmetric_open_linear,
    kpi_norm_symmetric_open_exponential,
)
from firebench.metrics.table import _score_to_color
from firebench.metrics.tools import ctx_get_or_compute, CtxKeyError


# kpi_norm_bounded_linear
# -----------------------
@pytest.mark.parametrize(
    "x, a, b, expected_score",
    [
        (0.0, 0.0, 10.0, 0.0),  # Lower bound
        (10.0, 0.0, 10.0, 100.0),  # Upper bound
        (5.0, 0.0, 10.0, 50.0),  # Midpoint
        (2.5, 0.0, 10.0, 25.0),  # General case
    ],
)
def test_kpi_norm_bounded_linear(x, a, b, expected_score):
    assert kpi_norm_bounded_linear(x, a, b) == pytest.approx(expected_score, abs=1e-12)


@pytest.mark.parametrize(
    "x, a, b",
    [
        (-1.0, 0.0, 10.0),  # Below lower bound
        (11.0, 0.0, 10.0),  # Above upper bound
    ],
)
def test_kpi_norm_bounded_linear_raises(x, a, b):
    with pytest.raises(ValueError):
        kpi_norm_bounded_linear(x, a, b)


# kpi_norm_half_open_linear
# -------------------------
@pytest.mark.parametrize(
    "x, a, m, expected_score",
    [
        (0.0, 0.0, 10.0, 100.0),  # Optimal value
        (10.0, 0.0, 10.0, 0.0),  # Threshold
        (5.0, 0.0, 10.0, 50.0),  # Midpoint
        (15.0, 0.0, 10.0, 0.0),  # Clipped above threshold
    ],
)
def test_kpi_norm_half_open_linear(x, a, m, expected_score):
    assert kpi_norm_half_open_linear(x, a, m) == pytest.approx(expected_score, abs=1e-12)


@pytest.mark.parametrize(
    "x, a, m",
    [
        (-1.0, 0.0, 10.0),  # x < a
    ],
)
def test_kpi_norm_half_open_linear_raises_on_x(x, a, m):
    with pytest.raises(ValueError):
        kpi_norm_half_open_linear(x, a, m)


@pytest.mark.parametrize(
    "x, a, m",
    [
        (1.0, 0.0, 0.0),  # m == a
        (1.0, 0.0, -1.0),  # m < a
    ],
)
def test_kpi_norm_half_open_linear_raises_on_m(x, a, m):
    with pytest.raises(ValueError):
        kpi_norm_half_open_linear(x, a, m)


# kpi_norm_half_open_exponential
# ------------------------------
@pytest.mark.parametrize(
    "x, a, m, expected_score",
    [
        (0.0, 0.0, 10.0, 100.0),  # Optimal value
        (10.0, 0.0, 10.0, 50.0),  # Definition of m
        (20.0, 0.0, 10.0, 25.0),  # One more half-life
    ],
)
def test_kpi_norm_half_open_exponential(x, a, m, expected_score):
    assert kpi_norm_half_open_exponential(x, a, m) == pytest.approx(expected_score, abs=1e-12)


@pytest.mark.parametrize(
    "x, a, m",
    [
        (-1.0, 0.0, 10.0),  # x < a
    ],
)
def test_kpi_norm_half_open_exponential_raises_on_x(x, a, m):
    with pytest.raises(ValueError):
        kpi_norm_half_open_exponential(x, a, m)


@pytest.mark.parametrize(
    "x, a, m",
    [
        (1.0, 0.0, 0.0),  # m == a
        (1.0, 0.0, -1.0),  # m < a
    ],
)
def test_kpi_norm_half_open_exponential_raises_on_m(x, a, m):
    with pytest.raises(ValueError):
        kpi_norm_half_open_exponential(x, a, m)


# kpi_norm_symmetric_open_linear
# ------------------------------
@pytest.mark.parametrize(
    "x, m, expected_score",
    [
        (0.0, 10.0, 100.0),  # Center
        (10.0, 10.0, 0.0),  # Positive threshold
        (-10.0, 10.0, 0.0),  # Negative threshold
        (5.0, 10.0, 50.0),  # Positive midpoint
        (-5.0, 10.0, 50.0),  # Negative midpoint
        (15.0, 10.0, 0.0),  # Clipped above threshold
        (-15.0, 10.0, 0.0),  # Clipped below threshold
    ],
)
def test_kpi_norm_symmetric_open_linear(x, m, expected_score):
    assert kpi_norm_symmetric_open_linear(x, m) == pytest.approx(expected_score, abs=1e-12)


@pytest.mark.parametrize(
    "x, m",
    [
        (0.0, 0.0),
        (1.0, -1.0),
    ],
)
def test_kpi_norm_symmetric_open_linear_raises(x, m):
    with pytest.raises(ValueError):
        kpi_norm_symmetric_open_linear(x, m)


# kpi_norm_symmetric_open_exponential
# -----------------------------------
@pytest.mark.parametrize(
    "x, m, expected_score",
    [
        (0.0, 10.0, 100.0),  # Center
        (10.0, 10.0, 50.0),  # Positive half-life
        (-10.0, 10.0, 50.0),  # Negative half-life
        (20.0, 10.0, 25.0),  # Two half-lives
        (-20.0, 10.0, 25.0),  # Two half-lives on negative side
    ],
)
def test_kpi_norm_symmetric_open_exponential(x, m, expected_score):
    assert kpi_norm_symmetric_open_exponential(x, m) == pytest.approx(expected_score, abs=1e-12)


@pytest.mark.parametrize(
    "x, m",
    [
        (0.0, 0.0),
        (1.0, -1.0),
    ],
)
def test_kpi_norm_symmetric_open_exponential_raises(x, m):
    with pytest.raises(ValueError):
        kpi_norm_symmetric_open_exponential(x, m)


# _score_to_color
# ---------------
@pytest.mark.parametrize(
    "score, expected_color",
    [
        (0.0, "#D6452A"),  # low score
        (10.0, "#D6452A"),
        (33.32, "#D6452A"),  # just below threshold
        (33.33, "#E8C441"),  # threshold
        (50.0, "#E8C441"),  # mid range
        (66.65, "#E8C441"),  # just below upper threshold
        (66.66, "#6BAF5F"),  # threshold
        (90.0, "#6BAF5F"),  # high score
        (100.0, "#6BAF5F"),
    ],
)
def test_score_to_color(score, expected_color):
    assert _score_to_color(score) == expected_color


# ctx_get_or_compute
# ------------------


def test_ctx_get_or_compute_returns_cached_value():
    key = ("model", "var", "metric")
    ctx_spec = {key: "test field"}
    ctx = {key: 42}

    def compute():
        raise RuntimeError("Should not be called")

    result = ctx_get_or_compute(ctx_spec, ctx, key, compute)

    assert result == 42


def test_ctx_get_or_compute_computes_and_caches():
    key = ("model", "var", "metric")
    ctx_spec = {key: "test field"}
    ctx = {}

    def compute(x):
        return x * 2

    result = ctx_get_or_compute(ctx_spec, ctx, key, compute, 5)

    assert result == 10
    assert ctx[key] == 10


def test_ctx_get_or_compute_raises_on_unknown_key():
    key = ("model", "var", "metric")
    ctx_spec = {}
    ctx = {}

    def compute():
        return 1

    with pytest.raises(CtxKeyError):
        ctx_get_or_compute(ctx_spec, ctx, key, compute)
