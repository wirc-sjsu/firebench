import logging
import os
import shutil

from .logging_config import create_file_handler, logger


def _check_source_file_exists(file_path: str):
    """
    Check if the source file exists.

    Parameters
    ----------
    file_path : str
        The path to the source file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """  # pylint: disable=line-too-long
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")


def _check_workflow_record_exists(record_path: str):
    """
    Check if the workflow record directory exists.

    Parameters
    ----------
    record_path : str
        The path to the workflow record directory.

    Raises
    ------
    OSError
        If the workflow record directory does not exist.
    """  # pylint: disable=line-too-long
    if not os.path.isdir(record_path):
        raise OSError(f"The workflow record directory '{record_path}' does not exist.")


def _handle_existing_destination_file(destination_file_path: str, overwrite: bool):
    """
    Handle the case where the destination file already exists.

    Parameters
    ----------
    destination_file_path : str
        The path to the destination file.
    overwrite : bool
        Whether to overwrite the file if it already exists.

    Raises
    ------
    OSError
        If the file already exists and overwrite is False.
    """  # pylint: disable=line-too-long
    if os.path.isfile(destination_file_path):
        if overwrite:
            os.remove(destination_file_path)
        else:
            raise OSError(
                f"The file '{destination_file_path}' already exists and overwrite option is set to False"
            )


def copy_file_to_workflow_record(workflow_record_name: str, file_path: str, overwrite: bool = False):
    """
    Copy a file to the specified workflow record directory.

    Parameters
    ----------
    workflow_record_name : str
        The name of the workflow record directory where the file will be copied.
    file_path : str
        The path to the file that needs to be copied.
    overwrite : bool, optional
        Whether to overwrite the file if it already exists in the destination directory. Defaults to False.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    OSError
        If the workflow record directory does not exist or if the file already exists and overwrite is False.
    """  # pylint: disable=line-too-long
    # Get record path
    record_path = os.path.join(get_local_db_path(), workflow_record_name)
    destination_file_path = os.path.join(record_path, os.path.basename(file_path))

    # If the file is already within the record directory
    if file_path == destination_file_path:
        logger.debug("source and destination are the same")
        return

    # Check if the source file exists
    _check_source_file_exists(file_path)

    # Check if the workflow record directory exists
    _check_workflow_record_exists(record_path)

    # Handle existing destination file
    _handle_existing_destination_file(destination_file_path, overwrite)

    # Copy file to workflow record directory
    shutil.copy2(file_path, destination_file_path)
    logger.debug("file %s copied to %s", file_path, destination_file_path)


def create_record_directory(workflow_record_name: str):
    """
    Create a workflow record directory.

    This function creates a new directory for storing workflow records. If the directory already exists,
    it will not raise an error and will simply return.
    Additionally, it creates a log file named 'firebench.log' in the created directory.

    Parameters
    ----------
    workflow_record_name : str
        The name of the directory to be created.
    """  # pylint: disable=line-too-long
    # Get record path
    record_path = os.path.join(get_local_db_path(), workflow_record_name)

    # Create the new record directory
    os.makedirs(record_path, exist_ok=True)

    # Create log file
    create_file_handler(os.path.join(record_path, "firebench.log"))


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
