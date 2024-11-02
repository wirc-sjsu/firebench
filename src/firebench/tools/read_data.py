import json
import os
from os import path

import numpy as np

from .logging_config import logger
from .namespace import StandardVariableNames as svn
from .units import ureg


def read_fuel_data_file(fuel_model_name: str, local_path_json_fuel_db: str = None):
    """
    Reads a CSV fuel data file and its corresponding metadata JSON file to produce a dictionary
    of data with Pint quantities.

    Parameters
    ----------
    fuel_model_name : str
        The name of the fuel model.
    local_path_json_fuel_db : str, optional
        The local path to the JSON fuel database. If not provided, the function will use the default package path.


    Returns
    -------
    dict
        A dictionary where the keys are standard variable names (Enum members) and the
        values are numpy arrays with Pint quantities.

    Raises
    ------
    ValueError
        If there is an issue with the variable name in the metadata.
    """  # pylint: disable=line-too-long
    # Load metadata
    json_file_path = _get_fuel_model_json_data_file_path(fuel_model_name, local_path_json_fuel_db)
    with open(json_file_path, "r") as f:
        metadata = json.load(f)

    # Read CSV data
    with open(path.join(path.dirname(json_file_path), metadata["data_path"]), "r") as file:
        content = file.readlines()

    # Process header to get field names
    fields = content[0].strip().split(",")
    data_dict = {field: [] for field in fields}

    # Process data lines
    for line in content[1:]:
        values = line.strip().split(",")
        for field, value in zip(fields, values):
            data_dict[field].append(value)

    # Convert data to numpy arrays and apply units
    output_data = {}
    for key, value in metadata["metadata"].items():
        try:
            std_var = svn(value["variable_name"])
        except ValueError:
            logger.warning(
                "input value %s not found in SVN. Data imported without unit", value["variable_name"]
            )
            output_data[value["variable_name"]] = np.array(data_dict[key], dtype=value["type"])
        else:
            output_data[std_var] = ureg.Quantity(
                np.array(data_dict[key], dtype=value["type"]), ureg(value["unit"])
            )

    # store number of fuel classes
    output_data["nb_fuel_classes"] = len(content[1:])

    return output_data


def __add_suffix(filename: str, suffix: str) -> str:
    """
    Add a suffix to the filename if it does not already have it.

    Parameters
    ----------
    filename : str
        The name of the file.
    suffix : str
        The suffix to add.

    Returns
    -------
    str
        The filename with the suffix.
    """  # pylint: disable=line-too-long
    if not filename.endswith(f".{suffix}"):
        filename += f".{suffix}"
    return filename


def _get_fuel_model_json_data_file_path(fuel_model_name: str, local_path_json_fuel_db: str = None) -> str:
    """
    Get the path to the JSON metadata file. The function first checks the local path, if provided.
    If the file is not found locally, it checks the default package data path.

    Parameters
    ----------
    fuel_model_name : str
        The name of the fuel model.
    local_path_json_fuel_db : str, optional
        The local path to the JSON fuel database. If not provided, the function will use the default package path.

    Returns
    -------
    str
        The path to the JSON data file.

    Raises
    ------
    FileNotFoundError
        If the JSON file is not found in the local or default paths.
    """  # pylint: disable=line-too-long
    # Add json suffix if needed
    json_filename = __add_suffix(fuel_model_name, "json")

    if local_path_json_fuel_db is None:
        # Use default path to data
        firebench_data_path = get_firebench_data_directory()
        json_file_path = os.path.join(firebench_data_path, "fuel_models", json_filename)
        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(f"File {json_file_path} not found in the package data path.")
    else:
        # Use specified local path to data
        json_file_path = os.path.join(local_path_json_fuel_db, json_filename)
        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(f"File {json_filename} not found in the local path: {json_file_path}")

    return json_file_path


def get_firebench_data_directory():
    """
    Retrieve the absolute path of the firebench data directory.

    This function checks for the environment variable 'FIREBENCH_DATA_PATH'
    to retrieve the path of the firebench data directory. If the environment
    variable is not set, it raises an EnvironmentError with a message indicating
    the need to define the path.

    Returns
    -------
    str
        The absolute path of the firebench data directory.

    Raises
    ------
    EnvironmentError
        If the 'FIREBENCH_DATA_PATH' environment variable is not set.
    """
    firebench_data_path = os.getenv("FIREBENCH_DATA_PATH")
    if not firebench_data_path:
        raise EnvironmentError(
            "Firebench data directory path is not set. Define the path using "
            "'export FIREBENCH_DATA_PATH=/path/to/your/firebench/data'"
        )
    return os.path.abspath(firebench_data_path)
