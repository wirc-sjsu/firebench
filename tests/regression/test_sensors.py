import firebench.sensors as fbs
import numpy as np
import pytest


@pytest.mark.parametrize(
    "fmc, age, expected_value",
    [
        (0, None, 0.74),
        (9.99, None, 0.74),
        (10, None, 0.90),
        (19.99, None, 0.90),
        (20, None, 1.94),
        (29.99, None, 1.94),
        (30, None, 2.27),
        (50, None, 2.27),
    ],
)
def test_CS506_rms(fmc, age, expected_value):
    result = fbs.CS506_rms(fmc, age)
    assert np.isclose(
        result, expected_value, rtol=1e-5
    ), f"Failed for {fmc=}, {age=}. expected {expected_value}, got {result}"


@pytest.mark.parametrize(
    "fmc, age, expected_value",
    [
        (0, None, 1.25),
        (9.99, None, 1.25),
        (10, None, 2),
        (19.99, None, 2),
        (20, None, 3.4),
        (29.99, None, 3.4),
        (30, None, 4.11),
        (50, None, 4.11),
    ],
)
def test_CS506_range90(fmc, age, expected_value):
    result = fbs.CS506_range90(fmc, age)
    assert np.isclose(
        result, expected_value, rtol=1e-5
    ), f"Failed for {fmc=}, {age=}. expected {expected_value}, got {result}"
