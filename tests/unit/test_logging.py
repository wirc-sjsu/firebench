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


@pytest.mark.parametrize(
    "level, expected_levels",
    [
        (ft.logging.DEBUG, ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        (ft.logging.INFO, ["INFO", "WARNING", "ERROR", "CRITICAL"]),
        (ft.logging.WARNING, ["WARNING", "ERROR", "CRITICAL"]),
        (ft.logging.ERROR, ["ERROR", "CRITICAL"]),
        (ft.logging.CRITICAL, ["CRITICAL"]),
    ],
)
def test_set_logging_level(caplog, level, expected_levels):
    """
    Test that set_logging_level sets the logger and handler levels correctly,
    and that only messages at or above the set level are captured.
    """
    # Set the logging level using the function under test
    ft.set_logging_level(level)

    # Clear any existing records in caplog
    caplog.clear()

    # Define log messages at all levels
    log_messages = {
        "DEBUG": "This is a DEBUG message",
        "INFO": "This is an INFO message",
        "WARNING": "This is a WARNING message",
        "ERROR": "This is an ERROR message",
        "CRITICAL": "This is a CRITICAL message",
    }

    # Emit log messages at all levels
    ft.logger.debug(log_messages["DEBUG"])
    ft.logger.info(log_messages["INFO"])
    ft.logger.warning(log_messages["WARNING"])
    ft.logger.error(log_messages["ERROR"])
    ft.logger.critical(log_messages["CRITICAL"])

    # Collect the levels of the captured log records
    captured_levels = [record.levelname for record in caplog.records]

    # Collect the messages of the captured log records
    captured_messages = [record.message for record in caplog.records]

    # Check that only the expected levels are captured
    assert (
        captured_levels == expected_levels
    ), f"Expected levels {expected_levels}, but got {captured_levels}"

    # Optional: Check that the messages correspond to the expected levels
    expected_messages = [log_messages[level_name] for level_name in expected_levels]
    assert (
        captured_messages == expected_messages
    ), f"Expected messages {expected_messages}, but got {captured_messages}"


# Run the tests
if __name__ == "__main__":
    pytest.main()
