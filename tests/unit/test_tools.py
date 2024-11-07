import os
import tempfile

import firebench.tools as ft
import numpy as np
import pytest
from firebench import svn, ureg
from pint import Quantity


def test_sobol_seq_basic():
    variables_info = {
        svn.LENGTH: {"unit": ureg.meter, "range": [0.0, 1.0]},
        svn.TIME: {"unit": ureg.second, "range": [10.0, 20.0]},
        svn.TEMPERATURE: {"unit": ureg.kelvin, "range": [273.15, 373.15]},
    }
    result, _, _ = ft.sobol_seq(8, variables_info)
    print(result)
    assert svn.LENGTH in result
    assert svn.TIME in result
    assert svn.TEMPERATURE in result
    assert isinstance(result[svn.LENGTH], Quantity)
    assert isinstance(result[svn.TIME], Quantity)
    assert isinstance(result[svn.TEMPERATURE], Quantity)


@pytest.mark.parametrize(
    "N, scramble, seed, N_sobol_th",
    [
        (8, False, None, 48),
        (16, True, 42, 96),
    ],
)
def test_sobol_seq_parameters(N, scramble, seed, N_sobol_th):
    variables_info = {
        svn.LENGTH: {"unit": ureg.meter, "range": [0.0, 1.0]},
        svn.TIME: {"unit": ureg.second, "range": [10.0, 20.0]},
    }
    result, _, N_sobol = ft.sobol_seq(N, variables_info, scramble=scramble, seed=seed)

    assert isinstance(result[svn.LENGTH], Quantity)
    assert isinstance(result[svn.TIME], Quantity)
    assert len(result[svn.LENGTH]) == N_sobol_th
    assert len(result[svn.TIME]) == N_sobol_th
    assert N_sobol == N_sobol_th


def test_scramble_effect():
    N = 8
    variables_info = {
        svn.LENGTH: {"unit": ureg.meter, "range": [0.0, 1.0]},
        svn.TIME: {"unit": ureg.second, "range": [10.0, 20.0]},
    }
    result_no_scramble, _, _ = ft.sobol_seq(N, variables_info, scramble=False)
    result_scramble, _, _ = ft.sobol_seq(N, variables_info, scramble=True)

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
    variables_info = {
        svn.LENGTH: {"unit": ureg.meter, "range": [0.0, 1.0]},
        svn.TIME: {"unit": ureg.second, "range": [10.0, 20.0]},
    }
    result_seed_42_a, _, _ = ft.sobol_seq(N, variables_info, scramble=scramble_1, seed=seed_1)
    result_seed_42_b, _, _ = ft.sobol_seq(N, variables_info, scramble=scramble_2, seed=seed_2)

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


def test_get_firebench_data_directory_success(mocker):
    # Mock the environment variable
    mocker.patch.dict(os.environ, {"FIREBENCH_DATA_PATH": "/fake/path/to/firebench/data"})

    # Call the function and check the result
    result = ft.read_data.get_firebench_data_directory()
    assert result == "/fake/path/to/firebench/data"


def test_get_firebench_data_directory_no_env_var(mocker):
    # Ensure the environment variable is not set
    mocker.patch.dict(os.environ, {}, clear=True)

    # Call the function and expect an EnvironmentError
    with pytest.raises(EnvironmentError, match="Firebench data directory path is not set"):
        ft.get_firebench_data_directory()


def test_fuel_model_json_file_not_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_fuel_data_directory = temp_dir
        custom_fuel_model_name = "mymodel"
        custom_fuel_model_json_path = os.path.join(
            custom_fuel_data_directory, f"{custom_fuel_model_name}.json"
        )

        # Ensure the file does not exist
        assert not os.path.isfile(custom_fuel_model_json_path)

        with pytest.raises(FileNotFoundError, match="not found"):
            ft.read_data._get_fuel_model_json_data_file_path(
                custom_fuel_model_name, local_path_json_fuel_db=custom_fuel_data_directory
            )


def test_fuel_model_json_file_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_fuel_model_name = "mymodel"
        custom_fuel_model_json_path = os.path.join(temp_dir, f"{custom_fuel_model_name}.json")

        # Create a dummy file
        with open(custom_fuel_model_json_path, "w") as dummy_file:
            dummy_file.write("test content")

        result_path = ft.read_data._get_fuel_model_json_data_file_path(
            custom_fuel_model_name, local_path_json_fuel_db=temp_dir
        )

        assert result_path == custom_fuel_model_json_path


def test_fuel_model_default_json_file_not_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["FIREBENCH_DATA_PATH"] = temp_dir
        custom_fuel_model_name = "mymodel"
        custom_fuel_model_json_path = os.path.join(
            temp_dir, "fuel_models", f"{custom_fuel_model_name}.json"
        )

        # Ensure the file does not exist
        assert not os.path.isfile(custom_fuel_model_json_path)

        with pytest.raises(FileNotFoundError, match="not found"):
            ft.read_data._get_fuel_model_json_data_file_path(
                custom_fuel_model_name, local_path_json_fuel_db=None
            )


def test_fuel_model_default_json_file_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["FIREBENCH_DATA_PATH"] = temp_dir
        custom_fuel_model_name = "mymodel"
        custom_fuel_model_json_path = os.path.join(temp_dir, f"{custom_fuel_model_name}.json")

        # Create a dummy file
        with open(custom_fuel_model_json_path, "w") as dummy_file:
            dummy_file.write("test content")

        result_path = ft.read_data._get_fuel_model_json_data_file_path(
            custom_fuel_model_name, local_path_json_fuel_db=temp_dir
        )

        assert result_path == custom_fuel_model_json_path


def test_check_input_completeness(caplog):
    # Test case with complete data
    input_data = {"wind_speed": 5, "temperature": 25, "humidity": 60}
    metadata_dict = {
        "wind": {"std_name": "wind_speed", "type": ft.ParameterType.input},
        "temp": {"std_name": "temperature", "type": ft.ParameterType.input},
        "hum": {"std_name": "humidity", "type": ft.ParameterType.input},
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

    # Test case with output types in metadata
    input_data_with_output = {"wind_speed": 5, "temperature": 25, "humidity": 60}
    metadata_with_output = {
        "wind": {"std_name": "wind_speed", "type": ft.ParameterType.input},
        "temp": {"std_name": "temperature", "type": ft.ParameterType.input},
        "hum": {"std_name": "humidity", "type": ft.ParameterType.input},
        "ros": {"std_name": "ros", "type": ft.ParameterType.output},  # Should be ignored
    }
    ft.check_input_completeness(input_data_with_output, metadata_with_output)

    # Test case with missing data but with output type in metadata
    incomplete_input_data_with_output = {"wind_speed": 5, "temperature": 25}
    metadata_with_output_incomplete = {
        "wind": {"std_name": "wind_speed", "type": ft.ParameterType.input},
        "temp": {"std_name": "temperature", "type": ft.ParameterType.input},
        "ros": {"std_name": "ros", "type": ft.ParameterType.output},  # Should be ignored
    }
    # This should not raise KeyError since 'humidity' is not in metadata_with_output_incomplete
    ft.check_input_completeness(incomplete_input_data_with_output, metadata_with_output_incomplete)

    # Ensure the function raises KeyError for the incomplete input that doesn't have "humidity"
    with pytest.raises(KeyError, match="The data 'humidity' is missing in the input dict"):
        ft.check_input_completeness(incomplete_input_data_with_output, metadata_with_output)

    # Change the logging level for the next tests
    ft.set_logging_level(ft.logging.INFO)
    
    # Test with optional input in input dict
    input_data_with_optional = {"wind_speed": 5, "temperature": 25}
    metadata_with_optional = {
        "wind": {"std_name": "wind_speed", "type": ft.ParameterType.input},
        "temp": {"std_name": "temperature", "type": ft.ParameterType.optional},
    }
    with caplog.at_level(ft.logging.INFO):
        ft.check_input_completeness(input_data_with_optional, metadata_with_optional)
        # As optional input is in input dict, no info in log
        assert (
            f"The optional data temperature is missing in the input dict. Default value will be used."
            not in caplog.text
        )

    # Test with optional input not in input dict
    input_data_with_optional = {"wind_speed": 5}
    metadata_with_optional = {
        "wind": {"std_name": "wind_speed", "type": ft.ParameterType.input},
        "temp": {"std_name": "temperature", "type": ft.ParameterType.optional},
    }
    with caplog.at_level(ft.logging.INFO):
        ft.check_input_completeness(input_data_with_optional, metadata_with_optional)
        # As optional input not is in input dict, info in log
        assert (
            f"The optional data temperature is missing in the input dict. Default value will be used."
            in caplog.text
        )


@pytest.mark.parametrize(
    "input_data, metadata_dict, expected_output",
    [
        (
            {"temperature": ureg.Quantity(25, ureg.celsius)},
            {
                "temp": {"std_name": "temperature", "units": "kelvin", "type": ft.ParameterType.input},
                "output_test": {
                    "std_name": "value",
                    "units": "some_units",
                    "type": ft.ParameterType.output,
                },
            },
            {"temperature": ureg.Quantity(298.15, ureg.kelvin)},
        ),
        (
            {"distance": ureg.Quantity(1000, ureg.meter)},
            {
                "dist": {"std_name": "distance", "units": "kilometer", "type": ft.ParameterType.input},
                "output_test": {
                    "std_name": "value",
                    "units": "some_units",
                    "type": ft.ParameterType.output,
                },
            },
            {"distance": ureg.Quantity(1, ureg.kilometer)},
        ),
        (
            {"speed": ureg.Quantity(100, ureg.kph)},
            {
                "spd": {"std_name": "speed", "units": "m/s", "type": ft.ParameterType.input},
                "output_test": {
                    "std_name": "value",
                    "units": "some_units",
                    "type": ft.ParameterType.output,
                },
            },
            {"speed": ureg.Quantity(27.77777778, ureg.m / ureg.s)},
        ),
    ],
)
def test_convert_input_data_units(input_data, metadata_dict, expected_output):
    output = ft.convert_input_data_units(input_data, metadata_dict)
    for key in expected_output:
        assert output[key].magnitude == pytest.approx(expected_output[key].magnitude)
        assert output[key].units == expected_output[key].units


@pytest.mark.parametrize(
    "input_data, metadata_dict, should_raise",
    [
        (
            {"temperature": ureg.Quantity([20, 25, 30], ureg.celsius)},
            {
                "temp": {
                    "std_name": "temperature",
                    "units": "celsius",
                    "range": (15, 35),
                    "type": ft.ParameterType.input,
                }
            },
            False,
        ),
        (
            {"temperature": ureg.Quantity([10, 25, 30], ureg.celsius)},
            {
                "temp": {
                    "std_name": "temperature",
                    "units": "celsius",
                    "range": (15, 35),
                    "type": ft.ParameterType.input,
                }
            },
            True,
        ),
        (
            {"temperature": ureg.Quantity([20, 25, 40], ureg.celsius)},
            {
                "temp": {
                    "std_name": "temperature",
                    "units": "celsius",
                    "range": (15, 35),
                    "type": ft.ParameterType.input,
                }
            },
            True,
        ),
        (
            {"temperature": ureg.Quantity([20, 25, 30], ureg.celsius)},
            {
                "temp": {
                    "std_name": "temperature",
                    "units": "celsius",
                    "range": (15, 35),
                    "type": ft.ParameterType.input,
                },
                "test": {
                    "std_name": "value",
                    "units": "some_units",
                    "range": (0, 100),
                    "type": ft.ParameterType.output,
                },
            },
            False,
        ),
    ],
)
def test_check_validity_range(input_data, metadata_dict, should_raise):
    if should_raise:
        with pytest.raises(ValueError):
            ft.check_validity_range(input_data, metadata_dict)
    else:
        ft.check_validity_range(input_data, metadata_dict)


# Run the tests
if __name__ == "__main__":
    pytest.main()
