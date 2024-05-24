import json
import os
import os.path as osp

import firebench.tools as ft
import numpy as np
import pytest
from firebench import ureg, svn
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


@pytest.mark.parametrize(
    "filename, suffix, expected",
    [
        ("file", "txt", "file.txt"),  # Case: No suffix, should add
        ("file.txt", "txt", "file.txt"),  # Case: Already has suffix, should not change
        ("file", "csv", "file.csv"),  # Case: No suffix, different suffix
        ("file.csv", "txt", "file.csv.txt"),  # Case: Different existing suffix
        ("", "txt", ".txt"),  # Case: Empty filename
        ("file.name.with.dots", "txt", "file.name.with.dots.txt"),  # Case: Filename with dots
    ],
)
def test_add_suffix(filename, suffix, expected):
    assert ft.read_data.__add_suffix(filename, suffix) == expected


def test_get_json_data_file_default_path():
    # Test with a real file in the default package path
    fuel_model_name = "Anderson13"
    expected_path = osp.abspath(
        osp.normpath(osp.join(osp.dirname(__file__), "..", "..", "data", "fuel_models", "Anderson13.json"))
    )
    func_path = osp.abspath(osp.normpath(ft.read_data.__get_json_data_file(fuel_model_name)))
    assert func_path == expected_path


def test_get_json_data_file_local_path():
    # Test with a real file in a local path
    fuel_model_name = "Anderson13"
    local_path = osp.abspath(
        osp.normpath(osp.join(osp.dirname(__file__), "..", "..", "data", "fuel_models"))
    )
    expected_path = osp.join(local_path, "Anderson13.json")
    func_path = osp.abspath(osp.normpath(ft.read_data.__get_json_data_file(fuel_model_name, local_path)))
    assert func_path == expected_path


def test_get_json_data_file_not_found():
    # Test with a non-existent file
    fuel_model_name = "non_existent_model"
    with pytest.raises(FileNotFoundError):
        ft.read_data.__get_json_data_file(fuel_model_name)
    local_path = osp.abspath(
        osp.normpath(osp.join(osp.dirname(__file__), "..", "..", "data", "fuel_models"))
    )
    with pytest.raises(FileNotFoundError):
        ft.read_data.__get_json_data_file(fuel_model_name, local_path)


def test_read_fuel_data_file():
    # Test with a real file in the default package path
    fuel_model_name = "Anderson13"

    # Assuming these files exist in the package
    package_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "fuel_models")
    )
    json_file_path = os.path.join(package_dir, "Anderson13.json")
    csv_file_path = os.path.join(package_dir, "data_Anderson13.csv")

    # Ensure the files exist
    assert os.path.isfile(json_file_path), f"Missing JSON file: {json_file_path}"
    assert os.path.isfile(csv_file_path), f"Missing CSV file: {csv_file_path}"

    # Run the function
    output_data = ft.read_fuel_data_file(fuel_model_name)

    # Known values from Anderson13.csv
    known_values = {
        "fuel_load_dry_total": [
            0.166,
            0.897,
            0.675,
            2.468,
            0.785,
            1.345,
            1.092,
            1.121,
            0.78,
            2.694,
            2.582,
            7.749,
            13.024,
        ],
    }

    # Compare the output to the known values
    for key, expected_values in known_values.items():
        std_var = svn(key)
        np.testing.assert_array_equal(output_data[std_var].magnitude, np.array(expected_values))
        assert output_data[std_var].units == ureg("kg/m**2")

def test_check_input_completeness():
    # Test case with complete data
    input_data = {"wind_speed": 5, "temperature": 25, "humidity": 60}
    metadata_dict = {
        "wind": {"std_name": "wind_speed"},
        "temp": {"std_name": "temperature"},
        "hum": {"std_name": "humidity"},
    }
    ft.check_input_completeness(input_data, metadata_dict)

    # Test case with missing data
    incomplete_input_data = {"wind_speed": 5, "temperature": 25}
    with pytest.raises(KeyError, match="The data 'humidity' is missing in the input dict"):
        ft.check_input_completeness(incomplete_input_data, metadata_dict)

    # Test case with empty input data
    empty_input_data = {}
    with pytest.raises(KeyError, match="The data 'wind_speed' is missing in the input dict"):
        ft.check_input_completeness(empty_input_data, metadata_dict)

    # Test case with empty metadata
    empty_metadata_dict = {}
    ft.check_input_completeness(input_data, empty_metadata_dict)

    # Test case with 'output_' keys in metadata
    input_data_with_output = {"wind_speed": 5, "temperature": 25, "humidity": 60}
    metadata_with_output = {
        "wind": {"std_name": "wind_speed"},
        "temp": {"std_name": "temperature"},
        "hum": {"std_name": "humidity"},
        "output_wind_speed": {"std_name": "output_wind_speed"},  # Should be ignored
    }
    ft.check_input_completeness(input_data_with_output, metadata_with_output)

    # Test case with missing data but with 'output_' key in metadata
    incomplete_input_data_with_output = {"wind_speed": 5, "temperature": 25}
    metadata_with_output_incomplete = {
        "wind": {"std_name": "wind_speed"},
        "temp": {"std_name": "temperature"},
        "output_wind_speed": {"std_name": "output_wind_speed"},  # Should be ignored
    }
    # This should not raise KeyError since 'humidity' is not in metadata_with_output_incomplete
    ft.check_input_completeness(incomplete_input_data_with_output, metadata_with_output_incomplete)

    # Ensure the function raises KeyError for the incomplete input that doesn't have "humidity"
    with pytest.raises(KeyError, match="The data 'humidity' is missing in the input dict"):
        ft.check_input_completeness(incomplete_input_data_with_output, metadata_with_output)

# Run the tests
if __name__ == "__main__":
    pytest.main()