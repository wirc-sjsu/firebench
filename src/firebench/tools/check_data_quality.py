import numpy as np
from pint import Quantity


def check_input_completeness(input_data: dict, metadata_dict: dict):
    """
    Check the completeness of the input data against the metadata dictionary.

    Parameters
    ----------
    input_data : dict
        Dictionary containing the input data.
    metadata_dict : dict
        Dictionary containing metadata, where each key is a metadata item and each value is a dictionary
        with at least the key "std_name" representing the standard name of the data item.

    Raises
    ------
    KeyError
        If any standard name specified in the metadata is missing in the input data.
    """  # pylint: disable=line-too-long
    for key, item in metadata_dict.items():
        if key.startswith("output_"):
            continue
        std_name_metadata = item["std_name"]
        if std_name_metadata not in input_data:
            raise KeyError(f"The data '{std_name_metadata}' is missing in the input dict")


def convert_input_data_units(input_data: dict, metadata_dict: dict) -> dict:
    """
    Convert the units of input data based on the metadata dictionary.

    Parameters
    ----------
    input_data : dict
        Dictionary containing the input data with units.
    metadata_dict : dict
        Dictionary containing metadata, where each key is a metadata item and each value is a dictionary
        with at least the key "std_name" representing the standard name of the data item and "units" specifying the target units.

    Returns
    -------
    dict
        A dictionary where the keys are standard variable names (as per metadata) and the values are quantities converted to the target units.

    Raises
    ------
    KeyError
        If any standard name specified in the metadata is missing in the input data.
    """  # pylint: disable=line-too-long
    output_dict = {}
    for key, item in metadata_dict.items():
        if key.startswith("output_"):
            continue
        std_name_metadata = item["std_name"]
        data: Quantity = input_data[std_name_metadata]
        output_dict[std_name_metadata] = data.to(item["units"])
    return output_dict


def check_validity_range(input_data: dict, metadata_dict: dict):
    """
    Check if the input data values fall within the specified validity range in the metadata dictionary.

    Parameters
    ----------
    input_data : dict
        Dictionary containing the input data with units.
    metadata_dict : dict
        Dictionary containing metadata, where each key is a metadata item and each value is a dictionary
        with at least the key "std_name" representing the standard name of the data item, "units" specifying the units, and "range" specifying the valid range as a tuple (min, max).

    Raises
    ------
    ValueError
        If any value in the input data is outside the specified validity range in the metadata.
    """  # pylint: disable=line-too-long
    for key, item in metadata_dict.items():
        if key.startswith("output_"):
            continue
        std_name_metadata = item["std_name"]
        data: Quantity = input_data[std_name_metadata]
        data_min = np.nanmin(data.magnitude)
        if data_min < item["range"][0]:
            raise ValueError(
                f"min value of input variable {std_name_metadata}: {data_min:.2e} {item['units']} "
                f"lower than lower bound of validity range {item['range'][0]:.2e}."
            )
        data_max = np.nanmax(data.magnitude)
        if data_max > item["range"][1]:
            raise ValueError(
                f"max value of input variable {std_name_metadata}: {data_max:.2e} {item['units']} "
                f"greater than upper bound of validity range {item['range'][1]:.2e}."
            )
