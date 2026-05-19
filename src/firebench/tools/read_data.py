import json
import os
from os import path
from pathlib import Path
import warnings

import numpy as np

from .logging_config import logger
from .namespace import StandardVariableNames as svn
from .units import ureg


def read_fuel_data_file(
    fuel_model_name: str,
    local_path_json_fuel_db: str = None,
    data_path: str | os.PathLike | None = None,
):
    """
    Reads a CSV fuel data file and its corresponding metadata JSON file to produce a dictionary
    of data with Pint quantities.

    Parameters
    ----------
    fuel_model_name : str
        The name of the fuel model.
    local_path_json_fuel_db : str, optional
        The local path to the JSON fuel database. If not provided, the function will use the default package path.
    data_path : str or os.PathLike, optional
        Explicit path to the Firebench data directory.


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
    # fuel models are in data/fuel_models/example_fuel_model.json
    fuel_models_path_within_firebench = "fuel_models"

    return read_data_file(
        fuel_model_name,
        fuel_models_path_within_firebench,
        local_path_json_fuel_db,
        data_path=data_path,
    )


def read_data_file(
    dataset_name: str,
    path_within_firebench: str,
    local_json_path: str = None,
    data_path: str | os.PathLike | None = None,
):
    """
    Reads a CSV data file and its corresponding metadata JSON file to produce a dictionary
    of data with Pint quantities.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to retrieve.
    path_within_firebench : str
        Path leading to the data within firebench from the data directory.
    local_json_path : str, optional
        The local path to the JSON fuel database. If not provided, the function will use the default package path.
    data_path : str or os.PathLike, optional
        Explicit path to the Firebench data directory.


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
    json_file_path = _get_json_data_file_path(
        dataset_name, path_within_firebench, local_json_path, data_path=data_path
    )
    with open(json_file_path, "r") as f:
        metadata = json.load(f)

    # Read CSV data
    with open(
        path.join(path.dirname(json_file_path), metadata["data_path"]), "r"
    ) as file:
        content = file.readlines()

    # get no data value
    if "no_data_value" in metadata.keys():
        no_data_value = metadata["no_data_value"]
    else:
        no_data_value = np.nan

    # Process header to get field names
    fields = content[0].strip().split(",")
    data_dict = {field: [] for field in fields}

    # Process data lines
    for line in content[1:]:
        values = line.strip().split(",")
        for field, value in zip(fields, values):
            if value == no_data_value:
                data_dict[field].append(np.nan)
            else:
                data_dict[field].append(value)

    # Convert data to numpy arrays and apply units
    output_data = {}
    for key, value in metadata["metadata"].items():
        try:
            std_var = svn(value["variable_name"])
        except ValueError:
            logger.warning(
                "input value %s not found in SVN. Data imported without unit",
                value["variable_name"],
            )
            output_data[value["variable_name"]] = np.array(
                data_dict[key], dtype=value["type"]
            )
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


def _get_json_data_file_path(
    dataset_name: str,
    path_within_firebench: str,
    local_json_path: str = None,
    data_path: str | os.PathLike | None = None,
) -> str:
    """
    Get the path to the JSON metadata file. The function first checks the local path, if provided.
    If the file is not found locally, it checks the default package data path.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to retrieve.
    path_within_firebench : str
        Path leading to the data within firebench from the data directory.
    local_json_path : str, optional
        The local path to the JSON dataset. If not provided, the function will use the default package path.
    data_path : str or os.PathLike, optional
        Explicit path to the Firebench data directory.

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
    json_filename = __add_suffix(dataset_name, "json")

    if local_json_path is None:
        # Use default path to data
        firebench_data_path = get_firebench_data_directory(data_path)
        json_file_path = os.path.join(
            firebench_data_path, path_within_firebench, json_filename
        )
        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(
                f"File {json_file_path} not found in the package data path."
            )
    else:
        # Use specified local path to data
        json_file_path = os.path.join(local_json_path, json_filename)
        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(
                f"File {json_filename} not found in the local path: {json_file_path}"
            )

    return json_file_path


def _default_firebench_data_directory() -> Path:
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parents[3] / "data",
        current_file.parents[2] / "data",
        current_file.parents[1] / "data",
        Path.cwd() / "data",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def get_firebench_data_directory(data_path: str | os.PathLike | None = None):
    """
    Retrieve the absolute path of the firebench data directory.

    If ``data_path`` is not provided, this function uses the bundled repository
    ``data`` directory. The legacy FIREBENCH_DATA_PATH environment variable is
    still supported temporarily for backward compatibility.

    Returns
    -------
    str
        The absolute path of the firebench data directory.

    Parameters
    ----------
    data_path : str or os.PathLike, optional
        Explicit path to the Firebench data directory.
    """
    if data_path is not None:
        return os.path.abspath(os.fspath(data_path))

    firebench_data_path = os.getenv("FIREBENCH_DATA_PATH")
    if firebench_data_path:
        warnings.warn(
            "FIREBENCH_DATA_PATH is deprecated and will be removed in a future release. "
            "Use the Firebench data configuration or pass data_path explicitly instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return os.path.abspath(firebench_data_path)

    return os.path.abspath(_default_firebench_data_directory())
