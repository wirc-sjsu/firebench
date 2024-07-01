import os
import firebench.tools as ft
import pytest

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
    record_path = os.path.join("fake_local_db_path", workflow_record_name)

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=False)
    mock_makedirs = mocker.patch("os.makedirs")
    mocker.patch("firebench.tools.local_db_management.get_local_db_path", return_value="fake_local_db_path")

    # Test directory creation when it does not exist
    ft.create_record_directory(workflow_record_name)
    mock_makedirs.assert_called_once_with(record_path)

def test_create_record_directory_overwrite(mocker):
    workflow_record_name = "test_workflow"
    record_path = os.path.join("fake_local_db_path", workflow_record_name)

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=True)
    mock_rmtree = mocker.patch("shutil.rmtree")
    mock_makedirs = mocker.patch("os.makedirs")
    mock_logger = mocker.patch("firebench.tools.local_db_management.logger.info")
    mocker.patch("firebench.tools.local_db_management.get_local_db_path", return_value="fake_local_db_path")

    # Test directory creation with overwrite
    ft.create_record_directory(workflow_record_name, overwrite=True)
    mock_rmtree.assert_called_once_with(record_path)
    mock_makedirs.assert_called_once_with(record_path)
    mock_logger.assert_called_once_with(f"Workflow record {record_path} has been overwritten")

def test_create_record_directory_exists_no_overwrite(mocker):
    workflow_record_name = "test_workflow"
    record_path = os.path.join("fake_local_db_path", workflow_record_name)

    # Mocking os.path.exists to simulate directory existence
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("firebench.tools.local_db_management.get_local_db_path", return_value="fake_local_db_path")

    # Test directory creation without overwrite, expecting an OSError
    with pytest.raises(OSError, match=f"Workflow record {record_path} already exists and cannot be overwritten"):
        ft.create_record_directory(workflow_record_name)
# Run the tests
if __name__ == "__main__":
    pytest.main()
