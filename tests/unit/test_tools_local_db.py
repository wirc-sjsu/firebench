import os
import shutil

import firebench.tools as ft
import pytest
import tempfile


def test_get_local_db_path(mocker):
    # Test when the environment variable is set
    mocker.patch.dict(os.environ, {"FIREBENCH_LOCAL_DB": "/path/to/your/firebench/local/db"})
    assert ft.get_local_db_path() == "/path/to/your/firebench/local/db"

    # Test when the environment variable is not set
    mocker.patch.dict(os.environ, {}, clear=True)
    with pytest.raises(Exception) as excinfo:
        ft.get_local_db_path()
    assert "Firebench local database path is not set." in str(excinfo.value)


def test_create_record_directory(mocker):
    workflow_record_name = "test_workflow"

    # Mocking get_local_db_path to return a fake path
    mocker.patch("os.path.join", return_value="/fake/local/db/path/test_workflow")
    mocker.patch("os.makedirs")

    # Test directory creation
    ft.create_record_directory(workflow_record_name)
    os.makedirs.assert_called_once_with("/fake/local/db/path/test_workflow", exist_ok=True)


def test_copy_file_to_workflow_record_success(mocker):
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow_record_name = "test_workflow"
        file_name = "file.txt"
        file_path = os.path.join(temp_dir, file_name)
        record_path = os.path.join(temp_dir, workflow_record_name)

        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create a dummy file to copy
        with open(file_path, "w") as f:
            f.write("test content")

        # Create the workflow record directory
        os.makedirs(record_path)

        # Test successful copy
        ft.copy_file_to_workflow_record(workflow_record_name, file_path)

        # Check if the file is copied
        assert os.path.isfile(os.path.join(record_path, file_name))


def test_copy_file_to_workflow_record_file_not_found(mocker):
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow_record_name = "test_workflow"
        file_path = os.path.join(temp_dir, "non_existent_file.txt")

        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create the workflow record directory
        record_path = os.path.join(temp_dir, workflow_record_name)
        os.makedirs(record_path)

        # Test file not found error
        with pytest.raises(FileNotFoundError):
            ft.copy_file_to_workflow_record(workflow_record_name, file_path)


def test_copy_file_to_workflow_record_directory_not_found(mocker):
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow_record_name = "test_workflow"
        file_name = "file.txt"
        file_path = os.path.join(temp_dir, file_name)

        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create a dummy file to copy
        with open(file_path, "w") as f:
            f.write("test content")

        # Do not create the workflow record directory

        # Test workflow record directory not found error
        with pytest.raises(OSError):
            ft.copy_file_to_workflow_record(workflow_record_name, file_path)


def test_copy_file_to_workflow_record_file_exists_no_overwrite(mocker):
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow_record_name = "test_workflow"
        file_name = "file.txt"
        file_path = os.path.join(temp_dir, file_name)
        record_path = os.path.join(temp_dir, workflow_record_name)

        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create a dummy file to copy
        with open(file_path, "w") as f:
            f.write("test content")

        # Create the workflow record directory and the destination file
        os.makedirs(record_path)
        shutil.copy2(file_path, record_path)

        # Test file already exists and overwrite is False
        with pytest.raises(OSError):
            ft.copy_file_to_workflow_record(workflow_record_name, file_path)


# Run the tests
if __name__ == "__main__":
    pytest.main()
