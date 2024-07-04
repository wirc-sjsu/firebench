import io
import os
import shutil
import tempfile

import firebench.tools as ft
import pytest
from firebench.tools.local_db_management import (
    _check_source_file_exists,
    _check_workflow_record_exists,
    _handle_existing_destination_file,
)


def test_get_local_db_path(mocker):
    # Test when the environment variable is set
    mocker.patch.dict(os.environ, {"FIREBENCH_LOCAL_DB": "/path/to/your/firebench/local/db"})
    assert ft.get_local_db_path() == "/path/to/your/firebench/local/db"

    # Test when the environment variable is not set
    mocker.patch.dict(os.environ, {}, clear=True)
    with pytest.raises(Exception) as excinfo:
        ft.get_local_db_path()
    assert "Firebench local database path is not set." in str(excinfo.value)


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


def test_check_source_file_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        existing_file_path = os.path.join(temp_dir, "existing_file.txt")
        non_existing_file_path = os.path.join(temp_dir, "non_existing_file.txt")

        # Create a dummy file to test the existing file case
        with open(existing_file_path, "w") as f:
            f.write("test content")

        # Test when the file exists
        try:
            _check_source_file_exists(existing_file_path)
        except FileNotFoundError:
            pytest.fail("FileNotFoundError raised unexpectedly for an existing file.")

        # Test when the file does not exist
        with pytest.raises(FileNotFoundError) as exc_info:
            _check_source_file_exists(non_existing_file_path)

        assert str(exc_info.value) == f"The file '{non_existing_file_path}' does not exist."


def test_check_workflow_record_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        existing_record_path = os.path.join(temp_dir, "existing_record")
        non_existing_record_path = os.path.join(temp_dir, "non_existing_record")

        # Create a dummy directory to test the existing record case
        os.makedirs(existing_record_path)

        # Test when the directory exists
        try:
            _check_workflow_record_exists(existing_record_path)
        except OSError:
            pytest.fail("OSError raised unexpectedly for an existing directory.")

        # Test when the directory does not exist
        with pytest.raises(OSError) as exc_info:
            _check_workflow_record_exists(non_existing_record_path)

        assert (
            str(exc_info.value)
            == f"The workflow record directory '{non_existing_record_path}' does not exist."
        )


def test_handle_existing_destination_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        existing_file_path = os.path.join(temp_dir, "existing_file.txt")
        non_existing_file_path = os.path.join(temp_dir, "non_existing_file.txt")

        # Create a dummy file to test the existing file case
        with open(existing_file_path, "w") as f:
            f.write("test content")

        # Test when the file exists and overwrite is True
        try:
            _handle_existing_destination_file(existing_file_path, overwrite=True)
            assert not os.path.isfile(existing_file_path), "File should be removed when overwrite is True."
        except OSError:
            pytest.fail("OSError raised unexpectedly when overwrite is True.")

        # Recreate the dummy file for the next test
        with open(existing_file_path, "w") as f:
            f.write("test content")

        # Test when the file exists and overwrite is False
        with pytest.raises(OSError) as exc_info:
            _handle_existing_destination_file(existing_file_path, overwrite=False)
        assert (
            str(exc_info.value)
            == f"The file '{existing_file_path}' already exists and overwrite option is set to False"
        )

        # Test when the file does not exist
        try:
            _handle_existing_destination_file(non_existing_file_path, overwrite=False)
        except OSError:
            pytest.fail("OSError raised unexpectedly for a non-existing file.")

        # Ensure the non-existing file is still non-existent
        assert not os.path.isfile(non_existing_file_path), "Non-existing file should remain non-existent."


def test_same_source_and_destination(mocker):
    workflow_record_name = "dummy_workflow"
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create the workflow record directory
        ft.create_record_directory(workflow_record_name)

        file_path = os.path.join(temp_dir, workflow_record_name, "same_file.txt")

        # Create a dummy file
        with open(file_path, "w") as f:
            f.write("test content")

        # Test when the source and destination are the same
        try:
            ft.copy_file_to_workflow_record(workflow_record_name, file_path, overwrite=True)
        except Exception:
            pytest.fail("Exception raised unexpectedly when source and destination are the same.")

        # Check if the file still exists
        assert os.path.isfile(
            file_path
        ), "File should still exist when source and destination are the same."


# Run the tests
if __name__ == "__main__":
    pytest.main()
