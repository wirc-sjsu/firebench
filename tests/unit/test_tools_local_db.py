import os
import firebench.tools as ft
import pytest

from firebench.tools.local_db_management import __create_record_directory


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
    record_path = "fake_record_path"

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=False)
    mock_makedirs = mocker.patch("os.makedirs")

    # Test directory creation when it does not exist
    __create_record_directory(record_path)
    mock_makedirs.assert_called_once_with(record_path)

def test_create_record_directory_overwrite(mocker):
    record_path = "fake_record_path"

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=True)
    mock_rmtree = mocker.patch("shutil.rmtree")
    mock_makedirs = mocker.patch("os.makedirs")

    # Test directory creation with overwrite
    __create_record_directory(record_path, overwrite=True)
    mock_rmtree.assert_called_once_with(record_path)
    mock_makedirs.assert_called_once_with(record_path)

def test_create_record_directory_exists_no_overwrite(mocker):
    record_path = "fake_record_path"

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=True)

    # Test directory creation without overwrite, expecting an OSError
    with pytest.raises(OSError, match=f"Workflow record {record_path} already exists and cannot be overwritten"):
        __create_record_directory(record_path)

# Run the tests
if __name__ == "__main__":
    pytest.main()
