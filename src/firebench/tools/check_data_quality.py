import numpy as np
from pint import Quantity

from ..ros_models import RateOfSpreadModel
from .input_info import ParameterType
from .logging_config import logger


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
        # check that mandatory input is present
        if item["type"] == ParameterType.input:
            std_name_metadata = item["std_name"]
            if std_name_metadata not in input_data:
                logger.error("The data %s is missing in the input dict", std_name_metadata)
                raise KeyError(f"The data '{std_name_metadata}' is missing in the input dict")

        # check if optional input is present
        if item["type"] == ParameterType.optional:
            std_name_metadata = item["std_name"]
            if std_name_metadata not in input_data:
                logger.info(
                    "The optional data %s is missing in the input dict. Default value will be used.",
                    std_name_metadata,
                )


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
        if item["type"] == ParameterType.output:
            continue
        std_name_metadata = item["std_name"]
        if std_name_metadata in input_data.keys():
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
        if item["type"] == ParameterType.output:
            continue
        std_name_metadata = item["std_name"]
        if std_name_metadata in input_data.keys():
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


def extract_magnitudes(input_dict):
    """
    Extract magnitudes from a dictionary of quantities.

    Parameters
    ----------
    input_dict : dict
        A dictionary where each value is expected to have a 'magnitude' attribute (from pint.Quantity).

    Returns
    -------
    dict
        A new dictionary with the same keys as `input_dict`, where each value is the
        'magnitude' attribute of the corresponding value in `input_dict`.

    Notes
    -----
    If accessing 'value.magnitude' raises an exception, a warning is logged, and the key is kept identical.
    """  # pylint: disable=line-too-long
    final_input = {}
    for key, value in input_dict.items():
        try:
            final_input[key] = value.magnitude
        except (AttributeError, TypeError, ValueError) as e:
            logger.warning("Failed to get magnitude for key '%s': %s", key, e)
            final_input[key] = value
    return final_input


def check_data_quality_ros_model(input_dict: dict[str, Quantity], ros_model: RateOfSpreadModel) -> dict:
    """
    Check and process the input data quality for a Rate of Spread (ROS) model.

    This function performs the following checks and conversions on the input data:
    - Completeness: Ensures all necessary inputs for the ROS model are present in the input dictionary.
    - Unit Conversion: Converts units of input data to match the units specified in the ROS model's metadata.
    - Validity Range: Verifies that the input data values are within the valid ranges specified by the model's metadata.

    Parameters
    ----------
    input_dict : dict
        Dictionary containing the input data for the ROS model. The keys are the standard names of the variables,
        and the values are quantities with units.
    ros_model : RateOfSpreadModel
        An instance of a subclass of `RateOfSpreadModel` that provides the metadata for the ROS model.

    Returns
    -------
    dict
        A new dictionary with the input data checked for completeness, units converted, and values verified to be within valid ranges.
        The values are converted to their magnitude (unitless).
    """  # pylint: disable=line-too-long

    # Completeness check
    check_input_completeness(input_dict, ros_model.metadata)

    # Unit conversion
    input_converted = convert_input_data_units(input_dict, ros_model.metadata)

    # Validity range check
    check_validity_range(input_converted, ros_model.metadata)

    # Create final input dictionary with magnitudes
    final_input = extract_magnitudes(input_converted)

    return final_input
