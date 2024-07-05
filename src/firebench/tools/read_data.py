import importlib.resources
import json
import os
from os import path

import numpy as np

from .namespace import StandardVariableNames as svn
from .units import ureg
from .logging_config import logger


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
    json_file_path = __get_json_data_file(fuel_model_name, local_path_json_fuel_db)
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
            logger.warning("ignore the input value: %s", value["variable_name"])
        else:
            output_data[std_var] = ureg.Quantity(
                np.array(data_dict[key], dtype=np.float64), ureg(value["unit"])
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


def __get_json_data_file(fuel_model_name: str, local_path_json_fuel_db: str = None) -> str:
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
        json_file_path = importlib.resources.files("firebench").parent.parent.joinpath(
            "data", "fuel_models", json_filename
        )
        defaultexists = os.path.exists(json_file_path)

        if not defaultexists:
            raise FileNotFoundError(f"File {json_file_path} not found in the package data path.")
    else:
        # Use specified local path to data
        json_file_path = os.path.join(local_path_json_fuel_db, json_filename)
        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(f"File {json_filename} not found in the local path: {json_file_path}")

    return json_file_path
