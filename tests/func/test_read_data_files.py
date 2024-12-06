import os

import firebench.tools as ft
import numpy as np
import pytest
from firebench import svn, ureg


def test_read_fuel_data_file_local():
    # Test with a real file in the default package path
    fuel_model_name = "Anderson13"

    # Assuming these files exist in the package
    json_file_path = os.path.join(ft.get_firebench_data_directory(), "fuel_models", "Anderson13.json")
    csv_file_path = os.path.join(ft.get_firebench_data_directory(), "fuel_models", "data_Anderson13.csv")

    # Ensure the files exist
    assert os.path.isfile(json_file_path), f"Missing JSON file: {json_file_path}"
    assert os.path.isfile(csv_file_path), f"Missing CSV file: {csv_file_path}"

    # Run the function
    output_data = ft.read_fuel_data_file(fuel_model_name)

    # Known values from data_Anderson13.csv
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


def test_read_dummy_fuel_data_file_local():

    # Assuming these files exist in the package
    json_file_path = os.path.join(ft.get_firebench_data_directory(), "test", "dummy_fuel_model.json")
    csv_file_path = os.path.join(ft.get_firebench_data_directory(), "test", "data_dummy_fuel_model.csv")

    # Ensure the files exist
    assert os.path.isfile(json_file_path), f"Missing JSON file: {json_file_path}"
    assert os.path.isfile(csv_file_path), f"Missing CSV file: {csv_file_path}"

    # Run the function
    output_data = ft.read_data_file("dummy_fuel_model", "test")

    # Known values from data_dummy_fuel_model.csv
    known_values = {
        "fuel_height": [
            1,
            2,
            4,
        ],
        "fuel_load_dry_total": [
            2,
            4.9,
            np.nan,
        ],
    }

    # Compare the output to the known values
    for key, expected_values in known_values.items():
        std_var = svn(key)
        np.testing.assert_array_equal(output_data[std_var].magnitude, np.array(expected_values))


@pytest.mark.parametrize("add_complementary_field", [True, False])
def test_import_scott_burgan_40_fuel_model(add_complementary_field):
    fuel_data = ft.import_scott_burgan_40_fuel_model(add_complementary_field=add_complementary_field)

    assert svn.FUEL_HEIGHT in fuel_data, "Total fuel load key is missing"
    assert len(fuel_data[svn.FUEL_HEIGHT]) == 40, "Need to have 40 classes"

    if add_complementary_field:
        # Check that complementary fields are present
        assert svn.FUEL_LOAD_DRY_TOTAL in fuel_data, "Total fuel load key is missing"
        assert svn.FUEL_SURFACE_AREA_VOLUME_RATIO in fuel_data, "Total SAVR key is missing"
        assert svn.FUEL_LOAD_DEAD_RATIO in fuel_data, "Dead fuel ratio key is missing"
    else:
        # Check that complementary fields are NOT present
        assert svn.FUEL_LOAD_DRY_TOTAL not in fuel_data, "Total fuel load key should not be present"
        assert svn.FUEL_SURFACE_AREA_VOLUME_RATIO not in fuel_data, "Total SAVR key should not be present"
        assert svn.FUEL_LOAD_DEAD_RATIO not in fuel_data, "Dead fuel ratio key should not be present"


def test_import_anderson_13_fuel_model():
    fuel_data = ft.import_anderson_13_fuel_model()

    assert svn.FUEL_HEIGHT in fuel_data, "Total fuel load key is missing"
    assert len(fuel_data[svn.FUEL_HEIGHT]) == 13, "Need to have 40 classes"


# Run the tests
if __name__ == "__main__":
    pytest.main()
