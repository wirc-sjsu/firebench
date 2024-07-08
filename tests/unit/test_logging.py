import os

import firebench.tools as ft
import pytest
import tempfile
from firebench.tools.logging_config import create_file_handler


def test_create_file_handler():
    with tempfile.TemporaryDirectory() as temp_dir:
        log_path = os.path.join(temp_dir, "test_log.log")

        # Ensure the log file does not exist initially
        assert not os.path.isfile(log_path)

        # Create the file handler
        create_file_handler(log_path)

        # Verify the log file was created
        assert os.path.isfile(log_path)

        # Verify the log file handler was added to the logger
        handler_found = False
        for handler in ft.logger.handlers:
            if isinstance(handler, ft.logging.FileHandler) and handler.baseFilename == log_path:
                handler_found = True
                break
        assert handler_found

        # Verify the log file is empty
        with open(log_path, "r") as log_file:
            assert log_file.read() == ""

        # Test logging to the file
        ft.logger.warning("Test warning message")

        # Verify the log message was written to the log file
        with open(log_path, "r") as log_file:
            log_content = log_file.read()
            assert "Test warning message" in log_content

        # Test the function's behavior when the log file already exists
        create_file_handler(log_path)

        # Verify the log file is empty after being recreated
        with open(log_path, "r") as log_file:
            assert log_file.read() == ""


# Run the tests
if __name__ == "__main__":
    pytest.main()
