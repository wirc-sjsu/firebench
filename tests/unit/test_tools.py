import firebench.tools as ft
import numpy as np
import pytest
from firebench import ureg
from pint import Quantity, Unit


def test_sobol_seq_basic():
    variables_info = {
        "length": (ureg.meter, [0.0, 1.0]),
        "time": (ureg.second, [10.0, 20.0]),
        "temperature": (ureg.kelvin, [273.15, 373.15]),
    }
    result = ft.sobol_seq(8, variables_info)

    assert "length" in result
    assert "time" in result
    assert "temperature" in result
    assert isinstance(result["length"], Quantity)
    assert isinstance(result["time"], Quantity)
    assert isinstance(result["temperature"], Quantity)


@pytest.mark.parametrize(
    "variables_info, expected_exception, exception_msg",
    [
        (
            {"length": (ureg.meter, [0.0])},
            ValueError,
            "Range for variable 'length' must have exactly 2 elements.",
        ),
        (
            {"length": (ureg.meter, [1.0, 0.0])},
            ValueError,
            "Upper range value must be greater than lower range value for variable 'length'.",
        ),
    ],
)
def test_sobol_seq_exceptions(variables_info, expected_exception, exception_msg):
    with pytest.raises(expected_exception) as excinfo:
        ft.sobol_seq(8, variables_info)
    assert str(excinfo.value) == exception_msg


@pytest.mark.parametrize(
    "N, scramble, seed",
    [
        (8, False, None),
        (16, True, 42),
    ],
)
def test_sobol_seq_parameters(N, scramble, seed):
    variables_info = {"length": (ureg.meter, [0.0, 1.0]), "time": (ureg.second, [10.0, 20.0])}
    result = ft.sobol_seq(N, variables_info, scramble=scramble, seed=seed)

    assert "length" in result
    assert "time" in result
    assert isinstance(result["length"], Quantity)
    assert isinstance(result["time"], Quantity)
    assert len(result["length"]) == N
    assert len(result["time"]) == N


def test_scramble_effect():
    N = 8
    variables_info = {"length": (ureg.meter, [0.0, 1.0]), "time": (ureg.second, [10.0, 20.0])}
    result_no_scramble = ft.sobol_seq(N, variables_info, scramble=False)
    result_scramble = ft.sobol_seq(N, variables_info, scramble=True)

    for key in variables_info.keys():
        assert not np.array_equal(
            result_no_scramble[key].magnitude, result_scramble[key].magnitude
        ), f"{key} should be different when scrambled."


@pytest.mark.parametrize(
    "scramble_1, seed_1, scramble_2, seed_2, expected_similar",
    [
        (False, None, False, None, True),
        (True, 42, True, 42, True),
        (True, 42, True, 18, False),
    ],
)
def test_seed_reproducibility(scramble_1, seed_1, scramble_2, seed_2, expected_similar):
    N = 8
    variables_info = {"length": (ureg.meter, [0.0, 1.0]), "time": (ureg.second, [10.0, 20.0])}
    result_seed_42_a = ft.sobol_seq(N, variables_info, scramble=scramble_1, seed=seed_1)
    result_seed_42_b = ft.sobol_seq(N, variables_info, scramble=scramble_2, seed=seed_2)

    for key in variables_info.keys():
        if expected_similar:
            assert np.array_equal(
                result_seed_42_a[key].magnitude, result_seed_42_b[key].magnitude
            ), f"{key} should be the same for the same seed."
        else:
            assert not np.array_equal(
                result_seed_42_a[key].magnitude, result_seed_42_b[key].magnitude
            ), f"{key} should be different for different seeds."


@pytest.mark.parametrize(
    "dict1, dict2, expected",
    [
        ({"a": 1, "b": 2}, {"c": 3, "d": 4}, {"a": 1, "b": 2, "c": 3, "d": 4}),  # No conflicts
        ({"a": 1}, {"b": 2, "c": 3}, {"a": 1, "b": 2, "c": 3}),  # No conflicts
        ({}, {"a": 1}, {"a": 1}),  # One empty dictionary
        ({"a": 1}, {}, {"a": 1}),  # One empty dictionary
    ],
)
def test_merge_dictionaries(dict1, dict2, expected):
    assert ft.merge_dictionaries(dict1, dict2) == expected


@pytest.mark.parametrize(
    "dict1, dict2, conflicting_keys",
    [
        ({"a": 1, "b": 2}, {"a": 3, "c": 4}, {"a"}),  # Single conflict
        ({"a": 1}, {"a": 2}, {"a"}),  # Single conflict
        ({"a": 1, "b": 2}, {"b": 3, "c": 4}, {"b"}),  # Single conflict
    ],
)
def test_merge_dictionaries_key_conflict(dict1, dict2, conflicting_keys):
    with pytest.raises(KeyError) as excinfo:
        ft.merge_dictionaries(dict1, dict2)
    assert str(conflicting_keys) in str(excinfo.value)
