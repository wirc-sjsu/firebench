import numpy as np
import pytest
from firebench.stats import auto_bins


def test_constant_data_returns_two_bins():
    bins = auto_bins([5, 5, 5])
    assert np.allclose(bins, [5, 6]), "Should return two bins for constant data"


def test_nan_values_are_ignored():
    data = [np.nan, 1, 2, 3]
    bins = auto_bins(data, max_bins=3)
    assert bins[0] == 0
    assert bins[-1] >= 3


def test_returns_correct_number_of_bins():
    data = np.linspace(0, 10, 100)
    bins = auto_bins(data, max_bins=5)
    assert len(bins) <= 6  # 5 bins means 6 edges


def test_bin_edges_are_aligned_with_zero():
    data = [0.5, 1.0, 1.5]
    bins = auto_bins(data)
    assert np.isclose(bins[0], 0.0)
