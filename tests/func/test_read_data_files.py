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


# Run the tests
if __name__ == "__main__":
    pytest.main()
