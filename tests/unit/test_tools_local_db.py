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
    update_markdown_with_hashes,
    update_date_in_markdown,
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


def test_generate_file_path_in_record(mocker):
    new_file_name = "new_file.txt"
    record_name = "test_record"

    with tempfile.TemporaryDirectory() as temp_dir:
        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Create the workflow record directory
        record_path = os.path.join(temp_dir, record_name)
        os.makedirs(record_path)

        # Test creating a new file path
        new_file_path = ft.generate_file_path_in_record(new_file_name, record_name)
        assert new_file_path == os.path.join(record_path, new_file_name)

        # Create a dummy file
        with open(new_file_path, "w") as f:
            f.write("test content")

        # Test when the file already exists and overwrite is False
        with pytest.raises(
            OSError, match=f"file {new_file_path} already exists and overwrite option is set to False"
        ):
            ft.generate_file_path_in_record(new_file_name, record_name, overwrite=False)

        # Test when the file already exists and overwrite is True
        new_file_path_overwrite = ft.generate_file_path_in_record(
            new_file_name, record_name, overwrite=True
        )
        assert new_file_path_overwrite == new_file_path


def test_get_file_path_in_record():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set the environment variable for the local db path
        os.environ["FIREBENCH_LOCAL_DB"] = temp_dir

        # Create a dummy workflow record directory
        record_name = "test_workflow"
        record_path = os.path.join(temp_dir, record_name)
        os.makedirs(record_path)

        # Create a dummy file in the workflow record directory
        file_name = "test_file.txt"
        file_path = os.path.join(record_path, file_name)
        with open(file_path, "w") as f:
            f.write("test content")

        # Test successful retrieval of file path
        result_path = ft.get_file_path_in_record(file_name, record_name)
        assert result_path == file_path

        # Test file not found
        with pytest.raises(OSError, match="does not exist"):
            ft.get_file_path_in_record("non_existent_file.txt", record_name)


def test_update_markdown_with_hashes():
    """
    Test that the function correctly updates the 'firebench-hash-list' section in a markdown file.
    """
    # Initial markdown content with a placeholder section
    initial_content = """# Sample Markdown File

This is a sample markdown file for testing.

<!-- firebench-hash-list -->
<!-- end of firebench-hash-list -->

Some other content.

"""

    # Expected content after updating
    hash_dict = {
        "file1.txt": "hash1",
        "file2.txt": "hash2",
        "file3.txt": "hash3",
    }

    expected_hash_list = "\n".join(
        [f"- **{filename}**: `{hash_value}`" for filename, hash_value in hash_dict.items()]
    )
    expected_section = (
        f"<!-- firebench-hash-list -->\n{expected_hash_list}\n<!-- end of firebench-hash-list -->"
    )

    expected_content = initial_content.replace(
        "<!-- firebench-hash-list -->\n<!-- end of firebench-hash-list -->",
        expected_section,
    )

    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".md") as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(initial_content)
        temp_file.flush()  # Ensure content is written

    try:
        # Call the function to update the markdown file
        update_markdown_with_hashes(temp_file_path, hash_dict)

        # Read the updated content
        with open(temp_file_path, "r") as file:
            updated_content = file.read()

        # Assert that the updated content matches the expected content
        assert updated_content == expected_content, "The markdown file was not updated as expected."

    finally:
        # Clean up the temporary file
        os.remove(temp_file_path)


def test_update_date_in_markdown():
    """
    Test that the function correctly updates the 'Date of record creation' line in a markdown file.
    """
    # Initial markdown content with a placeholder date
    initial_content = """# Sample Markdown File

This is a sample markdown file for testing.

- Date of record creation: old_date

Some other content.

"""

    # The date string to be updated
    new_date = "2023-10-01"

    # Expected content after updating
    expected_content = initial_content.replace(
        "- Date of record creation: old_date", f"- Date of record creation: {new_date}"
    )

    # Create a temporary markdown file
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".md") as temp_file:
        temp_file_path = temp_file.name
        temp_file.write(initial_content)
        temp_file.flush()  # Ensure content is written

    try:
        # Call the function to update the date in the markdown file
        update_date_in_markdown(temp_file_path, new_date)

        # Read the updated content
        with open(temp_file_path, "r") as file:
            updated_content = file.read()

        # Assert that the updated content matches the expected content
        assert (
            updated_content == expected_content
        ), "The date in the markdown file was not updated as expected."

    finally:
        # Clean up the temporary file
        os.remove(temp_file_path)


# Run the tests
if __name__ == "__main__":
    pytest.main()
