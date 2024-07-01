import os
import shutil

from .logging_config import logger


def get_local_db_path():
    """
    Retrieve the local database path from the environment variable FIREBENCH_LOCAL_DB.

    This function checks for the presence of the environment variable FIREBENCH_LOCAL_DB, which should contain
    the path to the local FireBench database. If the environment variable is not set, an exception is raised with
    a message instructing the user to set the variable.

    Returns
    -------
    str
        The path to the local FireBench database.

    Raises
    ------
    EnvironmentError
        If the FIREBENCH_LOCAL_DB environment variable is not set.
    """  # pylint: disable=line-too-long
    local_db_path = os.getenv("FIREBENCH_LOCAL_DB")
    if not local_db_path:
        raise EnvironmentError(
            "Firebench local database path is not set. Define the path using 'export FIREBENCH_LOCAL_DB=/path/to/your/firebench/local/db'"
        )
    return local_db_path


def __create_record_directory(record_path: str, overwrite: bool = False):
    """
    Create a workflow record directory.

    This function creates a new directory for storing workflow records. If the directory already exists,
    it will either overwrite it (if `overwrite` is True) or raise an error (if `overwrite` is False).

    Parameters
    ----------
    record_path : str
        The path of the directory to be created.
    overwrite : bool, optional
        Whether to overwrite the directory if it already exists. Defaults to False.

    Raises
    ------
    OSError
        If the directory already exists and `overwrite` is False.
    """
    # Check if the record path already exists
    if os.path.exists(record_path):
        if overwrite:
            shutil.rmtree(record_path)
        else:
            raise OSError(f"Workflow record {record_path} already exists and cannot be overwritten")

    # Create the new record directory
    os.makedirs(record_path)


