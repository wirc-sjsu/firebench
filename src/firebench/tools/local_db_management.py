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


def copy_file_to_workflow_record(workflow_record_name: str, file_path: str):
    """
    Copy a file to the specified workflow record directory.

    Parameters
    ----------
    workflow_record_name : str
        The name of the workflow record directory where the file will be copied.
    file_path : str
        The path to the file that needs to be copied.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    OSError
        If the workflow record directory does not exist.
    """
    # Get record path
    record_path = os.path.join(get_local_db_path(), workflow_record_name)

    # Check if the file file exists
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    # Check if the workflow record directory exists
    if not os.path.isdir(record_path):
        raise OSError(f"The workflow record directory '{record_path}' does not exist.")

    # Copy file to workflow record directory
    shutil.copy2(file_path, record_path)

def create_record_directory(workflow_record_name: str, overwrite: bool = False):
    """
    Create a workflow record directory.

    This function creates a new directory for storing workflow records. If the directory already exists,
    it will either overwrite it (if `overwrite` is True) or raise an error (if `overwrite` is False).

    Parameters
    ----------
    workflow_record_name : str
        The name of the directory to be created.
    overwrite : bool, optional
        Whether to overwrite the directory if it already exists. Defaults to False.

    Raises
    ------
    OSError
        If the directory already exists and `overwrite` is False.
    """
    # Get record path
    record_path = os.path.join(get_local_db_path(), workflow_record_name)

    # Check if the record path already exists
    if os.path.exists(record_path):
        if overwrite:
            shutil.rmtree(record_path)
            logger.info(f"Workflow record {record_path} has been overwritten")
        else:
            raise OSError(f"Workflow record {record_path} already exists and cannot be overwritten")

    # Create the new record directory
    os.makedirs(record_path)





def save_workflow_record(workflow_record_name: str, workflow_data: dict, script_path: str, overwrite_record:bool=False):
    """
    Save the workflow in a directory called workflow record.
    The data is saved in a json file.
    A copy of the workflow script is saved in the record
    """
    

    # create the record directory
    __create_record_directory(record_path, overwrite=overwrite_record)

    # copy script file to workflow record directory
    shutil.copy2(script_path, record_path)

    # save workflow data in json file
