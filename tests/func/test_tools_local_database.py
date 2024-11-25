import os
import tempfile

import firebench.tools as ft
import pytest


def test_create_record_directory(mocker):
    workflow_record_name = "test_workflow"

    with tempfile.TemporaryDirectory() as temp_dir:
        # Mocking environment variable for local db path
        mocker.patch("os.getenv", return_value=temp_dir)

        # Test directory creation
        ft.create_record_directory(workflow_record_name)

        # Verify the directory was created
        expected_path = os.path.join(temp_dir, workflow_record_name)
        assert os.path.isdir(expected_path)


# Run the tests
if __name__ == "__main__":
    pytest.main()
