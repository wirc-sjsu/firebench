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

    # Check if the file exists
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    # Check if the workflow record directory exists
    if not os.path.isdir(record_path):
        raise OSError(f"The workflow record directory '{record_path}' does not exist.")

    # Check if destination file already exists
    destination_file_path = os.path.join(record_path, os.path.basename(file_path))
    if os.path.isfile(destination_file_path) and not overwrite:
        raise OSError(
            f"The file '{destination_file_path}' already exists and overwrite option is set to False"
        )

    # Copy file to workflow record directory
    shutil.copy2(file_path, record_path)
    logger.info("file %s copied to %s", file_path, record_path)


def create_record_directory(workflow_record_name: str):
    """
    Create a workflow record directory.

    This function creates a new directory for storing workflow records. If the directory already exists,
    it will not raise an error and will simply return.

    Parameters
    ----------
    workflow_record_name : str
        The name of the directory to be created.
    """
    # Get record path
    record_path = os.path.join(get_local_db_path(), workflow_record_name)

    # Create the new record directory
    os.makedirs(record_path, exist_ok=True)
